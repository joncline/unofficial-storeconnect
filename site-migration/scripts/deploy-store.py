#!/usr/bin/env python3
"""Deploy a StoreConnect store from local backup archive to a destination org.

Reads from orgs/<src_org>/stores/<slug>/ and orgs/<src_org>/themes/<slug>/
(created by backup-store.py) and pushes to the destination org/store.

Usage:
    # Preview what would happen (no writes)
    python3 scripts/deploy-store.py <src_org> <src_store_id> <dst_org> <dst_store_id> --dry-run

    # Execute (deploy onto an existing destination store)
    python3 scripts/deploy-store.py <src_org> <src_store_id> <dst_org> <dst_store_id>

    # Create a brand-new destination store and deploy onto it
    python3 scripts/deploy-store.py <src_org> <src_store_id> <dst_org> --create-store

Flags:
    --create-store   create a new store in <dst_org> instead of targeting an
                     existing <dst_store_id>.
    --name="..."     override the new store's Name (default: the staged record's
                     Name). Use for a same-org copy so it's distinguishable.
    --no-default     do NOT set the deployed store as the org's Primary store
                     (default is to set it). Use for same-org store->store copies
                     so the existing primary keeps its domain routing.
    --dry-run        print actions without writing.

Example (same-org copy alongside the existing store):
    python3 scripts/deploy-store.py <org> <src_store_id> <org> --create-store \
        --name="My Store (Copy)" --no-default --dry-run
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (
    sf_query, slugify,
    create_theme, push_template, push_variable, push_locale, push_asset,
    push_store_variable, update_record, create_record,
)

REPO_ROOT = Path(__file__).parent.parent

SKIP_FIELDS = {
    # NOTE: 'Name' is intentionally NOT skipped — the destination store is
    # (re)named from the staged record (e.g. the default "Sample Store" becomes
    # "STO"). Identity fields below stay skipped.
    'Id', 'OwnerId', 'IsDeleted',
    'CreatedDate', 'CreatedById', 'LastModifiedDate', 'LastModifiedById',
    'SystemModstamp', 'LastViewedDate', 'LastReferencedDate', 'attributes',
    's_c__Code__c', 's_c__sC_Id__c', 's_c__Cache_Version__c',
    # s_c__Default__c is skipped here and handled explicitly: by default the deployed
    # store is set as the org's default (StoreConnect unsets the prior default).
    # Pass --no-default to leave the org's primary store alone (e.g. same-org
    # store->store copy, where you don't want to hijack the existing default).
    's_c__Default__c',
    's_c__Domain__c', 's_c__Link__c', 's_c__Preview_Store__c',
    's_c__Unique_Domain_Path__c', 'Content_Key_External_Id__c',
    's_c__Meta_Title__c',  # org-specific storefront <title> (e.g. "Acme/…") — set per org, don't copy
    's_c__Theme_Id__c',  # set separately to the new cloned theme
    's_c__Logo_Id__c', 's_c__Email_Logo_Id__c',  # cross-org Media IDs
    's_c__Footer_Menu_Id__c', 's_c__Header_Menu_Id__c',  # cross-org Menu IDs
    's_c__Head_Content_Block_Id__c',  # cross-org Content Block ID
    's_c__Home_Page_Id__c', 's_c__Terms_Page_Id__c',  # cross-org Page IDs
    's_c__Pricebook_Id__c',  # cross-org Pricebook ID
}

# Store variables NOT copied cross-org — org-specific credentials/keys the target
# org must supply itself. Keeps the migration credential-free.
SKIP_STORE_VARIABLES = {
    'GOOGLE_MAPS_API_KEY',
}


def load_store_archive(src_org, src_store_id):
    """Locate and load the source store backup. Returns (store_rec, store_vars, theme_slug)."""
    stores_dir = REPO_ROOT / 'orgs' / src_org / 'stores'
    if not stores_dir.exists():
        raise RuntimeError(
            f"No store backups found at orgs/{src_org}/stores/. "
            f"Run: python3 scripts/backup-store.py {src_org} {src_store_id}"
        )

    # Find the store directory whose record.json matches the source store ID
    store_dir = None
    for d in stores_dir.iterdir():
        rec_path = d / 'record.json'
        if rec_path.exists():
            rec = json.loads(rec_path.read_text())
            if rec.get('Id') == src_store_id:
                store_dir = d
                break

    if store_dir is None:
        raise RuntimeError(
            f"Store {src_store_id} not found in orgs/{src_org}/stores/. "
            f"Run: python3 scripts/backup-store.py {src_org} {src_store_id}"
        )

    store_rec = json.loads((store_dir / 'record.json').read_text())
    store_vars_path = store_dir / 'store-variables.json'
    store_vars = json.loads(store_vars_path.read_text()) if store_vars_path.exists() else []

    theme_id = store_rec.get('s_c__Theme_Id__c')
    if not theme_id:
        raise RuntimeError("Source store has no theme linked")

    # Find theme directory
    themes_dir = REPO_ROOT / 'orgs' / src_org / 'themes'
    theme_dir = None
    for d in themes_dir.iterdir():
        md = d / 'theme.md'
        if md.exists() and f'`{theme_id}`' in md.read_text():
            theme_dir = d
            break

    if theme_dir is None:
        raise RuntimeError(
            f"Theme {theme_id} not found in orgs/{src_org}/themes/. "
            f"Run: python3 scripts/backup-store.py {src_org} {src_store_id}"
        )

    return store_rec, store_vars, theme_dir


def theme_title(theme_dir):
    """Return the theme name from theme.md's '# Theme: NAME' header, or None."""
    md = theme_dir / 'theme.md'
    if md.exists():
        first = md.read_text().splitlines()[0] if md.read_text().strip() else ''
        if first.startswith('# Theme:'):
            return first.split(':', 1)[1].strip()
    return None


