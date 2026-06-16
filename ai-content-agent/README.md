# StoreConnect AI Content Agent

A safe, scoped path for letting an **AI agent edit your StoreConnect content** —
products' marketing copy, page/article tags, traits & variants, and POS layouts —
**without** giving it the keys to pricing, orders, customers, or org configuration.

The pattern: a dedicated **API-only Salesforce user**, on the free *Salesforce
Integration* license, holding only content-scoped permissions. Your AI agent (Claude
Code, a custom Agentforce/SDK bot, a script — anything that drives the `sf` CLI or the
Salesforce REST API) authenticates **as that user**, so Salesforce itself enforces the
boundary. The agent literally *cannot* change a price or read a customer record,
regardless of what it's prompted to do.

> Unofficial tooling — not affiliated with or supported by StoreConnect.

## Why this instead of admin credentials

Pointing an agent at an admin (or the StoreConnect Sync user) means a prompt injection,
a hallucinated bulk update, or a buggy loop can touch *anything* — orders, payments,
customer PII, pricebooks. Scoping the agent to a purpose-built user turns "please be
careful" into a permission boundary the platform enforces:

- **Least privilege.** Content CRUD + Product2 *content* fields only. No pricing
  (PricebookEntry), no Orders, no Accounts/Contacts, no Setup.
- **No interactive login.** API-only profile — the user can drive the API but is
  **blocked from the Salesforce UI** ("Access Restricted for API Only Users").
- **Free.** Uses a *Salesforce Integration* license (5 ship free with every org).
- **Auditable.** Every change is stamped with the agent user, separate from humans.

This is the same hardening StoreConnect applies to its own **Sync user**, aimed at an
AI content role.

## The scope (what the agent can touch)

Permissions come from three layers — two **packaged** StoreConnect sets plus one
**custom** set in this repo:

| Layer | Grants |
|---|---|
| StoreConnect **Content Manager** (packaged) | Articles, Pages, Menus, Content Blocks, Media — the core CMS objects |
| StoreConnect **Theme Manager** (packaged) | Themes, theme templates, locale translations |
| **SC Agent CMS Extras** (this repo) | the gaps a content-focused product manager hits — see below |

**`SC_Agent_CMS_Extras`** (`salesforce/permissionsets/`) adds:

- **Full CRUD** on POS layout/view config — `Pos_View`, `Pos_Layout`,
  `Pos_Layout_Field`, `Pos_Layout_Filter`, `Pos_Action_Group`, `Pos_Action_Item`,
  `Pos_Print_Template`.
- **Full CRUD** on page/article tags — `Article_Tag`, `Page_Tag`.
- **Full CRUD** on the traits/variants family — `Trait`, `Trait_Type`, `Trait_Value`,
  `Trait_Category`, `Product_Trait_Template`, `Product_Trait_Template_Item`,
  `Product_Variant`.
- **Read + Edit on `Product2` — content fields only** (display name, slug, all the
  Markdown body/description fields, meta/SEO fields, search keywords, condition,
  position, social image, available/discontinue dates, trait-template link).
  **No Create, no Delete**, and **no pricing/inventory fields** — pricing lives on
  PricebookEntry, which the agent can't see at all.

### Deliberately excluded

- **Pricing & inventory** — PricebookEntry, prices, stock. Not granted anywhere.
- **Orders, Carts, Payments, Customers/Accounts/Contacts** — no access.
- **Brands.** StoreConnect brands are `Account` records; granting them would expose
  customer data. `Product2.s_c__Brand_Id__c` stays writable, but brand *records* are
  not readable. Add a separate, narrow grant if you truly need brand management.

Want a different agent persona (catalog/merchandising, pricing, inventory,
order/fulfilment, full admin)? This same three-layer recipe applies — swap the packaged
sets and tailor the custom set. This repo ships the **content** role as the reference.

## Working with an AI assistant

This component is written to be driven by an AI coding assistant working in the repo.
Two reading paths:

