#!/usr/bin/env python3
"""Provision an API-only StoreConnect "Content Agent" user in a target org.

Creates a scoped, login-restricted user an AI agent (or any integration) can act
as to manage *content* — never pricing, orders, or customers. The user gets:

  * the API-only profile on the free **Salesforce Integration** license
  * the **SalesforceAPIIntegrationPsl** permission-set license
  * StoreConnect **Content Manager** + **Theme Manager** (packaged perm sets)
  * **SC Agent CMS Extras** (this repo) — POS layout/view config, page/article
    tags, traits/variants, and edit access to Product2 *content* fields only

PREREQUISITE: deploy the SC_Agent_CMS_Extras permission set first (one command):

    sf project deploy start -o <ORG_ALIAS> \
        --source-dir salesforce/permissionsets --manifest salesforce/package.xml

AUTH MODEL (set up after provisioning — see README.md): two flows work.
  * web login -- `sf org login web -a <ORG_ALIAS>-content-agent`. Refresh-token
    backed, persists across restarts; best for a long-running CLI agent. Needs a
    one-time browser login, so set a password (pass --set-password, or reset from
    Setup -> Users). The "Access Restricted for API Only Users" page appears AFTER
    the CLI has captured credentials, which is expected.
  * External Client App + OAuth Client Credentials, run-as this user. No browser or
    password; short-lived token with no refresh token; best for headless services.
This script only provisions the user + permissions; the boundary is the same either way.

Everything is idempotent. Pass --dry-run to print the plan without writing.

Usage:
    python3 scripts/provision-content-agent.py <ORG_ALIAS> \
        --username content-agent@yourorg.example.com \
        --email ops@example.com \
        [--first Content] [--last Agent] [--user-alias ctntagnt] \
        [--set-password 'S0meStr0ng!Pass'] [--dry-run]

The org alias must already be authenticated to the `sf` CLI as an admin
(`sf org login web -a <ORG_ALIAS>`).
"""

import json
import subprocess
import sys

# StoreConnect packaged permission sets to assign (NamespacePrefix, Name).
PACKAGED_PERMSETS = [
    ('s_c', 'storeConnect_Content_Manager'),   # StoreConnect Content Manager
    ('s_c', 'StoreConnect_Theme_Manager'),      # StoreConnect Theme Manager
]
CUSTOM_PERMSET = 'SC_Agent_CMS_Extras'          # deployed from this repo (no namespace)
PSL_DEVNAME = 'SalesforceAPIIntegrationPsl'
API_VERSION = 'v62.0'
# API-only profiles ship under different names across org versions; match either.
API_ONLY_PROFILES = (
    'Minimum Access - API Only Integrations',
    'Salesforce API Only System Integrations',
)


