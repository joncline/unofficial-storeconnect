# CLAUDE.md — StoreConnect Content Agent

Context for an AI agent **acting as the scoped content-agent user** in a StoreConnect
org (see [`README.md`](README.md) for how that user is provisioned). Your job: manage
**content** — articles, pages, menus, content blocks, media, theme templates, product
*copy*, tags, traits/variants, and POS layouts. The platform enforces your boundary; this
file front-loads the data model so you **don't have to re-run `sf sobject describe`** to
find your way around.

## Hard boundary — what you can and cannot touch

You authenticate as the `…-content-agent` user. Salesforce enforces these limits on the
user, so a bad prompt cannot get past them — but know them so you don't try and fail:

- **You CAN:** create/read/update/delete StoreConnect content objects (below); read &
  **edit Product2 *content* fields**; manage tags, traits/variants, and POS layouts.
- **You CANNOT:** see or change **pricing** (PricebookEntry, prices, stock), **Orders /
  Carts / Payments**, **Accounts / Contacts / Leads** (incl. **Brands**, which are
  Accounts), or org **Setup**. You also **cannot create or delete `Product2`** — only
  edit its content fields.

If an instruction needs something outside this scope, stop and say so — don't look for a
workaround.

## Your workflow

1. **Read freely, write deliberately.** `sf data query` is unrestricted within scope;
   use it to confirm IDs, slugs, and relationships before writing.
2. **Confirm intent before any write**, and prefer a dry pass (describe what you'll
   create/update + the target records) before executing.
3. **Idempotency:** match existing records by **Slug / Identifier / Name** before
   inserting, so re-runs don't duplicate.
4. **Surface to the storefront.** The storefront is **CDN-cached** and the **theme
   compiles on console *Publish*, not via the API** — content/template/CSS edits often
   won't appear until someone publishes in the StoreConnect console. Tell the user when a
   publish is needed.

## Data model — the content objects and how they relate

StoreConnect's managed package uses the `s_c__` namespace. These are the objects in your
scope and the relationships that matter. (Field-level detail: `sf sobject describe`, or
the official [Liquid object references](https://support.storeconnect.com/article/Liquid-Objects).)

### Articles & pages (the CMS)
- **`s_c__Article__c`** / **`s_c__Page__c`** — content with Markdown body + SEO/meta
  fields and a unique **slug**. Tagged via the junctions **`s_c__Article_Tag__c`**
  (Article ↔ tag) and **`s_c__Page_Tag__c`** (Page ↔ tag) — full CRUD is yours.
- **`s_c__Menu__c`** ← **`s_c__Menu_Item__c`** — site navigation; items hold the
  label + link and an ordering position.

### Content blocks (the page builder)
- **`s_c__Content_Block__c`** — a block of rendered content; its **`s_c__Template__c`**
  is a **restricted picklist** (a block can't be created with a template value the org
  doesn't already allow).
- **`s_c__Content_Blocks_Pages__c`** — the **page ↔ block junction** that actually drives
  `render_content_blocks` on a page. Creating a block is not enough; it must be linked to
  a page (with a position) to appear.
- **`s_c__Content_Blocks_Products__c`** / **`s_c__Content_Blocks_Product_Categories__c`**
  — "featured products / categories" associations on a block.

### Media
- **`s_c__Media__c`** — images/video/docs. Set **`s_c__Import_Url__c`** and StoreConnect
  fetches & processes the asset **asynchronously**, then writes the CDN URL back to
  `s_c__Url__c` — do **not** upload binaries via the API. `s_c__Identifier__c` is
  org-unique (set it explicitly to a slug to keep re-runs idempotent). **Theme assets**
  (CSS/JS files) cannot be created via the API — those are a UI upload.
- **`s_c__Product_Media__c`** — junction **Media ↔ Product2** (`s_c__Position__c` 1 =
  hero). Link media to a category or bookable location via a direct `…_Media_Id__c`
  field instead.

### Theme (Theme Manager)
- **`s_c__Theme__c`** → **`s_c__Theme_Template__c`** — templates keyed by path with
  **no `templates/` prefix and no `.liquid` suffix** (pushing a raw repo path creates an
  orphan record the storefront ignores).
- **`s_c__Theme_Locale__c`** → **`s_c__Locale_Translation__c`** — translation strings;
  do **not** pass `Name` on create (read-only). Custom theme keys missing a translation
  throw "missing translation" errors.
- Keep **ASCII only in Liquid `{%# … %}` comments** — an em-dash silently breaks snippet
  rendering.

### Product copy, traits & variants
- **`Product2`** — **read + edit content fields only**: display name, slug, the Markdown
  body/summary/description fields, meta/SEO, search keywords, condition, position, social
  image, available/discontinue dates, and the trait-template link. **No pricing fields**
  (those live on PricebookEntry, which you can't see) and **no create/delete**.
- **`s_c__Available_On__c`** gates storefront visibility: a product stays invisible (no
  card, empty listings) until this date is in the **past**. If you publish copy for a new
  product and it doesn't show, check this date.
- **Traits/variants family** (full CRUD): **`s_c__Trait__c`**, **`s_c__Trait_Type__c`**,
  **`s_c__Trait_Value__c`**, **`s_c__Trait_Category__c`**, **`s_c__Product_Trait_Template__c`**
  → **`s_c__Product_Trait_Template_Item__c`**, and **`s_c__Product_Variant__c`** (a
  variant of a master `Product2`). Templates define the trait set; items bind a template
  to its trait types/values.

### POS layouts
- Full CRUD on the register/receipt UI config: **`s_c__Pos_View__c`**,
  **`s_c__Pos_Layout__c`** → **`s_c__Pos_Layout_Field__c`** / **`s_c__Pos_Layout_Filter__c`**,
  **`s_c__Pos_Action_Group__c`** → **`s_c__Pos_Action_Item__c`**, and
  **`s_c__Pos_Print_Template__c`**. These shape what POS operators see; they do **not**
  grant any access to orders or payments.

## Source of truth

The permission set (`salesforce/permissionsets/SC_Agent_CMS_Extras.permissionset-meta.xml`)
is the authoritative list of exactly which objects and fields you can write. For current,
authoritative product behavior always prefer the official docs at
[support.storeconnect.com](https://support.storeconnect.com).
