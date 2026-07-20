#!/usr/bin/env bash
set -euo pipefail

# Git hooks run with a stripped PATH and never source shell profiles, so nvm's
# node is missing even when `node` works in your terminal. Bootstrap it here.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ensure_node() {
  if command -v node >/dev/null 2>&1; then
    return 0
  fi

  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ -s "$NVM_DIR/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "$NVM_DIR/nvm.sh"
    if [ -f "$ROOT/.nvmrc" ]; then
      nvm use --silent >/dev/null 2>&1 || nvm install --silent >/dev/null 2>&1
    fi
  fi

  if command -v node >/dev/null 2>&1; then
    return 0
  fi

  for dir in /opt/homebrew/bin /usr/local/bin; do
    if [ -x "$dir/node" ]; then
      export PATH="$dir:$PATH"
      return 0
    fi
  done

  echo "pre-commit prettier: node not found in PATH." >&2
  echo "Install Node $(cat "$ROOT/.nvmrc" 2>/dev/null || echo 22)+ and run: cd web && pnpm install" >&2
  exit 127
}

ensure_node

exec "$ROOT/web/node_modules/.bin/prettier" --write --ignore-unknown "$@"
