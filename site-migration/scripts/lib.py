"""Shared utilities for StoreConnect theme pull scripts."""

import csv
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sf_query(org, soql):
    result = subprocess.run(
        ['sf', 'data', 'query', '--target-org', org, '--query', soql, '--json'],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Could not parse sf output:\n{result.stdout[:500]}")

    if data.get('status', 0) != 0:
        raise RuntimeError(data.get('message') or data.get('data', {}).get('message') or 'Query failed')

    return data['result']['records']


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def pull_theme(org, theme_id, repo_root):
    """Pull all records for a single theme and write to orgs/<org>/themes/<slug>/."""
    themes = sf_query(
        org,
        f"SELECT Id, Name, s_c__sC_Id__c FROM s_c__Theme__c WHERE Id = '{theme_id}'",
    )
    if not themes:
        raise RuntimeError(f"Theme {theme_id} not found in org {org}")

    theme = themes[0]
    theme_name = theme['Name']
    theme_sc_id = theme.get('s_c__sC_Id__c') or ''
    slug = slugify(theme_name)

    out = Path(repo_root) / 'orgs' / org / 'themes' / slug
    print(f"  {theme_name}  →  orgs/{org}/themes/{slug}")

    out.mkdir(parents=True, exist_ok=True)
    (out / 'templates').mkdir(exist_ok=True)
    (out / 'assets').mkdir(exist_ok=True)

    pulled_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    (out / 'theme.md').write_text(
        f"# Theme: {theme_name}\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| Salesforce ID | `{theme_id}` |\n"
        f"| StoreConnect ID | `{theme_sc_id}` |\n"
        f"| Org | `{org}` |\n"
        f"| Pulled | {pulled_at} |\n"
    )

    # Templates
    templates = sf_query(
        org,
        f"SELECT s_c__Key__c, s_c__Content__c "
        f"FROM s_c__Theme_Template__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' "
        f"ORDER BY s_c__Key__c",
    )
    for t in templates:
        key = t['s_c__Key__c']
        path = out / 'templates' / (key + '.liquid')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(t['s_c__Content__c'] or '')

    # Variables
    variables = sf_query(
        org,
        f"SELECT s_c__Key__c, s_c__Value__c "
        f"FROM s_c__Theme_Variable__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' "
        f"ORDER BY s_c__Key__c",
    )
    with open(out / 'variables.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['key', 'value'])
        for v in variables:
            w.writerow([v['s_c__Key__c'], v.get('s_c__Value__c') or ''])

    # Locales
    locales = sf_query(
        org,
        f"SELECT Name, s_c__Code__c, s_c__Active__c, s_c__Default__c "
        f"FROM s_c__Theme_Locale__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' "
        f"ORDER BY s_c__Code__c",
    )
    with open(out / 'locales.md', 'w') as f:
        f.write(f"# Locales: {theme_name}\n\n")
        f.write("| Name | Code | Active | Default |\n")
        f.write("|---|---|---|---|\n")
        for locale in locales:
            f.write(
                f"| {locale['Name']} "
                f"| {locale['s_c__Code__c']} "
                f"| {locale['s_c__Active__c']} "
                f"| {locale['s_c__Default__c']} |\n"
            )

    # Assets
    assets = sf_query(
        org,
        f"SELECT s_c__Key__c, s_c__Url__c "
        f"FROM s_c__Theme_Asset__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' "
        f"ORDER BY s_c__Key__c",
    )
    with open(out / 'assets.md', 'w') as f:
        f.write(f"# Assets: {theme_name}\n\n")
        f.write("| Key | URL |\n")
        f.write("|---|---|\n")
        for a in assets:
            f.write(f"| {a['s_c__Key__c']} | {a.get('s_c__Url__c') or ''} |\n")

    for a in assets:
        key = a['s_c__Key__c']
        url = a.get('s_c__Url__c')
        if url:
            dest = out / 'assets' / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['curl', '-sL', url, '-o', str(dest)], capture_output=True)

    return {
        'name': theme_name,
        'templates': len(templates),
        'variables': len(variables),
        'locales': len(locales),
        'assets': len(assets),
    }


def get_sc_orgs():
    """Return aliases of all connected orgs whose alias starts with 'sc'."""
    result = subprocess.run(
        ['sf', 'org', 'list', '--json'],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    orgs = []
    for key in ('nonScratchOrgs', 'sandboxes', 'scratchOrgs', 'other'):
        for org in data.get('result', {}).get(key, []):
            alias = org.get('alias', '')
            status = org.get('connectedStatus', '')
            if alias.lower().startswith('sc') and status in ('Connected', 'NamedOrgNotFoundError'):
                if alias not in orgs:
                    orgs.append(alias)
    return sorted(orgs)


def should_skip(theme_name):
    """Skip themes explicitly marked for deletion."""
    return 'TO BE DELETED' in theme_name.upper()


def _sf_rest(org, method, path, body=None):
    """Call the Salesforce REST API via sf CLI. Returns parsed JSON or None (204)."""
    import os, tempfile
    args = ['sf', 'api', 'request', 'rest', path, '--method', method, '--target-org', org]
    tmp = None
    if body is not None:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(body, f)
            tmp = f.name
        args += ['--body', f'@{tmp}']
    result = subprocess.run(args, capture_output=True, text=True)
    if tmp:
        os.unlink(tmp)

    # Ignore beta command warnings, but fail on actual errors
    stderr = result.stderr.strip() if result.stderr else ''
    is_beta_warning = 'beta' in stderr.lower() and result.returncode == 1
    if result.returncode != 0 and not is_beta_warning:
        raise RuntimeError(
            f"sf CLI failed on {method} {path} (exit {result.returncode}): "
            f"{stderr or result.stdout.strip() or '(no output)'}"
        )

    text = result.stdout.strip()
    if not text:
        return None
    parsed = json.loads(text)
    if isinstance(parsed, list) and parsed and 'errorCode' in parsed[0]:
        raise RuntimeError(f"SF API error on {method} {path}: {parsed[0].get('message')} ({parsed[0].get('errorCode')})")
    return parsed


def create_record(org, sobject, data):
    """POST a new Salesforce record via REST API. Returns the new record Id."""
    result = _sf_rest(org, 'POST', f'/services/data/v62.0/sobjects/{sobject}', data)
    if not result or not result.get('success'):
        raise RuntimeError(f"Create {sobject} failed: {result}")
    return result['id']


def update_record(org, sobject, record_id, data):
    """PATCH a Salesforce record via REST API."""
    _sf_rest(org, 'PATCH', f'/services/data/v62.0/sobjects/{sobject}/{record_id}', data)


def delete_record(org, sobject, record_id):
    """DELETE a Salesforce record via `sf data delete record`.

    Note: we don't reuse _sf_rest because `sf api request rest --method DELETE`
    rejects requests without a body ("No 'mode' found in 'body' entry"), so
    REST-style deletes via that path silently fail.
    """
    result = subprocess.run(
        ['sf', 'data', 'delete', 'record',
         '--sobject', sobject, '--record-id', record_id,
         '--target-org', org],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or 'Successfully deleted' not in result.stdout:
        raise RuntimeError(
            f"Delete {sobject}/{record_id} failed: "
            f"{result.stderr.strip() or result.stdout.strip() or '(no output)'}"
        )


def create_theme(org, name):
    """Create a new Theme record. Returns the record Id."""
    return create_record(org, 's_c__Theme__c', {'Name': name})


def push_template(org, theme_id, key, content):
    """Create or update a Theme Template record. Returns the record Id."""
    existing = sf_query(
        org,
        f"SELECT Id FROM s_c__Theme_Template__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' AND s_c__Key__c = '{key}'",
    )
    if existing:
        update_record(org, 's_c__Theme_Template__c', existing[0]['Id'], {'s_c__Content__c': content})
        return existing[0]['Id']
    return create_record(org, 's_c__Theme_Template__c', {
        's_c__Theme_Id__c': theme_id,
        's_c__Key__c': key,
        's_c__Content__c': content,
    })


def push_variable(org, theme_id, key, value):
    """Create or update a Theme Variable record. Returns the record Id."""
    existing = sf_query(
        org,
        f"SELECT Id FROM s_c__Theme_Variable__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' AND s_c__Key__c = '{key}'",
    )
    if existing:
        update_record(org, 's_c__Theme_Variable__c', existing[0]['Id'], {'s_c__Value__c': value})
        return existing[0]['Id']
    return create_record(org, 's_c__Theme_Variable__c', {
        's_c__Theme_Id__c': theme_id,
        's_c__Key__c': key,
        's_c__Value__c': value,
    })


def push_locale(org, theme_id, code, name, active, default):
    """Create or update a Theme Locale record. Returns the record Id."""
    existing = sf_query(
        org,
        f"SELECT Id FROM s_c__Theme_Locale__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' AND s_c__Code__c = '{code}'",
    )
    fields = {'Name': name, 's_c__Active__c': active, 's_c__Default__c': default}
    if existing:
        update_record(org, 's_c__Theme_Locale__c', existing[0]['Id'], fields)
        return existing[0]['Id']
    return create_record(org, 's_c__Theme_Locale__c', {
        's_c__Theme_Id__c': theme_id,
        's_c__Code__c': code,
        **fields,
    })


def push_asset(org, theme_id, key, url):
    """Create or update a Theme Asset record (CDN URL). Returns the record Id."""
    existing = sf_query(
        org,
        f"SELECT Id FROM s_c__Theme_Asset__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' AND s_c__Key__c = '{key}'",
    )
    if existing:
        update_record(org, 's_c__Theme_Asset__c', existing[0]['Id'], {'s_c__Url__c': url})
        return existing[0]['Id']
    return create_record(org, 's_c__Theme_Asset__c', {
        's_c__Theme_Id__c': theme_id,
        's_c__Key__c': key,
        's_c__Url__c': url,
    })


def push_store_variable(org, store_id, key, value, available_in_liquid):
    """Create or update a Store Variable record. Returns the record Id."""
    existing = sf_query(
        org,
        f"SELECT Id FROM s_c__Store_Variable__c "
        f"WHERE s_c__Store_Id__c = '{store_id}' AND s_c__Key__c = '{key}'",
    )
    fields = {'s_c__Value__c': value, 's_c__Available_In_Liquid__c': available_in_liquid}
    if existing:
        update_record(org, 's_c__Store_Variable__c', existing[0]['Id'], fields)
        return existing[0]['Id']
    return create_record(org, 's_c__Store_Variable__c', {
        's_c__Store_Id__c': store_id,
        's_c__Key__c': key,
        'Name': key,
        **fields,
    })
