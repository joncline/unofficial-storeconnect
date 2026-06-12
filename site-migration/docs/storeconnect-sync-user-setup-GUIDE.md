# Create a StoreConnect Sync User (AI-assisted runbook)

A repeatable guide for provisioning a StoreConnect sync user in any org. Source
article (human):
<https://support.storeconnect.com/articles/how-to-create-a-storeconnect-sync-user>
— **agents:** fetch the clean-markdown version by appending `.md`:
<https://support.storeconnect.com/articles/how-to-create-a-storeconnect-sync-user.md>

The runbook is split into two parts:

- **Part A — Automated.** An AI assistant runs these via the Salesforce CLI
  (`sf`). Each step has a description above the command(s).
- **Part B — Interactive.** A human does these in the browser — they **cannot** be
  done from the CLI (the *View All Data* checkbox and the password / OTP login).

Do Part A first, then Part B.

---
---

# Agent playbook (automation summary)

For an AI agent driving this end-to-end. The whole of **Part A is automatable** via
`sf` / REST — including setting the password; only **two browser steps in Part B**
are not. Order matters and every step is idempotent. This is the strategy only —
exact field names, filters, endpoints, and commands live in Parts A/B below; use
those, don't hardcode values from another org.

**Preconditions**
- The target org alias is authenticated to `sf` (confirm with `sf org display`).
- The StoreConnect managed package is installed — the sync permission sets and
  license don't exist until it is. If the perm-set lookups in A1 come back empty,
  install the package first, then retry.

**Part A — automatable (CLI / REST)**
1. **Find the org's own Ids** (A1, read-only): Profile, the two perm sets, and the
   PSL — never reuse another org's. Match the integration Profile by its **user
   license** (`Salesforce Integration`), not its display name (which varies by org
   version).
2. **Create the user** (A2) on the API-only profile. API creation sets **no
   password and sends no email**. Username and Email must both be email-format; the
   Email must be a real inbox you control.
3. **Assign access** (A3): the permission-set **license first**, then both
   permission sets (`StoreConnect Sync Standard Permission` + `StoreConnect Sync
   User Permission`) — the license must precede the perm sets.
4. **Set the password via REST `setPassword`** (B2-preferred — runnable here, no
   email): POST the password to the user's `password` sub-resource. Avoids the
   Reset-Password email + org email-Deliverability dependency and **skips the
   emailed device-verification OTP** — but it's the **initial/temporary** credential;
   the user still resets it on first login (Part B). Verify `LastPasswordChangeDate`,
   then record it.

**Part B — human-only (browser; no API exists)**
1. Enable **View All Data** on the **Standard** sync perm set (`storeConnect_Sync_standard`,
   local/unmanaged) in Setup — a CLI update is rejected (`FIELD_INTEGRITY_EXCEPTION`)
   because it cascades many dependent permissions.
2. **Clear the first-login challenge** in the browser: with the API-set password the
   user lands on a **"Set New Password"** screen (no OTP/email wait); the email-reset
   path instead hits a **device-verification OTP**. (The **security question** is a
   separate item — not settable via any API; complete it once in the browser or relax
   it via org password/session policy.) Then **connect the user in the StoreConnect
   console**.

> A fully zero-touch connection would require OAuth (a Connected App + JWT) instead
> of username/password — bigger setup, usually not worth it.

---
---

# Part A — Automated setup (AI + Salesforce CLI)

> **AI:** confirm the org alias first, then run the read-only queries in A1 to
> fetch this org's record IDs. **Never reuse IDs from another org** — Profile /
> PermissionSet / PermissionSetLicense IDs are org-specific.

## A0. Prerequisites & decisions

- `sf` CLI authenticated to the target org with an alias (e.g. `sc-target`).
- The "Salesforce Integration" user licenses must have free seats (5 ship free).
- Decide the new user's **Name**, **Username**, and **Email**.
  > ⚠️ **Both the Username and the Email must be in email format** (`name@domain`).
  > - **Username** — must be globally unique and email-format, but the domain does
  >   **not** need to be real or deliverable (e.g. `sync@<yourorg>.com`).
  > - **Email** — must be a **real inbox you control**, since the set-password /
  >   verification mail is sent there.

## A1. Find the org-specific IDs (read-only)

Query the Profile, the two permission sets, and the permission set license.

The API-only integration Profile has been **renamed across org versions** — it's
*Minimum Access - API Only Integrations* in newer orgs and *Salesforce API Only
System Integrations* in older ones. Match on its **user license** instead of the
name, which is stable:

```
sf data query -o <ALIAS> -q "SELECT Id, Name FROM Profile WHERE UserLicense.Name = 'Salesforce Integration'"
```

```
sf data query -o <ALIAS> -q "SELECT Id, Label FROM PermissionSet WHERE Label IN ('StoreConnect Sync Standard Permission','StoreConnect Sync User Permission')"
```

