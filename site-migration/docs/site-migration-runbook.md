# StoreConnect Site Migration — Runbook

Migrate an existing StoreConnect **store from a source org into another org** — a
sandbox, a scratch org, or another org — reproducing its catalog, content, design,
and POS so the target renders the same storefront. Every step is an idempotent
script that supports `--dry-run`.

**The typical case:** you already have a working store in a **source org** and want
to replicate it into a **target org**. Point the runbook at your source (`SOURCE_ORG` +
`SOURCE_STORE_ID`) and your target (`TARGET_ORG`), capture the source store once with
`scripts/backup-store.py`, then run the ordered steps.

This package ships with the **STO / Southern Trail Outfitters** store as a worked
example template (`reference/stores/sto/` + `reference/themes/sto-v1/`) so you can
see the expected shape — replace it by capturing your own source store (see
**Configure**). A migrated store carries: hierarchical categories, products +
PricebookEntries across all pricebooks, product + content-block media, pages,
articles, menu(s), the content blocks + page junctions + featured-products /
featured-categories associations that build the homepage, the theme, the store logo,
and POS.

> The bundled STO example also carries an "Using AI to Build & Migrate StoreConnect Sites" demo page (+
> articles and content block) — optional, safe to leave in or remove.

## Automated path (orchestrator)

`scripts/replicate-store.py` runs every step in this runbook in order, prompting
**up front** for source org + store, target org, and the new store name. It is
**dry run by default** and writes nothing without `--execute` (and confirms each
step). It auto-detects a same-org copy and adds `--no-default`, `--suffix`, and
`--theme-suffix` (independent primary-flag handling, content, and theme).

```bash
python3 scripts/replicate-store.py            # interactive, dry run
python3 scripts/replicate-store.py --execute   # interactive, writes
```

Use `--skip-backup` to reuse an already-captured backup on re-runs. The sections
below document each step the orchestrator runs (and the manual commands if you
prefer to drive them yourself).

## Configure

Set these for **your** source org and each target org. The source org must be
authenticated to `sf` — the migration pulls media URLs, featured associations, and
the store logo **live** from it (not just from the bundled backup).

```bash
SOURCE_ORG=<your-source-org-alias>
```

```bash
SOURCE_STORE_ID=<source-s_c__Store__c-Id>
```

```bash
TARGET_ORG=<target-org-alias>
```

> **No target store Id needed up front.** The default flow **creates** the store in
> Step 3 (`deploy-store.py --create-store`) and you capture its Id as
> `$TARGET_STORE_ID` then. Only set `TARGET_STORE_ID` yourself if you're deploying
> onto an **existing** target store (pass it to `deploy-store.py` in place of
> `--create-store`).

> **Using a different reference store?** Re-capture it with
> `python3 scripts/backup-store.py $SOURCE_ORG $SOURCE_STORE_ID`, then move the produced
> `orgs/$SOURCE_ORG/stores/<slug>` + `orgs/$SOURCE_ORG/themes/<slug>` into
> `reference/stores/sto` + `reference/themes/sto-v1` (or adjust Step 1 paths). Run
> all scripts from the project root.

---

## 0. Prerequisites

- This project checked out locally; **run all scripts from the project root**.
- Both orgs authenticated to `sf` with aliases: the **source** (`$SOURCE_ORG`, see
  **Configure**) and the **target** (`$TARGET_ORG`).
- The target already has the **StoreConnect managed package** installed. A
  **sandbox** (copy of a prod that has it) or an org you've installed it into is
  ready as-is. A **blank** org or a **scratch** org needs the package first — see 0.1
  (or put it in the scratch definition).
- For the sync user (0.2), the "Salesforce Integration" license must have free seats
  (5 ship free).
- Read-only `sf data query` is used freely; every write step is a script or
  command you run yourself (dry-run first).

> **0.1 below is only needed if the target org doesn't have StoreConnect yet.** A
> sandbox (copy of a prod that has it) or an existing StoreConnect org is ready
> as-is — skip to **0.2** (sync user), or straight to **Step 1** if the sync user
> already exists. A scratch org needs the package in its scratch definition or
> installed per 0.1.

### 0.1 Install the StoreConnect managed package (if the target lacks it)

