#!/usr/bin/env python3
"""Provision a default Point-of-Sale setup (1 Outlet + 1 Register) for a store.

StoreConnect POS model:
  s_c__Outlet__c    one per physical/virtual sales point (s_c__Store_Id__c req.)
  s_c__Register__c  belongs to an outlet (s_c__Outlet_Id__c required)

Creates a clean default outlet + register for the destination store. We do NOT
copy the source outlet (it belongs to a different store and carries a
store-specific address + a cross-org anonymous-checkout Contact). Idempotent —
matches the outlet by Name+Store and the register by Name+Outlet.

Reads dst store from orgs/<dst_org>/category-map.json. Run AFTER deploy-store.py.

Usage:
    python3 scripts/provision-pos.py <dst_org> [--outlet "Main Outlet"] [--register "Register 1"] [--dry-run]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, create_record

REPO_ROOT = Path(__file__).parent.parent


def opt(flag, default):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main():
    dry_run = '--dry-run' in sys.argv
    outlet_name = opt('--outlet', 'Main Outlet')
    register_name = opt('--register', 'Register 1')
    rest = [a for a in sys.argv[1:]
            if not a.startswith('--') and a not in (outlet_name, register_name)]
    if len(rest) != 1:
        print('Usage: python3 scripts/provision-pos.py <dst_org> '
              '[--outlet NAME] [--register NAME] [--dry-run]')
        sys.exit(1)
    dst_org = rest[0]
    mode = 'DRY RUN' if dry_run else 'LIVE'

    cmap = json.loads((REPO_ROOT / 'orgs' / dst_org / 'category-map.json').read_text())
    store_id = cmap['dst_store_id']
    print(f'[{mode}] Provision POS -> {dst_org}  (store {store_id})')

    std_pb = sf_query(dst_org, "SELECT Id FROM Pricebook2 WHERE IsStandard = true LIMIT 1")
    std_pb_id = std_pb[0]['Id'] if std_pb else None

    # ── Anonymous Checkout contact (required by an Outlet validation rule) ────
    # The outlet needs a Contact for POS guest checkout. Provision a dedicated
    # one (idempotent) rather than reuse sample data.
    contact_id = None
    if dry_run:
        contact_id = 'DRY_CONTACT'
        print('  anon checkout contact: would ensure "Anonymous Checkout"')
    else:
        found = sf_query(dst_org,
            "SELECT Id FROM Contact WHERE FirstName = 'Anonymous' AND LastName = 'Checkout' LIMIT 1")
        if found:
            contact_id = found[0]['Id']
            print(f'  (exists) Anonymous Checkout contact  ({contact_id})')
        else:
            contact_id = create_record(dst_org, 'Contact',
                {'FirstName': 'Anonymous', 'LastName': 'Checkout'})
            print(f'  + Anonymous Checkout contact  ({contact_id})')

    # ── Outlet (idempotent by Name + Store) ──────────────────────────────────
    existing_o = [] if dry_run else sf_query(
        dst_org, f"SELECT Id FROM s_c__Outlet__c "
                 f"WHERE Name = '{outlet_name}' AND s_c__Store_Id__c = '{store_id}' LIMIT 1")
    if existing_o:
        outlet_id = existing_o[0]['Id']
        print(f'  (exists) Outlet {outlet_name}  ({outlet_id})')
    else:
        # Register Code must be >= 20 chars AND globally unique across the org.
        # Derive it from the store id so a second store (e.g. STO beside an
        # existing store) doesn't collide with another outlet's code.
        data = {'Name': outlet_name, 's_c__Store_Id__c': store_id,
                's_c__Register_Code__c': f'main-outlet-{store_id}',
                's_c__Anonymous_Checkout_Contact_Id__c': contact_id}
        if std_pb_id:
            data['s_c__Pricebook_Id__c'] = std_pb_id
        if dry_run:
            outlet_id = 'DRY_OUTLET'
            print(f'  + Outlet {outlet_name}  {data}')
        else:
            outlet_id = create_record(dst_org, 's_c__Outlet__c', data)
            print(f'  + Outlet {outlet_name}  ({outlet_id})')

    # ── Register (idempotent by Name + Outlet) ───────────────────────────────
    existing_r = [] if dry_run else sf_query(
        dst_org, f"SELECT Id FROM s_c__Register__c "
                 f"WHERE Name = '{register_name}' AND s_c__Outlet_Id__c = '{outlet_id}' LIMIT 1")
    if existing_r:
        print(f'  (exists) Register {register_name}  ({existing_r[0]["Id"]})')
    else:
        data = {'Name': register_name, 's_c__Active__c': True, 's_c__Outlet_Id__c': outlet_id}
        if dry_run:
            print(f'  + Register {register_name}  {data}')
        else:
            rid = create_record(dst_org, 's_c__Register__c', data)
            print(f'  + Register {register_name}  ({rid})')

    print('Done.')


if __name__ == '__main__':
    main()
