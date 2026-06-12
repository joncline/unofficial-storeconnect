# StoreConnect Site Migration — Solution Design

A detailed design reference for the migration tooling: what each script does, what
it reads and writes, how it decides to **reuse vs. create**, and the data-model
facts behind those decisions. Read this to understand the system **without making an
AI re-introspect the code** — then, if you want, ask an AI to confirm a specific
claim here against the actual script.

- **Procedure (how to run, in order):** [`site-migration-runbook.md`](site-migration-runbook.md)
- **Field-level object reference:** [`../scripts/sc-objects.md`](../scripts/sc-objects.md)
- **Homepage content model:** [`content-block-and-catalog-model.md`](content-block-and-catalog-model.md)
- **Agent orientation:** [`../CLAUDE.md`](../CLAUDE.md)

> Scope note: behavior described here reflects the scripts in `../scripts/`. If a
> script changes, treat the code as source of truth and update this doc.

---

## 1. Goal & approach

Replicate a StoreConnect **store** — catalog, categories, media, content, theme, and
POS — from a **source org** into a **target org**, so the target renders the same
storefront. The same pipeline also copies a store into a **new store in the same
org**.

Design principles:

1. **`sf` CLI only.** Every write goes through `scripts/lib.py` → `_sf_rest`
   (`sf api request rest`). Reads use `sf data query`. No app server, no Apex.
2. **Backup → stage → deploy.** A source store is captured to a local file backup,
   that backup is staged under the *target's* working folder, and each step deploys
   from those files into the target org.
3. **Idempotent + dry-runnable.** Every step matches existing records by a natural
   key and is safe to re-run; every step supports `--dry-run`.
4. **Reuse-if-present / create-if-absent.** The core rule (see §4). Org-wide records
   that already exist are reused; per-store records are created.
