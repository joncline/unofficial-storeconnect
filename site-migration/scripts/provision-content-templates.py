#!/usr/bin/env python3
"""Register custom content-block template picklist values in a target org.

`s_c__Content_Block__c.s_c__Template__c` is a **restricted** picklist. The custom
theme block templates the migrated content blocks use (e.g. `sto-hero`,
`sto-promo`, `inf-logo-block`) exist in the source org but NOT in a blank target,
so creating those blocks fails with INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST. This
step adds the missing values to the picklist — via the Tooling API CustomField
metadata (subscriber orgs CAN extend this managed field's local value set) — so
`deploy-store-content.py` can create every block. Run it BEFORE Step 7.

The values added are exactly those referenced by the staged content blocks
(`orgs/<dst_org>/stores/<store>/content-blocks/*/record.json`) that aren't already
valid in the target. Idempotent: values already present are skipped.

Usage:
    python3 scripts/provision-content-templates.py <dst_org> [--dry-run]
"""

import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))
from lib import _sf_rest

REPO_ROOT = Path(__file__).parent.parent
API = '/services/data/v62.0'
TOOLING = f'{API}/tooling'
SOBJECT = 's_c__Content_Block__c'
FIELD = 's_c__Template__c'
FIELD_DEV, FIELD_NS = 'Template', 's_c'


def strip_nulls(o):
    """Tooling API rejects null complex fields when a Metadata blob is sent back."""
    if isinstance(o, dict):
        return {k: strip_nulls(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [strip_nulls(v) for v in o]
    return o


def tooling_query(org, soql):
    return _sf_rest(org, 'GET', f'{TOOLING}/query?q={quote(soql)}')['records']


def current_template_values(org):
    desc = _sf_rest(org, 'GET', f'{API}/sobjects/{SOBJECT}/describe')
    fld = next(f for f in desc['fields'] if f['name'] == FIELD)
    return {v['value'] for v in fld.get('picklistValues', [])}


def template_field_id(org):
    """Resolve the org-specific CustomField Id for SOBJECT.FIELD."""
    ent = tooling_query(org,
        f"SELECT DurableId FROM EntityDefinition WHERE QualifiedApiName='{SOBJECT}'")
    durable = ent[0]['DurableId']
    for r in tooling_query(org,
            f"SELECT Id, TableEnumOrId FROM CustomField "
            f"WHERE DeveloperName='{FIELD_DEV}' AND NamespacePrefix='{FIELD_NS}'"):
        if r['TableEnumOrId'].startswith(durable):   # 18-char id startswith 15-char durable
            return r['Id']
    raise RuntimeError(f"{FIELD} CustomField not found on {SOBJECT} in {org}")


def needed_templates(store_dir):
    vals = set()
    cb = store_dir / 'content-blocks'
    if cb.exists():
        for d in sorted(cb.iterdir()):
            rec = d / 'record.json'
            if rec.exists():
                t = json.loads(rec.read_text()).get(FIELD)
                if t:
                    vals.add(t)
    return vals


def main():
    dry_run = '--dry-run' in sys.argv
    rest = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(rest) != 1:
        print('Usage: python3 scripts/provision-content-templates.py <dst_org> [--dry-run]')
        sys.exit(1)
    dst_org = rest[0]
    mode = 'DRY RUN' if dry_run else 'LIVE'

    store_dir = next(d for d in (REPO_ROOT / 'orgs' / dst_org / 'stores').iterdir()
                     if (d / 'record.json').exists())
    need = needed_templates(store_dir)
    have = current_template_values(dst_org)
    missing = sorted(need - have)

    print(f'[{mode}] content-block template picklist -> {dst_org}')
    print(f'  needed by blocks: {len(need)}  |  already valid: {len(need & have)}  |  '
          f'missing: {len(missing)}')
    for m in missing:
        print(f'   + {m}')
    if not missing:
        print('  nothing to add.')
        return
    if dry_run:
        print(f'  (dry run) would add {len(missing)} value(s) to {FIELD}')
        return

    fid = template_field_id(dst_org)
    rec = _sf_rest(dst_org, 'GET', f'{TOOLING}/sobjects/CustomField/{fid}')
    meta = strip_nulls(rec['Metadata'])
    values = meta['valueSet']['valueSetDefinition']['value']
    names = {v['valueName'] for v in values}
    for m in missing:
        if m not in names:
            values.append({'valueName': m, 'label': m, 'default': False})
    _sf_rest(dst_org, 'PATCH', f'{TOOLING}/sobjects/CustomField/{fid}', {'Metadata': meta})

    now = current_template_values(dst_org)
    still = [m for m in missing if m not in now]
    if still:
        print(f'  WARN: these were not added: {still}')
        sys.exit(1)
    print(f'  added {len(missing)} value(s); picklist now has {len(now)}.')


if __name__ == '__main__':
    main()
