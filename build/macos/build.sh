#!/bin/bash
# build/macos/build.sh — Lumina macOS Production Build Script
# Produces: release/Lumina-<version>-mac.dmg (signed optional)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🔷 Lumina macOS Build Script"
echo "   Project Root: $PROJECT_ROOT"
echo ""

cd "$PROJECT_ROOT"

# ── Node path ──────────────────────────────────────────────────────────────────
TOOLS_NODE="$PROJECT_ROOT/.tools/bin"
if [ -d "$TOOLS_NODE" ]; then
  export PATH="$TOOLS_NODE:$PATH"
fi

NODE_BIN=$(which node 2>/dev/null || echo "")
NPM_BIN=$(which npm 2>/dev/null || echo "")

if [ -z "$NODE_BIN" ]; then
  echo "❌ Node.js not found. Install Node.js v18+ or run: brew install node"
  exit 1
fi

echo "✓ Node: $($NODE_BIN -v)  npm: $($NPM_BIN -v)"

# ── Install npm deps ───────────────────────────────────────────────────────────
echo ""
echo "📦 Installing npm dependencies..."
$NPM_BIN ci --prefer-offline || $NPM_BIN install

# ── macOS-specific Python env check ───────────────────────────────────────────
PYTHON_ENV="$PROJECT_ROOT/python-dependencies/macos-intel"
if [ ! -d "$PYTHON_ENV" ]; then
  echo "⚠️  macOS bundled Python environment not found at:"
  echo "   $PYTHON_ENV"
  echo "   The packaged app will try system python3 as fallback."
else
  echo "✓ macOS Python environment: $PYTHON_ENV"
fi

# ── Run electron-builder for macOS ────────────────────────────────────────────
echo ""
echo "🏗️  Building macOS DMG..."
$NPM_BIN run build:mac -- --publish=never

echo ""
echo "✅ macOS build complete!"
echo "   Output: $PROJECT_ROOT/release/"
ls -lh "$PROJECT_ROOT/release/"*.dmg 2>/dev/null || echo "   (DMG files listed above)"
