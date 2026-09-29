#!/usr/bin/env python3
"""
herdr-catchup: Automated upstream release catchup runner for vantt/herdr fork.
Applies custom patch series on top of upstream releases and verifies build & tests.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VANTT_DIR = REPO_ROOT / "vantt"
PATCHES_DIR = VANTT_DIR / "patches"
SERIES_FILE = PATCHES_DIR / "series.toml"
STATE_FILE = VANTT_DIR / ".catchup_state.json"
DIST_DIR = REPO_ROOT / "dist"

DEFAULT_UPSTREAM_URL = "https://github.com/herdrdev/herdr.git"
DEFAULT_CHANNEL = "vantt"
DEFAULT_BUILD_ID = "1"


def run_cmd(cmd, cwd=REPO_ROOT, env=None, check=True, capture=True):
    """Run shell command with proper environment."""
    merged_env = os.environ.copy()
    # Ensure local bin is in PATH for zig and other tools
    local_bin = str(Path.home() / ".local/bin")
    user_local_bin = "/home/vantt/.local/bin"
    for b in [user_local_bin, local_bin]:
        if b not in merged_env.get("PATH", "").split(":"):
            merged_env["PATH"] = f"{b}:{merged_env.get('PATH', '')}"

    if env:
        merged_env.update(env)

    if isinstance(cmd, list):
        shell = False
    else:
        shell = True

    res = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        shell=shell,
        check=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )
    if check and res.returncode != 0:
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        err_msg = (
            f"Command failed (exit {res.returncode}): {cmd_str}\n"
            f"stdout: {res.stdout if capture else ''}\n"
            f"stderr: {res.stderr if capture else ''}"
        )
        raise RuntimeError(err_msg)
    return res


def parse_series_toml(file_path):
    """
    Parse series.toml without external dependencies.
    Supports [[patches]] blocks with key = 'value' fields.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Series file not found: {file_path}")

    patches = []
    current_patch = None

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line == "[[patches]]":
                if current_patch:
                    patches.append(current_patch)
                current_patch = {}
                continue

            if current_patch is not None and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # Strip quotes and inline comments
                if val.startswith(('"', "'")):
                    quote_char = val[0]
                    end_idx = val.find(quote_char, 1)
                    if end_idx != -1:
                        val = val[1:end_idx]
                else:
                    # Strip any trailing comment
                    val = val.split("#", 1)[0].strip()
                current_patch[key] = val

    if current_patch:
        patches.append(current_patch)

    return patches


def ensure_upstream_remote():
    """Ensure upstream remote is present and points to canonical repo."""
    res = run_cmd("git remote -v")
    remotes = res.stdout.strip().splitlines()
    upstream_exists = any(line.startswith("upstream\t") for line in remotes)
    if not upstream_exists:
        print(f"Adding upstream remote: {DEFAULT_UPSTREAM_URL}")
        run_cmd(["git", "remote", "add", "upstream", DEFAULT_UPSTREAM_URL])
    return "upstream"


def fetch_upstream():
    """Fetch upstream tags and master."""
    print("Fetching upstream tags and refs...")
    run_cmd(["git", "fetch", "upstream", "--tags", "+refs/heads/*:refs/remotes/upstream/*"])


def get_latest_stable_tag():
    """Find the highest semver stable tag v* from git."""
    res = run_cmd(["git", "tag", "-l", "v*"])
    tags = [t.strip() for t in res.stdout.splitlines() if t.strip()]

    # Filter out preview tags or non-semver
    stable_tags = []
    for tag in tags:
        match = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", tag)
        if match:
            major, minor, patch = map(int, match.groups())
            stable_tags.append(((major, minor, patch), tag))

    if not stable_tags:
        raise RuntimeError("No stable tags matching v* found in repository!")

    stable_tags.sort(key=lambda x: x[0])
    latest_tag = stable_tags[-1][1]
    return latest_tag


