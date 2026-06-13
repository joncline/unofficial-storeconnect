# CLAUDE.md — StoreConnect Site Migration

Context for an AI agent working in this folder. The goal: **replicate a
StoreConnect store from one org into another** (or copy a store within the same
org) — catalog, categories, media, content, theme, and POS — using the `sf` CLI.
Read this first; it front-loads the data model and gotchas so you **don't need to
re-run `sf sobject describe`** on the orgs. Full field tables live in
[`scripts/sc-objects.md`](scripts/sc-objects.md); the ordered procedure is
[`docs/site-migration-runbook.md`](docs/site-migration-runbook.md).

## Your workflow when asked to migrate / copy a store

Follow this; don't rediscover the design by reading every script.

1. **Read the docs first.** This file, then `docs/solution-design.md` (per-script
   behavior + idempotency), then `docs/site-migration-runbook.md` (the order). Only
   open a specific script to *confirm* a detail the user questions.
2. **Confirm intent before any write.** Identify source org + store and target org.
   If source org == target org, it's a same-org copy → `--no-default`, `--suffix`,
   and `--theme-suffix` are needed (the orchestrator adds them). State what will be
   **created vs. reused**
   (see §"Same-org copy vs cross-org" and `solution-design.md`).
3. **Dry-run.** Run `python3 scripts/replicate-store.py` (or individual steps) with
   `--dry-run`/no `--execute`, and show the plan. **Never write to an org without the
   user's explicit go-ahead.**
4. **Execute on approval, step by step.** Prefer per-step confirmation (don't pass
   `--yes` on a first real run) so the user can inspect output between writes.
5. **Verify.** Run the count queries + storefront/POS checks (runbook §10,
   `solution-design.md` §8) and report what was created.

**Source of truth:** if a script's behavior differs from these docs, trust the code
and update the doc.

## How to run

- **Orchestrator (recommended):** `python3 scripts/replicate-store.py` — interactive,
  asks source/target up front, **dry run by default**, writes nothing without
  `--execute`. It runs every runbook step in order.
- **Manual:** follow `docs/site-migration-runbook.md` step by step.
- Run all scripts **from the project root** (paths resolve relative to it).

## Hard rules

- **All SF writes go through `scripts/lib.py`** (`_sf_rest` → `sf api request rest`).
  Never use `sf org display` access tokens directly — they expire. Read-only
  `sf data query` is fine to use freely.
- **Always `--dry-run` first.** Every write script supports it. Every script is
  **idempotent** (matches existing records by Name / Slug / Identifier /
  ProductCode) — safe to re-run after an interruption.
- **Never copy org-specific identity fields** cross-org: `s_c__Domain__c`,
  `s_c__Unique_Domain_Path__c`, `s_c__Meta_Title__c` (storefront `<title>`), and any
  `*_Id__c` **lookup** to a record in the other org (they fail insert with
  `INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY`). The scripts already strip these.
- **The theme compiles on console publish, not via API.** Pushing templates/variables
  is enough to stage them, but the storefront's compiled CSS only regenerates when
  someone publishes in the StoreConnect console. **Theme assets** (CSS/JS/image files)
  also cannot be created via API — upload via the UI (or stage as ContentVersion →
  public URL → media import).
- **Credentials are never copied** — `GOOGLE_MAPS_API_KEY` (and similar) are skipped;
  set them per target org.
- This is a **public repo** — never commit real client data, org Ids, or secrets.
  The `reference/` store is sanitized; users' own backups go in the gitignored
  `orgs/` working dir.

## Data model — what you need before touching an org

StoreConnect's managed package uses the `s_c__` namespace. The relationships and
traps that matter for migration:

### Store, theme, taxonomy
- `s_c__Store__c` — the storefront. `s_c__Default__c` = the org's **primary** store
  (only one; setting it true unsets the prior). `s_c__Theme_Id__c`, `s_c__*_Menu_Id__c`,
  `s_c__Head_Content_Block_Id__c`, `s_c__Home_Page_Id__c`/`Terms_Page_Id__c`,
  `s_c__Logo_Id__c`/`Email_Logo_Id__c`, `s_c__Pricebook_Id__c` are all repointed after
  the referenced records are created.
- `s_c__Theme__c` — one per store (reused by Name if it already exists). Templates are
  `s_c__Theme_Template__c` keyed by path **without** a `templates/` prefix or
  `.liquid` suffix.
- `s_c__Taxonomy__c` — **one per store** (`s_c__Store_Id__c`, required). Categories
  belong to a taxonomy, so **each store has its own categories** even within one org.

### Categories (the tree is a separate object)
- `s_c__Product_Category__c` — belongs to a taxonomy (`s_c__Taxonomy_Id__c`, required).
  **There is NO parent field.** `s_c__Path__c` is a flat per-level slug.
- `s_c__Product_Category_Hierarchy__c` — **the tree**: one row per parent→child edge
  (`s_c__Parent_Id__c`, `s_c__Child_Id__c`, `s_c__Position__c`). Root categories have
  no row. `provision-categories.py` recreates these and emits `category-map.json`
  (source→dest id map) consumed by later steps.

### Products, pricebooks, media
- `Product2` — standard object. `s_c__Slug__c` identifies it for remapping. A **future**
  `s_c__Available_On__c` hides the product from the storefront — `migrate-catalog.py`
  clamps future values to "now" on create.