```
sf data query -o <ALIAS> -q "SELECT Id, MasterLabel FROM PermissionSetLicense WHERE DeveloperName = 'SalesforceAPIIntegrationPsl'"
```

Record the four IDs:

| Item | Field to fill |
|---|---|
| Profile — *Minimum Access - API Only Integrations* (older orgs: *Salesforce API Only System Integrations*) | `<PROFILE_ID>` |
| Perm Set License — *Salesforce API Integration* | `<PSL_ID>` |
| Perm Set — *StoreConnect Sync Standard Permission* | `<STD_PERMSET_ID>` |
| Perm Set — *StoreConnect Sync User Permission* | `<USER_PERMSET_ID>` |

> The two perm sets differ by namespace. **StoreConnect Sync Standard Permission**
> (API name `storeConnect_Sync_standard`) is **local/unmanaged** — no namespace
> prefix — so it's safe to edit and won't be reverted on package upgrade; this is
> the one you edit in B1. **StoreConnect Sync User Permission** (API name
> `storeConnect_Sync`) is **packaged** (`s_c` namespace) — do not modify it.

## A2. Create the user

Uses the "Salesforce Integration" license implicitly via the API-only profile.
Choose your own Name / Username / Email (A0) and adjust timezone/locale to suit
the org. The name below is just the suggested convention.

```
sf data create record -o <ALIAS> -s User -v "FirstName='<FIRST_NAME>' LastName='<LAST_NAME>' Username='<USERNAME>' Email='<EMAIL>' Alias='<ALIAS_8CHARS>' TimeZoneSidKey='Australia/Sydney' LocaleSidKey='en_AU' EmailEncodingKey='UTF-8' LanguageLocaleKey='en_US' ProfileId='<PROFILE_ID>'"
```

> Convention: `FirstName='StoreConnect' LastName='Sync User'`, `Alias` ≤ 8 chars
> (e.g. `scsync`). Note the returned `005...` **User Id** — call it `<USER_ID>`
> below. No password is set on API creation.

## A3. Assign the license + permission sets

Assign the permission set license **first**, then the two permission sets.

```
sf data create record -o <ALIAS> -s PermissionSetLicenseAssign -v "AssigneeId=<USER_ID> PermissionSetLicenseId=<PSL_ID>"
```

```
sf data create record -o <ALIAS> -s PermissionSetAssignment -v "AssigneeId=<USER_ID> PermissionSetId=<STD_PERMSET_ID>"
```

```
sf data create record -o <ALIAS> -s PermissionSetAssignment -v "AssigneeId=<USER_ID> PermissionSetId=<USER_PERMSET_ID>"
```

## A4. Verify (read-only)

```
sf data query -o <ALIAS> -q "SELECT Name, Username, Profile.Name, IsActive FROM User WHERE Username='<USERNAME>'"
```

```
sf data query -o <ALIAS> -q "SELECT PermissionSetLicense.MasterLabel FROM PermissionSetLicenseAssign WHERE Assignee.Username='<USERNAME>'"
```

```
sf data query -o <ALIAS> -q "SELECT PermissionSet.Label FROM PermissionSetAssignment WHERE Assignee.Username='<USERNAME>' AND PermissionSet.Label LIKE 'StoreConnect Sync%'"
```

Expected: user active on the API-only profile, PSL = *Salesforce API Integration*,
and both *StoreConnect Sync* permission sets present.

---
---

# Part B — Interactive setup (human, in the browser)

These steps **cannot** be done via the CLI and must be performed by an admin in
the Salesforce UI.

## B1. Enable "View All Data" on the Standard permission set

The *View All Data* permission depends on a large cascade of other permissions
(`ViewSetup`, `ViewRoles`, `ViewPublicReports`, etc., plus `Read` + `View All` on
every object). The Setup UI checkbox enables them all automatically; a CLI update
is rejected with `FIELD_INTEGRITY_EXCEPTION`.

> **Setup → Permission Sets → StoreConnect Sync Standard Permission →
> System Permissions → Edit → tick "View All Data" → Save.**

The exact perm set is **StoreConnect Sync Standard Permission** — API name
`storeConnect_Sync_standard`, **no namespace prefix**. *Not* "StoreConnect Sync
User Permission" (`storeConnect_Sync`, in the `s_c` managed namespace). View All
Data lives on the **Standard** perm set deliberately: it's the local/unmanaged one,
so the edit survives package upgrades, and it travels to every sync user assigned it.

Verify (read-only, can be run by the AI afterward):

```
sf data query -o <ALIAS> -q "SELECT Label, PermissionsViewAllData FROM PermissionSet WHERE Id='<STD_PERMSET_ID>'"
```

Expect `PermissionsViewAllData = true`.

## B2. Set the password

### B2 (preferred) — set the password via API (no email)

