#!/usr/bin/env bash

OS=`uname -s | cut -d "_" -f 1`

if [ "$OS" == "Darwin" ]; then
  /bin/echo 'tell application "Finder" to sleep' | /usr/bin/osascript
else
  case "$XDG_CURRENT_DESKTOP" in
   *CINNAMON*|*Cinnamon*|*cinnamon*)
     echo /usr/bin/cinnamon-screensaver-command  --lock
     ;;
   *MATE*|*Mate*|*mate*)
     echo /usr/bin/mate-screensaver-command --lock
     ;;
   *GNOME*|*Gnome*|*gnome*)
     echo /usr/bin/gnome-screensaver-command --lock
     ;;
     *)
       break
       ;;
  esac
fi
