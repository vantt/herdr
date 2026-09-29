#!/bin/sh
set -eu

# Herdr Fork Installer for vantt/herdr
# Downloads the latest verified binary release from GitHub and installs safely.

REPO="vantt/herdr"
INSTALL_DIR="${HERDR_INSTALL_DIR:-$HOME/.local/bin}"
TARGET="$INSTALL_DIR/herdr"

usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --version <tag>   Install a specific release tag (default: latest)"
    echo "  --dry-run         Check latest version and download URL without installing"
    echo "  --rollback        Rollback to the most recent backup"
    echo "  -h, --help        Show this help message"
    exit 0
}

log() {
    printf "==> %s\n" "$*"
}

err() {
    printf "Error: %s\n" "$*" >&2
    exit 1
}

# Parse options
SPECIFIC_TAG=""
DRY_RUN=0
ROLLBACK=0

while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            shift
            [ $# -gt 0 ] || err "--version requires a tag argument"
            SPECIFIC_TAG="$1"
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        --rollback)
            ROLLBACK=1
            ;;
        -h|--help)
            usage
            ;;
        *)
            err "Unknown option: $1"
            ;;
    esac
    shift
done

# Handle rollback
if [ "$ROLLBACK" -eq 1 ]; then
    log "Looking for backup files in $INSTALL_DIR..."
    LATEST_BAK="$(ls -t "$TARGET".bak-* 2>/dev/null | head -n 1 || true)"
    if [ -z "$LATEST_BAK" ]; then
        err "No backup found matching $TARGET.bak-*"
    fi
    log "Restoring from $LATEST_BAK -> $TARGET"
    cp "$LATEST_BAK" "$TARGET"
    chmod 755 "$TARGET"
    log "Rollback successful. Version: $("$TARGET" --version)"
    exit 0
fi

# 1. Detect OS & CPU architecture
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) arch="x86_64" ;;
    aarch64|arm64) arch="aarch64" ;;
    *) err "Unsupported CPU architecture: $ARCH" ;;
esac

if [ "$OS" != "linux" ]; then
    err "Currently prebuilt binaries for vantt/herdr are provided for Linux ($OS detected). Build locally on macOS/Windows using: python3 vantt/scripts/catchup.py"
fi

log "Detected platform: ${OS}-${arch}"

# 2. Fetch release metadata from GitHub
if [ -n "$SPECIFIC_TAG" ]; then
    API_URL="https://api.github.com/repos/$REPO/releases/tags/$SPECIFIC_TAG"
    log "Fetching metadata for release $SPECIFIC_TAG from GitHub..."
else
    API_URL="https://api.github.com/repos/$REPO/releases/latest"
    log "Fetching latest release metadata from GitHub ($REPO)..."
fi

RELEASE_DATA="$(curl -fsSL --retry 3 --connect-timeout 10 "$API_URL" 2>/dev/null || true)"
if [ -z "$RELEASE_DATA" ]; then
    err "Could not connect to GitHub API or release not found at $API_URL"
fi

TAG_NAME="$(printf '%s\n' "$RELEASE_DATA" | grep '"tag_name":' | head -n 1 | cut -d '"' -f 4)"
TARBALL_URL="$(printf '%s\n' "$RELEASE_DATA" | grep "browser_download_url.*herdr-${OS}-${arch}\.tar\.gz" | head -n 1 | cut -d '"' -f 4 || true)"

if [ -z "$TARBALL_URL" ]; then
    # Fallback to any linux x86_64 tarball in release assets
    TARBALL_URL="$(printf '%s\n' "$RELEASE_DATA" | grep "browser_download_url.*${arch}.*\.tar\.gz" | head -n 1 | cut -d '"' -f 4 || true)"
fi

if [ -z "$TARBALL_URL" ]; then
    err "No asset matching herdr-${OS}-${arch}.tar.gz found in release $TAG_NAME. Check https://github.com/$REPO/releases"
fi

log "Target release: $TAG_NAME"
log "Download URL:   $TARBALL_URL"

if [ "$DRY_RUN" -eq 1 ]; then
    log "[DRY RUN] Would download $TARBALL_URL and install to $TARGET"
    exit 0
fi

# 3. Download and extract
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT INT TERM

log "Downloading binary..."
curl -fsSL --retry 3 --progress-bar "$TARBALL_URL" -o "$TMPDIR/herdr.tar.gz"

log "Extracting archive..."
tar -xzf "$TMPDIR/herdr.tar.gz" -C "$TMPDIR"

if [ ! -f "$TMPDIR/herdr" ]; then
    err "Extracted archive did not contain an executable named 'herdr'"
fi

chmod +x "$TMPDIR/herdr"

# 4. Safe installation with timestamped backup
mkdir -p "$INSTALL_DIR"
if [ -f "$TARGET" ]; then
    TIMESTAMP="$(date +%Y%m%d%H%M%S)"
    BACKUP="$TARGET.bak-$TIMESTAMP"
    log "Existing binary found. Creating backup: $BACKUP"
    cp "$TARGET" "$BACKUP"
fi

log "Installing binary to $TARGET..."
cp "$TMPDIR/herdr" "$TARGET"
chmod 755 "$TARGET"

# 5. Verify installation
log "Verifying installed binary..."
INSTALLED_VER="$("$TARGET" --version 2>/dev/null || true)"
log "Version: $INSTALLED_VER"

if "$TARGET" agent start --help 2>&1 | grep -q -- '--executable'; then
    log "Capability verification: PASS (--executable flag confirmed)"
else
    printf "Warning: --executable flag not exhibited in help text!\n" >&2
fi

echo ""
echo "======================================================================"
echo " SUCCESS: Herdr fork ($TAG_NAME) installed to $TARGET"
echo "======================================================================"
echo " NOTE: Any existing running sessions or background gateway (forgentX)"
echo "       will continue running with the previous binary until restarted."
echo " When you are ready to use the new binary with forgentX gateway:"
echo "   fgos gateway stop && fgos gateway start"
echo ""
echo " In case of any unexpected issues, rollback instantly with:"
echo "   curl -fsSL https://raw.githubusercontent.com/$REPO/master/vantt/install.sh | sh -s -- --rollback"
echo "======================================================================"
