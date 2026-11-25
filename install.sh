#!/usr/bin/env bash
# Installs Facelock for the current user, on any distribution with GNOME and Python 3.
# Its Python packages go in their own environment in ~/.local/share/facelock/venv. If there's
# an NVIDIA GPU, asks whether to use it. --dlib adds the dlib models, from an unofficial build.
# Usage: ./install.sh [--cpu | --gpu] [--dlib] [path to a python that already has the packages]
set -euo pipefail

UUID="facelock@lviola"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/extension"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
TARGET="$DATA/gnome-shell/extensions/$UUID"
VENV="$DATA/facelock/venv"
OLD_UUID="faceguard@lviola"
OLD_TARGET="$DATA/gnome-shell/extensions/$OLD_UUID"
PYTHON_VERSION=3.12  # what the pinned packages have wheels for; uv downloads it if it's missing
INSIGHTFACE=insightface==2.1
UV_VERSION=0.13.9
ARCH="$(uname -m)"

fail() {
    echo "error: $1" >&2
    exit 1
}

usage() {
    echo "Usage: ./install.sh [--cpu | --gpu] [--dlib] [path to a python that already has the packages]"
}

COMPUTE=""
DLIB=""
PYTHON=""
for argument in "$@"; do
    case "$argument" in
        --cpu | --gpu)
            [ -z "$COMPUTE" ] || fail "pass only one of --cpu and --gpu"
            COMPUTE="${argument#--}"
            ;;
        --dlib) DLIB=1 ;;
        -h | --help) usage; exit 0 ;;
        -*) usage >&2; fail "unknown option $argument" ;;
        *)
            [ -z "$PYTHON" ] || fail "pass only one python"
            PYTHON="$argument"
            ;;
    esac
done
[ -z "$PYTHON" ] || [ -z "$COMPUTE$DLIB" ] || fail "--cpu, --gpu and --dlib can't be combined with your own python"

# Everything is checked before anything is downloaded or changed.
for tool in python3 glib-compile-schemas gsettings gnome-extensions; do
    command -v "$tool" >/dev/null || fail "$tool not found. Install the package that provides it and run this again."
done

# Prints the NVIDIA GPU's name if its driver works. Other GPUs can't run the models:
# onnxruntime has no Vulkan support, and its WebGPU plugin doesn't find GPUs that aren't on PCI,
# such as Apple silicon's.
nvidia_gpu() {
    PYTHONDONTWRITEBYTECODE=1 python3 - "$SOURCE/daemon/backends" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import devices
print(devices.gpu_name() or "")
PY
}

# Moves the settings, photo and models of Face Guard, Facelock's old name, and removes it.
migrate_face_guard() {
    local old=org.gnome.shell.extensions.faceguard key value
    echo "Moving your settings and reference photo from Face Guard."
    if [ -n "$NEW_INSTALL" ]; then
        while read -r key; do
            case "$key" in python-path | enroll-active) continue ;; esac
            if ! value="$(gsettings --schemadir "$OLD_TARGET/schemas" get "$old" "$key" 2>/dev/null)" ||
                ! gsettings --schemadir "$TARGET/schemas" set org.gnome.shell.extensions.facelock "$key" "$value"; then
                echo "Couldn't move the setting $key." >&2
            fi
        done < <(gsettings --schemadir "$OLD_TARGET/schemas" list-keys "$old" 2>/dev/null)
    fi
    mkdir -p "$DATA/facelock" || return 1
    for key in reference.jpg models; do
        if [ -e "$DATA/faceguard/$key" ] && [ ! -e "$DATA/facelock/$key" ]; then
            mv "$DATA/faceguard/$key" "$DATA/facelock/$key" || return 1
        fi
    done
    # Edited directly, since gnome-extensions can't enable what GNOME Shell hasn't loaded yet.
    value="$(gsettings get org.gnome.shell enabled-extensions)" || return 1
    case "$value" in
        *"'$UUID'"*) ;;
        *"'$OLD_UUID'"*) gsettings set org.gnome.shell enabled-extensions "${value//"'$OLD_UUID'"/"'$UUID'"}" || return 1 ;;
    esac
    rm -rf "${OLD_TARGET:?}" || return 1
    case "$PYTHON" in
        "$DATA/faceguard/venv/"*) ;;  # passed as an argument, so still in use
        *) rm -rf "$DATA/faceguard/venv" ;;
    esac
    rmdir "$DATA/faceguard" 2>/dev/null || true
}

