#!/usr/bin/env python3
"""Provision StoreConnect tier pricebooks into a target org.

Mirrors every non-standard, active Pricebook2 from a source org into a
destination org, matched by Name. Idempotent — re-running skips pricebooks that
already exist in the destination. The standard pricebook is never touched (every
org ships with one).

Part of the site migration: stands up the tier pricebooks
(Wholesale / Hidden / Gold / Bronze / Silver) so the product PricebookEntries
migrated in a later step have a home. Run this BEFORE the catalog migration.

Usage:
    python3 scripts/provision-pricebooks.py <src_org> <dst_org> [--dry-run]

Example:
    python3 scripts/provision-pricebooks.py <source-org> <target-org> --dry-run
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import sf_query, create_record

# Fields copied from each source pricebook (only non-null values are sent).
# Deliberately excludes:
#   Id, IsStandard         - managed by the platform
#   s_c__sC_Id__c          - per-record StoreConnect internal id (unique)
#   s_c__Tax_Zone_Id__c    - cross-org reference that won't resolve in the target
COPY_FIELDS = [
    'Name', 'IsActive', 'Description',
    's_c__Add_To_Cart_Text__c', 's_c__Buy_It_Now_Text__c',
    's_c__Hide_Price_Text__c', 's_c__Out_Of_Stock_Text__c',
    's_c__Unavailable_Text__c',
    's_c__Default_Earn_Rate__c', 's_c__Default_Purchase_Rate__c',
    's_c__Order_Quantity_Maximum__c', 's_c__Tax_Method__c',
    's_c__Minimum_Deposit_Amount__c', 's_c__Minimum_Deposit_Percent__c',
    's_c__Minimum_Deposit_Points__c',
]


def main():
    dry_run = '--dry-run' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        print('Usage: python3 scripts/provision-pricebooks.py <src_org> <dst_org> [--dry-run]')
        sys.exit(1)
    src_org, dst_org = args

    mode = 'DRY RUN' if dry_run else 'LIVE'
    print(f'[{mode}] Provision pricebooks: {src_org} -> {dst_org}')

    # Source: every non-standard pricebook with its copyable field values.
    field_list = ', '.join(COPY_FIELDS)
    src_pbs = sf_query(
        src_org,
        f'SELECT {field_list} FROM Pricebook2 WHERE IsStandard = false ORDER BY Name',
    )
    if not src_pbs:
        print('  No non-standard pricebooks in source. Nothing to do.')
        return

    # Destination: existing pricebook names, for idempotency.
    existing = {p['Name'] for p in sf_query(dst_org, 'SELECT Name FROM Pricebook2')}

    created = skipped = 0
    for pb in src_pbs:
        name = pb['Name']
        if name in existing:
            print(f'  (exists) {name}')
            skipped += 1
            continue

        data = {k: pb[k] for k in COPY_FIELDS if pb.get(k) is not None}
        # A new pricebook must be active to hold usable entries.
        data['IsActive'] = True

        if dry_run:
            print(f'  + would create {name}  {data}')
            created += 1
            continue

        new_id = create_record(dst_org, 'Pricebook2', data)
        print(f'  + created {name}  ({new_id})')
        created += 1

    print(f'Done. {created} created, {skipped} already present.')


if __name__ == '__main__':
    main()
