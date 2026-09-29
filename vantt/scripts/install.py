#!/usr/bin/env python3
"""
herdr-install: Explicit installation and rollback tool for patched Herdr binary.
Safely replaces ~/.local/bin/herdr with backup and warns about running gateways.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_SRC = Path(__file__).resolve().parent.parent.parent / "target" / "release" / "herdr"
DEFAULT_DEST = Path("/home/vantt/.local/bin/herdr")
BACKUP_DIR = DEFAULT_DEST.parent


def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed (exit {res.returncode}): {' '.join(cmd)}\n{res.stderr}")
    return res


def list_backups():
    if not BACKUP_DIR.exists():
        return []
    backups = sorted(BACKUP_DIR.glob("herdr.bak-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups


def rollback():
    backups = list_backups()
    if not backups:
        print("No backups found in", BACKUP_DIR)
        sys.exit(1)

    latest = backups[0]
    print(f"Latest backup: {latest}")
    print(f"Restoring to {DEFAULT_DEST}...")
    tmp_dest = DEFAULT_DEST.with_suffix(f".tmp.{os.getpid()}")
    shutil.copy2(latest, tmp_dest)
    os.chmod(tmp_dest, 0o755)
    os.replace(tmp_dest, DEFAULT_DEST)

    ver_res = run_cmd([str(DEFAULT_DEST), "--version"], check=False)
    print(f"Rolled back successfully to version: {ver_res.stdout.strip()}")
    print("\n[!] REMINDER: Restart gateway when ready: fgos gateway stop && fgos gateway start\n")


def install(src_path, dest_path, dry_run=False):
    src = Path(src_path).resolve()
    dest = Path(dest_path).resolve()

    if not src.exists():
        raise FileNotFoundError(f"Source binary does not exist at {src}. Run catchup.py first!")

    # Verify source binary
    ver_res = run_cmd([str(src), "--version"])
    new_version = ver_res.stdout.strip()
    help_res = run_cmd([str(src), "agent", "start", "--help"])
    if "--executable" not in help_res.stdout:
        raise RuntimeError("Source binary does not exhibit '--executable' flag in 'agent start --help'!")

    print(f"Source binary verified: {new_version}")
    print(f"Destination target:     {dest}")

    if dry_run:
        print("\n[DRY RUN] Everything verified. Binary ready to install.")
        return

    # Backup existing destination
    if dest.exists():
        cur_ver_res = run_cmd([str(dest), "--version"], check=False)
        old_version = cur_ver_res.stdout.strip().replace(" ", "_").replace("/", "_") if cur_ver_res.returncode == 0 else "unknown"
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"herdr.bak-{old_version}-{ts}"
        backup_path = dest.parent / backup_name
        print(f"Creating backup of existing binary at: {backup_path}")
        shutil.copy2(dest, backup_path)

    # Install new binary atomically
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Copying {src} -> {dest} (atomic)...")
    tmp_dest = dest.with_suffix(f".tmp.{os.getpid()}")
    shutil.copy2(src, tmp_dest)
    os.chmod(tmp_dest, 0o755)
    os.replace(tmp_dest, dest)

    # Verify installed binary
    installed_ver = run_cmd([str(dest), "--version"]).stdout.strip()
    print(f"\n========================================================")
    print(f"INSTALLATION SUCCESSFUL!")
    print(f"Installed: {dest}")
    print(f"Version:   {installed_ver}")
    print(f"")
    print(f"[!] IMPORTANT REMINDER:")
    print(f"Running gateways, sessions, and panes are STILL RUNNING the old binary.")
    print(f"Herdr will NOT restart them automatically.")
    print(f"When ready to apply changes, restart gateway manually:")
    print(f"    fgos gateway stop && fgos gateway start")
    print(f"")
    print(f"To rollback at any time:")
    print(f"    python3 {Path(__file__).resolve()} --rollback")
    print(f"========================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Install or rollback patched Herdr binary.")
    parser.add_argument("--binary", default=str(DEFAULT_SRC), help=f"Source binary path (default: {DEFAULT_SRC})")
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help=f"Destination binary path (default: {DEFAULT_DEST})")
    parser.add_argument("--dry-run", action="store_true", help="Check binary without copying")
    parser.add_argument("--rollback", action="store_true", help="Rollback to most recent backup")
    parser.add_argument("--list-backups", action="store_true", help="List available backups")

    args = parser.parse_args()

    if args.list_backups:
        backups = list_backups()
        if not backups:
            print("No backups found.")
        else:
            print("Available backups:")
            for b in backups:
                mtime = datetime.datetime.fromtimestamp(b.stat().st_mtime).isoformat()
                print(f"  {b.name} (modified: {mtime})")
        sys.exit(0)

    if args.rollback:
        rollback()
        sys.exit(0)

    install(args.binary, args.dest, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
