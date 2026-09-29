---
name: herdr-catchup
description: Catch up the vantt/herdr fork to the latest upstream release (or a specified ref), reapply all feature patches, build the release binary, and run verification tests.
---

# Herdr Fork Upstream Catchup

Use this skill whenever you need to bring the fork `vantt/herdr` up to date with a new release of `herdrdev/herdr`, or test the patch series against an upstream preview or master commit.

## Safety Rules

- Never replace `~/.local/bin/herdr` automatically.
- Never restart background gateways (`fgos gateway`) or terminate active user sessions.
- Never force-push or rebase over existing green release branches (`vantt/v*`).
- Always run tests and verify binary version before reporting success.

## Workflow

### 1. Catch up to latest upstream release
Run the catchup script from the repo root:

```bash
python3 vantt/scripts/catchup.py
```

This will:
1. Fetch latest tags from `upstream` (`herdrdev/herdr`).
2. Identify the highest stable release tag (`v*`).
3. Checkout a dedicated release branch: `vantt/<tag>`.
4. Apply the patch series defined in `vantt/patches/series.toml`.
5. Compile the release binary with fork identity (`0.9.1-vantt.1`).
6. Run unit tests and verify `--executable` appears in `herdr agent start --help`.

### 2. Catch up to a specific ref (preview tag or master)
To test early against upstream master:

```bash
python3 vantt/scripts/catchup.py --ref upstream/master
```

### 3. Handling Conflicts
If a patch encounters a merge conflict, `catchup.py` halts, leaves the conflicted working tree intact, and saves `.catchup_state.json`.

To resolve:
1. Read the invariant guide referenced in `vantt/patches/<patch-id>-spec.md` (or `metadata_file` in `series.toml`).
2. Inspect conflicted files: `git diff --name-only --diff-filter=U`.
3. Resolve conflicts according to the stated invariants (do not alter semantics).
4. Stage resolved files: `git add <files>`.
5. Resume catchup:
   ```bash
   python3 vantt/scripts/catchup.py --continue
   ```

### 4. Installing the Built Binary
Installation is an explicit manual step:

```bash
# Check before installing
python3 vantt/scripts/install.py --dry-run

# Perform installation (automatically creates ~/.local/bin/herdr.bak-*)
python3 vantt/scripts/install.py
```

To rollback:
```bash
python3 vantt/scripts/install.py --rollback
```