def read_templates(theme_dir):
    """Yield (key, content) for every template in the archive."""
    templates_dir = theme_dir / 'templates'
    if not templates_dir.exists():
        return
    for path in sorted(templates_dir.rglob('*.liquid')):
        rel = path.relative_to(templates_dir)
        key = str(rel.with_suffix(''))  # strip .liquid extension
        content = path.read_text()
        yield key, content


def read_variables(theme_dir):
    """Yield (key, value) for every theme variable in the archive."""
    csv_path = theme_dir / 'variables.csv'
    if not csv_path.exists():
        return
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):
            yield row['key'], row.get('value', '')


def read_locales(theme_dir):
    """Yield (name, code, active, default) from locales.md."""
    md_path = theme_dir / 'locales.md'
    if not md_path.exists():
        return
    for line in md_path.read_text().splitlines():
        if not line.startswith('|') or line.startswith('| Name') or line.startswith('|---'):
            continue
        parts = [p.strip() for p in line.strip('|').split('|')]
        if len(parts) < 4:
            continue
        name, code, active_str, default_str = parts[0], parts[1], parts[2], parts[3]
        yield name, code, active_str.lower() == 'true', default_str.lower() == 'true'


def read_assets(theme_dir):
    """Yield (key, url) for every asset with a URL in assets.md."""
    md_path = theme_dir / 'assets.md'
    if not md_path.exists():
        return
    for line in md_path.read_text().splitlines():
        if not line.startswith('|') or line.startswith('| Key') or line.startswith('|---'):
            continue
        parts = [p.strip() for p in line.strip('|').split('|')]
        if len(parts) < 2:
            continue
        key, url = parts[0], parts[1]
        if url:
            yield key, url


