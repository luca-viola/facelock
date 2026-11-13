#!/usr/bin/env bash
# Builds FaceGuard.app signed with a Developer ID, notarizes it, staples the ticket and zips it
# to hand out: dist/FaceGuard.app and dist/FaceGuard.zip.
#
# Needs a "Developer ID Application" certificate in the keychain and notarytool credentials
# stored once with:
#   xcrun notarytool store-credentials <profile> --apple-id <id> --team-id <team>
# The profile name is taken from NOTARY_PROFILE (default: snappo-notary, the one Snappo uses).
#
# The app runs the Python daemon, so this build records no Python path: whoever uses it sets
# one in Settings, under Advanced.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

IDENTITY="${IDENTITY:-$(security find-identity -v -p codesigning | awk '/Developer ID Application/ {print $2; exit}')}"
PROFILE="${NOTARY_PROFILE:-snappo-notary}"
[ -n "$IDENTITY" ] || { echo "error: no Developer ID Application certificate found" >&2; exit 1; }

NO_PYTHON_PATH=1 ./build-app.sh "$IDENTITY"

APP="dist/FaceGuard.app"
ZIP="dist/FaceGuard.zip"
codesign --verify --deep --strict "$APP"

ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
spctl --assess --type execute --verbose "$APP"

# Zips again, now with the ticket stapled.
rm "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
echo "Done: $APP and $ZIP"
