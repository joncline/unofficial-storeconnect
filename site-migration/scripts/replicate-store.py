#!/usr/bin/env python3
"""Interactive orchestrator — replicate a StoreConnect store end to end.

Asks UP FRONT which org + store to replicate FROM and which org to replicate
INTO (they may be the same org), then runs the full migration runbook in order,
each step idempotent and dry-runnable:

  1.  stage    backup-store.py            (capture the source store locally)
  2.  prices   provision-pricebooks.py
  3.  store    deploy-store.py --create-store [--no-default] [--name=]
  4.  cats     provision-categories.py    (writes orgs/<dst>/category-map.json)
  5.  catalog  migrate-catalog.py
  6.  media    migrate-media.py
  6b. tmpl     provision-content-templates.py
  7.  content  deploy-store-content.py [--suffix=]
  8.  pos      provision-pos.py
  8b. roles    provision-store-user-roles.py

SAME-ORG COPY: when source org == target org the wizard automatically adds
  --no-default  (don't hijack the org's existing primary store) and
  --suffix=<s>  (page Slug is org-wide unique + content blocks are org-wide, so
                the copy needs unique keys to get independent content).

--skip-backup reuses an already-captured source backup (skips step 1) — handy for
fast re-runs and dry runs once the backup is staged.

Safety: DRY RUN by default — prints every command and previews each step without
writing. Pass --execute to perform writes; each step still asks for confirmation
(use --yes to auto-confirm). Nothing is written to any org without --execute.

Usage:
    python3 scripts/replicate-store.py                 # interactive, dry run
    python3 scripts/replicate-store.py --execute        # interactive, writes (confirms each step)

Non-interactive (skip prompts by supplying answers):
    python3 scripts/replicate-store.py --src-org A --src-store <id> --dst-org B \
        [--name "My Store"] [--suffix=-copy] [--no-default] [--execute] [--yes]
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import slugify

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS = REPO_ROOT / 'scripts'
PY = sys.executable


def arg(flag, default=None):
    """Return the value for `--flag value` (space form) or `--flag=value`, else default."""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == flag:
            return argv[i + 1] if i + 1 < len(argv) else default
        if a.startswith(flag + '='):
            return a.split('=', 1)[1]
    return default


def sf_query(org, soql):
    """Run a read-only SOQL query, return list of record dicts."""
    out = subprocess.run(
        ['sf', 'data', 'query', '--target-org', org, '--json', '-q', soql],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"query failed on {org}: {out.stderr or out.stdout}")
    return json.loads(out.stdout)['result']['records']


def connected_orgs():
    """Return [(alias, username)] for every connected org with an alias."""
    out = subprocess.run(['sf', 'org', 'list', '--json'], capture_output=True, text=True)
    data = json.loads(out.stdout)['result']
    seen, orgs = set(), []
    for bucket in data.values():
        if not isinstance(bucket, list):
            continue
        for o in bucket:
            alias = o.get('alias')
            if not alias or alias in seen:
                continue
            if str(o.get('connectedStatus', '')).lower() not in ('connected', ''):
                continue
            seen.add(alias)
            orgs.append((alias, o.get('username', '')))
    return sorted(orgs)


def choose(prompt, options, render):
    """Numbered single-select prompt. options: list; render: item -> label."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {render(opt)}")
    while True:
        raw = input("  # > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  (enter the number)")