def main():
    dry_run = '--dry-run' in sys.argv
    create_store = '--create-store' in sys.argv
    no_default = '--no-default' in sys.argv
    # Optional --name="My Store" overrides the deployed store's Name (otherwise it
    # inherits the staged record's Name). Useful when adding a store alongside one
    # of the same name (e.g. a same-org copy) so the two are distinguishable.
    name_override = next((a.split('=', 1)[1] for a in sys.argv[1:]
                          if a.startswith('--name=')), None)
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    # --create-store makes a brand-new store record (named from the staged archive)
    # and deploys onto it. By default the deployed store is set as the org's default
    # (Primary) store. Pass --no-default to leave the org's existing primary alone —
    # the right choice for same-org store->store copies.
    if create_store:
        if len(args) != 3:
            print("Usage: python3 scripts/deploy-store.py <src_org> <src_store_id> "
                  "<dst_org> --create-store [--dry-run]")
            sys.exit(1)
        src_org, src_store_id, dst_org = args
        dst_store_id = None
    else:
        if len(args) != 4:
            print("Usage: python3 scripts/deploy-store.py <src_org> <src_store_id> "
                  "<dst_org> <dst_store_id> [--dry-run]   (or --create-store instead "
                  "of <dst_store_id>)")
            sys.exit(1)
        src_org, src_store_id, dst_org, dst_store_id = args

    if dry_run:
        print("── DRY RUN — no changes will be made ──────────────────────────\n")

    def act(label, fn=None):
        if dry_run:
            print(f"  [DRY RUN] {label}")
        else:
            print(f"  {label}")
            if fn:
                return fn()

    # ── Load archive ─────────────────────────────────────────────────────────
    print("Loading source store archive...")
    store_rec, store_vars, theme_dir = load_store_archive(src_org, src_store_id)
    store_name = name_override or store_rec.get('Name', src_store_id)

    # Resolve (or create) the destination store.
    if create_store:
        primary_note = "left as-is" if no_default else "set as Primary"
        if dry_run:
            dst_store_id = 'DRY_NEW_STORE'
            dst_name = store_name
            print(f"  [DRY RUN] create store '{store_name}' in {dst_org} "
                  f"(org primary {primary_note})")
        else:
            dst_store_id = create_record(dst_org, 's_c__Store__c', {'Name': store_name})
            dst_name = store_name
            print(f"  + created store '{store_name}'  ({dst_store_id})")
    else:
        dst_stores = sf_query(dst_org, f"SELECT Id, Name FROM s_c__Store__c WHERE Id = '{dst_store_id}'")
        if not dst_stores:
            raise RuntimeError(f"Destination store {dst_store_id} not found in {dst_org}")
        dst_name = dst_stores[0]['Name']

    templates = list(read_templates(theme_dir))
    variables = list(read_variables(theme_dir))
    locales = list(read_locales(theme_dir))
    assets = list(read_assets(theme_dir))

    print(f"  Source:    {store_name} ({src_org})")
    print(f"  Dest:      {dst_name} ({dst_org})")
    print(f"  Theme dir: {theme_dir.relative_to(REPO_ROOT)}")
    print(f"  Templates: {len(templates)}  Variables: {len(variables)}  "
          f"Locales: {len(locales)}  Assets: {len(assets)}  "
          f"Store vars: {len(store_vars)}\n")

    # ── Step 1: Create theme (idempotent) ────────────────────────────────────
    # Prefer the staged theme.md title (e.g. "STO v1") so the deployed theme
    # carries the intended brand name; fall back to the old "{store} ({dst})".
    new_theme_name = theme_title(theme_dir) or f"{store_name} ({dst_name})"
    print(f"Step 1: Create theme '{new_theme_name}'")
    existing_themes = sf_query(
        dst_org,
        f"SELECT Id FROM s_c__Theme__c WHERE Name = '{new_theme_name}' "
        f"ORDER BY CreatedDate DESC LIMIT 1",
    )
    if existing_themes and not dry_run:
        new_theme_id = existing_themes[0]['Id']
        print(f"  (exists) {new_theme_name}  →  {new_theme_id}")
    else:
        new_theme_id = act(f"create_theme({dst_org}, '{new_theme_name}')",
                           lambda: create_theme(dst_org, new_theme_name))

    # ── Step 2: Push templates ───────────────────────────────────────────────
    print(f"\nStep 2: Push {len(templates)} templates")
    for key, content in templates:
        act(f"push_template {key}",
            lambda k=key, c=content: push_template(dst_org, new_theme_id, k, c))

    # ── Step 3: Push theme variables ─────────────────────────────────────────
    print(f"\nStep 3: Push {len(variables)} theme variables")
    for key, value in variables:
        act(f"push_variable {key}",
            lambda k=key, v=value: push_variable(dst_org, new_theme_id, k, v))

    # ── Step 4: Push locales ─────────────────────────────────────────────────
    print(f"\nStep 4: Push {len(locales)} locales")
    for name, code, active, default in locales:
        act(f"push_locale {code} ({name})",
            lambda n=name, c=code, a=active, d=default: push_locale(dst_org, new_theme_id, c, n, a, d))

    # ── Step 5: Push assets ──────────────────────────────────────────────────
    print(f"\nStep 5: Push {len(assets)} assets")
    for key, url in assets:
        act(f"push_asset {key}",
            lambda k=key, u=url: push_asset(dst_org, new_theme_id, k, u))

    # ── Step 6: Push store variables ─────────────────────────────────────────
    pushable_vars = [v for v in store_vars if v['s_c__Key__c'] not in SKIP_STORE_VARIABLES]
    skipped_vars = [v['s_c__Key__c'] for v in store_vars if v['s_c__Key__c'] in SKIP_STORE_VARIABLES]
    skip_note = f"  (skipping {', '.join(skipped_vars)})" if skipped_vars else ""
    print(f"\nStep 6: Push {len(pushable_vars)} store variables{skip_note}")
    for v in pushable_vars:
        act(
            f"push_store_variable {v['s_c__Key__c']} = {str(v.get('s_c__Value__c', ''))[:60]}",
            lambda sv=v: push_store_variable(
                dst_org, dst_store_id,
                sv['s_c__Key__c'],
                sv.get('s_c__Value__c') or '',
                sv.get('s_c__Available_In_Liquid__c', False),
            ),
        )

    # ── Step 7: Update dest store fields ─────────────────────────────────────
    update_data = {k: v for k, v in store_rec.items() if k not in SKIP_FIELDS and v is not None}
    if name_override:
        update_data['Name'] = name_override
    if not dry_run:
        update_data['s_c__Theme_Id__c'] = new_theme_id
    print(f"\nStep 7: Update dest store ({len(update_data)} fields + theme ID)")
    act(
        f"update_record s_c__Store__c {dst_store_id} ({len(update_data)} fields)",
        lambda: update_record(dst_org, 's_c__Store__c', dst_store_id, update_data),
    )

    # ── Step 8: Set as the org's default/Primary store (unless --no-default) ──
    if no_default:
        print("\nStep 8: leaving the org's primary store unchanged (--no-default)")
    else:
        print("\nStep 8: Set this store as the org's default (Primary)")
        act(
            f"update_record s_c__Store__c {dst_store_id} (s_c__Default__c=true)",
            lambda: update_record(dst_org, 's_c__Store__c', dst_store_id,
                                  {'s_c__Default__c': True}),
        )

    if dry_run:
        print("\n── DRY RUN complete — no changes were made ─────────────────────")
    else:
        print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Deploy complete.
  New theme:  {new_theme_name}
  Theme ID:   {new_theme_id}
  Dest store: {dst_name} ({dst_store_id})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")


if __name__ == '__main__':
    main()