- **Setting up the agent user** — start here in `README.md`. A good first prompt:

  > Read `ai-content-agent/README.md`. I want to set up a scoped content agent in org
  > `<ALIAS>`. Walk me through deploying the permission set and running
  > `provision-content-agent.py` in `--dry-run` first; don't write to the org until I
  > approve.

- **Acting as the content agent** (doing content work once provisioned) — read
  [`CLAUDE.md`](CLAUDE.md): the content data model, object relationships, the hard
  scope boundary, and the safe-edit workflow, so the agent works from documented model
  knowledge rather than introspecting the org.

## Requirements

- **The StoreConnect managed package must be installed in the target org.** This is a
  StoreConnect-specific role — the permission set references StoreConnect (`s_c__`)
  objects and fields, and it assigns the packaged Content Manager + Theme Manager sets.
  Without StoreConnect installed it will not deploy or assign.
- The `sf` CLI authenticated to the target org **as an admin**
  (`sf org login web -a <ALIAS>`).
- A free *Salesforce Integration* license seat (`SELECT TotalLicenses, UsedLicenses
  FROM UserLicense WHERE Name = 'Salesforce Integration'` — 5 ship free per org).

## Setup

### 1. Deploy the permission set

```
sf project deploy start -o <ALIAS> --source-dir salesforce/permissionsets --manifest salesforce/package.xml
```

### 2. Provision the user + assignments

Dry-run first to see the plan, then run it for real:

```
python3 scripts/provision-content-agent.py <ALIAS> --username content-agent@yourorg.example.com --email ops@example.com --dry-run
```

```
python3 scripts/provision-content-agent.py <ALIAS> --username content-agent@yourorg.example.com --email ops@example.com --set-password 'S0meStr0ng!Passphrase'
```

The script verifies a free license seat, resolves the API-only profile, confirms the
permission set is deployed, creates the user, and assigns the PSL + Content Manager +
Theme Manager + SC Agent CMS Extras. It's idempotent — safe to re-run. (Username must be
globally unique across all Salesforce orgs, like any Salesforce username.)

### 3. Connect the agent — pick an auth flow

The user is provisioned; next, set up your agent so its API calls run as this user. Two
flows work — choose based on how the agent runs:

**Option A — web login (refresh-token backed).** Best for a long-running agent driving
the `sf` CLI: the refresh token persists across restarts, no re-minting.

```
sf org login web -a <ALIAS>-content-agent
```

Log in once in the browser as the content-agent user (the `--set-password` from step 2,
or a Setup → Users password reset). Salesforce will then show **"Access Restricted for
API Only Users"** — expected and correct: the page appears *after* the `sf` CLI has
already captured the refresh-token-backed credentials. The UI is blocked; the API
session persists. Point your agent at the `<ALIAS>-content-agent` alias.

**Option B — External Client App + OAuth Client Credentials.** Best for headless,
server-to-server agents with no browser or password: create an External Client App
(Setup → External Client Apps), enable the Client Credentials flow, and set its *run-as*
user to the content agent. The app's own key/secret mint access tokens, and the calls
execute as the content-agent user. Note the token is **short-lived with no refresh
token**, so the agent re-mints on each cycle/expiry — fine for a service that already
manages its own token loop.

Either way the *permission boundary is identical* — it's enforced on the user, not the
auth flow.

### 4. Verify the boundary

Acting as the agent, confirm it can read its content scope and is denied everything
else:

```
sf data query -o <ALIAS>-content-agent -q "SELECT Id, Name FROM Product2 LIMIT 1"
```

```
sf data query -o <ALIAS>-content-agent -q "SELECT Id FROM Order LIMIT 1"
```

The Product2 read should succeed; the Order query should fail with
`INVALID_TYPE` / insufficient access. A `Product2` **insert** should also be denied
(read/edit only, no create), and any write to a pricing field should fail.

## Files

```
ai-content-agent/
  README.md                                      setup + runbook (this file)
  CLAUDE.md                                      agent brief: content data model + boundary
  salesforce/
    package.xml                                  deploy manifest
    permissionsets/
      SC_Agent_CMS_Extras.permissionset-meta.xml the custom content scope
  scripts/
    provision-content-agent.py                   idempotent user provisioner (--dry-run)
```
