#!/usr/bin/env python3
"""Migrate product media into a target org and link it to products.

For every product-media junction captured in the local backup
  orgs/<dst_org>/stores/<store>/categories/<cat>/products/<product>/product-media.json
this:
  1. ensures the s_c__Media__c record exists in the target (idempotent by
     Identifier), importing the image from the SOURCE media's public CDN URL
     (s_c__Url__c) via s_c__Import_Url__c — StoreConnect then pulls it into the
     target org's own CDN.
  2. links it to the migrated product via s_c__Product_Media__c, mapping the
     product by Slug.

Note on the ContentVersion path: when a media item has NO public URL (a raw
binary), the pattern is to upload it as a Salesforce ContentVersion,
publish it, and use that public link as the Import_Url. Every media item in this
catalog already has a public s_c__Url__c, so we import directly from it; the
ContentVersion step is unnecessary here.

Reads src/dst orgs from orgs/<dst_org>/category-map.json. Run AFTER the catalog
migration (products must exist).

Usage:
    python3 scripts/migrate-media.py <dst_org> [--dry-run]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, create_record, slugify

REPO_ROOT = Path(__file__).parent.parent


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    dry_run = '--dry-run' in sys.argv
    rest = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(rest) != 1:
        print('Usage: python3 scripts/migrate-media.py <dst_org> [--dry-run]')
        sys.exit(1)
    dst_org = rest[0]

    cmap = json.loads((REPO_ROOT / 'orgs' / dst_org / 'category-map.json').read_text())
    src_org = cmap['src_org']
    mode = 'DRY RUN' if dry_run else 'LIVE'
    print(f'[{mode}] Migrate media: {src_org} -> {dst_org}')

    stores_root = REPO_ROOT / 'orgs' / dst_org / 'stores'
    store_dir = next(d for d in stores_root.iterdir() if (d / 'categories').exists())

    # ── Gather junctions from the backup: (product_slug, src_media_id, position)
    junctions = []
    src_media_ids = set()
    for cat in cmap['categories']:
        prod_root = store_dir / 'categories' / slugify(cat['name']) / 'products'
        if not prod_root.exists():
            continue
        for pdir in sorted(prod_root.iterdir()):
            pm = pdir / 'product-media.json'
            rec = pdir / 'record.json'
            if not pm.exists() or not rec.exists():
                continue
            slug = json.loads(rec.read_text()).get('s_c__Slug__c')
            for row in json.loads(pm.read_text()):
                mid = row.get('s_c__Media_Id__c')
                if not mid:
                    continue
                src_media_ids.add(mid)
                junctions.append({'slug': slug, 'media': mid,
                                  'position': row.get('s_c__Position__c')})
    print(f'  {len(junctions)} junctions, {len(src_media_ids)} distinct media')

    # ── Source media details (Name, File_Type, Url, Identifier) ──────────────
    src_media = {}
    for chunk in chunked(sorted(src_media_ids), 150):
        ids = "','".join(chunk)
        for m in sf_query(src_org,
                f"SELECT Id, Name, s_c__File_Type__c, s_c__Url__c, s_c__Identifier__c "
                f"FROM s_c__Media__c WHERE Id IN ('{ids}')"):
            src_media[m['Id']] = m

    # ── Ensure media in target (idempotent by Identifier) ────────────────────
    dst_media_by_ident = {}
    if not dry_run:
        for m in sf_query(dst_org, "SELECT Id, s_c__Identifier__c FROM s_c__Media__c"):
            if m.get('s_c__Identifier__c'):
                dst_media_by_ident[m['s_c__Identifier__c']] = m['Id']

    media_map = {}            # src media id -> dst media id
    created_media = 0
    for mid in sorted(src_media_ids):
        m = src_media.get(mid)
        if not m:
            print(f'  WARN: source media {mid} not found, skipping')
            continue
        ident = m.get('s_c__Identifier__c') or f'media-{mid[-8:]}'
        if ident in dst_media_by_ident:
            media_map[mid] = dst_media_by_ident[ident]
            continue
        data = {'Name': m['Name'], 's_c__File_Type__c': m.get('s_c__File_Type__c') or 'image',
                's_c__Identifier__c': ident, 's_c__Import_Url__c': m.get('s_c__Url__c')}
        if dry_run:
            media_map[mid] = f'DRY_{ident}'
            print(f"  + media {m['Name']}  import={str(m.get('s_c__Url__c'))[:50]}")
        else:
            new_id = create_record(dst_org, 's_c__Media__c', data)
            media_map[mid] = new_id
            dst_media_by_ident[ident] = new_id
        created_media += 1

    # ── Target products by Slug ──────────────────────────────────────────────
    products_by_slug = {}
    if not dry_run:
        for p in sf_query(dst_org, "SELECT Id, s_c__Slug__c FROM Product2 WHERE s_c__Slug__c != null"):
            products_by_slug[p['s_c__Slug__c']] = p['Id']

    # ── Create product-media junctions (idempotent) ──────────────────────────
    created_links = skipped_links = 0
    for j in junctions:
        dst_media_id = media_map.get(j['media'])
        dst_prod_id = products_by_slug.get(j['slug']) if not dry_run else f"DRY_{j['slug']}"
        if not dst_media_id or not dst_prod_id:
            print(f"  WARN: cannot link slug={j['slug']} media={j['media']} (missing target)")
            continue
        if not dry_run:
            exists = sf_query(dst_org,
                f"SELECT Id FROM s_c__Product_Media__c WHERE s_c__Media_Id__c='{dst_media_id}' "
                f"AND s_c__Product_Id__c='{dst_prod_id}' LIMIT 1")
            if exists:
                skipped_links += 1
                continue
        link = {'s_c__Media_Id__c': dst_media_id, 's_c__Product_Id__c': dst_prod_id,
                's_c__Position__c': j['position'] if j['position'] is not None else 1}
        if dry_run:
            print(f"  + link {j['slug']} <- media {j['media']}")
        else:
            create_record(dst_org, 's_c__Product_Media__c', link)
        created_links += 1

    print(f'\nDone. media: +{created_media}  product-media links: +{created_links} '
          f'({skipped_links} existed)')


if __name__ == '__main__':
    main()
