#!/bin/bash
# Opens a URL in a new full-screen window of a browser, instead of a tab in an existing window.
# Usage: open-fullscreen.sh URL [browser]    (browser defaults to Microsoft Edge)
# Works with Chromium browsers (Edge, Google Chrome, Brave) and Safari. Clicking the View
# menu needs the Accessibility permission for the app running this.
set -euo pipefail

URL="${1:?usage: open-fullscreen.sh URL [browser]}"
BROWSER="${2:-Microsoft Edge}"

if [ "$BROWSER" = "Safari" ]; then
    osascript - "$URL" <<'APPLESCRIPT'
on run {pageAddress}
    tell application "Safari"
        activate
        make new document with properties {URL:pageAddress}
    end tell
end run
APPLESCRIPT
else
    # The browser's name goes into the script itself, because AppleScript can only
    # resolve its "URL of" terms for an application it knows when compiling.
    osascript - "$URL" <<APPLESCRIPT
on run {pageAddress}
    tell application "$BROWSER"
        activate
        set newWindow to make new window
        set URL of active tab of newWindow to pageAddress
    end tell
end run
APPLESCRIPT
fi

sleep 1  # the new window must exist before the menu can act on it
# The View menu rather than a key press, which didn't reach the new window reliably.
osascript - "$BROWSER" <<'APPLESCRIPT'
on run {browserName}
    tell application "System Events"
        tell process browserName
            set frontmost to true
            click menu item "Enter Full Screen" of menu "View" of menu bar 1
        end tell
    end tell
end run
APPLESCRIPT