If the target org doesn't already have StoreConnect, install it before migrating —
the namespace objects (`s_c__Store__c`, etc.) don't exist until the managed package
is installed. Install the **same version your source org runs** so the migrated data
lines up (StoreConnect eCommerce, namespace `s_c`). Find that version + its package
version Id (`04t…`) by listing the package on the **source** org:

```bash
sf package installed list --target-org $SOURCE_ORG
```

Install it into the target org (takes several minutes — `--wait` polls to completion):

```bash
sf package install --package <04t...PackageVersionId> --target-org $TARGET_ORG --wait 30 --no-prompt
```

Verify the namespace now resolves (the query succeeding — not erroring with
"sObject type 's_c__Store__c' is not supported" — confirms the install; the count
itself will be 0 until Step 3 creates the STO store):

```bash
sf data query --target-org $TARGET_ORG --query "SELECT COUNT() FROM s_c__Store__c"
```

### 0.2 Create the API-only StoreConnect sync user (required)

A freshly provisioned org has the package but is **not yet connected to the
StoreConnect web service** — the storefront and POS will not work until an
**API-only StoreConnect sync user** exists and is connected in the StoreConnect
console. Provision it **before Step 1** so the store/catalog you deploy actually
syncs. Follow the dedicated runbook end to end: **`docs/storeconnect-sync-user-setup-GUIDE.md`**.

- **Part A (CLI, automatable):** query *this org's* Profile / permission-set / PSL
  IDs (never reuse another org's IDs — they're org-specific), create the user on the
  *Salesforce API Only System Integrations* profile, then assign the *Salesforce API
  Integration* PSL + both *StoreConnect Sync* permission sets.
- **Part B (browser, manual):** tick **View All Data** on the Standard perm set
  (the CLI rejects it), set the password, clear the first-login OTP, then finish
  connecting the sync user in the StoreConnect console.

Step 3 creates a new store in the target (via `deploy-store.py --create-store`) and,
by default, sets it as the target org's default store. You'll capture its Id as
`$TARGET_STORE_ID` after Step 3 and use it for every later step. `$SOURCE_STORE_ID` (your source
store) is used as `<src_store_id>` in the commands below.

---

## 1. Stage the source store into the target's working folder

The catalog/media/content scripts read the source store backup from
`orgs/<TARGET_ORG>/stores/...` and the theme from `orgs/<TARGET_ORG>/themes/...`. Copy the
**reference template** (the bundled STO example, or your own captured source store —
see Configure) into the target org's working folder:

```bash
mkdir -p orgs/$TARGET_ORG/themes orgs/$TARGET_ORG/stores
```

```bash
cp -r reference/themes/sto-v1 orgs/$TARGET_ORG/themes/sto-v1
```

```bash
cp -r reference/stores/sto orgs/$TARGET_ORG/stores/sto
```

> Migrating your **own** source store (not the bundled STO)? First capture it with
> `python3 scripts/backup-store.py $SOURCE_ORG $SOURCE_STORE_ID` (writes under
> `orgs/$SOURCE_ORG/`), then either refresh `reference/` from that output or stage
> directly from `orgs/$SOURCE_ORG/stores/<slug>` into `orgs/$TARGET_ORG/`.

---

## 2. Pricebooks  (`provision-pricebooks.py`)

Mirror the 5 non-standard tier pricebooks (Bronze/Gold/Hidden/Silver/Wholesale)
from the reference org. Standard already exists in every org.

```bash
python3 scripts/provision-pricebooks.py $SOURCE_ORG $TARGET_ORG --dry-run
```

```bash
python3 scripts/provision-pricebooks.py $SOURCE_ORG $TARGET_ORG
```

## 3. Store record + theme  (`deploy-store.py --create-store`)

Create a new **STO** store record and deploy the store fields + STO v1 theme onto
it. Source org = the new org (we read the staged backup co-located under
`orgs/$TARGET_ORG/`). `--create-store` makes a brand-new store named from the staged
record ("STO"); the process is the same for the org's first or Nth store. Because
the reference STO store is the default, the deploy **sets the new STO store as the
org's default/Primary store** (StoreConnect unsets any prior default), so the org
domain root serves STO.

