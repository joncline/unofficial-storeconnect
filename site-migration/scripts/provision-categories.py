#!/usr/bin/env python3
"""Provision a store's product categories (taxonomy tree) into a target org.

Copies every product category under the SOURCE store's taxonomy into the
DESTINATION store's taxonomy, matched by Name, AND reproduces the category
hierarchy. Idempotent — re-running skips categories/edges already present.

StoreConnect category model:
  s_c__Taxonomy__c                   one per store (s_c__Store_Id__c, required)
  s_c__Product_Category__c           belongs to a taxonomy (s_c__Taxonomy_Id__c,
                                     required). There is NO parent field on the
                                     category itself; s_c__Path__c is a flat
                                     per-level slug (e.g. "women", "big-kids").
  s_c__Product_Category_Hierarchy__c the tree: one row per parent->child edge
                                     (s_c__Parent_Id__c, s_c__Child_Id__c,
                                     s_c__Position__c, s_c__Primary_Parent__c).
                                     Edges are direct (depth-1); root categories
                                     have no row. This is what builds the nested
                                     category navigation.

Media references (s_c__Media_Id__c, s_c__Social_Image_Id__c) are org-specific and
are NOT copied here — they're backfilled during the catalog/media migration.
s_c__Parent_Count__c is left for the platform to maintain from the edges.

Emits a category id-map (source id -> destination id) to
  orgs/<dst_org>/category-map.json
which the catalog migration step consumes to place products.

Part of the site migration. Run AFTER deploy-store.py (the destination
store + its taxonomy must exist) and BEFORE the catalog migration.

Usage:
    python3 scripts/provision-categories.py \
        <src_org> <src_store_id> <dst_org> <dst_store_id> [--dry-run]

Example (STO reference store -> a target):
    python3 scripts/provision-categories.py \
        <source-org> a2qa500000FWJF0AAP <dst_org> <dst_store_id> --dry-run
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, create_record

REPO_ROOT = Path(__file__).parent.parent

# Category fields copied from source (only non-null values are sent). Excludes
# Id, s_c__sC_Id__c (per-record internal), s_c__Taxonomy_Id__c (set to the dest
# taxonomy), s_c__Product_Id__c, and the media references (backfilled later).
CAT_FIELDS = [
    'Name', 's_c__Display_Name__c', 's_c__Title__c', 's_c__Subtitle__c',
    's_c__Path__c', 's_c__Position__c',
    's_c__Introduction_Markdown__c', 's_c__Information_Markdown__c',
    's_c__Meta_Title__c', 's_c__Meta_Description__c',
]


def provision_hierarchy(src_org, src_tax_id, dst_org, id_map, dry_run):
    """Reproduce the category tree in the destination taxonomy.

    Reads every parent->child edge from the source taxonomy's
    s_c__Product_Category_Hierarchy__c, remaps both endpoints via id_map, and
    creates the edge in the destination (idempotent by (parent,child) pair).
    Returns (created, skipped, unmapped).
    """
    edges = sf_query(
        src_org,
        f"SELECT s_c__Parent_Id__c, s_c__Child_Id__c, s_c__Position__c, "
        f"s_c__Primary_Parent__c FROM s_c__Product_Category_Hierarchy__c "
        f"WHERE s_c__Child_Id__r.s_c__Taxonomy_Id__c = '{src_tax_id}'",
    )
    print(f'\n  Hierarchy edges (source): {len(edges)}')

    # Existing destination edges (idempotency), keyed by (parent_dst, child_dst).
    existing_edges = set()
    dst_child_ids = [v for v in id_map.values() if v and not str(v).startswith('DRY_')]
    if not dry_run and dst_child_ids:
        ids = "','".join(dst_child_ids)
        for e in sf_query(
            dst_org,
            f"SELECT s_c__Parent_Id__c, s_c__Child_Id__c "
            f"FROM s_c__Product_Category_Hierarchy__c WHERE s_c__Child_Id__c IN ('{ids}')",
        ):
            existing_edges.add((e['s_c__Parent_Id__c'], e['s_c__Child_Id__c']))

    created = skipped = unmapped = 0
    for e in edges:
        p_dst = id_map.get(e['s_c__Parent_Id__c'])
        c_dst = id_map.get(e['s_c__Child_Id__c'])
        if not p_dst or not c_dst:
            print(f"    WARN: edge unmapped parent={e['s_c__Parent_Id__c']} "
                  f"child={e['s_c__Child_Id__c']}")
            unmapped += 1
            continue
        if (p_dst, c_dst) in existing_edges:
            skipped += 1
            continue
        data = {'s_c__Parent_Id__c': p_dst, 's_c__Child_Id__c': c_dst}
        if e.get('s_c__Position__c') is not None:
            data['s_c__Position__c'] = e['s_c__Position__c']
        if e.get('s_c__Primary_Parent__c') is not None:
            data['s_c__Primary_Parent__c'] = e['s_c__Primary_Parent__c']
        if dry_run:
            print(f"    + edge pos={e.get('s_c__Position__c')}  {p_dst} -> {c_dst}")
        else:
            create_record(dst_org, 's_c__Product_Category_Hierarchy__c', data)
        created += 1
    print(f'  Hierarchy: +{created} edges ({skipped} existed, {unmapped} unmapped)')
    return created, skipped, unmapped


def taxonomy_for_store(org, store_id):
    """Return the taxonomy Id for a store, or None."""
    rows = sf_query(
        org,
        f"SELECT Id, Name FROM s_c__Taxonomy__c WHERE s_c__Store_Id__c = '{store_id}'",
    )
    return rows[0] if rows else None


def main():
    dry_run = '--dry-run' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 4:
        print('Usage: python3 scripts/provision-categories.py '
              '<src_org> <src_store_id> <dst_org> <dst_store_id> [--dry-run]')
        sys.exit(1)
    src_org, src_store_id, dst_org, dst_store_id = args

    mode = 'DRY RUN' if dry_run else 'LIVE'
    print(f'[{mode}] Provision categories: {src_org}/{src_store_id} -> {dst_org}/{dst_store_id}')

    # ── Source taxonomy ──────────────────────────────────────────────────────
    src_tax = taxonomy_for_store(src_org, src_store_id)
    if not src_tax:
        print(f'  ERROR: source store {src_store_id} has no taxonomy.')
        sys.exit(1)
    print(f"  Source taxonomy: {src_tax['Name']} ({src_tax['Id']})")

    # ── Destination taxonomy (find or create) ────────────────────────────────
    dst_tax = taxonomy_for_store(dst_org, dst_store_id)
    if dst_tax:
        dst_tax_id = dst_tax['Id']
        print(f"  Dest taxonomy:   {dst_tax['Name']} ({dst_tax_id})  (exists)")
    else:
        dst_store = sf_query(dst_org, f"SELECT Name FROM s_c__Store__c WHERE Id = '{dst_store_id}'")
        tax_name = f"{dst_store[0]['Name']} Taxonomy" if dst_store else 'Store Taxonomy'
        if dry_run:
            dst_tax_id = 'DRY_TAXONOMY'
            print(f"  Dest taxonomy:   would create '{tax_name}' for store {dst_store_id}")
        else:
            dst_tax_id = create_record(
                dst_org, 's_c__Taxonomy__c',
                {'Name': tax_name, 's_c__Store_Id__c': dst_store_id},
            )
            print(f"  Dest taxonomy:   created '{tax_name}' ({dst_tax_id})")

    # ── Source categories under the source taxonomy ──────────────────────────
    field_list = ', '.join(['Id'] + CAT_FIELDS)
    src_cats = sf_query(
        src_org,
        f"SELECT {field_list} FROM s_c__Product_Category__c "
        f"WHERE s_c__Taxonomy_Id__c = '{src_tax['Id']}' ORDER BY Name",
    )
    print(f'  Source categories: {len(src_cats)}')

    # ── Existing dest categories by Name (idempotency) ───────────────────────
    existing = {}
    if not dry_run or dst_tax:
        for c in sf_query(
            dst_org,
            f"SELECT Id, Name FROM s_c__Product_Category__c "
            f"WHERE s_c__Taxonomy_Id__c = '{dst_tax_id}'",
        ):
            existing[c['Name']] = c['Id']

    # ── Ensure each category, building the src->dst id map ────────────────────
    id_map = {}
    created = skipped = 0
    for cat in src_cats:
        name = cat['Name']
        if name in existing:
            print(f'  (exists) {name}')
            id_map[cat['Id']] = existing[name]
            skipped += 1
            continue

        data = {k: cat[k] for k in CAT_FIELDS if cat.get(k) is not None}
        data['s_c__Taxonomy_Id__c'] = dst_tax_id

        if dry_run:
            print(f'  + would create {name}  (path={cat.get("s_c__Path__c")})')
            id_map[cat['Id']] = f'DRY_{name}'
            created += 1
            continue

        new_id = create_record(dst_org, 's_c__Product_Category__c', data)
        print(f'  + created {name}  ({new_id})')
        id_map[cat['Id']] = new_id
        created += 1

    # ── Reproduce the category hierarchy (parent->child edges) ───────────────
    provision_hierarchy(src_org, src_tax['Id'], dst_org, id_map, dry_run)

    # ── Emit the category id-map for the catalog step ────────────────────────
    payload = {
        'src_org': src_org, 'src_store_id': src_store_id, 'src_taxonomy_id': src_tax['Id'],
        'dst_org': dst_org, 'dst_store_id': dst_store_id, 'dst_taxonomy_id': dst_tax_id,
        'categories': [
            {'name': c['Name'], 'path': c.get('s_c__Path__c'),
             'src_id': c['Id'], 'dst_id': id_map.get(c['Id'])}
            for c in src_cats
        ],
    }
    map_path = REPO_ROOT / 'orgs' / dst_org / 'category-map.json'
    if dry_run:
        print(f'\n  (dry run) would write category map -> {map_path.relative_to(REPO_ROOT)}')
    else:
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(json.dumps(payload, indent=2))
        print(f'\n  category map -> {map_path.relative_to(REPO_ROOT)}')

    print(f'Done. {created} created, {skipped} already present.')


if __name__ == '__main__':
    main()
