#!/usr/bin/env bash
# Installs Face Guard for the current user. Creates the "faceguard" conda
# environment if it's missing, unless you pass a python to use instead.
# Usage: ./install.sh [path to a python that has the packages in environment.yml]
set -euo pipefail

UUID="faceguard@lviola"
ENV_NAME="faceguard"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/extension"
TARGET="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$UUID"

fail() {
    echo "error: $1" >&2
    exit 1
}

conda_env_python() {
    command -v conda >/dev/null || fail "conda not found. Install it, or pass a python path."
    if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
        echo "Creating the $ENV_NAME conda environment. This downloads several GB." >&2
        conda env create --yes --file "$ROOT/environment.yml" >&2
    fi
    conda run --name "$ENV_NAME" python -c 'import sys; print(sys.executable)'
}

PYTHON="${1:-$(conda_env_python)}"

"$PYTHON" -c 'import insightface, onnxruntime, cv2' 2>/dev/null ||
    fail "$PYTHON can't import insightface, onnxruntime and cv2. To repair the environment, run: conda env update --name $ENV_NAME --file $ROOT/environment.yml"

# Done here rather than on first use, when it would look like a hang in the panel.
echo "Preparing buffalo_l. The first time, this downloads the models and builds the GPU cache."
PREPARED="$(PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$SOURCE/daemon/faceguard_daemon.py" --prepare | tail -n 1 || true)"
case "$PREPARED" in
    *'"prepared"'*CUDAExecutionProvider*) echo "buffalo_l is ready and using the GPU." ;;
    *'"prepared"'*) echo "warning: buffalo_l is ready but running on the CPU, which is much slower." >&2 ;;
    *) fail "couldn't prepare buffalo_l: ${PREPARED:-the daemon stopped without a message}" ;;
esac

mkdir -p "$TARGET"
rm -rf "${TARGET:?}"/*
cp -r "$SOURCE"/. "$TARGET"/
find "$TARGET" -name __pycache__ -type d -prune -exec rm -rf {} +
glib-compile-schemas "$TARGET/schemas"
gsettings --schemadir "$TARGET/schemas" set org.gnome.shell.extensions.faceguard python-path "$PYTHON"

echo "Installed to $TARGET, using $PYTHON"
if gnome-extensions list 2>/dev/null | grep -qx "$UUID"; then
    echo "Next: gnome-extensions disable $UUID && gnome-extensions enable $UUID"
else
    echo "Next: log out and back in, then run: gnome-extensions enable $UUID"
fi
