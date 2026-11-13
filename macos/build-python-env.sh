#!/usr/bin/env bash
# Builds python-env/: a relocatable Python with everything the daemon needs, to go inside
# FaceGuard.app so it runs on a Mac with nothing installed. Needs uv and cmake on this Mac
# (brew install uv cmake), plus the Xcode command line tools, to build dlib once.
#
# Everything is built for macOS 14 (the app's minimum) on Apple silicon.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
ROOT="$PWD"
ENV="${PYTHON_ENV_DIR:-$ROOT/python-env}"
VERSION=3.12
export MACOSX_DEPLOYMENT_TARGET=14.0

# uv's own Python (python-build-standalone), not Homebrew's, which isn't relocatable.
uv python install "$VERSION"
SOURCE="$(dirname "$(dirname "$(realpath "$(uv python find --managed-python "$VERSION")")")")"

rm -rf "$ENV"
mkdir -p "$ENV"
cp -R "$SOURCE" "$ENV/python"
PYTHON="$ENV/python/bin/python$VERSION"
install() { uv pip install --python "$PYTHON" --break-system-packages "$@"; }

install --only-binary :all: -r requirements-bundle.txt
install --only-binary :all: --no-deps insightface

# dlib has no wheels, so it's built here. Its PNG and JPEG support must be its own bundled copies,
# compiled in statically: a system copy (Homebrew's, MacPorts', or XQuartz's, which is found on a
# Mac that has any of them) would be linked as an /opt/... library that other Macs don't have.
# dlib's find_libpng.cmake and find_libjpeg.cmake return at once if PNG_FOUND or JPEG_FOUND is
# already defined, so presetting them to 0 makes it use its own. GIF support is dropped, and the
# GUI would need X11. BLAS is Apple's Accelerate. dlib's setup.py turns every DLIB_* environment
# variable into a cmake option, and cmake reads the toolchain file from CMAKE_TOOLCHAIN_FILE.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
install setuptools wheel
"$PYTHON" -m pip download dlib --no-deps --no-binary :all: -d "$WORK" -q
tar -xzf "$WORK"/dlib-*.tar.gz -C "$WORK"
# dlib's bundled zlib 1.2.11 and libpng 1.6.37 take the macro TARGET_OS_MAC, which every modern
# macOS defines, to mean classic Mac OS 9, and then fail to compile (no <fp.h>, and fdopen()
# defined away). Later releases of both fixed it the same way.
sed -i '' 's/#if defined(MACOS) || defined(TARGET_OS_MAC)/#if defined(MACOS)/' "$WORK"/dlib-*/dlib/external/zlib/zutil.h
sed -i '' 's/defined(THINK_C) || defined(__SC__) || defined(TARGET_OS_MAC)/defined(THINK_C) || defined(__SC__)/' \
    "$WORK"/dlib-*/dlib/external/libpng/pngpriv.h
cat > "$WORK/no-system-libs.cmake" <<'CMAKE'
set(PNG_FOUND 0)
set(JPEG_FOUND 0)
set(CMAKE_DISABLE_FIND_PACKAGE_GIF TRUE)
set(CMAKE_IGNORE_PREFIX_PATH /opt/homebrew /usr/local /opt/X11 /opt/local /sw)
CMAKE
(cd "$WORK"/dlib-*/ && \
    CMAKE_TOOLCHAIN_FILE="$WORK/no-system-libs.cmake" DLIB_NO_GUI_SUPPORT=ON DLIB_USE_CUDA=OFF \
    "$PYTHON" setup.py bdist_wheel)
install --no-deps "$WORK"/dlib-*/dist/dlib-*.whl

# Things the daemon never uses.
rm -rf "$ENV/python/lib/python$VERSION/test" "$ENV/python/lib/python$VERSION/idlelib" \
       "$ENV/python/lib/python$VERSION/tkinter" "$ENV/python/share"
# Tcl/Tk, for tkinter, which was just removed.
rm -rf "$ENV"/python/lib/tcl9 "$ENV"/python/lib/tcl9.0 "$ENV"/python/lib/tk9.0 "$ENV"/python/lib/itcl* \
       "$ENV"/python/lib/thread* "$ENV"/python/lib/libtcl* "$ENV"/python/lib/libtk*
rm -f "$ENV"/python/lib/python$VERSION/lib-dynload/_tkinter*
find "$ENV" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$ENV/python/lib/python$VERSION/site-packages" -type d \( -name tests -o -name test \) -prune -exec rm -rf {} +

# Checks, so a bad environment fails here and not on someone else's Mac.
echo "Checking…"
env -i HOME="$HOME" "$PYTHON" -c "import cv2, dlib, insightface, numpy, onnxruntime; print('imports ok')"
# Anything that isn't a system library or inside the app would be missing on another Mac.
LEAKS="$(find "$ENV" -type f \( -name '*.so' -o -name '*.dylib' -o -perm +111 \) -print0 | xargs -0 -n 1 sh -c '
    file "$1" | grep -q Mach-O || exit 0
    # otool -L also lists a library'"'"'s own install name, which isn'"'"'t a dependency.
    OWN="$(otool -D "$1" | tail -n +2)"
    otool -L "$1" | tail -n +2 | awk "NF {print \$1}" | grep -vxF "$OWN" | grep -vxF "$1" \
        | grep -vE "^(/System/|/usr/lib/|@rpath/|@loader_path/|@executable_path/)" | sed "s|^|$1: |"
    true' _)"
if [ -n "$LEAKS" ]; then echo "error: libraries that other Macs won't have:" >&2; echo "$LEAKS" >&2; exit 1; fi

echo "Built $ENV ($(du -sh "$ENV" | cut -f1))"
