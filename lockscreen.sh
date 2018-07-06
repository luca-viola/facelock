#!/usr/bin/env bash

OS=`uname -s | cut -d "_" -f 1`

if [ "$OS" == "Darwin" ]; then
  /bin/echo 'tell application "Finder" to sleep' | /usr/bin/osascript
else
  /usr/bin/cinnamon-screensaver-command  --lock
fi
