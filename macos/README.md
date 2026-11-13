# Face Guard for macOS

A menu bar app that does what the GNOME extension does, with the same daemon
(`../extension/daemon`). There are two front ends, which share `settings.json`:

- **`FaceGuardApp/`, the Swift app.** A SwiftUI popup and Settings window laid out like the GNOME
  ones. This is the one to use.
- **`faceguard.py`, the Python app** (rumps and PyObjC). The first version, with everything in menus.
  Don't run both at once.

## The Swift app

```sh
./build-python-env.sh   # once: a relocatable Python with everything the daemon needs (about 420 MB)
./build-app.sh          # builds and signs dist/FaceGuard.app, with that Python inside it
open dist/FaceGuard.app
```

The app carries its own Python (python-build-standalone from uv, plus the pinned packages in
`requirements-bundle.txt`, dlib included), so it runs on a Mac with nothing installed. Building it
needs `brew install uv cmake` and the Xcode command line tools, to compile dlib once. Everything
is built for macOS 14 and Apple silicon, and the script fails if any binary links a library that
isn't a system one. Without `python-env/`, the app falls back to the `.venv` it was built beside
(`make venv`), or to the Python set under Advanced in Settings, which always wins.

It's signed with your first Apple Development certificate, so the Camera and Automation
permissions survive rebuilds. Pass another identity as the first argument to `build-app.sh`.

### Releasing

```sh
./release-app.sh    # signs with your Developer ID, notarizes, staples, and zips to dist/FaceGuard.zip
```

It needs notarytool credentials stored in the keychain (`NOTARY_PROFILE`, default `snappo-notary`).
It signs every binary in the bundled Python (the interpreter also gets the camera entitlement,
since it is the process that opens the camera), so run `./build-python-env.sh` first. The icon
comes from `icon/make-icon.swift`.

## The Python app

## Install and run

```sh
brew install python@3.12
make venv       # creates .venv with the packages in requirements.txt
make prepare    # downloads the default buffalo_l model, about 280 MB
make run
```

Then, from the eye icon in the menu bar: **Take Reference Photo…** (or
**Choose Reference File…**), then **Watch camera**.

Settings are in `~/Library/Application Support/faceguard/settings.json`, and the
log is `~/Library/Logs/FaceGuard.log`.

## How it differs from GNOME

| | GNOME | macOS |
|---|---|---|
| Camera | Video4Linux | AVFoundation, through OpenCV. Cameras are stored by unique ID |
| GPU | CUDA | CoreML (CPU is still the default: it's slower to start and uses more memory) |
| Lock | `Main.screenShield` | `SACLockScreenImmediate`, else `pmset displaysleepnow` |
| Camera off while locked | the shell disables the extension | the app listens for screen lock, display sleep and system sleep |
| Other-face actions | lock, workspace, command, notify, eyes | lock, command, notify, eyes. Switching Desktops is left out: macOS has no API for it, and key presses only act on the display under the pointer, so it only worked on displays with several Desktops |
| Minimize apps | minimizes windows | hides the apps, the ones you pick or **All open apps** |

## Models

`make venv` installs dlib too (it builds from source if there's no wheel, which needs
`brew install cmake`), and the app bundle has it built in, so the **dlib, HOG detector** and **dlib, CNN detector** models show up
in Settings, and download about 30 MB the first time. Measured on an Apple silicon Mac, per snap
of one face: HOG takes 57 ms and 140 MB; CNN takes 200 ms and about 1 GB. They run on the CPU.
buffalo_l takes 77 ms on the CPU and 27 ms with CoreML, which uses more memory.

## Allow collaboration

A switch in the popup, also on **Control-Option-C** in any app, for when someone is meant to look
at your screen. It turns off the actions for another face but not the lock when your own face goes
away. It isn't saved: it starts off after every launch, and it ends when the screen locks. Turning
it on undoes what another face already set off (eyes closed, apps shown again), and turning it off
while someone is still in view applies the action straight away. A notification says which way it
went, since the shortcut gives no other sign. The Python app doesn't have it.

## Permissions

macOS asks for **Camera** access the first time you watch or take a photo. It is
granted to the app that started the daemon: when run with `make run`, that is your
terminal app. If you refused it, allow it under System Settings, Privacy & Security,
Camera. Face Guard doesn't need Accessibility or Screen Recording.

## Opening a page full screen

`open <url>` adds a tab to a browser that's already running. As the command for
"Run a command", `/path/to/macos/open-fullscreen.sh "https://example.com" "Microsoft Edge"`
opens the page in a new window and makes it full screen. It supports Chromium browsers
and Safari, and needs the Accessibility permission for the app running Face Guard.

## Not done yet

- A standalone `.app` bundle (py2app, signing and notarizing), as for Snappo.
- A Settings window. Everything is in the menu for now.