def sf_query(org, soql):
    r = subprocess.run(
        ['sf', 'data', 'query', '-o', org, '-q', soql, '--json'],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Could not parse sf output:\n{r.stdout[:500]}\n{r.stderr[:500]}")
    if data.get('status', 0) != 0:
        raise RuntimeError(data.get('message') or 'Query failed')
    return data['result']['records']


def sf_create(org, sobject, fields, dry_run):
    pairs = ' '.join(f"{k}='{v}'" for k, v in fields.items())
    if dry_run:
        print(f"    [dry-run] sf data create record -o {org} -s {sobject} -v \"{pairs}\"")
        return None
    r = subprocess.run(
        ['sf', 'data', 'create', 'record', '-o', org, '-s', sobject, '-v', pairs, '--json'],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout or '{}')
    if data.get('status', 0) != 0:
        raise RuntimeError(f"Create {sobject} failed: {data.get('message') or r.stdout[:400]}")
    return data['result']['id']


def set_password(org, user_id, password, dry_run):
    path = f"/services/data/{API_VERSION}/sobjects/User/{user_id}/password"
    if dry_run:
        print(f"    [dry-run] sf api request rest {path} --method POST --body '{{\"NewPassword\":\"***\"}}'")
        return
    r = subprocess.run(
        ['sf', 'api', 'request', 'rest', path, '-o', org, '--method', 'POST',
         '--body', json.dumps({'NewPassword': password})],
        capture_output=True, text=True,
    )
    # setPassword returns HTTP 204 (empty body) on success.
    if r.returncode != 0 and 'error' in (r.stdout + r.stderr).lower():
        raise RuntimeError(f"setPassword failed: {r.stdout[:400]}{r.stderr[:400]}")
    print("    password set.")


def opt(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main():
    dry_run = '--dry-run' in sys.argv
    flag_values = {opt(f) for f in ('--username', '--email', '--first', '--last',
                                    '--user-alias', '--set-password')}
    pos = [a for a in sys.argv[1:] if not a.startswith('--') and a not in flag_values]
    if len(pos) != 1:
        print(__doc__)
        sys.exit(1)
    org = pos[0]
    username = opt('--username')
    email = opt('--email')
    if not username or not email:
        print("ERROR: --username and --email are required.\n")
        print(__doc__)
        sys.exit(1)
    first = opt('--first', 'Content')
    last = opt('--last', 'Agent')
    user_alias = opt('--user-alias', 'ctntagnt')
    password = opt('--set-password')

    tag = ' (DRY RUN)' if dry_run else ''
    print(f"==> Provisioning content agent in '{org}'{tag}\n")

    # 1. Free Salesforce Integration seat?
    lic = sf_query(org, "SELECT TotalLicenses, UsedLicenses FROM UserLicense "
                        "WHERE Name = 'Salesforce Integration'")
    if not lic:
        sys.exit("ERROR: no Salesforce Integration license in this org.")
    total, used = lic[0]['TotalLicenses'], lic[0]['UsedLicenses']
    print(f"  Salesforce Integration license: {used}/{total} used ({total - used} free)")
    if total - used <= 0:
        sys.exit("ERROR: no free Integration seat. Deactivate a stale integration "
                 "user or buy a 5-pack.")

    # 2. API-only profile
    quoted = ','.join(f"'{p}'" for p in API_ONLY_PROFILES)
    profs = sf_query(org, "SELECT Id, Name FROM Profile WHERE "
                          "UserLicense.Name = 'Salesforce Integration' "
                          f"AND Name IN ({quoted}) ORDER BY Name LIMIT 1")
    if not profs:
        sys.exit("ERROR: no API-only profile on the Salesforce Integration license.")
    profile_id, profile_name = profs[0]['Id'], profs[0]['Name']
    print(f"  API-only profile: {profile_name} ({profile_id})")

    # 3. Confirm the permission set is deployed (deploy it first — see PREREQUISITE).
    if not sf_query(org, "SELECT Id FROM PermissionSet WHERE "
                         f"Name = '{CUSTOM_PERMSET}' AND NamespacePrefix = null"):
        sys.exit(f"ERROR: permission set '{CUSTOM_PERMSET}' is not deployed. Run:\n"
                 f"  sf project deploy start -o {org} "
                 "--source-dir salesforce/permissionsets --manifest salesforce/package.xml")

    # 4. Create (or find) the user
    print(f"\n  User {username}")
    existing = sf_query(org, f"SELECT Id FROM User WHERE Username = '{username}'")
    if existing:
        user_id = existing[0]['Id']
        print(f"    exists: {user_id}")
    else:
        user_id = sf_create(org, 'User', {
            'FirstName': first, 'LastName': last, 'Username': username,
            'Email': email, 'Alias': user_alias,
            'TimeZoneSidKey': 'Australia/Sydney', 'LocaleSidKey': 'en_AU',
            'EmailEncodingKey': 'UTF-8', 'LanguageLocaleKey': 'en_US',
            'ProfileId': profile_id,
        }, dry_run)
        print(f"    created: {user_id or '(dry-run)'}")

    if dry_run and not existing:
        print("\n  [dry-run] remaining assignments depend on the new user Id — "
              "skipping in dry run.")
        print("\n==> Dry run complete.")
        return

    # 5a. PSL
    print(f"\n  Permission-set license: {PSL_DEVNAME}")
    psl = sf_query(org, "SELECT Id FROM PermissionSetLicense WHERE "
                        f"DeveloperName = '{PSL_DEVNAME}'")
    if not psl:
        sys.exit(f"ERROR: PSL {PSL_DEVNAME} not found.")
    psl_id = psl[0]['Id']
    if sf_query(org, "SELECT Id FROM PermissionSetLicenseAssign WHERE "
                     f"AssigneeId = '{user_id}' AND PermissionSetLicenseId = '{psl_id}'"):
        print("    = already assigned")
    else:
        sf_create(org, 'PermissionSetLicenseAssign',
                  {'AssigneeId': user_id, 'PermissionSetLicenseId': psl_id}, dry_run)
        print("    + assigned")

    # 5b. Permission sets (packaged pair + custom)
    print("\n  Permission sets:")
    clauses = [f"(NamespacePrefix = '{ns}' AND Name = '{nm}')" for ns, nm in PACKAGED_PERMSETS]
    clauses.append(f"(NamespacePrefix = null AND Name = '{CUSTOM_PERMSET}')")
    permsets = sf_query(org, "SELECT Id, Label, Name FROM PermissionSet WHERE "
                             + ' OR '.join(clauses))
    found = {p['Name'] for p in permsets}
    for ns, nm in PACKAGED_PERMSETS:
        if nm not in found:
            print(f"    ! WARNING: packaged perm set '{nm}' not found — is the "
                  "StoreConnect package installed?")
    for p in permsets:
        if sf_query(org, "SELECT Id FROM PermissionSetAssignment WHERE "
                         f"AssigneeId = '{user_id}' AND PermissionSetId = '{p['Id']}'"):
            print(f"    = {p['Label']} (already assigned)")
        else:
            sf_create(org, 'PermissionSetAssignment',
                      {'AssigneeId': user_id, 'PermissionSetId': p['Id']}, dry_run)
            print(f"    + {p['Label']}")

    # 5c. Optional password (needed for the one-time browser login)
    if password:
        print("\n  Setting password (for the one-time web login)")
        set_password(org, user_id, password, dry_run)

    # 6. Verify
    print("\n==> Verification")
    psls = sf_query(org, "SELECT PermissionSetLicense.DeveloperName FROM "
                         f"PermissionSetLicenseAssign WHERE AssigneeId = '{user_id}'")
    print("  PSLs:        " + ', '.join(x['PermissionSetLicense']['DeveloperName'] for x in psls))
    psas = sf_query(org, "SELECT PermissionSet.Label FROM PermissionSetAssignment "
                         f"WHERE AssigneeId = '{user_id}' AND PermissionSet.IsOwnedByProfile = false")
    print("  Perm sets:   " + ', '.join(x['PermissionSet']['Label'] for x in psas))

    print(f"\n==> Done. {username} ({user_id}) is a scoped content agent.")
    print("    Connect the CLI as this user (durable refresh token):")
    print(f"      sf org login web -a {org}-content-agent")
    if not password:
        print("    First set/reset its password (Setup -> Users) or re-run with --set-password.")


if __name__ == '__main__':
    main()