def resolve_commit_sha(ref):
    """Resolve a git ref to commit SHA."""
    res = run_cmd(["git", "rev-parse", f"{ref}^{{commit}}"])
    return res.stdout.strip()


def check_git_clean():
    """Ensure no uncommitted changes in tracked files (ignore untracked)."""
    res = run_cmd(["git", "status", "--porcelain", "-uno"])
    if res.stdout.strip():
        raise RuntimeError(
            "Working directory has uncommitted tracked changes. "
            "Please stash or commit before running catchup:\n"
            + res.stdout.strip()
        )


def check_patch_already_applied(patch_path):
    """
    Check if a patch is already present in the current HEAD.
    If 'git apply --check -R' succeeds, the patch changes are already in the tree!
    """
    res = run_cmd(["git", "apply", "--check", "-R", str(patch_path)], check=False)
    return res.returncode == 0


def get_file_sha256(path):
    """Compute sha256 of file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class CatchupRunner:
    def __init__(self, target_ref=None, channel=DEFAULT_CHANNEL, build_id=DEFAULT_BUILD_ID,
                 skip_tests=False, dry_run=False, clean=False):
        self.target_ref = target_ref
        self.channel = channel
        self.build_id = build_id
        self.skip_tests = skip_tests
        self.dry_run = dry_run
        self.clean = clean
        self.report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "target_ref": None,
            "target_sha": None,
            "release_branch": None,
            "channel": channel,
            "build_id": build_id,
            "patches": [],
            "binary_path": None,
            "binary_version": None,
            "binary_sha256": None,
            "tests_passed": False,
            "status": "INIT",
        }

    def run(self):
        check_git_clean()
        ensure_upstream_remote()
        fetch_upstream()

        # Determine target ref
        if not self.target_ref:
            self.target_ref = get_latest_stable_tag()
            print(f"Targeting latest upstream stable release: {self.target_ref}")
        else:
            print(f"Targeting specified ref: {self.target_ref}")

        target_sha = resolve_commit_sha(self.target_ref)
        self.report["target_ref"] = self.target_ref
        self.report["target_sha"] = target_sha

        # Sanitized branch name: e.g. vantt/v0.9.1 or vantt/upstream_master
        clean_tag_name = self.target_ref.replace("refs/tags/", "").replace("upstream/", "")
        release_branch = f"vantt/{clean_tag_name}"
        self.report["release_branch"] = release_branch

        print(f"Target commit: {target_sha[:10]}")
        print(f"Release branch: {release_branch}")

        # Load patch series
        patches = parse_series_toml(SERIES_FILE)
        print(f"Loaded {len(patches)} patch(es) from {SERIES_FILE}")

        if self.dry_run:
            print("\n[DRY RUN] Plan summary:")
            print(f"  Target: {self.target_ref} ({target_sha[:10]})")
            print(f"  Branch: {release_branch}")
            print(f"  Patches to evaluate:")
            for p in patches:
                print(f"    - [{p.get('id')}] {p.get('name')}")
            self.report["status"] = "DRY_RUN_COMPLETE"
            return self.report

        # Check Idempotency
        # Check if release_branch already exists
        branch_exists = run_cmd(
            ["git", "rev-parse", "--verify", release_branch], check=False
        ).returncode == 0

        target_bin = REPO_ROOT / "target" / "release" / "herdr"

        if branch_exists and not self.clean:
            # Check if this branch is already checked out or valid
            print(f"Branch '{release_branch}' already exists. Checking state...")
            run_cmd(["git", "checkout", release_branch])
            
            # Verify if binary exists and version matches
            if target_bin.exists():
                ver_res = run_cmd([str(target_bin), "--version"], check=False)
                expected_suffix = f"{self.channel}.{self.build_id}"
                if ver_res.returncode == 0 and expected_suffix in ver_res.stdout:
                    print(f"Branch '{release_branch}' already built and verified: {ver_res.stdout.strip()}")
                    self.report["status"] = "IDEMPOTENT_ALREADY_VERIFIED"
                    self.report["binary_path"] = str(target_bin)
                    self.report["binary_version"] = ver_res.stdout.strip()
                    self.report["binary_sha256"] = get_file_sha256(target_bin)
                    self.report["tests_passed"] = True
                    return self.report

        # Create or reset release branch from target ref
        print(f"Checking out clean release branch '{release_branch}' from {target_sha[:10]}...")
        run_cmd(["git", "checkout", "-B", release_branch, target_sha])

        # Apply patches in series
        for idx, patch in enumerate(patches):
            p_id = patch.get("id")
            p_name = patch.get("name")
            p_file = PATCHES_DIR / patch.get("patch_file")
            p_status = patch.get("upstream_status", "unsubmitted")

            print(f"\nEvaluating patch [{idx+1}/{len(patches)}]: {p_id} ('{p_name}')")

            if not p_file.exists():
                raise FileNotFoundError(f"Patch file not found: {p_file}")

            # Check if upstream already incorporated this patch
            if p_status == "merged" or check_patch_already_applied(p_file):
                print(f"  -> SKIPPED: Changes already present in upstream {self.target_ref}")
                self.report["patches"].append({
                    "id": p_id,
                    "name": p_name,
                    "status": "SKIPPED_UPSTREAM_MERGED",
                })
                continue

            # Apply patch
            print(f"  -> Applying patch: {p_file.name}...")
            apply_res = run_cmd(["git", "apply", "--3way", str(p_file)], check=False)

            if apply_res.returncode != 0:
                print(f"  [!] CONFLICT applying patch '{p_id}'!")
                # Find conflicted files
                unmerged = run_cmd(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
                conflicted_files = [f.strip() for f in unmerged.stdout.splitlines() if f.strip()]
                
                # Save state
                state = {
                    "target_ref": self.target_ref,
                    "target_sha": target_sha,
                    "release_branch": release_branch,
                    "channel": self.channel,
                    "build_id": self.build_id,
                    "failed_patch_index": idx,
                    "failed_patch_id": p_id,
                    "conflicted_files": conflicted_files,
                }
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)

                print("\n========================================================")
                print("CONFLICT OCCURRED DURING CATCHUP")
                print(f"Patch ID: {p_id}")
                print(f"Patch Name: {p_name}")
                print(f"Conflicted Files:\n  " + "\n  ".join(conflicted_files))
                print(f"Metadata & Invariant reference: {patch.get('metadata_file')}")
                print("Action Required:")
                print("  1. Resolve conflicts in the working directory following invariants.")
                print("  2. Run 'git add <resolved-files>'")
                print("  3. Run 'python3 vantt/scripts/catchup.py --continue'")
                print("========================================================\n")

                self.report["status"] = "CONFLICT"
                self.report["failed_patch"] = p_id
                self.report["conflicted_files"] = conflicted_files
                return self.report

            # Commit the patch
            run_cmd(["git", "add", "-A"])
            run_cmd(["git", "commit", "-m", p_name])
            print(f"  -> Successfully applied and committed: {p_id}")
            self.report["patches"].append({
                "id": p_id,
                "name": p_name,
                "status": "APPLIED",
            })

        # Build release binary
        print("\nBuilding release binary with fork identity...")
        build_env = {
            "HERDR_BUILD_CHANNEL": self.channel,
            "HERDR_BUILD_ID": self.build_id,
        }
        run_cmd(
            ["cargo", "build", "--release", "--locked", "--bin", "herdr"],
            env=build_env,
            capture=False,
        )

        if not target_bin.exists():
            raise RuntimeError(f"Build succeeded but binary not found at: {target_bin}")

        # Verify version and feature
        ver_res = run_cmd([str(target_bin), "--version"])
        binary_version = ver_res.stdout.strip()
        print(f"Verified binary version: {binary_version}")

        help_res = run_cmd([str(target_bin), "agent", "start", "--help"])
        if "--executable" not in help_res.stdout:
            raise RuntimeError("Binary verification failed: '--executable' missing from 'agent start --help'!")
        print("Verified capability: 'herdr agent start --help' exhibits '--executable'.")

        self.report["binary_path"] = str(target_bin)
        self.report["binary_version"] = binary_version
        self.report["binary_sha256"] = get_file_sha256(target_bin)

        # Run tests
        if not self.skip_tests:
            print("\nRunning verification tests...")
            for patch in patches:
                test_cmd = patch.get("test_command")
                if test_cmd:
                    print(f"Running test for [{patch.get('id')}]: {test_cmd}")
                    run_cmd(test_cmd, env=build_env, capture=False)
            self.report["tests_passed"] = True
        else:
            print("\nSkipping tests (--skip-tests specified).")
            self.report["tests_passed"] = None

        # Clean state file if exists
        if STATE_FILE.exists():
            STATE_FILE.unlink()

        self.report["status"] = "SUCCESS"
        print(f"\n>>> CATCHUP SUCCESSFUL on branch '{release_branch}'! <<<")
        print(f"Artifact: {target_bin}")
        print(f"Version:  {binary_version}")
        print(f"Install:  python3 vantt/scripts/install.py\n")
        return self.report

    def continue_after_conflict(self):
        """Resume catchup after conflict resolution."""
        if not STATE_FILE.exists():
            raise RuntimeError("No active catchup conflict state found to continue!")

        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Verify no unresolved merge conflicts remain
        unmerged = run_cmd(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
        if unmerged.stdout.strip():
            raise RuntimeError("Unresolved conflicts still remain:\n" + unmerged.stdout.strip())

        patches = parse_series_toml(SERIES_FILE)
        failed_idx = state["failed_patch_index"]
        p_name = patches[failed_idx]["name"]

        print(f"Committing resolved patch: {p_name}")
        run_cmd(["git", "add", "-A"])
        run_cmd(["git", "commit", "-m", p_name])

        # Resume remaining patches
        self.target_ref = state["target_ref"]
        self.channel = state["channel"]
        self.build_id = state["build_id"]

        print("Resuming catchup for remaining patches...")
        STATE_FILE.unlink()
        return self.run()

    def abort(self):
        """Abort catchup and clean up state."""
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            STATE_FILE.unlink()
            print("Aborting catchup and resetting uncommitted changes...")
            run_cmd(["git", "reset", "--hard", "HEAD"])
            print("Catchup aborted.")
        else:
            print("No catchup state to abort.")


def main():
    parser = argparse.ArgumentParser(description="Catch up Herdr fork with upstream release.")
    parser.add_argument("--ref", help="Upstream git ref to catch up to (default: latest stable v*)")
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help=f"Build channel identifier (default: {DEFAULT_CHANNEL})")
    parser.add_argument("--build-id", default=DEFAULT_BUILD_ID, help=f"Build ID (default: {DEFAULT_BUILD_ID})")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests after build")
    parser.add_argument("--dry-run", action="store_true", help="Show execution plan without modifying git or building")
    parser.add_argument("--clean", action="store_true", help="Force rebuild even if branch already green")
    parser.add_argument("--continue", dest="cont", action="store_true", help="Resume after resolving conflict")
    parser.add_argument("--abort", action="store_true", help="Abort ongoing catchup")
    parser.add_argument("--json", action="store_true", help="Output report in JSON format")

    args = parser.parse_args()

    runner = CatchupRunner(
        target_ref=args.ref,
        channel=args.channel,
        build_id=args.build_id,
        skip_tests=args.skip_tests,
        dry_run=args.dry_run,
        clean=args.clean,
    )

    if args.abort:
        runner.abort()
        sys.exit(0)

    if args.cont:
        report = runner.continue_after_conflict()
    else:
        report = runner.run()

    if args.json:
        print("\n" + json.dumps(report, indent=2))

    if report.get("status") in ["SUCCESS", "IDEMPOTENT_ALREADY_VERIFIED", "DRY_RUN_COMPLETE"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
