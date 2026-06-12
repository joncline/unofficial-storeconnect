#!/usr/bin/env python3
"""Provision StoreConnect store-user roles for the org's primary login user.

The StoreConnect **web console** and **website builder** require the human login
user (the System Administrator created when the org was signed up — NOT the
API-only sync user) to hold store-user roles. Without them the console/builder
won't open for that user.

This mirrors a reference org, where the signup admin has two
store-agnostic roles (`s_c__Store_Scope__c = all`, no store link):

    Admin - Console   (s_c__Store_Role__c: type 'web console',     level 'viewer')
    Admin - Content   (s_c__Store_Role__c: type 'content changes', level 'editor')

The script (idempotent):
  1. ensures each `s_c__Store_Role__c` definition exists (matched by Name),
  2. resolves the target user (the initial active System Administrator, or
     `--user <username>`),
  3. ensures one `s_c__Store_User_Role__c` per role links that user to it with
     Scope = 'all'.

Run after the store is created. Roles are store-agnostic, so it does not need a
store Id.

Usage:
    python3 scripts/provision-store-user-roles.py <org> [--user <username>] [--dry-run]

Example:
    python3 scripts/provision-store-user-roles.py <target-org> --dry-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, create_record

# The roles to provision, matched/created by Name. Type + Level must match the
# StoreConnect picklist values used by the reference org.
ROLES = [
    {'Name': 'Admin - Console', 's_c__Type__c': 'web console',     's_c__Level__c': 'viewer'},
    {'Name': 'Admin - Content', 's_c__Type__c': 'content changes', 's_c__Level__c': 'editor'},
]


def resolve_user(org, username):
    """Return (Id, Username) for the target user.

    With --user, look it up by exact Username. Otherwise pick the org's initial
    active System Administrator (earliest-created), which is the signup login
    user — never the API-only sync user (it's on the integration profile).
    """
    if username:
        rows = sf_query(org, f"SELECT Id, Username FROM User WHERE Username = '{username}'")
        if not rows:
            raise RuntimeError(f"No user with Username '{username}' in {org}")
        return rows[0]['Id'], rows[0]['Username']

    rows = sf_query(
        org,
        "SELECT Id, Username FROM User "
        "WHERE Profile.Name = 'System Administrator' AND IsActive = true "
        "ORDER BY CreatedDate ASC LIMIT 1",
    )
    if not rows:
        raise RuntimeError(
            f"No active System Administrator found in {org}; pass --user <username>"
        )
    return rows[0]['Id'], rows[0]['Username']


def ensure_role(org, role, existing, dry_run):
    """Return the Id of the Store_Role named role['Name'], creating it if absent."""
    name = role['Name']
    if name in existing:
        print(f"  (role exists) {name}  ({existing[name]})")
        return existing[name]
    if dry_run:
        print(f"  + would create role {name}  {role}")
        return None
    new_id = create_record(org, 's_c__Store_Role__c', role)
    print(f"  + created role {name}  ({new_id})")
    return new_id


def main():
    dry_run = '--dry-run' in sys.argv
    username = None
    if '--user' in sys.argv:
        i = sys.argv.index('--user')
        if i + 1 < len(sys.argv):
            username = sys.argv[i + 1]
    args = [a for a in sys.argv[1:] if not a.startswith('--') and a != username]
    if len(args) != 1:
        print('Usage: python3 scripts/provision-store-user-roles.py <org> [--user <username>] [--dry-run]')
        sys.exit(1)
    org = args[0]

    mode = 'DRY RUN' if dry_run else 'LIVE'
    print(f'[{mode}] Provision store-user roles in {org}')

    user_id, user_name = resolve_user(org, username)
    print(f'  Target user: {user_name}  ({user_id})')

    # Existing role definitions, by Name, for idempotency.
    existing_roles = {
        r['Name']: r['Id']
        for r in sf_query(org, 'SELECT Id, Name FROM s_c__Store_Role__c')
    }

    # Existing user-role links for this user, by Store_Role_Id, for idempotency.
    existing_links = {
        r['s_c__Store_Role_Id__c']
        for r in sf_query(
            org,
            "SELECT s_c__Store_Role_Id__c FROM s_c__Store_User_Role__c "
            f"WHERE s_c__User_Id__c = '{user_id}'",
        )
    }

    created_links = skipped_links = 0
    for role in ROLES:
        role_id = ensure_role(org, role, existing_roles, dry_run)

        if role_id is not None and role_id in existing_links:
            print(f"  (link exists) {user_name} -> {role['Name']}")
            skipped_links += 1
            continue

        link = {
            's_c__User_Id__c': user_id,
            's_c__Store_Role_Id__c': role_id,
            's_c__Store_Scope__c': 'all',
        }
        if dry_run:
            shown = dict(link, s_c__Store_Role_Id__c=role_id or f"<new {role['Name']}>")
            print(f"  + would create link {user_name} -> {role['Name']}  {shown}")
            created_links += 1
            continue

        new_id = create_record(org, 's_c__Store_User_Role__c', link)
        print(f"  + created link {user_name} -> {role['Name']}  ({new_id})")
        created_links += 1

    print(f'Done. {created_links} link(s) created, {skipped_links} already present.')


if __name__ == '__main__':
    main()