```bash
python3 scripts/deploy-store.py $TARGET_ORG $SOURCE_STORE_ID $TARGET_ORG --create-store --dry-run
```

```bash
python3 scripts/deploy-store.py $TARGET_ORG $SOURCE_STORE_ID $TARGET_ORG --create-store
```

The live run prints `+ created store 'STO'  (<id>)`. Capture that Id as `$TARGET_STORE_ID`
for the remaining steps:

```bash
TARGET_STORE_ID=$(sf data query --target-org "$TARGET_ORG" --query "SELECT Id FROM s_c__Store__c WHERE Name = 'STO' ORDER BY CreatedDate DESC LIMIT 1" --json | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['records'][0]['Id'])")
echo "$TARGET_STORE_ID"
```

- Creates the store named **"STO"** (Name is deployed from the staged record) and
  **sets it as the org's default store**, a fresh theme named **"STO v1"**, pushes the
  9 templates (6 custom block templates `templates/blocks/sto-*.liquid` — sto-hero
  / sto-promo / sto-featured-products / sto-featured-categories / sto-newsletter /
  sto-split-content — plus snippets header / footer / products-card), locale, and
  store variables.
- **Skips `GOOGLE_MAPS_API_KEY`** (org-specific credential — set per org later).
- A brand-new store gets its own auto-provisioned domain; set
  `s_c__Unique_Domain_Path__c` later for a friendly path (Manual steps).
