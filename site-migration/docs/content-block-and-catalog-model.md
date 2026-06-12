# StoreConnect content-block & catalog model

Reference notes for how a store's homepage "design" and catalog are actually
assembled — the relationships you must reproduce when migrating a store, all handled
by the scripts in this package.

## Content-block model (the homepage "design")

A page's blocks and the homepage "featured" sections are driven by junction objects
— all reproduced by `deploy-store-content.py`:

| Object | Links | Drives |
|---|---|---|
| `s_c__Content_Blocks_Pages__c` | `s_c__Page_Id__c` + `s_c__Content_Block_Id__c` (+ `s_c__Position__c`, `s_c__Usage_Type__c`) | what `render_content_blocks` assembles for each page (e.g. Home = ordered blocks, hero → logos) |
| `s_c__Content_Blocks_Products__c` | `s_c__Content_Block_Id__c` + `s_c__Product_Id__c` (+ Position) | the "featured products" block (`content_block.products`) |
| `s_c__Content_Blocks_Product_Categories__c` | **`s_c__Cntnt_Blk_Id__c`** + `s_c__Category_Id__c` (+ Position) | the "featured categories" block (`content_block.product_categories`) — note the truncated `Cntnt_Blk` field name |
| `s_c__Content_Blocks_Children__c` | `s_c__Parent_Id__c` + `s_c__Child_Id__c` | block nesting |

Without the featured-products / featured-categories junctions, those homepage blocks
render "coming soon" even when the catalog is fully present.

Other facts:
- Store → block lookups: exactly 5 on `s_c__Store__c` —
  `s_c__{Head,Header,Footer,Body,Disabled}_Content_Block_Id__c`.
- **By-name blocks**: a Liquid filter renders any block by identifier; a store-scoped
  backup (junction + store-field capture) misses these (e.g. a global head block).
- `s_c__Content_Block__c.s_c__Template__c` is a **restricted picklist** — custom
  theme templates (sto-hero, etc.) must be registered via
  `scripts/provision-content-templates.py` (Tooling API) before blocks can be
  created, or the create fails with `INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST`.
- Category hierarchy is a separate object (`s_c__Product_Category_Hierarchy__c`,
  parent→child edges) — there is no parent field on the category; `s_c__Path__c` is a
  flat per-level slug.
- Store logo (`s_c__Logo_Id__c`) is a cross-org media lookup — imported + set by
  `deploy-store-content.py` (not the base store deploy).
