#!/usr/bin/env python3
"""Migrate a store's product catalog into a target org (faithful copy).

Reads the product backup under
  orgs/<dst_org>/stores/<store>/categories/<cat>/products/<product>/
    record.json            full Product2 fields
    pricebook-entries.json all PBEs (real prices, all pricebooks, bundle attrs)
and the category id-map written by provision-categories.py
  orgs/<dst_org>/category-map.json

For each product it:
  1. creates the Product2 (faithful field copy — every CREATEABLE non-null field,
     minus identity/internal fields). Variants need no special handling: the
     master/variant relationship is convention-based (Family + ProductCode +
     s_c__Variant_Title__c), not a record-Id FK, so copying the fields preserves
     it. There are no bundles in this catalog. A FUTURE s_c__Available_On__c is
     clamped to now so products aren't hidden from the storefront (past values
     are kept as-is).
  2. creates PricebookEntries across all 6 pricebooks with the real UnitPrice +
     bundle attrs, mapping source->target pricebook BY NAME. The Standard entry
     is created first (Salesforce requires it before tier entries).
  3. links the product to its destination category.

Media (product-media.json) is handled by a separate step.

Idempotent — matches existing products by ProductCode (then Slug), PBEs by
(pricebook, product), category links by (product, category).

Usage:
    python3 scripts/migrate-catalog.py <dst_org> [--category NAME] [--dry-run]

Example (pilot one category, then all):
    python3 scripts/migrate-catalog.py <target-org> --category Donations --dry-run
    python3 scripts/migrate-catalog.py <target-org>
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, create_record, slugify, _sf_rest

REPO_ROOT = Path(__file__).parent.parent
API = '/services/data/v62.0'


def backdate_available_on(data):
    """Clamp a FUTURE s_c__Available_On__c to now so the product isn't hidden from
    the storefront. Past/absent values are left untouched (faithful copy).
    Mutates `data` in place; returns the new value if it changed, else None.

    The source store can carry a future availability date (e.g. set during a
    staging/demo build); copied verbatim it would make every product invisible
    until that date. We only override when the date is in the future.
    """
    v = data.get('s_c__Available_On__c')
    if not v:
        return None
    try:
        # SF datetime like '2026-11-11T00:00:00.000+0000' (offset assumed +0000)
        dt = datetime.strptime(v[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    now = datetime.now(timezone.utc)
    if dt > now:
        new = now.strftime('%Y-%m-%dT00:00:00.000+0000')
        data['s_c__Available_On__c'] = new
        return new
    return None

# Createable fields we still must NOT copy (identity / per-record internal /
# cross-org references). Non-createable + formula fields are excluded
# automatically via the describe.
PRODUCT_SKIP = {
    's_c__sC_Id__c',                 # per-record StoreConnect internal id
    'Content_Key_External_Id__c',    # unique external id
    's_c__Placeholder_For_Id__c',    # cross-org Product2 reference
}

# PBE fields copied verbatim (when present) on top of the price/pricebook/product.
PBE_ATTRS = [
    's_c__Hide_Price__c', 's_c__Hide_Price_Text__c', 's_c__Bundle_Price_Strategy__c',
    's_c__Disable_Quantity_Selection__c', 's_c__Bundle_Only__c',
]


def createable_fields(org, sobject):
    """Createable field names, EXCLUDING reference (lookup) fields. Lookups hold
    org-specific record ids that don't resolve cross-org and trigger
    INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY on insert — e.g.
    s_c__Brand_Id__c (Account), s_c__Social_Image_Id__c (Media),
    s_c__Product_Trait_Template_Id__c. Any of these that matter are backfilled
    by a later step (media) or left for manual brand assignment."""
    desc = _sf_rest(org, 'GET', f'{API}/sobjects/{sobject}/describe')
    return {f['name'] for f in desc['fields']
            if f.get('createable') and f['type'] != 'reference'}


def find_existing_product(org, code, slug):
    for field, val in (('ProductCode', code), ('s_c__Slug__c', slug)):
        if not val:
            continue
        rows = sf_query(org, f"SELECT Id FROM Product2 WHERE {field} = '{val}' LIMIT 1")
        if rows:
            return rows[0]['Id']
    return None


def main():
    dry_run = '--dry-run' in sys.argv
    rest = [a for a in sys.argv[1:] if not a.startswith('--')]
    cat_filter = None
    if '--category' in sys.argv:
        i = sys.argv.index('--category')
        cat_filter = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        rest = [a for a in rest if a != cat_filter]
    if len(rest) != 1:
        print('Usage: python3 scripts/migrate-catalog.py <dst_org> [--category NAME] [--dry-run]')
        sys.exit(1)
    dst_org = rest[0]

    mode = 'DRY RUN' if dry_run else 'LIVE'
    print(f'[{mode}] Migrate catalog -> {dst_org}' + (f'  (category: {cat_filter})' if cat_filter else ''))

    # ── Inputs ───────────────────────────────────────────────────────────────
    cmap = json.loads((REPO_ROOT / 'orgs' / dst_org / 'category-map.json').read_text())
    stores_root = REPO_ROOT / 'orgs' / dst_org / 'stores'
    store_dir = next(d for d in stores_root.iterdir() if (d / 'categories').exists())

    createable = createable_fields(dst_org, 'Product2')

    # dst pricebooks by name -> (id, is_standard)
    pbs = {p['Name']: (p['Id'], p['IsStandard'])
           for p in sf_query(dst_org, 'SELECT Id, Name, IsStandard FROM Pricebook2')}

    totals = {'products': 0, 'prod_exists': 0, 'pbes': 0, 'links': 0}

    for cat in cmap['categories']:
        if cat_filter and cat['name'] != cat_filter:
            continue
        dst_cat_id = cat['dst_id']
        cat_dir = store_dir / 'categories' / slugify(cat['name'])
        prod_root = cat_dir / 'products'
        if not prod_root.exists():
            print(f"  [{cat['name']}] no products dir, skipping")
            continue

        print(f"\n=== Category: {cat['name']}  ->  {dst_cat_id} ===")
        for pdir in sorted(prod_root.iterdir()):
            rec_path = pdir / 'record.json'
            if not rec_path.exists():
                continue
            rec = json.loads(rec_path.read_text())
            name = rec.get('Name', pdir.name)
            code, slug = rec.get('ProductCode'), rec.get('s_c__Slug__c')

            # ── Product (idempotent) ──────────────────────────────────────────
            existing = None if dry_run else find_existing_product(dst_org, code, slug)
            if existing:
                product_id = existing
                totals['prod_exists'] += 1
                print(f'  (exists) {name}')
            else:
                data = {k: v for k, v in rec.items()
                        if k in createable and k not in PRODUCT_SKIP and v is not None}
                backdated = backdate_available_on(data)
                note = f'  [Available_On -> {backdated}]' if backdated else ''
                if dry_run:
                    product_id = f'DRY_{slug or code or name}'
                    print(f'  + product {name}  ({len(data)} fields){note}')
                else:
                    product_id = create_record(dst_org, 'Product2', data)
                    print(f'  + product {name}  ({product_id}){note}')
                totals['products'] += 1

            # ── PBEs (standard first) ─────────────────────────────────────────
            entries = json.loads((pdir / 'pricebook-entries.json').read_text()) \
                if (pdir / 'pricebook-entries.json').exists() else []
            entries.sort(key=lambda e: 0 if (e.get('Pricebook2') or {}).get('Name') == 'Standard Price Book' else 1)
            for e in entries:
                pb_name = (e.get('Pricebook2') or {}).get('Name')
                target = pbs.get(pb_name)
                if not target:
                    print(f'    WARN: no target pricebook named {pb_name!r}, skipping entry')
                    continue
                pb_id, is_std = target
                if not dry_run and find_existing_pbe(dst_org, pb_id, product_id):
                    continue
                pbe = {'Pricebook2Id': pb_id, 'Product2Id': product_id,
                       'UnitPrice': e.get('UnitPrice') or 0,
                       'IsActive': e.get('IsActive', True)}
                if not is_std:
                    pbe['UseStandardPrice'] = False
                for a in PBE_ATTRS:
                    if e.get(a) is not None:
                        pbe[a] = e[a]
                if dry_run:
                    print(f'    + PBE {pb_name} ${pbe["UnitPrice"]}')
                else:
                    create_record(dst_org, 'PricebookEntry', pbe)
                totals['pbes'] += 1

            # ── Category link (idempotent) ────────────────────────────────────
            if not dry_run and find_existing_link(dst_org, product_id, dst_cat_id):
                pass
            else:
                link = {'s_c__Product_Id__c': product_id, 's_c__Category_Id__c': dst_cat_id,
                        's_c__Active__c': True, 's_c__Primary__c': True}
                if dry_run:
                    print(f'    + category link')
                else:
                    create_record(dst_org, 's_c__Products_Product_Categories__c', link)
                totals['links'] += 1

    print(f'\nDone. products: +{totals["products"]} ({totals["prod_exists"]} existed)  '
          f'PBEs: +{totals["pbes"]}  category links: +{totals["links"]}')


def find_existing_pbe(org, pb_id, product_id):
    rows = sf_query(org,
        f"SELECT Id FROM PricebookEntry WHERE Pricebook2Id = '{pb_id}' "
        f"AND Product2Id = '{product_id}' LIMIT 1")
    return rows[0]['Id'] if rows else None


def find_existing_link(org, product_id, cat_id):
    rows = sf_query(org,
        f"SELECT Id FROM s_c__Products_Product_Categories__c "
        f"WHERE s_c__Product_Id__c = '{product_id}' AND s_c__Category_Id__c = '{cat_id}' LIMIT 1")
    return rows[0]['Id'] if rows else None


if __name__ == '__main__':
    main()
