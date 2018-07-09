#!/usr/bin/env bash

xdg_path="$HOME/.local/share/applications"
facelock_desktop="$xdg_path/facelock.desktop"

exepath=`realpath ../facelock.py`
iconpath=`realpath ../tray.png`


desktopEntry="#!/usr/bin/env xdg-open  

[Desktop Entry]
Version=1.0
Name=Facelock
GenericName=Facelock
Terminal=false
Type=Application
Categories=Utility;Security;
Exec=\"${exepath}\"
Icon=${iconpath}
Icon[en_US]=${iconpath}"


if [ ! -f "$xdg_path/facelock.desktop" ]; then
  echo "${desktopEntry}" > "$xdg_path/facelock.desktop"
else
  echo "There is already a desktop file for facelock."
fi