choose_compute() {
    local gpu answer=""
    gpu="$(nvidia_gpu || true)"
    if [ "$COMPUTE" = gpu ]; then
        [ "$ARCH" = x86_64 ] || fail "--gpu needs an x86_64 computer, and this one is $ARCH. Run it without --gpu to use the CPU."
        [ -n "$gpu" ] || fail "no NVIDIA GPU with a working driver was found. Run it without --gpu to use the CPU."
    elif [ -z "$COMPUTE" ]; then
        COMPUTE=cpu
        if [ -n "$gpu" ] && [ "$ARCH" = x86_64 ]; then
            echo "Found a usable GPU: $gpu. It's faster than the CPU, but uses several hundred MB more"
            echo "memory and downloads a few GB."
            if [ -t 0 ]; then
                read -r -p "Use the GPU? [y/N] " answer || true
            else
                echo "Not asking, since there's no terminal. Pass --gpu to use it."
            fi
            case "$answer" in [yY]*) COMPUTE=gpu ;; esac
        fi
    fi
}

# Sets UV to the installed uv, or to a pinned copy downloaded to a temporary folder.
find_uv() {
    UV="$(type -P uv || true)"
    [ -z "$UV" ] || return 0
    local sha tag
    case "$ARCH" in
        x86_64)
            tag=manylinux_2_17_x86_64.manylinux2014_x86_64
            sha=d7f459fe4fd247d830351c75686d3996ace3c6f3f728eb0e85a30b7ada0cef19 ;;
        aarch64)
            tag=manylinux_2_28_aarch64
            sha=ecb6028d79dc96fbeafffe5c8af62a7099487ebc05a701e76714eebcffd06375 ;;
    esac
    WORK="$(mktemp -d)"
    trap 'rm -rf "$WORK"' EXIT
    echo "Downloading uv $UV_VERSION, which sets up the Python environment."
    python3 -I - "$UV_VERSION" "uv-$UV_VERSION-py3-none-$tag.whl" "$sha" "$WORK/uv" <<'PY' || fail "couldn't download uv. Check your connection."
import hashlib, io, json, os, sys, urllib.request, zipfile
version, filename, sha, target = sys.argv[1:]
with urllib.request.urlopen(f"https://pypi.org/pypi/uv/{version}/json", timeout=60) as response:
    url = next(f["url"] for f in json.load(response)["urls"] if f["filename"] == filename)
with urllib.request.urlopen(url, timeout=60) as response:
    wheel = response.read()
if hashlib.sha256(wheel).hexdigest() != sha:
    sys.exit("uv's checksum doesn't match")
with open(target, "wb") as file:
    file.write(zipfile.ZipFile(io.BytesIO(wheel)).read(f"uv-{version}.data/scripts/uv"))
os.chmod(target, 0o755)
PY
    UV="$WORK/uv"
}

