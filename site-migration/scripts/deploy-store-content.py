#!/usr/bin/env python3
"""Deploy a store's content (content-blocks, articles, pages, menus + items)
into a target org and repoint the store's references.

Reads the store backup under orgs/<dst_org>/stores/<store>/ and the category
id-map (orgs/<dst_org>/category-map.json), then, in dependency order:
  1. content-blocks   (idempotent by Identifier; imports each block's own media
                       from the source CDN URL + remaps the media lookups) -> cb_map
  2. articles         (idempotent by Slug; sets Store_Id)    -> article_map
  3. pages            (idempotent by Slug; sets Store_Id)    -> page_map
  4. menus            (idempotent by Identifier; Store_Id)   -> menu_map
  5. menu items       (remap Menu/Category/Article/Page/Product/Parent refs;
                       two-pass so Parent_Id resolves)
  5b. content-block <-> page junctions (s_c__Content_Blocks_Pages__c from
                       content-block-pages.json; remap Page_Id + Content_Block_Id,
                       preserve Position/Usage_Type/Tag — this is what
                       render_content_blocks reads to build each page's design)
  6. repoint the destination store: Header/Footer menu, Head content block,
     Home/Terms page, Pricebook.

Reference fields are remapped via the maps above (+ category-map for categories,
Slug for products). Content-block media lookups (Image/Media/File/Video/Document)
ARE remapped (block media is imported here, idempotent by Identifier); product
image references are handled by migrate-media.py.

Run AFTER deploy-store.py + provision-categories.py + migrate-catalog.py.

Usage:
    python3 scripts/deploy-store-content.py <dst_org> [--dry-run]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, create_record, update_record, _sf_rest

REPO_ROOT = Path(__file__).parent.parent
API = '/services/data/v62.0'
SKIP = {'Id', 'OwnerId', 'IsDeleted', 'CreatedDate', 'CreatedById', 'LastModifiedDate',
        'LastModifiedById', 'SystemModstamp', 'LastViewedDate', 'LastReferencedDate',
        'attributes', 's_c__sC_Id__c', 'Content_Key_External_Id__c'}

# Content-block media lookups (all -> s_c__Media__c). These are imported + remapped
# (unlike other reference fields, which are skipped).
MEDIA_LOOKUPS = ['s_c__Image_Id__c', 's_c__Media_Id__c', 's_c__File_Id__c',
                 's_c__Video_Id__c', 's_c__Document_Id__c']


def nonref_createable(org, sobject):
    desc = _sf_rest(org, 'GET', f'{API}/sobjects/{sobject}/describe')
    return {f['name'] for f in desc['fields'] if f.get('createable') and f['type'] != 'reference'}


def picklist_values(org, sobject, field):
    """Valid values for a (restricted) picklist field in the target org."""
    desc = _sf_rest(org, 'GET', f'{API}/sobjects/{sobject}/describe')
    for f in desc['fields']:
        if f['name'] == field:
            return {v['value'] for v in f.get('picklistValues', [])}
    return set()


def featured_associations(src_org, dst_org, cb_map, cat_map, dry_run):
    """Recreate content-block 'featured products' / 'featured categories'
    associations that drive the sto-featured-products / sto-featured-categories
    blocks (they render content_block.products / content_block.product_categories).

    Source-driven (like block media): reads the junctions from the source org for
    the blocks we created (cb_map keys are source block ids), remaps the block via
    cb_map, the product by Slug, and the category via cat_map. Idempotent.

      s_c__Content_Blocks_Products__c          (Content_Block_Id, Product_Id, Position)
      s_c__Content_Blocks_Product_Categories__c(Cntnt_Blk_Id, Category_Id, Position)
    """
    src_block_ids = list(cb_map.keys())
    if not src_block_ids:
        return
    in_ids = "','".join(src_block_ids)
    dst_blocks = [v for v in cb_map.values() if not str(v).startswith('DRY_')]

    prod_by_slug = {}
    if not dry_run:
        for p in sf_query(dst_org, "SELECT Id, s_c__Slug__c FROM Product2 WHERE s_c__Slug__c != null"):
            prod_by_slug[p['s_c__Slug__c']] = p['Id']

    # ── Featured products ────────────────────────────────────────────────────
    fp = sf_query(src_org,
        f"SELECT s_c__Content_Block_Id__c, s_c__Product_Id__r.s_c__Slug__c, s_c__Position__c "
        f"FROM s_c__Content_Blocks_Products__c WHERE s_c__Content_Block_Id__c IN ('{in_ids}')")
    existing = set()
    if not dry_run and dst_blocks:
        bids = "','".join(dst_blocks)
        for r in sf_query(dst_org, f"SELECT s_c__Content_Block_Id__c, s_c__Product_Id__c "
                f"FROM s_c__Content_Blocks_Products__c WHERE s_c__Content_Block_Id__c IN ('{bids}')"):
            existing.add((r['s_c__Content_Block_Id__c'], r['s_c__Product_Id__c']))
    created = skipped = 0
    for r in fp:
        dblk = cb_map.get(r['s_c__Content_Block_Id__c'])
        slug = (r.get('s_c__Product_Id__r') or {}).get('s_c__Slug__c')
        dprod = f'DRY_{slug}' if dry_run else prod_by_slug.get(slug)
        if not dblk or not dprod:
            print(f"    WARN: featured-product unmapped (slug={slug})")
            continue
        if (dblk, dprod) in existing:
            skipped += 1
            continue
        data = {'s_c__Content_Block_Id__c': dblk, 's_c__Product_Id__c': dprod}
        if r.get('s_c__Position__c') is not None:
            data['s_c__Position__c'] = r['s_c__Position__c']
        if not dry_run:
            create_record(dst_org, 's_c__Content_Blocks_Products__c', data)
        created += 1
    print(f'  featured products: +{created} ({skipped} existed)')

    # ── Featured categories ──────────────────────────────────────────────────
    fc = sf_query(src_org,
        f"SELECT s_c__Cntnt_Blk_Id__c, s_c__Category_Id__c, s_c__Position__c "
        f"FROM s_c__Content_Blocks_Product_Categories__c WHERE s_c__Cntnt_Blk_Id__c IN ('{in_ids}')")
    existing = set()
    if not dry_run and dst_blocks:
        bids = "','".join(dst_blocks)
        for r in sf_query(dst_org, f"SELECT s_c__Cntnt_Blk_Id__c, s_c__Category_Id__c "
                f"FROM s_c__Content_Blocks_Product_Categories__c WHERE s_c__Cntnt_Blk_Id__c IN ('{bids}')"):
            existing.add((r['s_c__Cntnt_Blk_Id__c'], r['s_c__Category_Id__c']))
    created = skipped = 0
    for r in fc:
        dblk = cb_map.get(r['s_c__Cntnt_Blk_Id__c'])
        dcat = cat_map.get(r['s_c__Category_Id__c'])
        if not dblk or not dcat:
            print(f"    WARN: featured-category unmapped (cat={r['s_c__Category_Id__c']})")
            continue
        if (dblk, dcat) in existing:
            skipped += 1
            continue
        data = {'s_c__Cntnt_Blk_Id__c': dblk, 's_c__Category_Id__c': dcat}
        if r.get('s_c__Position__c') is not None:
            data['s_c__Position__c'] = r['s_c__Position__c']
        if not dry_run:
            create_record(dst_org, 's_c__Content_Blocks_Product_Categories__c', data)
        created += 1
    print(f'  featured categories: +{created} ({skipped} existed)')


def ensure_block_media(src_org, dst_org, src_media_ids, dry_run):
    """Import content-block media into dst from each source media's public CDN URL
    (s_c__Url__c -> s_c__Import_Url__c), idempotent by Identifier.

    Block media are NOT product media, so migrate-media.py doesn't cover them.
    Returns src_media_id -> dst_media_id.
    """
    media_map = {}
    ids = sorted(src_media_ids)
    if not ids:
        return media_map

    src_media = {}
    for i in range(0, len(ids), 150):
        chunk = "','".join(ids[i:i + 150])
        for m in sf_query(src_org,
                f"SELECT Id, Name, s_c__File_Type__c, s_c__Url__c, s_c__Identifier__c "
                f"FROM s_c__Media__c WHERE Id IN ('{chunk}')"):
            src_media[m['Id']] = m

    dst_by_ident = {}
    if not dry_run:
        for m in sf_query(dst_org,
                "SELECT Id, s_c__Identifier__c FROM s_c__Media__c WHERE s_c__Identifier__c != null"):
            dst_by_ident[m['s_c__Identifier__c']] = m['Id']

    for mid in ids:
        m = src_media.get(mid)
        if not m:
            print(f'    WARN: block media {mid} not found in {src_org}')
            continue
        ident = m.get('s_c__Identifier__c') or f'media-{mid[-8:]}'
        if ident in dst_by_ident:
            media_map[mid] = dst_by_ident[ident]
            print(f'    (exists) media {ident}')
            continue
        data = {'Name': m['Name'], 's_c__File_Type__c': m.get('s_c__File_Type__c') or 'image',
                's_c__Identifier__c': ident, 's_c__Import_Url__c': m.get('s_c__Url__c')}
        if dry_run:
            media_map[mid] = f'DRY_{ident}'
            print(f"    + media {ident}  import={str(m.get('s_c__Url__c'))[:50]}")
        else:
            new_id = create_record(dst_org, 's_c__Media__c', data)
            media_map[mid] = new_id
            dst_by_ident[ident] = new_id
            print(f'    + media {ident}  ({new_id})')
    return media_map


def copy_fields(rec, fields):
    return {k: v for k, v in rec.items() if k in fields and k not in SKIP and v is not None}


def main():
    dry_run = '--dry-run' in sys.argv
    rest = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(rest) != 1:
        print('Usage: python3 scripts/deploy-store-content.py <dst_org> [--dry-run]')
        sys.exit(1)
    dst_org = rest[0]
    mode = 'DRY RUN' if dry_run else 'LIVE'

    cmap = json.loads((REPO_ROOT / 'orgs' / dst_org / 'category-map.json').read_text())
    dst_store_id = cmap['dst_store_id']
    src_org = cmap['src_org']
    cat_map = {c['src_id']: c['dst_id'] for c in cmap['categories']}
    store_dir = next(d for d in (REPO_ROOT / 'orgs' / dst_org / 'stores').iterdir()
                     if (d / 'record.json').exists())
    print(f'[{mode}] Deploy store content -> {dst_org}  (store {dst_store_id})')

    def load(sub):
        base = store_dir / sub
        return [json.loads((d / 'record.json').read_text()) for d in sorted(base.iterdir())
                if (d / 'record.json').exists()] if base.exists() else []

    def existing_by(sobject, field, where=''):
        if dry_run:
            return {}
        rows = sf_query(dst_org, f"SELECT Id, {field} FROM {sobject} WHERE {field} != null {where}")
        return {r[field]: r['Id'] for r in rows}

    def ensure(sobject, recs, key, fields, extra_fn, existing):
        """Create each rec if its key isn't already present; return src_id->dst_id."""
        idmap = {}
        for r in recs:
            kv = r.get(key)
            if kv in existing:
                idmap[r['Id']] = existing[kv]
                print(f'  (exists) {sobject.split("__")[1]} {r.get("Name")}')
                continue
            data = copy_fields(r, fields)
            data.update(extra_fn(r))
            if dry_run:
                idmap[r['Id']] = f'DRY_{kv}'
                print(f'  + {sobject.split("__")[1]} {r.get("Name")}')
            else:
                new = create_record(dst_org, sobject, data)
                idmap[r['Id']] = new
                existing[kv] = new
                print(f'  + {sobject.split("__")[1]} {r.get("Name")}  ({new})')
        return idmap

    # 1. Content blocks (+ each block's own media) ──────────────────────────────
    print('\n[1] Content blocks')
    blocks = load('content-blocks')
    block_media_ids = {b[f] for b in blocks for f in MEDIA_LOOKUPS if b.get(f)}
    print(f'  block media: {len(block_media_ids)} from {src_org}')
    block_media_map = ensure_block_media(src_org, dst_org, block_media_ids, dry_run)

    def cb_extra(r):
        extra = {}
        for f in MEDIA_LOOKUPS:
            if r.get(f):
                dst = block_media_map.get(r[f])
                if dst:
                    extra[f] = dst
                else:
                    print(f"    WARN: block '{r.get('Name')}' media {f}={r[f]} unmapped")
        return extra

    # s_c__Template__c is a RESTRICTED picklist. Custom block templates (sto-*,
    # inf-logo-block, sc-*) exist in the source org but NOT in a blank target until
    # they're registered there (via the StoreConnect theme sync). Creating a block
    # with an unknown template hard-fails. Skip those blocks (so menu/pages/articles
    # /valid-blocks/repoint still deploy) and report them — re-running after the
    # templates are registered will create the skipped blocks + their junctions.
    valid_tpl = picklist_values(dst_org, 's_c__Content_Block__c', 's_c__Template__c')
    usable, skipped_tpl = [], []
    for b in blocks:
        t = b.get('s_c__Template__c')
        if t and valid_tpl and t not in valid_tpl:
            skipped_tpl.append((b.get('Name'), t))
        else:
            usable.append(b)
    for name, t in skipped_tpl:
        print(f"  SKIP block '{name}': template '{t}' not a valid picklist value in {dst_org}")
    if skipped_tpl:
        print(f"  ({len(skipped_tpl)} block(s) skipped — register the templates in the "
              f"target, then re-run to add them)")

    cb_f = nonref_createable(dst_org, 's_c__Content_Block__c')
    cb_map = ensure('s_c__Content_Block__c', usable, 's_c__Identifier__c',
                    cb_f, cb_extra, existing_by('s_c__Content_Block__c', 's_c__Identifier__c'))

    # 1b. Featured product/category associations (drive the sto-featured-* blocks)
    print('\n[1b] Featured product/category associations')
    featured_associations(src_org, dst_org, cb_map, cat_map, dry_run)

    # 2. Articles ───────────────────────────────────────────────────────────────
    print('\n[2] Articles')
    art_f = nonref_createable(dst_org, 's_c__Article__c')
    art_map = ensure('s_c__Article__c', load('articles'), 's_c__Slug__c', art_f,
                     lambda r: {'s_c__Store_Id__c': dst_store_id},
                     existing_by('s_c__Article__c', 's_c__Slug__c'))

    # 3. Pages ───────────────────────────────────────────────────────────────────
    print('\n[3] Pages')
    pg_f = nonref_createable(dst_org, 's_c__Page__c')
    page_map = ensure('s_c__Page__c', load('pages'), 's_c__Slug__c', pg_f,
                      lambda r: {'s_c__Store_Id__c': dst_store_id},
                      existing_by('s_c__Page__c', 's_c__Slug__c'))

    # 4. Menus ───────────────────────────────────────────────────────────────────
    print('\n[4] Menus')
    mn_f = nonref_createable(dst_org, 's_c__Menu__c')
    menu_map = ensure('s_c__Menu__c', load('menus'), 's_c__Identifier__c', mn_f,
                      lambda r: {'s_c__Store_Id__c': dst_store_id},
                      existing_by('s_c__Menu__c', 's_c__Identifier__c'))

    # products by slug (for menu items that link a product)
    prod_by_slug = {} if dry_run else {
        p['s_c__Slug__c']: p['Id']
        for p in sf_query(dst_org, "SELECT Id, s_c__Slug__c FROM Product2 WHERE s_c__Slug__c != null")}

    # 5. Menu items (two-pass for Parent_Id) ─────────────────────────────────────
    print('\n[5] Menu items')
    mi_f = nonref_createable(dst_org, 's_c__Menu_Item__c')
    item_idmap = {}        # src item id -> dst item id
    pending_parent = []    # (dst_item_id, src_parent_id)
    existing_items = {} if dry_run else {
        i['s_c__Identifier__c']: i['Id']
        for i in sf_query(dst_org, "SELECT Id, s_c__Identifier__c FROM s_c__Menu_Item__c WHERE s_c__Identifier__c != null")}
    for menu_dir in sorted((store_dir / 'menus').iterdir()) if (store_dir / 'menus').exists() else []:
        items_path = menu_dir / 'items.json'
        menu_rec_path = menu_dir / 'record.json'
        if not items_path.exists() or not menu_rec_path.exists():
            continue
        # items.json doesn't carry s_c__Menu_Id__c — the owning menu is the folder.
        dst_menu_id = menu_map.get(json.loads(menu_rec_path.read_text())['Id'])
        for it in json.loads(items_path.read_text()):
            ident = it.get('s_c__Identifier__c')
            if ident in existing_items:
                item_idmap[it['Id']] = existing_items[ident]
                continue
            data = copy_fields(it, mi_f)
            # remap references
            data['s_c__Menu_Id__c'] = dst_menu_id
            for src_field, mp in (('s_c__Product_Category_Id__c', cat_map),
                                  ('s_c__Article_Id__c', art_map),
                                  ('s_c__Page_Id__c', page_map)):
                if it.get(src_field):
                    data[src_field] = mp.get(it[src_field])
            if it.get('s_c__Product_Id__c'):
                # product links are by src id -> resolve via source slug if needed; warn if unmapped
                print(f"    NOTE: item {it.get('Name')} links a Product by id; not remapped (verify)")
            if dry_run:
                print(f"  + item {it.get('Name')}  (menu={menu_dir.name})")
                item_idmap[it['Id']] = f"DRY_{ident}"
            else:
                data = {k: v for k, v in data.items() if v is not None}
                new = create_record(dst_org, 's_c__Menu_Item__c', data)
                item_idmap[it['Id']] = new
                if it.get('s_c__Parent_Id__c'):
                    pending_parent.append((new, it['s_c__Parent_Id__c']))
                print(f"  + item {it.get('Name')}  ({new})")
    # second pass: parents
    for dst_item, src_parent in pending_parent:
        parent_dst = item_idmap.get(src_parent)
        if parent_dst:
            update_record(dst_org, 's_c__Menu_Item__c', dst_item, {'s_c__Parent_Id__c': parent_dst})
            print(f'  ~ set parent on {dst_item}')

    # 5b. Content-block ↔ page junctions ─────────────────────────────────────────
    # This is what render_content_blocks reads to build each page's design.
    print('\n[5b] Content-block ↔ page junctions')
    cbp_path = store_dir / 'content-block-pages.json'
    if cbp_path.exists():
        rows = json.loads(cbp_path.read_text())
        existing_pairs = set()
        if not dry_run:
            dst_page_ids = [v for v in page_map.values() if v and not str(v).startswith('DRY_')]
            if dst_page_ids:
                ids = "','".join(dst_page_ids)
                for j in sf_query(dst_org,
                        f"SELECT s_c__Page_Id__c, s_c__Content_Block_Id__c "
                        f"FROM s_c__Content_Blocks_Pages__c WHERE s_c__Page_Id__c IN ('{ids}')"):
                    existing_pairs.add((j['s_c__Page_Id__c'], j['s_c__Content_Block_Id__c']))
        created = skipped = 0
        for r in rows:
            dpage = page_map.get(r.get('s_c__Page_Id__c'))
            dblock = cb_map.get(r.get('s_c__Content_Block_Id__c'))
            ref = r.get('s_c__Content_Block_Id__r') or {}
            bname = ref.get('Name') if isinstance(ref, dict) else None
            if not dpage or not dblock:
                print(f"  WARN: junction unmapped page={r.get('s_c__Page_Id__c')} "
                      f"block={r.get('s_c__Content_Block_Id__c')} ({bname})")
                continue
            if (dpage, dblock) in existing_pairs:
                skipped += 1
                continue
            data = {'s_c__Page_Id__c': dpage, 's_c__Content_Block_Id__c': dblock}
            for f in ('s_c__Position__c', 's_c__Usage_Type__c', 's_c__Tag__c'):
                if r.get(f) is not None:
                    data[f] = r[f]
            if dry_run:
                print(f"  + junction pos={r.get('s_c__Position__c')}  {bname or dblock}")
            else:
                create_record(dst_org, 's_c__Content_Blocks_Pages__c', data)
                print(f"  + junction pos={r.get('s_c__Position__c')}  {bname or dblock}")
            created += 1
        print(f'  junctions: +{created} ({skipped} existed)')
    else:
        print('  (no content-block-pages.json)')

    # 6. Repoint store references ────────────────────────────────────────────────
    print('\n[6] Repoint store references')
    store_rec = json.loads((store_dir / 'record.json').read_text())
    std_pb = sf_query(dst_org, "SELECT Id FROM Pricebook2 WHERE IsStandard = true LIMIT 1")
    repoint = {}
    for field, mp in (('s_c__Header_Menu_Id__c', menu_map), ('s_c__Footer_Menu_Id__c', menu_map),
                      ('s_c__Head_Content_Block_Id__c', cb_map),
                      ('s_c__Home_Page_Id__c', page_map), ('s_c__Terms_Page_Id__c', page_map)):
        src = store_rec.get(field)
        if src and mp.get(src):
            repoint[field] = mp[src]
    if std_pb:
        repoint['s_c__Pricebook_Id__c'] = std_pb[0]['Id']

    # Store logo media — Logo_Id/Email_Logo_Id are cross-org media (skipped by
    # deploy-store). Import them from the source CDN URL (reusing the block-media
    # importer) and set the remapped media ids on the store so the storefront logo
    # appears.
    logo_src_ids = {store_rec[f] for f in ('s_c__Logo_Id__c', 's_c__Email_Logo_Id__c')
                    if store_rec.get(f)}
    if logo_src_ids:
        print(f'  logo media: {len(logo_src_ids)} from {src_org}')
        logo_map = ensure_block_media(src_org, dst_org, logo_src_ids, dry_run)
        for f in ('s_c__Logo_Id__c', 's_c__Email_Logo_Id__c'):
            if store_rec.get(f) and logo_map.get(store_rec[f]):
                repoint[f] = logo_map[store_rec[f]]

    for k, v in repoint.items():
        print(f'  {k} -> {v}')
    if not dry_run and repoint:
        update_record(dst_org, 's_c__Store__c', dst_store_id, repoint)

    print('\nDone.')


if __name__ == '__main__':
    main()