Creating the user via API sets **no password and sends no email**, so there is
nothing to wait for. Rather than triggering a reset email (which also depends on
org email Deliverability being "All email"), set a known password directly with the
REST `setPassword` call — this is part of **Part A** and the AI can run it. The
API-set password is the **initial/temporary** credential: on first login the user
**is still prompted to set a new password** (the "Set New Password" screen, see B3).
What this buys you over the email flow is **skipping the emailed device-verification
OTP cycle** (and the email-Deliverability dependency) — not skipping the password
reset itself.

Find the org's latest API version, then POST the new password to the user's
`password` sub-resource (`<USER_ID>` from A2):

```
sf api request rest "/services/data/" -o <ALIAS> | python3 -c "import sys,json;print(json.load(sys.stdin)[-1]['version'])"
```

```
printf '{"NewPassword":"<STRONG_PWD>"}' > /tmp/pwd.json && sf api request rest "/services/data/v<APIV>/sobjects/User/<USER_ID>/password" --method POST --body @/tmp/pwd.json -o <ALIAS>; rm -f /tmp/pwd.json
```

A successful call returns **HTTP 204** (empty body, exit 0). The password must meet
the org's policy (default ≥ 8 chars, mixed alpha + numeric). Verify:

```
sf data query -o <ALIAS> -q "SELECT Username, LastPasswordChangeDate FROM User WHERE Id='<USER_ID>'"
```

Expect `LastPasswordChangeDate` populated. Record the password — it's a live
credential for the StoreConnect connection. This replaces the email flow below.

**What is / isn't automatable here:**
- **Password** — set via API. On first login the user is taken straight to the
  **"Set New Password"** screen (the API-set password is the initial/temporary one)
  and confirms a new one — **no emailed device-verification OTP** to wait for.
- **Security question/answer** — **not settable via any API** (no public field,
  endpoint, or Apex method). It must be completed once in the browser, or the
  requirement relaxed via org password/session policies.
- **Fully UI-less** auth would require OAuth (a Connected App + JWT / named
  credential), which bypasses the login screen entirely — a larger setup than the
  StoreConnect wizard's username/password(+token), so usually not worth it here.

### B2 (alternative) — Reset Password email (UI)

Use this only if you prefer the standard email flow over setting the password
directly.

1. **Setup → Users → Users**, open the sync user.
2. Click **Reset Password**. Salesforce may first ask you to **verify your own
   admin identity** before it will proceed.
3. The reset email is sent to the sync user's **Email** address. Open it and
   **click the link**.
4. **Set the password** and **Save**.

> No email arriving? It's only sent by this **Reset Password** action (never by API
> user creation), and a fresh org may have Deliverability set below "All email" —
> **Setup → Deliverability → Access to Send Email = "All email"**, then retry. The
> API path above avoids this entirely.

## B3. Log in once to complete the first-login challenge

**Attempt a login** as the sync user (with the password from B2). One of two
challenges appears — clear whichever you get:

- **"Set New Password" screen** (the path when the password was set via the B2 API
  call): on first login you're pushed straight to it — **no OTP/email wait**. Set a
  new password (and the security question, if prompted) and submit.
- **Device-verification OTP** (the path the Reset-Password email flow tends to hit):
  Salesforce emails a **one-time passcode** to the sync user's Email — enter it.

Because this is an API-only profile, the page then says **no UI access is
available** — that's expected and confirms the challenge is cleared. The sync user
is now ready for StoreConnect.

## B4. Continue setup in the StoreConnect console

The remaining configuration is done interactively inside the StoreConnect
console. Follow the StoreConnect support documentation to finish connecting the
sync user and completing setup:
<https://support.storeconnect.com/articles/how-to-create-a-storeconnect-sync-user>
(agents: append `.md` —
<https://support.storeconnect.com/articles/how-to-create-a-storeconnect-sync-user.md>)

## B5. Record types (only if applicable)

If the org uses multiple record types on Accounts, Contacts, or Orders, disable
*Enhanced Profile List Views* and *Enhanced Profile User Interface* in User
Management Settings, then assign default record types via the API Only
Integrations profile.

---
---

## Worksheet: record this org's as-built values

Fill this in per org as you run Parts A/B. **All Ids are org-specific** — look them
up in A1 for the org you're provisioning; never copy them from another org.

| Item | Value |
|---|---|
| Org alias / Org Id | `<ALIAS>` / `<00D…>` |
| Username (email-format, globally unique) | `sync@<yourorg>.com` |
| Email (a real inbox you control) | `<you@example.com>` |
| User Id | `<005…>` |
| Profile Id (API-only integration profile) | `<00e…>` |
| PSL Id (*Salesforce API Integration*) | `<0PL…>` |
| Std perm set Id (*StoreConnect Sync Standard Permission*) | `<0PS…>` |
| User perm set Id (*StoreConnect Sync User Permission*) | `<0PS…>` |
