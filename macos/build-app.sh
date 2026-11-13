#!/usr/bin/env bash
# Builds dist/FaceGuard.app from the Swift package. The app uses the Python daemon shared with
# the GNOME extension, which it runs with the interpreter in ./.venv (make venv).
# Usage: ./build-app.sh [signing identity]    (default: your first Apple Development identity, else ad hoc)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE="$ROOT/FaceGuardApp"
APP="$ROOT/dist/FaceGuard.app"
BUNDLE_ID="io.github.luca-viola.faceguard"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || echo 0.1.0)"

# By hash, because a name can match more than one certificate.
IDENTITY="${1:-$(security find-identity -v -p codesigning | awk '/Apple Development/ {print $2; exit}')}"
IDENTITY="${IDENTITY:--}"

echo "Building…"
(cd "$PACKAGE" && swift build -c release)
BINARY="$(cd "$PACKAGE" && swift build -c release --show-bin-path)/FaceGuard"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BINARY" "$APP/Contents/MacOS/FaceGuard"
cp -R "$ROOT/../extension/daemon" "$APP/Contents/Resources/daemon"
find "$APP/Contents/Resources/daemon" -name __pycache__ -type d -prune -exec rm -rf {} +

# The interpreter that has insightface, onnxruntime and opencv.
if [ -x "$ROOT/.venv/bin/python" ]; then
    echo "$ROOT/.venv/bin/python" > "$APP/Contents/Resources/python-path.txt"
else
    echo "warning: no .venv found. Run 'make venv', or set the Python path in Settings." >&2
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>FaceGuard</string>
    <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
    <key>CFBundleName</key><string>Face Guard</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>LSMinimumSystemVersion</key><string>14.0</string>
    <key>LSUIElement</key><true/>
    <key>NSPrincipalClass</key><string>NSApplication</string>
    <key>NSCameraUsageDescription</key>
    <string>Face Guard watches the camera to tell whether you are at the screen and who else is looking at it.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>Face Guard hides your apps when someone else looks at the screen.</string>
</dict>
</plist>
PLIST

cat > "$ROOT/dist/FaceGuard.entitlements" <<'ENT'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.device.camera</key><true/>
    <key>com.apple.security.automation.apple-events</key><true/>
</dict>
</plist>
ENT

# A stable identity keeps the Camera and Automation permissions across rebuilds. An ad hoc
# signature changes every time, so macOS would ask again.
codesign --force --options runtime --entitlements "$ROOT/dist/FaceGuard.entitlements" \
    --sign "$IDENTITY" "$APP"
echo "Built $APP, signed with: $IDENTITY"
