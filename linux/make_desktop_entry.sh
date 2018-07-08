#!/usr/bin/env bash

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


echo "${desktopEntry}"