- `PricebookEntry` — a product is not purchasable until it has a PBE. Standard pricebook:
  `SELECT Id FROM Pricebook2 WHERE IsStandard = true LIMIT 1`. Tier pricebooks
  (Bronze/Gold/Silver/Hidden/Wholesale) are mirrored by `provision-pricebooks.py`.
- `s_c__Media__c` — `s_c__File_Type__c` (picklist: image/video/document/file/url) is
  **required**. Set `s_c__Import_Url__c` to a public CDN URL; SC fetches it async and
  writes `s_c__Url__c`. `s_c__Identifier__c` is **org-wide unique** — generate fresh
  (`'media-' + token_hex(7)`) unless a specific identifier is needed for theme
  `all_media["…"]` lookups. Link to products via the `s_c__Product_Media__c` junction
  (not a field on Product2); link to a category via `s_c__Media_Id__c` on the category.

### Content (pages, blocks, menus) — the homepage model
See [`docs/content-block-and-catalog-model.md`](docs/content-block-and-catalog-model.md).
- `s_c__Page__c` — `s_c__Slug__c` is **org-wide UNIQUE**; has `s_c__Store_Id__c`.
- `s_c__Content_Block__c` — **org-wide, NO store field.** Identified by
  `s_c__Identifier__c`. `s_c__Template__c` is a **restricted picklist** — custom
  templates (`sto-hero`, `sto-promo`, `sto-featured-*`, `sto-newsletter`,
  `sto-split-content`, `inf-logo-block`) must be registered in the target first
  (`provision-content-templates.py`) or the insert fails with
  `INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST`.
- `s_c__Content_Blocks_Pages__c` — page↔block junction (Position/Usage_Type). **This is
  what `render_content_blocks` reads to assemble each page** — without it, pages render
  empty.
- `s_c__Content_Blocks_Products__c` / `s_c__Content_Blocks_Product_Categories__c` —
  "featured products / categories" that populate the homepage feature blocks; without
  them those blocks show "coming soon".
- `s_c__Menu__c` / `s_c__Menu_Item__c` — menus have `s_c__Store_Id__c`; items are
  identified by `s_c__Identifier__c` and **must link exactly one** of Article / Page /
  Product Category / Product / URL — always set `s_c__URL__c = '#'` as a fallback.
  Items don't store their menu id in the backup (the owning menu is the folder).

### POS
- `provision-pos.py` creates an **Anonymous Checkout Contact** (required), 1 Outlet,
  1 Register. **Register Code must be ≥ 20 chars** (validation rule). Reads the store
  id from `category-map.json`.

## Same-org copy vs cross-org

The same pipeline does both. **Same-org** (source org == target org) needs three
extra flags the orchestrator sets automatically — the point of an in-org clone is to
**restyle the theme / front end independently** of the live store:
- **`--no-default`** on `deploy-store.py` — so the copy doesn't seize the org's primary
  store flag (which would steal the live store's domain routing).
- **`--theme-suffix=<s>`** on `deploy-store.py` — the theme is matched by Name, so
  without it the copy would *share* the source theme. The suffix gives the copy its
  **own** theme so its theme/front end can be edited without affecting the source.
- **`--suffix=<s>`** on `deploy-store-content.py` — because `s_c__Page__c.s_c__Slug__c`
  is org-wide unique and content blocks are org-wide, the copy needs unique
  slugs/identifiers to get **independent** pages/blocks/menus instead of colliding with
  and reusing the source's.

So a same-org copy gets an **independent theme, content, and taxonomy**. Truly shared
org-wide records (products by Slug, media by Identifier, pricebooks by Name, template
picklist values) are still reused, not duplicated.

## File map

- `scripts/replicate-store.py` — interactive orchestrator (entry point).
- `scripts/backup-store.py` — capture a source store to `orgs/<alias>/`.
- `scripts/{provision-pricebooks,deploy-store,provision-categories,migrate-catalog,`
  `migrate-media,provision-content-templates,deploy-store-content,provision-pos,`
  `provision-store-user-roles}.py` — the ordered steps.
- `scripts/lib.py` — shared `sf` query/write helpers (`_sf_rest`).
- `scripts/sc-objects.md` — full per-object field reference (from `describe`).
- `docs/solution-design.md` — detailed design: per-script behavior, idempotency keys,
  reuse-vs-create, same-org vs cross-org. Read this before introspecting the scripts.
- `docs/site-migration-runbook.md` — the ordered runbook + gotchas.
- `docs/storeconnect-sync-user-setup-GUIDE.md` — create + connect the API-only sync user.
- `docs/content-block-and-catalog-model.md` — homepage content-block/junction model.
- `reference/` — sanitized example store (STO) + theme; the migration source template.
- `orgs/` — gitignored working dir; backups of your own orgs land here.

## Verify after a run

```bash
sf data query --target-org <org> --query "SELECT COUNT() FROM Product2"
sf data query --target-org <org> --query "SELECT COUNT() FROM s_c__Product_Category_Hierarchy__c"
```
Then open the storefront preview (`*.storeconnect.app`) — browse categories, confirm
prices + images render, open the cart — and load a POS register. Expected counts for
the bundled STO example are in the runbook (§10).
