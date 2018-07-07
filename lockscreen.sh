#!/usr/bin/env bash

OS=`uname -s | cut -d "_" -f 1`

if [ "$OS" == "Darwin" ]; then
  /bin/echo 'tell application "Finder" to sleep' | /usr/bin/osascript
else
  case "$XDG_CURRENT_DESKTOP" in
    *CINNAMON*|*Cinnamon*|*cinnamon*)
      /usr/bin/cinnamon-screensaver-command  --lock
      ;;
    *MATE*|*Mate*|*mate*)
      /usr/bin/mate-screensaver-command --lock
      ;;
    *GNOME*|*Gnome*|*gnome*)
      /usr/bin/dbus-send --type=method_call --dest=org.gnome.ScreenSaver \
	        /org/gnome/ScreenSaver org.gnome.ScreenSaver.Lock
      ;;
    *KDE*|*Kde*|*kde*)
       qdbus org.freedesktop.ScreenSaver /ScreenSaver Lock
       ;;
     *)
       /usr/bin/xlock
       ;;
  esac
fi
