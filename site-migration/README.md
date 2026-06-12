# StoreConnect Site Migration

Migrate a StoreConnect **store from a source org into another org** — a sandbox, a
scratch org, or another production / partner org — reproducing its catalog, content,
design, and POS so the target renders the same storefront. Driven entirely by the
Salesforce CLI (`sf`); every write step is an idempotent Python script that supports
`--dry-run`.

> Unofficial tooling — not affiliated with or supported by StoreConnect.

## What it migrates

Hierarchical product categories (+ the `Product_Category_Hierarchy` tree), products
+ PricebookEntries across all pricebooks, product media + content-block media
(imported from the source CDN URLs), pages / articles / menus, the content blocks +
the page↔block junctions and featured-products/categories associations that build
the homepage, the theme (templates + custom-template picklist values), the store
logo, store variables, and a default POS (outlet + register).

## Prerequisites

- `sf` CLI authenticated to **both** orgs (source + target).
- The **target** has the StoreConnect managed package installed (a sandbox/most orgs
  already do; a brand-new blank org needs the signup + install steps — see the
  runbook §0.1/§0.2).
- A StoreConnect **sync user** connected on the target (runbook §0.3 +
  `docs/storeconnect-sync-user-setup-GUIDE.md`) — the storefront/POS don't go live
  until this is done.
- Python 3.

## Configure

Set your source (reference) and target, then follow the runbook:

```bash
REF_ORG=<source-org-sf-alias>
REF_STORE_ID=<source-s_c__Store__c-Id>
NEW=<target-org-sf-alias>
```

The migration pulls media URLs, featured associations, and the store logo **live**
from the source org, so it must stay authenticated.

A bundled example store (**STO / Southern Trail Outfitters**) ships under
`reference/` so you can see the expected shape; replace it by capturing your own
source store with `scripts/backup-store.py` (see the runbook §1).

## Run it

Follow **`docs/site-migration-runbook.md`** end to end. Ordered steps:

| # | Step | Script |
|---|---|---|
| 1 | Stage the source store into the target's working folder | (`cp` from `reference/`) |
| 2 | Pricebooks (tier price books) | `provision-pricebooks.py` |
| 3 | Store record + theme (creates the store, sets it default) | `deploy-store.py --create-store` |
| 4 | Categories + hierarchy (+ writes `category-map.json`) | `provision-categories.py` |
| 5 | Catalog: products + PricebookEntries | `migrate-catalog.py` |
| 6 | Product media | `migrate-media.py` |
| 6b | Register custom content-block template picklist values | `provision-content-templates.py` |
| 7 | Content blocks + media + page junctions + featured assoc + logo | `deploy-store-content.py` |
| 8 | POS (anonymous-checkout contact + outlet + register) | `provision-pos.py` |
| 8b | Store-user roles (web console / website builder access) | `provision-store-user-roles.py` |

`scripts/backup-store.py` captures a source store into a local backup;
`scripts/lib.py` holds the shared `sf` query/write helpers;
`scripts/sc-objects.md` is a StoreConnect object/field reference.

## Same-org store → store copy

You can also use this to copy one store's elements onto **another store in the same
org** — set `REF_ORG` and `NEW` to the **same alias**, with different store Ids:

```bash
REF_ORG=myorg   NEW=myorg
REF_STORE_ID=<source-store-Id>          # the store to copy from
# target store: create a fresh one in Step 3 with --create-store --no-default,
# or pass an existing target store Id to deploy-store.py
```

Notes for same-org use:
- **Use `--no-default`** on `deploy-store.py` so the copy doesn't hijack the org's
  existing primary store (`deploy-store.py <src_org> <src_store_id> <dst_org>
  --create-store --no-default`).
- **No duplication:** products (matched by ProductCode/Slug), media (by Identifier),
  pricebooks (by Name), and template values are **reused** — the copy just links the
  existing records to the new store's taxonomy/menu/pages.
- **Reference (lookup) fields are still skipped** even though they'd resolve in-org
  (the scripts strip lookups for cross-org safety). Product media + the store logo
  are re-linked by the media/content steps; other org-specific lookups (e.g. product
  `Brand`/Account) would need a follow-up if you require them.

## Known caveats

- **Org-specific fields are not copied**: domain / unique domain path, and the store
  `Meta_Title` (the storefront `<title>`) — set those per target org.
- Every step is **idempotent** — safe to re-run if interrupted.

## Docs

- `docs/site-migration-runbook.md` — the full ordered runbook.
- `docs/storeconnect-sync-user-setup-GUIDE.md` — create + connect the sync user.
- `docs/content-block-and-catalog-model.md` — the content-block/junction model behind
  the homepage and how the catalog is structured.