create_environment() {
    case "$ARCH" in
        x86_64 | aarch64) ;;
        *) fail "there are no packages for $ARCH. Pass a python that has insightface, onnxruntime and cv2." ;;
    esac
    choose_compute
    find_uv
    if [ ! -x "$VENV/bin/python" ]; then
        # Asked for explicitly, since uv can be configured not to download a Python by itself.
        "$UV" python find "$PYTHON_VERSION" >/dev/null 2>&1 || "$UV" python install --no-bin "$PYTHON_VERSION"
        "$UV" venv --clear --python "$PYTHON_VERSION" "$VENV"
    fi
    PYTHON="$VENV/bin/python"
    # The two onnxruntime packages share files, so one can't be installed over the other.
    local requirements=requirements-cpu.txt other=onnxruntime-gpu
    if [ "$COMPUTE" = gpu ]; then requirements=requirements-cuda.txt other=onnxruntime; fi
    if "$UV" pip show --python "$PYTHON" "$other" >/dev/null 2>&1; then
        "$UV" pip uninstall --python "$PYTHON" onnxruntime onnxruntime-gpu
    fi
    "$UV" pip install --python "$PYTHON" --only-binary :all: -r "$ROOT/requirements.txt" -r "$ROOT/$requirements"
    "$UV" pip install --python "$PYTHON" --only-binary :all: --no-deps "$INSIGHTFACE"
    if [ -n "$DLIB" ]; then
        "$UV" pip install --python "$PYTHON" --only-binary :all: --no-deps --require-hashes -r "$ROOT/requirements-dlib.txt"
        "$PYTHON" -c 'import dlib' || fail "dlib was installed but can't be loaded; the reason is above."
    fi
}

if [ -z "$PYTHON" ]; then
    create_environment
else
    PYTHON="$(type -P "$PYTHON")" || fail "can't run that python"
    case "$PYTHON" in /*) ;; *) PYTHON="$PWD/$PYTHON" ;; esac
fi

"$PYTHON" -c 'import insightface, onnxruntime, cv2' ||
    fail "$PYTHON can't import the packages Facelock needs; the reason is above. If it's the environment in $VENV, delete that folder and run this again."

DAEMON="$SOURCE/daemon/facelock_daemon.py"

# Done here rather than on first use, when it would look like a hang in the panel.
# Other models are downloaded when first chosen in Settings.
echo "Preparing the default model, buffalo_l. The first time, this downloads it."
PREPARED="$(PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$DAEMON" --prepare | tail -n 1 || true)"
case "$PREPARED" in
    *'"prepared"'*) echo "buffalo_l is ready." ;;
    *) fail "couldn't prepare buffalo_l: ${PREPARED:-the daemon stopped without a message}" ;;
esac
if [ "$COMPUTE" = gpu ]; then
    case "$(PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$DAEMON" --prepare --compute gpu | tail -n 1 || true)" in
        *'"compute": "gpu"'*) echo "The GPU works." ;;
        *) fail "the model couldn't run on the GPU. Run ./install.sh --cpu to use the CPU." ;;
    esac
fi

NEW_INSTALL=""
[ -d "$TARGET" ] || NEW_INSTALL=1
mkdir -p "$TARGET"
rm -rf "${TARGET:?}"/*
cp -r "$SOURCE"/. "$TARGET"/
find "$TARGET" -name __pycache__ -type d -prune -exec rm -rf {} +
glib-compile-schemas "$TARGET/schemas"
# Most people never had Face Guard, and leftovers of it mustn't stop the install.
if [ -d "$OLD_TARGET" ]; then
    migrate_face_guard || echo "Couldn't move everything from Face Guard. What's left is in $OLD_TARGET and $DATA/faceguard." >&2
fi
gsettings --schemadir "$TARGET/schemas" set org.gnome.shell.extensions.facelock python-path "$PYTHON"
if [ -n "$COMPUTE" ]; then
    gsettings --schemadir "$TARGET/schemas" set org.gnome.shell.extensions.facelock use-gpu \
        "$([ "$COMPUTE" = gpu ] && echo true || echo false)"
fi

echo "Installed to $TARGET, using $PYTHON"
if gnome-extensions list 2>/dev/null | grep -qx "$UUID"; then
    # GNOME Shell keeps an extension's code in memory, so disabling and enabling it
    # isn't enough for an update.
    echo "Next: log out and back in to load the new version."
elif gsettings get org.gnome.shell enabled-extensions 2>/dev/null | grep -qF "'$UUID'"; then
    echo "Next: log out and back in."
else
    echo "Next: log out and back in, then run: gnome-extensions enable $UUID"
fi