- **Same-org store→store copy:** add **`--no-default`** (so the new store does NOT
  become the org's primary / hijack the existing default) **and `--theme-suffix=<s>`**
  (so the copy gets its **own** theme instead of sharing the source's — the theme is
  matched by Name, and an in-org clone is usually for editing the theme / front end):
  `python3 scripts/deploy-store.py $TARGET_ORG $SOURCE_STORE_ID $TARGET_ORG --create-store --no-default --theme-suffix=-copy`.
  (The orchestrator sets both automatically; in Step 7 use the same value for `--suffix`.)

## 4. Categories + hierarchy + id-map  (`provision-categories.py`)

Copy the 20 categories into the new store's taxonomy, **reproduce the category
tree**, and emit `orgs/$TARGET_ORG/category-map.json` (consumed by the next steps).

There is **no parent field** on `s_c__Product_Category__c`. The tree lives in
`s_c__Product_Category_Hierarchy__c` (one row per parent→child edge). The script
reads the **16 source edges** and recreates them (idempotent). The 4 root
categories are "STO - AU - 1 - Demographic", "2 - Clothing", "3 - Gear", and
"4 - Technology". So this step creates **20 categories + 16 hierarchy edges**.

```bash
python3 scripts/provision-categories.py $SOURCE_ORG $SOURCE_STORE_ID $TARGET_ORG $TARGET_STORE_ID --dry-run
```

```bash
python3 scripts/provision-categories.py $SOURCE_ORG $SOURCE_STORE_ID $TARGET_ORG $TARGET_STORE_ID
```

## 5. Catalog: products + PBEs  (`migrate-catalog.py`)

Faithfully migrate the products across the 20 categories with real prices across
all 6 pricebooks + category links.

```bash
python3 scripts/migrate-catalog.py $TARGET_ORG --category Clothing --dry-run   # pilot one
```

```bash
python3 scripts/migrate-catalog.py $TARGET_ORG --category Clothing             # pilot live
```

```bash
python3 scripts/migrate-catalog.py $TARGET_ORG                                 # full catalog
```

Runs minutes (many `sf` calls). Idempotent — safe to re-run if interrupted.

## 6. Media  (`migrate-media.py`)

Import product media (from each source media's public CDN URL → target CDN) +
product-media links.

```bash
python3 scripts/migrate-media.py $TARGET_ORG --dry-run
```

```bash
python3 scripts/migrate-media.py $TARGET_ORG
```

## 6b. Content-block template picklist values  (`provision-content-templates.py`)

`s_c__Content_Block__c.s_c__Template__c` is a **restricted** picklist. The custom
theme block templates the design uses (`sto-hero`, `sto-promo`,
`sto-featured-products`, `sto-featured-categories`, `sto-newsletter`,
`sto-split-content`, `inf-logo-block`) exist in the source org but NOT in a blank
target, so Step 7 would fail with `INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST`. This
step adds the missing values (those the staged blocks reference) to the picklist
via the Tooling API. **Run it before Step 7.**

```bash
python3 scripts/provision-content-templates.py $TARGET_ORG --dry-run
```

```bash
python3 scripts/provision-content-templates.py $TARGET_ORG
```

## 7. Store content: pages/menus/articles/content-blocks  (`deploy-store-content.py`)

Create content-blocks, articles, pages, the menu + items (category/article/page
refs remapped), and repoint the store's Header/Footer menu, Head content block,
Home/Terms page, and Pricebook. This step now also:

- **imports each content block's OWN media** (Image / Media / File / Video /
  Document → `s_c__Media__c`) from the source CDN URL, idempotent by Identifier
  (this is separate from the product media in Step 6 — 3 content-block media);
- creates the **10 content blocks** with their media lookups remapped (skips any
  whose template isn't a valid picklist value — see Step 6b);
- creates the **`s_c__Content_Blocks_Pages__c` junctions** (internally step "5b")
  from `content-block-pages.json`, remapping Page_Id + Content_Block_Id and
  preserving Position / Usage_Type. This junction is what `render_content_blocks`
  reads to assemble each page (e.g. STO Home = 8 ordered blocks, hero @10 →
  logos @90);
- creates the **featured-products / featured-categories associations** (step "1b":
  `s_c__Content_Blocks_Products__c` + `s_c__Content_Blocks_Product_Categories__c`)
  that populate the homepage "New Season Picks" (8 products) and "Shop By Category"
  (5 categories) blocks. WITHOUT these the blocks render "coming soon" even though
  the catalog is present;
- imports the **store logo** media (`s_c__Logo_Id__c` / `s_c__Email_Logo_Id__c`)
  from the source CDN URL and sets it on the store (a cross-org lookup skipped by
  Step 3), so the storefront logo appears.

```bash
python3 scripts/deploy-store-content.py $TARGET_ORG --dry-run
```

```bash
python3 scripts/deploy-store-content.py $TARGET_ORG
```

> **Same-org copy:** add **`--suffix=<s>`** (e.g. `--suffix=-copy`). It appends
> `<s>` to every created page/article **Slug** and content-block/menu/menu-item
> **Identifier**. This is REQUIRED in-org: `s_c__Page__c.s_c__Slug__c` is org-wide
> unique and content blocks are org-wide (no store field), so without a suffix the
> new store would collide with — and reuse — the source store's content instead of
> getting independent copies. Leave it unset for a cross-org deploy into a blank
> target. (The orchestrator sets this automatically for a same-org copy.)

## 8. POS  (`provision-pos.py`)

Provision an Anonymous Checkout contact + 1 Outlet + 1 Register.

```bash
python3 scripts/provision-pos.py $TARGET_ORG --dry-run
```

```bash
python3 scripts/provision-pos.py $TARGET_ORG
```

## 8b. Store-user roles — web console / website builder access  (`provision-store-user-roles.py`)

The StoreConnect **web console** and **website builder** require the **human login
user** (the System Administrator created when the org was signed up — **not** the
API-only sync user) to hold store-user roles. Without them the console/builder
won't open for that user. This step ensures two store-agnostic roles
(`s_c__Store_Scope__c = all`, no store link), matching the reference org:

- **Admin - Console** — `s_c__Store_Role__c` type `web console`, level `viewer`
- **Admin - Content** — `s_c__Store_Role__c` type `content changes`, level `editor`

It creates each `s_c__Store_Role__c` if missing, resolves the target user (the
initial active System Administrator, or `--user <username>`), and links the user to
each role. Roles are store-agnostic, so this can run any time after the org admin
exists.

```bash
python3 scripts/provision-store-user-roles.py $TARGET_ORG --dry-run
```

```bash
python3 scripts/provision-store-user-roles.py $TARGET_ORG
```

---

## 9. Manual / post-provisioning steps (NOT scripted)

- **`s_c__Available_On__c` (handled automatically)**: a **future** `Available_On`
  would hide products from the storefront. `migrate-catalog.py` (Step 5) now
  clamps any future value to "now" on create, so products are visible
  immediately; past values are kept as-is. No manual fix needed — just confirm on
  the storefront.
- **Theme assets**: theme assets cannot be created via API — if the theme has
  CSS/JS/image assets, those must be uploaded via the StoreConnect UI (or staged
  as ContentVersion → public URL → media import).
- **Google Maps API key**: set `GOOGLE_MAPS_API_KEY` store variable to the target
  org's own key (deliberately not copied).
- **Product brands**: `s_c__Brand_Id__c` (lookup to Account) is not migrated
  (cross-org). Create brand Accounts and assign if the storefront needs them.
- **Domain path**: set the store's `s_c__Unique_Domain_Path__c` for a friendly URL.
- **Pricebook tiers → customers**: tier pricebooks exist but assigning customers to
  tiers is a per-org/runtime task.
- **Course demo (optional)**: the "Using AI to Build & Migrate StoreConnect Sites" page / articles /
  content block are a separate course demo and can be omitted for a pure retail
  storefront.

## 10. Verify

```bash
sf data query --target-org $TARGET_ORG --query "SELECT COUNT() FROM Product2"
```

```bash
sf data query --target-org $TARGET_ORG --query "SELECT COUNT() FROM s_c__Product_Media__c"
```

```bash
sf data query --target-org $TARGET_ORG --query "SELECT COUNT() FROM s_c__Product_Category_Hierarchy__c"
```

Expected counts (approximate where exact figures aren't certain):

- Pricebooks: 6
- Our categories: ≈ 20  +  hierarchy edges: ≈ 16
- Products + PBEs across the 6 pricebooks, plus product media + 3 content-block media
- Pages: 4   (STO Home, STO About, STO Contact, + optional "Using AI to Build & Migrate StoreConnect Sites")
- Articles: ≈ 6
- Menu: 1  /  items: 19   ("STO - AU - Main Menu")
- Content blocks: 10  /  page junctions: 9
- Outlet: 1  /  register: 1

- Open the storefront preview URL (org `*.storeconnect.app`) — browse categories,
  confirm prices + images render, open the cart. (Products' `Available_On` is
  auto-clamped to "now" by Step 5, so they should be visible immediately.)
- Open a POS register and confirm it loads with the catalog.

---

## Gotchas learned (org #1)

- **Category hierarchy is a separate object**, not a parent field. The tree lives
  in `s_c__Product_Category_Hierarchy__c` (one row per parent→child edge);
  `provision-categories.py` recreates the 16 edges (Step 4).
- **Content-block media + page↔block junctions are reproduced by the content
  step.** `deploy-store-content.py` imports each content block's own media and
  creates the `s_c__Content_Blocks_Pages__c` junctions — without the junctions,
  pages render empty (Step 7).
- **`Available_On` future-date trap (auto-handled)**: a future
  `s_c__Available_On__c` hides products from the storefront; `migrate-catalog.py`
  clamps future values to "now" on create (Step 5), so no manual backdate is
  needed.
- **Store creation / naming / default.** `deploy-store.py --create-store` makes a
  new store named "STO" (deploys the `Name` rather than skipping it) and **sets it
  as the org's default** (`s_c__Default__c`, matching the reference; StoreConnect
  unsets any prior default). Org-specific fields are NOT copied: `s_c__Domain__c`,
  `s_c__Unique_Domain_Path__c`, and `s_c__Meta_Title__c` (the storefront `<title>`,
  e.g. "Acme/…" — set per org). The store **logo** (`s_c__Logo_Id__c`) is a
  cross-org media lookup imported + set by Step 7, not Step 3.
- **Cross-org reference fields fail on insert** (`INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY`).
  `migrate-catalog.py` excludes all lookup fields; brand/media are handled
  separately. Watch for this on any new object.
- **Outlet validation rules**: an **Anonymous Checkout Contact is required**, and
  **Register Code must be ≥ 20 chars** — both handled by `provision-pos.py`.
- **Menu items** don't store their `s_c__Menu_Id__c` in the backup — the owning
  menu is inferred from the backup folder.
- **Idempotency**: every script matches existing records (by Name/Slug/Identifier/
  ProductCode) and is safe to re-run.
- **Folder naming**: org backup folders match the `sf` alias (`backup-store.py`
  writes by alias).