def main():
    dry_run = '--execute' not in sys.argv
    auto_yes = '--yes' in sys.argv
    interactive = not (arg('--src-org') and arg('--src-store') and arg('--dst-org'))

    print("━" * 64)
    print("StoreConnect store replication" + ("   [DRY RUN]" if dry_run else "   [EXECUTE]"))
    print("━" * 64)

    orgs = connected_orgs()
    if not orgs:
        print("No connected orgs found (sf org list). Authenticate first.")
        sys.exit(1)

    # ── Source org + store ────────────────────────────────────────────────────
    src_org = arg('--src-org')
    if not src_org:
        src_org = choose("Replicate FROM which org? (source)", orgs,
                         lambda o: f"{o[0]}   ({o[1]})")[0]
    elif src_org not in {o[0] for o in orgs}:
        print(f"source org '{src_org}' is not a connected alias"); sys.exit(1)

    src_store = arg('--src-store')
    src_store_name = None
    stores = sf_query(src_org,
        "SELECT Id, Name, s_c__Default__c FROM s_c__Store__c ORDER BY Name")
    by_id = {s['Id']: s for s in stores}
    if not src_store:
        pick = choose(f"Which store in {src_org} is the source?", stores,
                      lambda s: f"{s['Name']}   ({s['Id']})"
                                + ("  [default]" if s.get('s_c__Default__c') else ""))
        src_store, src_store_name = pick['Id'], pick['Name']
    else:
        if src_store not in by_id:
            print(f"store {src_store} not found in {src_org}"); sys.exit(1)
        src_store_name = by_id[src_store]['Name']

    # ── Target org ──────────────────────────────────────────────────────────
    dst_org = arg('--dst-org')
    if not dst_org:
        dst_org = choose("Replicate INTO which org? (target — may be the same)", orgs,
                         lambda o: f"{o[0]}   ({o[1]})"
                                   + ("  ← same as source" if o[0] == src_org else ""))[0]
    elif dst_org not in {o[0] for o in orgs}:
        print(f"target org '{dst_org}' is not a connected alias"); sys.exit(1)

    same_org = (src_org == dst_org)

    # ── New store name + (same-org) suffix ────────────────────────────────────
    default_name = f"{src_store_name} (Copy)" if same_org else src_store_name
    new_name = arg('--name')
    if new_name is None and interactive:
        raw = input(f"\nNew store name [{default_name}]: ").strip()
        new_name = raw or default_name
    new_name = new_name or default_name

    no_default = same_org or ('--no-default' in sys.argv)

    suffix = arg('--suffix', '')
    if same_org and not suffix:
        default_suffix = '-' + (slugify(new_name)[:12].strip('-') or 'copy')
        if interactive:
            raw = input(f"Same-org copy — slug/identifier suffix [{default_suffix}]: ").strip()
            suffix = raw or default_suffix
        else:
            suffix = default_suffix

    # ── Summary + confirm ─────────────────────────────────────────────────────
    print("\n" + "─" * 64)
    print("Plan")
    print(f"  Source:      {src_store_name}  ({src_store})  in {src_org}")
    print(f"  Target org:  {dst_org}" + ("   (SAME org — in-org copy)" if same_org else ""))
    print(f"  New store:   {new_name}")
    print(f"  Primary:     {'left unchanged (--no-default)' if no_default else 'new store set as org default'}")
    print(f"  Suffix:      {suffix or '(none — cross-org blank target)'}")
    print(f"  Mode:        {'DRY RUN (no writes)' if dry_run else 'EXECUTE (writes, confirms each step)'}")
    print("─" * 64)
    if not auto_yes:
        if input("\nProceed? [y/N] ").strip().lower() not in ('y', 'yes'):
            print("Aborted."); sys.exit(0)

    dr = ['--dry-run'] if dry_run else []

    def run(label, cmd, defer_in_dryrun=False):
        """Print + (optionally confirm) + run a sub-step. Returns True on success.

        defer_in_dryrun: step depends on the store created in step 3 (which doesn't
        exist during a dry run), so in dry-run we only print the planned command."""
        print("\n" + "═" * 64)
        print(f"STEP: {label}")
        print("  $ " + " ".join(cmd))
        print("═" * 64)
        if dry_run and defer_in_dryrun:
            print("  (planned — runs under --execute; depends on the new store record)")
            return True
        if not dry_run and not auto_yes:
            ans = input("  run this step? [y/N/skip] ").strip().lower()
            if ans in ('s', 'skip'):
                print("  (skipped)"); return True
            if ans not in ('y', 'yes'):
                print("  Aborted at this step."); sys.exit(1)
        res = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if res.returncode != 0:
            print(f"  ✗ step '{label}' failed (exit {res.returncode}).")
            if not auto_yes and input("  continue anyway? [y/N] ").strip().lower() not in ('y', 'yes'):
                sys.exit(1)
            return False
        return True

    S = lambda name: [PY, str(SCRIPTS / name)]

    # 1. Stage the source store backup (writes orgs/<src_org>/...) ──────────────
    # --skip-backup reuses an already-captured backup (fast re-runs / dry-runs).
    if '--skip-backup' in sys.argv:
        print("\nSTEP: 1/10  capture source backup  — SKIPPED (--skip-backup; reusing staged backup)")
    else:
        run("1/10  capture source backup", S('backup-store.py') + [src_org, src_store])
    if not same_org:
        # Cross-org: the catalog/content scripts read orgs/<dst_org>/. Stage a copy.
        import shutil
        src_root = REPO_ROOT / 'orgs' / src_org
        dst_root = REPO_ROOT / 'orgs' / dst_org
        for sub in ('stores', 'themes'):
            for d in (src_root / sub).glob('*'):
                tgt = dst_root / sub / d.name
                if not dry_run and d.is_dir():
                    tgt.parent.mkdir(parents=True, exist_ok=True)
                    if tgt.exists():
                        shutil.rmtree(tgt)
                    shutil.copytree(d, tgt)
                print(f"  staged {sub}/{d.name} -> orgs/{dst_org}/{sub}/")

    # 2. Pricebooks ─────────────────────────────────────────────────────────────
    run("2/10  pricebooks", S('provision-pricebooks.py') + [src_org, dst_org] + dr)

    # 3. Store record + theme ───────────────────────────────────────────────────
    deploy = S('deploy-store.py') + [dst_org, src_store, dst_org, '--create-store']
    if new_name:
        deploy.append(f'--name={new_name}')
    if no_default:
        deploy.append('--no-default')
    run("3/10  store record + theme", deploy + dr)

    # Resolve the new store Id (needed for categories). Only possible once created.
    new_store_id = None
    if not dry_run:
        rows = sf_query(dst_org,
            f"SELECT Id FROM s_c__Store__c WHERE Name = '{new_name}' "
            f"ORDER BY CreatedDate DESC LIMIT 1")
        if rows:
            new_store_id = rows[0]['Id']
            print(f"\n  → new store Id: {new_store_id}")
        else:
            print("  ✗ could not resolve the new store Id; aborting."); sys.exit(1)
    else:
        new_store_id = '<NEW_STORE_ID>'

    # 4. Categories + hierarchy + category-map.json ─────────────────────────────
    run("4/10  categories + hierarchy",
        S('provision-categories.py') + [src_org, src_store, dst_org, new_store_id] + dr,
        defer_in_dryrun=True)

    # 5–6. Catalog + media ──────────────────────────────────────────────────────
    run("5/10  catalog (products + PBEs)", S('migrate-catalog.py') + [dst_org] + dr,
        defer_in_dryrun=True)
    run("6/10  product media", S('migrate-media.py') + [dst_org] + dr,
        defer_in_dryrun=True)

    # 6b. Content-block template picklist values ─────────────────────────────────
    run("6b/10 content-block templates", S('provision-content-templates.py') + [dst_org] + dr,
        defer_in_dryrun=True)

    # 7. Content: pages/menus/articles/content-blocks ───────────────────────────
    content = S('deploy-store-content.py') + [dst_org]
    if suffix:
        content.append(f'--suffix={suffix}')
    run("7/10  store content (pages/blocks/menus)", content + dr, defer_in_dryrun=True)

    # 8 + 8b. POS + store-user roles ────────────────────────────────────────────
    run("8/10  POS (outlet + register)", S('provision-pos.py') + [dst_org] + dr,
        defer_in_dryrun=True)
    run("8b/10 store-user roles", S('provision-store-user-roles.py') + [dst_org] + dr,
        defer_in_dryrun=True)

    print("\n" + "━" * 64)
    if dry_run:
        print("DRY RUN complete — no org writes were made. Re-run with --execute.")
    else:
        print(f"Replication complete → {new_name} ({new_store_id}) in {dst_org}")
        print("Next (manual, see runbook §9): GOOGLE_MAPS_API_KEY, domain path,")
        print("theme assets, brands. Then verify the storefront + a POS register.")
    print("━" * 64)


if __name__ == '__main__':
    main()
