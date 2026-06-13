# StoreConnect Site Migration

Migrate a StoreConnect **store from a source org into another org** — a sandbox, a
scratch org, or another production / partner org — reproducing its catalog, content,
design, and POS so the target renders the same storefront. Driven entirely by the
Salesforce CLI (`sf`); every write step is an idempotent Python script that supports
`--dry-run`.

> **Same-org copies, too.** Source and target can be the **same org** — replicate a
> store into a brand-new store alongside the original (a store→store fork in one org).
> The wizard detects this and handles it automatically. See
> [Same-org store → store copy](#same-org-store--store-copy).

> Unofficial tooling — not affiliated with or supported by StoreConnect.

## What it migrates

Hierarchical product categories (+ the `Product_Category_Hierarchy` tree), products
+ PricebookEntries across all pricebooks, product media + content-block media
(imported from the source CDN URLs), pages / articles / menus, the content blocks +
the page↔block junctions and featured-products/categories associations that build
the homepage, the theme (templates + custom-template picklist values), the store
logo, store variables, and a default POS (outlet + register).

## Working with an AI assistant

This project is written to be driven by an AI coding assistant (e.g. Claude Code)
working in the repo — the docs exist so the agent can **read, not introspect**.

**Orient the agent (reading order):**

1. **`CLAUDE.md`** — the agent brief: rules, the data model, and the safe workflow.
   (Claude Code loads it automatically when you open this folder; for other tools,
   point the agent at it explicitly.)
2. **`docs/solution-design.md`** — what each script does, its idempotency key, and
   same-org vs cross-org behavior. This answers most "how does it…?" questions
   without reading code.
3. **`docs/site-migration-runbook.md`** — the ordered procedure to actually run.

**A good first prompt:**

> Read `CLAUDE.md` and `docs/solution-design.md`. I want to replicate store
> `<name/Id>` from org `<src alias>` into org `<dst alias>`. Summarize the plan and
> what will be created vs. reused, then run `scripts/replicate-store.py` in **dry
> run** first. Don't write anything to an org until I approve.

**The intended loop — read → confirm → dry-run → approve → execute → verify:**

- The agent should **rely on these docs first** and only open a specific script to
  *confirm* a detail you question — not to rediscover the whole design.
- Everything is **dry-run by default**; the agent runs `replicate-store.py` (or the
  individual steps) with `--dry-run` and shows you the plan.
- **You approve before any write.** The orchestrator also confirms each step unless
  you pass `--yes`. Nothing touches an org without `--execute`.
- After a run, the agent verifies with the queries + storefront/POS checks in the
  runbook (§10) and `solution-design.md` (§8).

If a script's behavior ever diverges from these docs, **the code is source of
truth** — ask the agent to reconcile and update the doc.

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
SOURCE_ORG=<source-org-sf-alias>
SOURCE_STORE_ID=<source-s_c__Store__c-Id>
TARGET_ORG=<target-org-sf-alias>
```

There's no **target store Id** here on purpose — the default flow **creates** the
store in Step 3 (`deploy-store.py --create-store`) and you capture its Id
(`TARGET_STORE_ID`) afterwards. Set one yourself only if you're deploying onto an
**existing** target store.

The migration pulls media URLs, featured associations, and the store logo **live**
from the source org, so it must stay authenticated.

A bundled example store (**STO / Southern Trail Outfitters**) ships under
`reference/` so you can see the expected shape; replace it by capturing your own
source store with `scripts/backup-store.py` (see the runbook §1).

## Run it

### One-command path — `replicate-store.py` (recommended)

An interactive orchestrator that **asks up front** which org + store to replicate
**from**, which org to replicate **into** (may be the same org), and the new store
name — then runs every step below in order. **Dry run by default**; nothing is
written to any org without `--execute`, and each step confirms before it runs.

```bash
python3 scripts/replicate-store.py                 # interactive, dry run (prints the plan)
python3 scripts/replicate-store.py --execute        # interactive, writes (confirms each step)
```

Non-interactive (supply the answers as flags):

```bash
python3 scripts/replicate-store.py --src-org A --src-store <id> --dst-org B \
    [--name "My Store"] [--suffix=-copy] [--no-default] [--skip-backup] [--execute] [--yes]
```

| Flag | Meaning |
|---|---|
| `--execute` | perform writes (default is dry run). |
| `--yes` | auto-confirm every step (otherwise each step prompts). |
| `--name "…"` | name of the new store (default: the source store's name, `(Copy)` appended for a same-org copy). |
| `--no-default` | don't set the new store as the org's primary (auto-on for a same-org copy). |
| `--suffix=<s>` | append `<s>` to created page/article Slugs + content-block/menu Identifiers (auto-set for a same-org copy — see below). |
| `--skip-backup` | reuse an already-captured source backup (skip step 1) for fast re-runs/dry-runs. |

When source org == target org the wizard automatically adds `--no-default` and a
`--suffix`, since a same-org copy needs both (see **Same-org store → store copy**).

### Manual path

Prefer to run the steps yourself? Follow **`docs/site-migration-runbook.md`** end to
end — the orchestrator runs exactly these, in this order:

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
org** — set `SOURCE_ORG` and `TARGET_ORG` to the **same alias**, with different store Ids:

```bash
SOURCE_ORG=myorg   TARGET_ORG=myorg
SOURCE_STORE_ID=<source-store-Id>          # the store to copy from
# target store: create a fresh one in Step 3 with --create-store --no-default,
# or pass an existing target store Id to deploy-store.py
```

The orchestrator detects a same-org copy automatically and adds the flags it needs
(`--no-default`, `--suffix`, and `--theme-suffix`); the notes below explain why.

Notes for same-org use:
- **Primary store left alone (`--no-default`).** The copy must not hijack the org's
  existing primary store (which serves the root domain). The orchestrator sets this;
  manually: `deploy-store.py <org> <src_store_id> <org> --create-store --no-default`.
- **The theme + content are made independent, so you can restyle freely.** The usual
  reason to clone a store in-org is to **modify the theme / front end** without
  touching the live store — so the copy must own them:
  - **Theme is duplicated** via **`--theme-suffix=<s>`** on `deploy-store.py`. The
    theme is matched by Name, so without a suffix the copy would *share* the source's
    theme (edits would hit both stores). The suffix gives the copy its **own** theme
    (e.g. `STO v1-rep`). The orchestrator sets it automatically for a same-org copy.
  - **Pages / articles / content blocks / menus are created fresh** via
    **`--suffix=<s>`** on `deploy-store-content.py` (appended to each Slug /
    Identifier). Required in-org because `s_c__Page__c.s_c__Slug__c` is org-wide unique
    and content blocks are org-wide (no store field) — without the suffix the copy
    would collide with, and reuse, the source's content. Categories are always
    per-store, so the taxonomy is independent either way.
- **Truly shared org-wide records are still reused** (reuse-if-present,
  create-if-absent): `Product2` (by ProductCode/Slug), `s_c__Media__c` (by
  Identifier), tier `Pricebook2` (by Name), and content-block **template picklist**
  values. The copy links these existing records into its own taxonomy/menu/pages —
  no duplicates. *(A `--duplicate` option to fork these too is a documented future
  idea — see below.)*
- **Reference (lookup) fields are still skipped** even though they'd resolve in-org
  (the scripts strip lookups for cross-org safety). Product media + the store logo
  are re-linked by the media/content steps; other org-specific lookups (e.g. product
  `Brand`/Account) would need a follow-up if you require them.

> **Possible future option — force-duplicate shared records.** Today the shared
> org-wide records above (products, media, pricebooks) are **reused**, so a same-org
> copy is a shared-catalog copy, not a full fork. A `--duplicate` option *could* be
> added to instead create independent copies of those records (suffixed
> ProductCode/Slug, media Identifier, pricebook Name — the same mechanism `--suffix`
> already uses for content), for when the new store needs a fully independent catalog.
> Not implemented yet; the current model is reuse-if-present / create-if-absent.

## Known caveats

- **Org-specific fields are not copied**: domain / unique domain path, and the store
  `Meta_Title` (the storefront `<title>`) — set those per target org.
- Every step is **idempotent** — safe to re-run if interrupted.

## Docs

- `docs/solution-design.md` — **detailed design reference**: what each script does,
  what it reads/writes, its idempotency key, and same-org vs cross-org behavior. Read
  this to understand the system without making an AI re-read all the code.
- `docs/site-migration-runbook.md` — the full ordered runbook.
- `docs/storeconnect-sync-user-setup-GUIDE.md` — create + connect the sync user.
- `docs/content-block-and-catalog-model.md` — the content-block/junction model behind
  the homepage and how the catalog is structured.
