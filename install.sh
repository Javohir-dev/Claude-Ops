#!/bin/sh
# Installs the `opsboard` command for this checkout and starts the dashboard.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"

case "$(uname -s)" in
  Darwin|Linux) ;;
  *) echo "Opsboard supports macOS and Linux only."; exit 1 ;;
esac

if [ -x /usr/bin/python3 ]; then PY=/usr/bin/python3; else PY="$(command -v python3 || true)"; fi
[ -n "$PY" ] || { echo "python3 not found — install Python 3.8 or newer."; exit 1; }
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 8))' || { echo "Python 3.8 or newer is required ($("$PY" --version))."; exit 1; }

command -v git >/dev/null || echo "note: git not found — 'opsboard update' will not work."
command -v docker >/dev/null || echo "note: docker not found — the Docker and Postgres pages will stay empty."
command -v claude >/dev/null || echo "note: Claude Code CLI not found — sessions still show, background fix runs will not."

chmod +x "$DIR/bin/opsboard" "$DIR/install.sh"
mkdir -p "$BIN"
cat > "$BIN/opsboard" <<EOF
#!/bin/sh
OPS_DASH_HOME="$DIR" exec "$DIR/bin/opsboard" "\$@"
EOF
chmod +x "$BIN/opsboard"
echo "installed: $BIN/opsboard -> $DIR"
if [ -f "$BIN/ops-dash" ]; then
  cp "$BIN/opsboard" "$BIN/ops-dash"
  echo "kept the old ops-dash command as an alias"
fi

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "add this line to your ~/.zshrc or ~/.bashrc, then open a new terminal:"
     echo "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

OPS_DASH_HOME="$DIR" "$DIR/bin/opsboard" up
