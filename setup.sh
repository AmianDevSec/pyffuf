#!/usr/bin/env bash
# setup.sh — install pyffuf.py as a global `pyffuf` command.
#
# Usage:
#   ./setup.sh                       # install ./pyffuf.py
#   ./setup.sh /path/to/pyffuf.py    # install from a specific path
#   ./setup.sh --uninstall           # remove the installed command
#   ./setup.sh --help                # show this help

set -euo pipefail

# ───── Config ────────────────────────────────────────────────
INSTALL_DIR="${HOME}/.local/bin"
BIN_NAME="pyffuf"
SRC_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pyffuf.py"

# ───── Colors (only if stdout is a TTY) ──────────────────────
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m';  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_CYAN=$'\033[36m'; C_MAGENTA=$'\033[35m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""
  C_RED=""; C_GREEN=""; C_YELLOW=""
  C_CYAN=""; C_MAGENTA=""
fi

info()  { printf '%s[+]%s %s\n' "$C_GREEN"   "$C_RESET" "$*"; }
warn()  { printf '%s[!]%s %s\n' "$C_YELLOW"  "$C_RESET" "$*"; }
err()   { printf '%s[x]%s %s\n' "$C_RED"     "$C_RESET" "$*" >&2; }
title() { printf '%s%s%s\n'     "$C_BOLD$C_MAGENTA" "$*" "$C_RESET"; }

# ───── Argument parsing ──────────────────────────────────────
UNINSTALL=0
SRC=""

for a in "$@"; do
  case "$a" in
    --uninstall|-u) UNINSTALL=1 ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)  SRC="$a" ;;
  esac
done

# ───── Uninstall path ────────────────────────────────────────
if (( UNINSTALL )); then
  title "PyFfuf uninstall"
  TARGET="${INSTALL_DIR}/${BIN_NAME}"
  if [[ -e "$TARGET" ]]; then
    rm -f -- "$TARGET"
    info "Removed ${C_CYAN}${TARGET}${C_RESET}"
  else
    warn "Not installed at ${TARGET}"
  fi
  exit 0
fi

# ───── Locate source ─────────────────────────────────────────
[[ -z "$SRC" ]] && SRC="$SRC_DEFAULT"

if [[ ! -f "$SRC" ]]; then
  err "pyffuf.py not found at: $SRC"
  err "Pass the path explicitly:  $0 /path/to/pyffuf.py"
  exit 1
fi

if [[ ! -r "$SRC" ]]; then
  err "Cannot read: $SRC"
  exit 1
fi

# Soft sanity check — warn if it doesn't look like the script we expect
if ! head -n 1 "$SRC" | grep -q '^#!'; then
  warn "Source has no shebang; I'll add one."
fi
if ! grep -q 'PyFfuf' "$SRC" 2>/dev/null; then
  warn "Source doesn't mention 'PyFfuf' — installing anyway."
fi

# ───── Ensure install dir ────────────────────────────────────
title "Installing PyFfuf → ${INSTALL_DIR}/${BIN_NAME}"
mkdir -p -- "$INSTALL_DIR"

# ───── Ensure ~/.local/bin is on PATH ────────────────────────
case ":${PATH}:" in
  *":${INSTALL_DIR}:"*)
    info "PATH already contains ${C_CYAN}${INSTALL_DIR}${C_RESET}"
    ;;
  *)
    warn "${INSTALL_DIR} is not in your PATH — appending to shell rc files."
    LINE='export PATH="$HOME/.local/bin:$PATH"'
    touched=0
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
      [[ -f "$rc" ]] || continue
      if ! grep -Fxq "$LINE" "$rc" 2>/dev/null; then
        {
          printf '\n# Added by pyffuf setup.sh\n'
          printf '%s\n' "$LINE"
        } >> "$rc"
        info "Updated ${C_CYAN}${rc}${C_RESET}"
        touched=1
      fi
    done
    if (( touched )); then
      warn "Run:  ${C_BOLD}source ~/.bashrc${C_RESET}  (or open a new terminal)"
    fi
    ;;
esac

# ───── Install (copy + normalize shebang + chmod) ────────────
TARGET="${INSTALL_DIR}/${BIN_NAME}"

cp -f -- "$SRC" "$TARGET"

# Normalize the shebang to /usr/bin/env python3 (portable across systems)
tmp="$(mktemp)"
{ printf '#!/usr/bin/env python3\n'; tail -n +2 "$TARGET"; } > "$tmp"
mv -f -- "$tmp" "$TARGET"
chmod 0755 -- "$TARGET"

info "Installed ${C_CYAN}${TARGET}${C_RESET}"

# ───── Dependency check: ffuf ────────────────────────────────
if command -v ffuf >/dev/null 2>&1; then
  info "ffuf found: $(command -v ffuf)"
else
  warn "ffuf is NOT on your PATH — pyffuf will fail at runtime."
  warn "Install it:"
  warn "  go install github.com/ffuf/ffuf/v2@latest"
  warn "  # or: sudo apt install ffuf"
  warn "  # or: download a release binary from https://github.com/ffuf/ffuf/releases"
fi

# ───── Smoke test ────────────────────────────────────────────
if "${TARGET}" --help >/dev/null 2>&1; then
  info "Smoke test OK — try:  ${C_BOLD}pyffuf --help${C_RESET}"
else
  err "Installed file failed to run. Check:  ${TARGET} --help"
  exit 1
fi

title "Done."
echo
echo "Quick start:"
echo "  ${C_CYAN}cat > wl.txt <<EOF${C_RESET}"
echo "  ${C_CYAN}/usr/share/wordlists/dirb/common.txt${C_RESET}"
echo "  ${C_CYAN}/usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt${C_RESET}"
echo "  ${C_CYAN}EOF${C_RESET}"
echo
echo "  ${C_CYAN}pyffuf -f wl.txt -u 'http://target.htb/FUZZ' -opt -t 100 -ac${C_RESET}"
