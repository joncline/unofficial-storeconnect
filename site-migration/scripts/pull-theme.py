#!/usr/bin/env python3
"""
Pull a StoreConnect theme snapshot from a Salesforce org and write it to
orgs/<org>/themes/<slug>/ for version control.

Usage:
    python3 scripts/pull-theme.py <org-alias> <theme-id>

Example:
    python3 scripts/pull-theme.py sc-events a2Rao00000141plEAA

Pulls:
  - Theme metadata         → orgs/<org>/themes/<slug>/theme.md
  - Theme templates (Liquid) → orgs/<org>/themes/<slug>/templates/**/*.liquid
  - Theme variables        → orgs/<org>/themes/<slug>/variables.csv
  - Theme locales          → orgs/<org>/themes/<slug>/locales.md
  - Theme assets (manifest + download CSS/JS) → orgs/<org>/themes/<slug>/assets/

Requires: sf CLI authenticated to the target org.
"""

import sys
import os
import json
import subprocess
import re
import csv
from pathlib import Path
from datetime import datetime, timezone


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


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    org = sys.argv[1]
    theme_id = sys.argv[2]
    repo_root = Path(__file__).parent.parent

    # ── Theme metadata ────────────────────────────────────────────────────────
    print(f"Fetching theme {theme_id} from org {org}...")
    themes = sf_query(
        org,
        f"SELECT Id, Name, s_c__sC_Id__c FROM s_c__Theme__c WHERE Id = '{theme_id}'",
    )
    if not themes:
        print(f"ERROR: Theme {theme_id} not found in org {org}.")
        sys.exit(1)

    theme = themes[0]
    theme_name = theme['Name']
    theme_sc_id = theme.get('s_c__sC_Id__c') or ''
    slug = slugify(theme_name)

    out = repo_root / 'orgs' / org / 'themes' / slug
    print(f"Theme : {theme_name}")
    print(f"Output: {out}\n")

    out.mkdir(parents=True, exist_ok=True)
    (out / 'templates').mkdir(exist_ok=True)
    (out / 'assets').mkdir(exist_ok=True)

    pulled_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    # ── theme.md ──────────────────────────────────────────────────────────────
    (out / 'theme.md').write_text(
        f"# Theme: {theme_name}\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| Salesforce ID | `{theme_id}` |\n"
        f"| StoreConnect ID | `{theme_sc_id}` |\n"
        f"| Org | `{org}` |\n"
        f"| Pulled | {pulled_at} |\n"
    )
    print("Saved theme.md")

    # ── Templates ─────────────────────────────────────────────────────────────
    print("Pulling templates...")
    templates = sf_query(
        org,
        f"SELECT s_c__Key__c, s_c__Content__c "
        f"FROM s_c__Theme_Template__c "
        f"WHERE s_c__Theme_Id__c = '{theme_id}' "
        f"ORDER BY s_c__Key__c",
    )
    for t in templates:
        key = t['s_c__Key__c']          # e.g. "blocks/container"
        path = out / 'templates' / (key + '.liquid')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(t['s_c__Content__c'] or '')
        print(f"  templates/{key}.liquid")
    print(f"Saved {len(templates)} templates.\n")

    # ── Variables ─────────────────────────────────────────────────────────────
    print("Pulling variables...")
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
    print(f"Saved {len(variables)} variables → variables.csv\n")

    # ── Locales ───────────────────────────────────────────────────────────────
    print("Pulling locales...")
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
    print(f"Saved {len(locales)} locales → locales.md\n")

    # ── Assets ────────────────────────────────────────────────────────────────
    print("Pulling assets...")
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

    downloaded = 0
    for a in assets:
        key = a['s_c__Key__c']
        url = a.get('s_c__Url__c')
        if url and key.endswith(('.css', '.js')):
            dest = out / 'assets' / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(['curl', '-sL', url, '-o', str(dest)], capture_output=True)
            if r.returncode == 0:
                print(f"  Downloaded assets/{key}")
                downloaded += 1
            else:
                print(f"  WARNING: failed to download {key}")

    print(f"Saved {len(assets)} asset records → assets.md  ({downloaded} files downloaded)\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("─" * 60)
    print(f"Done. Snapshot written to:  {out}")
    print()
    print("Next steps:")
    print("  git diff --stat")
    print("  git add orgs/")
    print(f"  git commit -m 'feat: pull {theme_name} snapshot from {org}'")


if __name__ == '__main__':
    main()