5. **Cross-org safe.** Identity fields, org-specific lookups, and credentials are
   never copied (they wouldn't resolve in another org).

---

## 2. Data flow & the `category-map.json` spine

```
source org ──backup-store.py──► orgs/<src>/stores/<slug>/ , orgs/<src>/themes/<slug>/
                                          │  (staged into the target's folder)
                                          ▼
                                orgs/<dst>/stores/<slug>/ , orgs/<dst>/themes/<slug>/
   provision-categories.py ──writes──► orgs/<dst>/category-map.json
                                          │  { src_org, dst_store_id, dst_taxonomy_id,
                                          │    categories:[{name,path,src_id,dst_id}] }
                                          ▼
   migrate-catalog / migrate-media / deploy-store-content / provision-pos
        all READ category-map.json for the target store id + src org + category id-map
```

`category-map.json` is the spine: **`provision-categories.py` writes it**, and the
catalog, media, content, and POS steps read it to learn the **target store id**, the
**source org** (for live media/logo/featured pulls), and the **source→target
category id map**. This is also why those later steps take only `<dst_org>` on the
command line — everything else comes from the map.

**Local backup layout** (produced by `backup-store.py`, consumed by the deploy steps):

```
orgs/<org>/stores/<store-slug>/
  record.json                      store fields
  store-variables.json
  categories/<cat-slug>/
    record.json
    products/<product-slug>/
      record.json                  Product2 fields
      pricebook-entries.json       PBEs across all pricebooks (with Pricebook2.Name)
      product-media.json           product↔media junctions (with source media id)
  content-blocks/<identifier>/record.json
  pages/<slug>/record.json
  articles/<slug>/record.json
  menus/<identifier>/{record.json, items.json}
  content-block-pages.json         page↔block junctions (drives render_content_blocks)
orgs/<org>/themes/<theme-slug>/
  theme.md  templates/**.liquid  variables.csv  locales.md  assets.md
```

---

## 3. Step-by-step (what each script does)

Run order matches the runbook. The orchestrator `replicate-store.py` runs all of
these; you can also run them individually.

### `replicate-store.py` — orchestrator (entry point)
- **Asks up front:** source org + store, target org, new store name. Lists connected
  orgs/stores so the operator picks (or pass `--src-org/--src-store/--dst-org` etc.).
- **Safety:** **dry run by default**; `--execute` performs writes; each step confirms
  (use `--yes` to auto-confirm). `--skip-backup` reuses a staged backup.
- **Same-org detection:** if source org == target org, automatically adds
  `--no-default` (don't hijack the org primary) and `--suffix=<slug>` (independent
  content — see §5).
- **Threads the new store id:** step 3 creates the store; the orchestrator resolves
  its Id (newest store of that Name) and passes it to `provision-categories.py`.
  Everything after that reads `category-map.json`.

### 1. `backup-store.py <org> <store_id>` — capture
- Reads the live store and writes the local backup layout shown in §2 (store,
  variables, categories+hierarchy, products+PBEs+media junctions, content blocks,
  pages, articles, menus+items, page↔block junctions, theme templates/variables/
  locales/assets).
- Writes under `orgs/<org>/` (folder = `sf` alias). For a cross-org migration this
  backup is then staged into `orgs/<dst>/`; for a same-org copy it's already there.

### 2. `provision-pricebooks.py <src_org> <dst_org>` — tier pricebooks
- Mirrors every **non-standard, active `Pricebook2`** from source to target.
- **Idempotent by `Name`** (reuses if present). New ones are forced `IsActive=true`.
- **Skips** the standard pricebook (every org has one), and excludes `Id`,
  `IsStandard`, `s_c__sC_Id__c`, and `s_c__Tax_Zone_Id__c` (cross-org reference).

### 3. `deploy-store.py <backup_org> <src_store_id> <dst_org> [<dst_store_id> | --create-store]`
- Reads the staged store + theme from `orgs/<backup_org>/` (so the first arg is the
  org whose folder holds the backup — for a same-org copy that's just the org).
- **Theme:** reused if a theme of the same Name exists, else created; pushes all
  templates (upsert by key, **no `templates/` prefix or `.liquid` suffix**),
  variables, locales, assets.
- **Store variables:** copied except `GOOGLE_MAPS_API_KEY` (per-org credential).
- **Store fields:** copies all non-skipped fields. `SKIP_FIELDS` always omits
  identity/system fields, `s_c__Domain__c`/`s_c__Unique_Domain_Path__c`/
  `s_c__Meta_Title__c`, and **cross-org lookups** (theme/menu/page/content-block/
  pricebook/logo ids — these are repointed later).
- **Flags:** `--create-store` makes a new store (named from the staged record, or
  `--name="…"`). **Step 8** sets the new store as the org **primary** *by default*;
  `--no-default` skips that (required for a same-org copy so the live store keeps the
  root domain).

### 4. `provision-categories.py <src_org> <src_store_id> <dst_org> <dst_store_id>`
- **Taxonomy is per-store.** Finds the target store's taxonomy or **creates one**
  (`"<store> Taxonomy"`).
- Copies every source category (under the source taxonomy) into the target taxonomy,
  **idempotent by `Name`** within that taxonomy. There is **no parent field** — it
  also reproduces the tree by reading `s_c__Product_Category_Hierarchy__c` edges and
  recreating them (**idempotent by `(parent,child)`**).
- **Writes `category-map.json`** (the spine — see §2).

### 5. `migrate-catalog.py <dst_org> [--category NAME]` — products + PBEs + links
- For each product in the backup: **idempotent by `ProductCode`, then `s_c__Slug__c`**
  (reuses the existing `Product2` if found — this is why a same-org run shows
  `(exists)`). New products copy every **createable, non-reference** field minus
  identity/internal fields; a **future `s_c__Available_On__c` is clamped to now** so
  products aren't hidden.
- **PBEs** across all pricebooks, mapped to target pricebooks **by Name**, Standard
  entry first (Salesforce requires it). **Idempotent by `(pricebook, product)`**.
- **Category link** (`s_c__Products_Product_Categories__c`) to the new category.
  **Idempotent by `(product, category)`**.
- Reference (lookup) fields like `s_c__Brand_Id__c` are **excluded** (they fail
  cross-org with `INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY`).

### 6. `migrate-media.py <dst_org>` — product media
- **Media record** (`s_c__Media__c`): **idempotent by `s_c__Identifier__c`**
  (org-wide unique). If the identifier exists it is **reused** (no re-import); if
  absent, a new record is created with `s_c__Import_Url__c` = the source media's
  public CDN `s_c__Url__c`, and StoreConnect pulls it into the target CDN async.
- **Product↔media junction** (`s_c__Product_Media__c`): **idempotent by
  `(media, product)`** (product matched by Slug); existing links are skipped.
- Does **not** apply the content `--suffix` — media stays shared org-wide.

### 6b. `provision-content-templates.py <dst_org>` — restricted picklist values
- `s_c__Content_Block__c.s_c__Template__c` is a **restricted picklist**. Custom block
  templates (`sto-hero`, `inf-logo-block`, …) exist in the source but not a blank
  target, so creating those blocks would fail
  (`INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST`).
- Reads the templates the staged blocks reference, computes which are missing in the
  target, and **adds them via the Tooling API** (CustomField metadata value set).
  **Idempotent** (present values skipped). Run **before** step 7.

### 7. `deploy-store-content.py <dst_org> [--suffix=<s>]` — pages/menus/blocks
Creates (in dependency order), remapping references via the maps it builds:
- **Content blocks** (idempotent by `s_c__Identifier__c`) + imports each block's own
  media (by Identifier) + remaps media lookups. Blocks whose template isn't a valid
  target picklist value are **skipped** (run 6b first).
- **Featured product/category associations** (`s_c__Content_Blocks_Products__c` /
  `…_Product_Categories__c`) — products by Slug, categories via the category map.
  Without these the feature blocks render "coming soon".
- **Articles** (by Slug) and **Pages** (by Slug), each stamped with the target
  `s_c__Store_Id__c`.
- **Menus** (by Identifier) + **menu items** (by Identifier): remaps menu / category /
  article / page references, two passes so `Parent_Id` resolves, and always keeps a
  `s_c__URL__c` fallback (an item must link exactly one target).
- **Page↔block junctions** (`s_c__Content_Blocks_Pages__c`, idempotent by
  `(page, block)`) — **this is what `render_content_blocks` reads to assemble each
  page**; without it pages render empty.
- **Repoints the store**: Header/Footer menu, Head content block, Home/Terms page,
  Pricebook (→ standard), and imports + sets the store **logo** media.
- **`--suffix=<s>`** appends `<s>` to every created page/article **Slug** and
  content-block/menu/menu-item **Identifier** (and keys idempotency off the suffixed
  value). See §5.

### 8. `provision-pos.py <dst_org>` — POS
- Reads the target store id from `category-map.json`. Creates an **Anonymous Checkout
  Contact** (required by validation), **1 Outlet**, **1 Register**. Register Code is
  generated **≥ 20 chars** (validation rule). Idempotent.

### 8b. `provision-store-user-roles.py <org> [--user <username>]` — console access
- The web console / website builder need the **human login user** (the signup System
  Administrator, **not** the API-only sync user) to hold store-user roles.
- Ensures two **store-agnostic** roles (by Name) — `Admin - Console` (web console /
  viewer) and `Admin - Content` (content changes / editor) — and links the resolved
  user to each with `s_c__Store_Scope__c = 'all'`. Idempotent. Needs no store id.

---

## 4. Idempotency — the natural key per object

Every step is "reuse-if-present, create-if-absent." The key it matches on:

| Record | Natural key (idempotency) | Scope |
|---|---|---|
| `Pricebook2` (tier) | `Name` | org-wide |
| `s_c__Theme__c` | `Name` | org-wide |
| `s_c__Taxonomy__c` | `s_c__Store_Id__c` | per-store (one each) |
| `s_c__Product_Category__c` | `Name` within the taxonomy | per-store taxonomy |
| `s_c__Product_Category_Hierarchy__c` | `(parent, child)` | per tree |
| `Product2` | `ProductCode`, then `s_c__Slug__c` | org-wide |
| `PricebookEntry` | `(pricebook, product)` | — |
| `s_c__Products_Product_Categories__c` | `(product, category)` | — |
| `s_c__Media__c` | `s_c__Identifier__c` | org-wide (unique) |
| `s_c__Product_Media__c` | `(media, product)` | — |
| `s_c__Content_Block__c` | `s_c__Identifier__c` | **org-wide (no store field)** |
| `s_c__Page__c` | `s_c__Slug__c` | **org-wide (unique)** |
| `s_c__Article__c` | `s_c__Slug__c` | org-wide |
| `s_c__Menu__c` / `s_c__Menu_Item__c` | `s_c__Identifier__c` | — |
| `s_c__Content_Blocks_Pages__c` | `(page, block)` | — |

The bolded rows are the reason a same-org copy needs `--suffix` (§5).

---

## 5. Same-org copy vs. cross-org migration

The same pipeline does both. **Same-org** (source org == target org) differs in two
ways, which the orchestrator sets automatically:

- **`--no-default`** (on `deploy-store.py`): the copy must not seize the org's
  primary-store flag — that store serves the root domain. The live store stays
  primary; the copy gets its own auto-provisioned `*.storeconnect.app` domain.
- **`--suffix=<s>`** (on `deploy-store-content.py`): because **page `Slug` is org-wide
  unique** and **content blocks are org-wide (no store field)**, the copy can't reuse
  those keys without colliding with — and reusing — the source's content. The suffix
  makes the page/article Slug and block/menu/item Identifier *absent* in the target,
  so they're created as **independent** copies for the new store.

What is **reused** vs **created** in a same-org copy:

| Reused (shared org-wide) | Created fresh (per-store) |
|---|---|
| `Product2` (by ProductCode/Slug) | the store **record** |
| `s_c__Media__c` (by Identifier) | `s_c__Taxonomy__c` + categories + hierarchy |
| tier `Pricebook2` (by Name) | Pages / articles (suffixed Slug) |
| `s_c__Theme__c` (by Name) | Content blocks / menus / items (suffixed Identifier) |
| `s_c__Template__c` picklist values | |

> **Theme is reused, not duplicated, in a same-org copy.** `deploy-store.py` matches
> the theme by **Name**, and a fresh backup captures the source theme's real name —
> so the copy **shares** the source store's theme (verified: an in-org clone pointed
> at the same `s_c__Theme__c` Id). Editing one store's theme then affects both. For an
> independent theme, give the deployed theme a distinct name (rename the staged
> `theme.md` title before Step 3). This is the same reuse-by-key behavior as products/
> media/pricebooks — only content (via `--suffix`) and the per-store taxonomy are
> forced independent.

> **Possible future option — force-duplicate shared records.** Today a same-org copy
> is a **shared-catalog** copy (products/media/pricebooks reused). A `--duplicate`
> option *could* create independent copies of those too (suffixed ProductCode/Slug,
> media Identifier, pricebook Name — the same mechanism `--suffix` uses for content),
> for a fully independent fork. **Not implemented.** The current model is
> reuse-if-present / create-if-absent.

For a **cross-org** migration into a blank target, none of the org-wide records exist
yet, so everything is created (no suffix needed; `--no-default` omitted so the
deployed store becomes that org's primary).

---

## 6. Cross-org safety & what is never copied

- **Identity / system fields** — `Id`, audit fields, `s_c__Domain__c`,
  `s_c__Unique_Domain_Path__c`, `s_c__Meta_Title__c` (storefront `<title>`),
  `s_c__sC_Id__c`, `Content_Key_External_Id__c`.
- **Cross-org lookups** — any `*_Id__c` pointing at a record in another org fails
  insert (`INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY`). The catalog step strips
  all reference fields; store-level lookups (theme/menu/page/block/pricebook/logo) are
  **repointed** after their targets are created. Product `Brand` (Account) is left for
  manual assignment.
- **Credentials** — `GOOGLE_MAPS_API_KEY` and similar are skipped; set per target org.

---

## 7. Platform constraints to know

- **Theme compiles on console publish, not via API.** Pushing templates/variables
  stages them, but the storefront's compiled CSS regenerates only on publish in the
  StoreConnect console.
- **Theme assets** (CSS/JS/image files) can't be created via API — upload via the UI
  (or stage as ContentVersion → public URL → media import).
- **Media import is async.** `s_c__Import_Url__c` is fetched by StoreConnect after
  create; `s_c__Url__c` (the target CDN URL) is written back a little later.
- **`s_c__Available_On__c` future-date trap.** A future value hides products from the
  storefront; the catalog step clamps future values to now on create.
- **Restricted picklist** `s_c__Template__c` must be extended in the target before
  custom-template blocks can be created (step 6b).
- **Sync user.** A target org's storefront/POS don't go live until an API-only
  StoreConnect sync user is connected — see
  [`storeconnect-sync-user-setup-GUIDE.md`](storeconnect-sync-user-setup-GUIDE.md).

---

## 8. Verify a run

```bash
sf data query --target-org <org> --query "SELECT COUNT() FROM Product2"
sf data query --target-org <org> --query "SELECT COUNT() FROM s_c__Product_Category_Hierarchy__c"
sf data query --target-org <org> --query "SELECT COUNT() FROM s_c__Content_Blocks_Pages__c"
```

Then open the storefront preview (`*.storeconnect.app`) — browse categories, confirm
prices + images, open the cart — and load a POS register. Expected counts for the
bundled STO example are in the runbook (§10).
