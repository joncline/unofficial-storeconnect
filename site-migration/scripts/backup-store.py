#!/usr/bin/env python3
"""Back up a StoreConnect store record and all related records.

Backs up:
  - Store record (all fields)
  - Store Variables
  - All Menus + Menu Items
  - All Pages
  - All Articles
  - Content Blocks referenced by the store
  - All Product Categories + per-product data:
      * record.json              — full Product2 fields (all fields via sf data get record)
      * pricebook-entries.json   — every PBE for the product including bundle attrs
                                   (Bundle_Only, Hide_Price, Hide_Price_Text,
                                   Bundle_Price_Strategy, Disable_Quantity_Selection)
      * product-media.json       — s_c__Product_Media__c junctions + Media identifier
      * bundle-structure.json    — s_c__Product_Component__c rows where the product
                                   is anchor or component + linked s_c__Component_Group__c
  - bundle-components/<slug>/    — same per-product files for any component products
                                   referenced by backed-up bundle anchors that aren't
                                   themselves in a category (e.g., bundle-only places)
  - Theme (templates, variables, locales, assets)

Usage:
    python3 scripts/backup-store.py <org> <store-id>

Output:
    orgs/<org>/stores/<slug>/
      record.json
      store-variables.json
      menus/<slug>/record.json
      menus/<slug>/items.json
      pages/<slug>/record.json
      articles/<slug>/record.json
      content-blocks/<slug>/record.json
      categories/<slug>/record.json
      categories/<slug>/products/<slug>/record.json
      categories/<slug>/products/<slug>/pricebook-entries.json
      categories/<slug>/products/<slug>/product-media.json
      categories/<slug>/products/<slug>/bundle-structure.json
      bundle-components/<slug>/record.json
      bundle-components/<slug>/pricebook-entries.json
      bundle-components/<slug>/product-media.json
      bundle-components/<slug>/bundle-structure.json
    orgs/<org>/themes/<slug>/   (theme files)
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, pull_theme, slugify

REPO_ROOT = Path(__file__).parent.parent

CONTENT_BLOCK_FIELDS = [
    's_c__Head_Content_Block_Id__c',
    's_c__Header_Content_Block_Id__c',
    's_c__Footer_Content_Block_Id__c',
    's_c__Body_Content_Block_Id__c',
    's_c__Disabled_Content_Block_Id__c',
]

PRICEBOOK_ENTRY_FIELDS = [
    'Id', 'Pricebook2Id', 'Pricebook2.Name', 'Product2Id', 'UnitPrice', 'IsActive',
    's_c__Bundle_Only__c', 's_c__Hide_Price__c', 's_c__Hide_Price_Text__c',
    's_c__Bundle_Price_Strategy__c', 's_c__Disable_Quantity_Selection__c',
]

PRODUCT_COMPONENT_FIELDS = [
    'Id', 's_c__Anchor_Product_Id__c', 's_c__Anchor_Product_Id__r.Name',
    's_c__Component_Product_Id__c', 's_c__Component_Product_Id__r.Name',
    's_c__Component_Product_Id__r.ProductCode',
    's_c__Group_Id__c', 's_c__Group_Id__r.Name',
    's_c__Min_Quantity__c', 's_c__Max_Quantity__c',
    's_c__Default_Quantity__c', 's_c__Free_Quantity__c',
    's_c__Required__c', 's_c__Position__c',
]

COMPONENT_GROUP_FIELDS = [
    'Id', 'Name', 's_c__Display_Name__c',
    's_c__Min_Components__c', 's_c__Max_Components__c',
    's_c__Min_Group_Quantity__c', 's_c__Max_Group_Quantity__c',
    's_c__Position__c',
]

PRODUCT_MEDIA_FIELDS = [
    'Id', 's_c__Product_Id__c', 's_c__Media_Id__c',
    's_c__Media_Id__r.s_c__Identifier__c',
    's_c__Position__c',
]


def sf_export_record(org, sobject, record_id):
    result = subprocess.run(
        ['sf', 'data', 'get', 'record',
         '--target-org', org,
         '--sobject', sobject,
         '--record-id', record_id,
         '--json'],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    if data.get('status', 0) != 0:
        raise RuntimeError(data.get('message') or json.dumps(data))
    rec = data['result']
    rec.pop('attributes', None)
    return rec


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def backup_store_variables(org, store_id, out):
    records = sf_query(
        org,
        f"SELECT Id, Name, s_c__Key__c, s_c__Value__c, s_c__Available_In_Liquid__c "
        f"FROM s_c__Store_Variable__c "
        f"WHERE s_c__Store_Id__c = '{store_id}' "
        f"ORDER BY s_c__Key__c",
    )
    for r in records:
        r.pop('attributes', None)
    write_json(out / 'store-variables.json', records)
    print(f"  {len(records)} store variable(s)  →  store-variables.json")
    return records


def backup_menus(org, store_id, out):
    menus = sf_query(
        org,
        f"SELECT Id, Name, s_c__Identifier__c, s_c__Style_Class_Names__c, s_c__sC_Id__c "
        f"FROM s_c__Menu__c WHERE s_c__Store_Id__c = '{store_id}' ORDER BY Name",
    )
    for menu in menus:
        menu.pop('attributes', None)
        menu_id = menu['Id']
        slug = slugify(menu.get('Name') or menu_id)
        menu_out = out / 'menus' / slug
        write_json(menu_out / 'record.json', menu)

        items = sf_query(
            org,
            f"SELECT Id, Name, s_c__Display_Name__c, s_c__Identifier__c, "
            f"s_c__Position__c, s_c__URL__c, s_c__Page_Id__c, s_c__Parent_Id__c, "
            f"s_c__Hide__c, s_c__Style_Class_Names__c, s_c__Article_Id__c, "
            f"s_c__Product_Category_Id__c, s_c__sC_Id__c "
            f"FROM s_c__Menu_Item__c "
            f"WHERE s_c__Menu_Id__c = '{menu_id}' "
            f"ORDER BY s_c__Position__c",
        )
        for item in items:
            item.pop('attributes', None)
        write_json(menu_out / 'items.json', items)
        print(f"  Menu '{menu.get('Name')}'  →  menus/{slug}/  ({len(items)} items)")


def backup_pages(org, store_id, out):
    pages = sf_query(
        org,
        f"SELECT Id, Name, s_c__Title__c, s_c__Subtitle__c, s_c__Slug__c, s_c__Path__c, "
        f"s_c__Body_Markdown__c, s_c__Meta_Title__c, s_c__Meta_Description__c, "
        f"s_c__Meta_Keywords__c, s_c__Visible__c, s_c__Hide__c, s_c__Require_Login__c, "
        f"s_c__Position__c, s_c__Parent_Id__c, s_c__sC_Id__c "
        f"FROM s_c__Page__c WHERE s_c__Store_Id__c = '{store_id}' ORDER BY Name",
    )
    for page in pages:
        page.pop('attributes', None)
        slug = slugify(page.get('s_c__Slug__c') or page.get('Name') or page['Id'])
        write_json(out / 'pages' / slug / 'record.json', page)
        print(f"  Page '{page.get('Name')}'  →  pages/{slug}/record.json")


def backup_articles(org, store_id, out):
    articles = sf_query(
        org,
        f"SELECT Id, Name, s_c__Title__c, s_c__Subtitle__c, s_c__Slug__c, s_c__Path__c, "
        f"s_c__Body_Markdown__c, s_c__Intro_Markdown__c, s_c__Summary_Markdown__c, "
        f"s_c__Meta_Title__c, s_c__Meta_Description__c, s_c__Meta_Keywords__c, "
        f"s_c__Published__c, s_c__Publish_On__c, s_c__Require_Login__c, s_c__sC_Id__c "
        f"FROM s_c__Article__c WHERE s_c__Store_Id__c = '{store_id}' ORDER BY Name",
    )
    for article in articles:
        article.pop('attributes', None)
        slug = slugify(article.get('s_c__Slug__c') or article.get('Name') or article['Id'])
        write_json(out / 'articles' / slug / 'record.json', article)
        print(f"  Article '{article.get('Name')}'  →  articles/{slug}/record.json")
    if articles:
        print(f"  {len(articles)} article(s) backed up")


def _strip_attributes(records):
    for r in records:
        r.pop('attributes', None)
    return records


def fetch_pbes_for_product(org, product_id):
    rows = sf_query(
        org,
        f"SELECT {', '.join(PRICEBOOK_ENTRY_FIELDS)} "
        f"FROM PricebookEntry WHERE Product2Id = '{product_id}' "
        f"ORDER BY Pricebook2.Name",
    )
    return _strip_attributes(rows)


def fetch_product_media(org, product_id):
    rows = sf_query(
        org,
        f"SELECT {', '.join(PRODUCT_MEDIA_FIELDS)} "
        f"FROM s_c__Product_Media__c WHERE s_c__Product_Id__c = '{product_id}' "
        f"ORDER BY s_c__Position__c",
    )
    return _strip_attributes(rows)


def fetch_bundle_structure(org, product_id):
    """Return Product_Component rows where this product is anchor or component,
    plus the Component_Group rows referenced as anchor-side. Components-side rows
    are included so we can see "where am I used"."""
    as_anchor = sf_query(
        org,
        f"SELECT {', '.join(PRODUCT_COMPONENT_FIELDS)} "
        f"FROM s_c__Product_Component__c "
        f"WHERE s_c__Anchor_Product_Id__c = '{product_id}' "
        f"ORDER BY s_c__Position__c",
    )
    as_component = sf_query(
        org,
        f"SELECT {', '.join(PRODUCT_COMPONENT_FIELDS)} "
        f"FROM s_c__Product_Component__c "
        f"WHERE s_c__Component_Product_Id__c = '{product_id}' "
        f"ORDER BY s_c__Position__c",
    )
    _strip_attributes(as_anchor)
    _strip_attributes(as_component)

    group_ids = sorted({r['s_c__Group_Id__c'] for r in as_anchor if r.get('s_c__Group_Id__c')})
    component_groups = []
    if group_ids:
        ids_clause = "','".join(group_ids)
        component_groups = sf_query(
            org,
            f"SELECT {', '.join(COMPONENT_GROUP_FIELDS)} "
            f"FROM s_c__Component_Group__c WHERE Id IN ('{ids_clause}') "
            f"ORDER BY s_c__Position__c",
        )
        _strip_attributes(component_groups)

    return {
        'as_anchor': as_anchor,
        'as_component': as_component,
        'component_groups': component_groups,
    }


def backup_product_data(org, product_id, out_path):
    """Back up full Product2 + PBEs + Product_Media + bundle structure for one product."""
    prod = sf_export_record(org, 'Product2', product_id)
    write_json(out_path / 'record.json', prod)

    pbes = fetch_pbes_for_product(org, product_id)
    if pbes:
        write_json(out_path / 'pricebook-entries.json', pbes)

    media = fetch_product_media(org, product_id)
    if media:
        write_json(out_path / 'product-media.json', media)

    bundle = fetch_bundle_structure(org, product_id)
    if bundle['as_anchor'] or bundle['as_component'] or bundle['component_groups']:
        write_json(out_path / 'bundle-structure.json', bundle)

    return prod, bundle


def backup_product_categories(org, store_id, out):
    cats = sf_query(
        org,
        f"SELECT Id, Name, s_c__Display_Name__c, s_c__Title__c, s_c__Subtitle__c, "
        f"s_c__Path__c, s_c__Introduction_Markdown__c, s_c__Information_Markdown__c, "
        f"s_c__Meta_Title__c, s_c__Meta_Description__c, s_c__Taxonomy_Id__c, "
        f"s_c__sC_Id__c "
        f"FROM s_c__Product_Category__c "
        f"WHERE s_c__Taxonomy_Id__r.s_c__Store_Id__c = '{store_id}' ORDER BY Name",
    )
    backed_up_product_ids = set()

    for cat in cats:
        cat.pop('attributes', None)
        cat_id = cat['Id']
        cat_slug = slugify(cat.get('Name') or cat_id)
        write_json(out / 'categories' / cat_slug / 'record.json', cat)

        junctions = sf_query(
            org,
            f"SELECT s_c__Product_Id__c, s_c__Position__c "
            f"FROM s_c__Products_Product_Categories__c "
            f"WHERE s_c__Category_Id__c = '{cat_id}' "
            f"ORDER BY s_c__Position__c",
        )
        product_count = 0
        for j in junctions:
            pid = j['s_c__Product_Id__c']
            if not pid:
                continue
            prod_lookup = sf_query(
                org,
                f"SELECT Id, Name, s_c__Slug__c FROM Product2 WHERE Id = '{pid}'",
            )
            if not prod_lookup:
                continue
            p = prod_lookup[0]
            pslug = slugify(p.get('s_c__Slug__c') or p.get('Name') or pid)
            backup_product_data(org, pid, out / 'categories' / cat_slug / 'products' / pslug)
            backed_up_product_ids.add(pid)
            product_count += 1

        print(f"  Category '{cat.get('Name')}'  →  categories/{cat_slug}/  ({product_count} products)")

    return backed_up_product_ids


def backup_orphan_bundle_components(org, anchor_ids, out):
    """Recursively back up any Product_Component child products that weren't
    captured by category-driven backup (e.g., bundle-only attendee/activity
    products that aren't displayed in a category listing)."""
    visited = set(anchor_ids)
    queue = list(anchor_ids)
    new_orphans = []

    while queue:
        pid = queue.pop()
        rows = sf_query(
            org,
            f"SELECT s_c__Component_Product_Id__c FROM s_c__Product_Component__c "
            f"WHERE s_c__Anchor_Product_Id__c = '{pid}'",
        )
        for r in rows:
            cid = r.get('s_c__Component_Product_Id__c')
            if cid and cid not in visited:
                visited.add(cid)
                queue.append(cid)
                new_orphans.append(cid)

    if not new_orphans:
        return

    print(f"  {len(new_orphans)} orphan bundle component product(s) — backing up to bundle-components/")
    for cid in new_orphans:
        prods = sf_query(
            org,
            f"SELECT Id, Name, s_c__Slug__c FROM Product2 WHERE Id = '{cid}'",
        )
        if not prods:
            continue
        p = prods[0]
        pslug = slugify(p.get('s_c__Slug__c') or p.get('Name') or cid)
        backup_product_data(org, cid, out / 'bundle-components' / pslug)
        print(f"    {p.get('Name')}  →  bundle-components/{pslug}/")


def backup_content_blocks(org, store_id, store_rec, out):
    """Back up content blocks used by the store.

    Content blocks are NOT store-scoped, so we capture the union of:
      1. blocks referenced by the store's 5 lookup fields
         (Head/Header/Footer/Body/Disabled), and
      2. blocks linked to any of the store's pages via the
         s_c__Content_Blocks_Pages__c junction (the per-page design blocks).
    The junction rows themselves are written to content-block-pages.json so
    the page<->block layout (Position/Usage_Type/Tag) can be reconstructed.

    Each block's full field set (incl. media lookups Image/Media/File/Video/
    Document_Id) is captured by sf_export_record.

    NOTE: blocks rendered only by name (the render-by-name Liquid filter, with
    no junction or store-field reference) cannot be discovered from data alone
    and are not captured here.
    """
    # Junction rows for this store's pages.
    junctions = sf_query(
        org,
        f"SELECT Id, s_c__Page_Id__c, s_c__Page_Id__r.s_c__Slug__c, "
        f"s_c__Content_Block_Id__c, s_c__Content_Block_Id__r.Name, "
        f"s_c__Position__c, s_c__Usage_Type__c, s_c__Tag__c, "
        f"Content_Key_External_Id__c, s_c__sC_Id__c "
        f"FROM s_c__Content_Blocks_Pages__c "
        f"WHERE s_c__Page_Id__r.s_c__Store_Id__c = '{store_id}' "
        f"ORDER BY s_c__Page_Id__r.s_c__Slug__c, s_c__Position__c",
    )
    for j in junctions:
        j.pop('attributes', None)
    if junctions:
        write_json(out / 'content-block-pages.json', junctions)
        print(f"  {len(junctions)} content-block <-> page junction(s)  "
              f"->  content-block-pages.json")

    block_ids = [store_rec.get(f) for f in CONTENT_BLOCK_FIELDS if store_rec.get(f)]
    block_ids += [j['s_c__Content_Block_Id__c'] for j in junctions
                  if j.get('s_c__Content_Block_Id__c')]

    seen = set()
    for block_id in block_ids:
        if block_id in seen:
            continue
        seen.add(block_id)

        block = sf_export_record(org, 's_c__Content_Block__c', block_id)
        slug = slugify(block.get('Name') or block_id)
        write_json(out / 'content-blocks' / slug / 'record.json', block)
        print(f"  Content Block '{block.get('Name')}'  →  content-blocks/{slug}/record.json")


def backup_store(org, store_id):
    stores = sf_query(org, f"SELECT Id, Name FROM s_c__Store__c WHERE Id = '{store_id}'")
    if not stores:
        raise RuntimeError(f"Store {store_id} not found in org {org}")

    store_name = stores[0]['Name']
    slug = slugify(store_name)
    out = REPO_ROOT / 'orgs' / org / 'stores' / slug
    out.mkdir(parents=True, exist_ok=True)

    print(f"Backing up store: {store_name} ({store_id})")
    store_rec = sf_export_record(org, 's_c__Store__c', store_id)
    write_json(out / 'record.json', store_rec)
    print(f"  Store record  →  orgs/{org}/stores/{slug}/record.json")

    backup_store_variables(org, store_id, out)
    backup_menus(org, store_id, out)
    backup_pages(org, store_id, out)
    backup_articles(org, store_id, out)
    category_product_ids = backup_product_categories(org, store_id, out)
    backup_orphan_bundle_components(org, category_product_ids, out)
    backup_content_blocks(org, store_id, store_rec, out)

    theme_id = store_rec.get('s_c__Theme_Id__c')
    if theme_id:
        print(f"Backing up theme: {theme_id}")
        stats = pull_theme(org, theme_id, REPO_ROOT)
        print(f"  Theme: {stats['name']}  ({stats['templates']} templates, "
              f"{stats['variables']} variables, {stats['assets']} assets)")
    else:
        print("  No theme linked to this store.")

    return store_rec


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/backup-store.py <org> <store-id>")
        sys.exit(1)

    org, store_id = sys.argv[1], sys.argv[2]
    backup_store(org, store_id)
    print("\nDone.")


if __name__ == '__main__':
    main()
