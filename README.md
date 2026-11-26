# Facelock

A GNOME Shell extension that watches the camera with InsightFace `buffalo_l`.

- **Your face is missing:** locks the screen after a grace period.
- **Your face and another are in view:** runs the action you choose (lock, switch
  workspace, run a command, notify, or show giant eyes), and can also minimize the
  apps you pick.

It can also unlock the screen with your face, optionally with a head-turn check and an
approval on your phone; see [Unlocking](#unlocking). Watching is a convenience guard, not
authentication: it has no liveness check, so a photo of you passes as you. Your normal
unlock password stays the real security.

## Install

```sh
./install.sh
```

Plain `./install.sh` is right for most computers. The options are:

| Command | When to use it |
|---|---|
| `./install.sh` | Most cases. Runs on the CPU, and asks first if it finds a usable NVIDIA GPU |
| `./install.sh --gpu` | Only with an NVIDIA GPU, on x86_64: uses it without asking |
| `./install.sh --cpu` | Uses the CPU without asking, even if there's an NVIDIA GPU |
| `./install.sh --dlib` | Also installs dlib, another engine to try that might be lighter. Its HOG detector uses less memory than `buffalo_l`, but needs faces turned towards the camera; its CNN detector is much slower |

`--dlib` can be combined with `--gpu` or `--cpu`, but dlib itself always runs on the CPU.
Choose its models in Settings afterwards.

This works on any distribution with GNOME 49 or later and Python 3, on x86_64 and
aarch64 (with glibc, so not musl distributions). It needs no compiler, conda or root. It
creates an environment in `~/.local/share/facelock/venv` with the pinned packages,
using [uv](https://docs.astral.sh/uv/) (downloaded temporarily if you don't have it) and
Python 3.12 (downloaded if you don't have it), and downloads the default `buffalo_l`
models to `~/.insightface/models` if they're missing.

If it finds an NVIDIA GPU with a working driver, it asks whether to use it. `--gpu` or
`--cpu` answers in advance. Other GPUs, including Apple silicon under Asahi Linux, aren't
supported, so those computers use the CPU. To use your own environment, pass its python
as an argument.

On Wayland, log out and back in once after the first install, then run:

```sh
gnome-extensions enable facelock@lviola
```

Open Settings from the shield icon in the top bar, set a reference image with
**Take Photo** or **Choose File**, then turn on **Watch camera**.

## macOS

The `macos` folder has a menu bar app, still called Face Guard, that uses the same daemon. See [macos/README.md](macos/README.md).

## How it works

GNOME extensions run inside the shell and can't load a GPU model, so the work is
split in two:

| Part | Does |
|---|---|
| `extension/extension.js`, `actions.js`, `daemonClient.js` | Panel icon, starts and stops the daemon, carries out actions |
| `extension/eyes.js`, `gaze.js` | The giant eyes overlay, and where its pupils point |
| `extension/icons/`, `tools/make_icons.py` | The panel icons, and the script that draws them |
| `extension/prefs.js` | Settings window and reference photo capture |
| `extension/daemon/facelock_daemon.py` | Entry point: reads the arguments and connects the parts below |
| `extension/daemon/camera.py`, `capture.py` | Finding and reading cameras, and the reference photo preview |
| `extension/daemon/sharing.py` | Letting go of the camera while another app uses it |
| `extension/daemon/backends/` | Face-recognition models behind one small interface (`base.py`) |
| `extension/daemon/recognition.py`, `monitor.py`, `enrollment.py` | Telling you from others, the watch loop, and storing the reference |
| `extension/daemon/protocol.py`, `errors.py`, `files.py` | Messages to the extension, exit codes, and private files |
| `extension/daemon/policy.py` | Decides when to trigger, with no camera or model dependency |
| `extension/unlocker.js`, `extension/daemon/unlock.py`, `liveness.py` | Unlocking from the lock screen |
| `extension/daemon/phone.py`, `webpush.py`, `relay.py`, `web/` | Pairing a phone and approving on it |

Watching stops whenever the screen is locked, and the daemon with it. It starts again
after you unlock, and the absence grace period starts over. On the lock screen the camera
is only used for unlocking, if that's on.

## Unlocking

Turn on **Unlock with face** in Settings. On the lock screen, Facelock waits for you to wake
the screen, press a key or move the mouse, then checks your face once. That check is stricter
than watching: the match must be 0.1 above your match threshold for three frames, with nobody
else in view. It gives up after 15 seconds; you get three tries per lock, then only the
password. The password always works too. It doesn't try after a lock caused by another face,
and not in the first 5 seconds after locking, so the key press that locked doesn't unlock.

Two options make it safer, and you can combine them:

- **Simple liveness detection** (on by default): you turn your head to one side and back. How far
  the nose sits from the middle of the eyes changes when a real head turns, but not when a
  photo is tilted. This stops a printed or on-screen photo, not a video of you.
- **Use passkey on phone:** after your face is recognized, your phone asks you to approve with
  Face ID or a fingerprint. The phone signs a single-use challenge with a passkey, and
  Facelock checks the signature against the key it saved when pairing. **Also pick a number on
  the phone** shows a number on the lock screen to pick on the phone, so you can't approve by
  habit, and a wrong pick can't produce a valid signature.

With neither, a photo of you unlocks the screen, and Settings says so.

### The phone

The phone side is a web page, [web/](web/), published at
<https://luca-viola.github.io/facelock/>. Nothing to install from an app store, on iPhone or
Android. To pair, press **Pair Phone** in Settings and scan the code, or open the page and type
the code. On iPhone, add the page to the Home Screen first and open it from there, since iPhone
only sends notifications to pages on the Home Screen (iOS 16.4 or later).

- The computer sends each request as a Web Push notification, through Apple's or Google's
  push service. It needs no server of Facelock's.
- The phone's answer comes back through [ntfy](https://ntfy.sh), a public message service,
  since a web page can't reach your computer directly. It's encrypted with a key only the phone
  and the computer have, and the answer to an unlock isn't stored there. You can run your own
  ntfy server and set it in **Relay server**, then pair again.
- There's no proximity check: you could approve from another room. Facelock has already seen
  only you at the screen by then, and the number check stops approving a request you didn't
  start.
- What the computer keeps is in `~/.local/share/facelock/phone.json`, readable only by you.
  **Forget** deletes it. On the phone, **Forget** on the page drops the computer; remove the
  passkey "Facelock: *computer*" from the phone's passwords too.

Unlocking doesn't open your keyring at the first login after boot; that still needs the
password.

## Behavior worth knowing

- **Allow collaboration:** a switch in the panel menu, also on **Ctrl+Alt+C**, for when someone is
  meant to look at your screen. The menu shows the shortcut under the switch. It turns off the actions for another face (lock, workspace, command,
  notify, eyes, minimized apps) but not the lock when your own face goes away. It isn't saved: it
  starts off after every unlock. Turning it on undoes what another face already set off, and turning
  it off while someone is still in view applies the action straight away. To change the shortcut:
  `gsettings --schemadir ~/.local/share/gnome-shell/extensions/facelock@lviola/schemas set
  org.gnome.shell.extensions.facelock toggle-collaboration "['<Super>c']"`. After updating, run
  `./install.sh` and log out and back in, since the extension has a new setting.

- **Face at a bad angle:** if only an unrecognized face is in view, that counts as
  you being absent, not as an intruder. An intruder needs your face matched in the
  same frame.
- **Tuning:** the panel menu shows the live match score. Set the match threshold
  below your usual score and well above a stranger's. Each model keeps its own
  threshold, since their scores differ.
- **Models and GPU:** choose the model in Settings. Other models download when first
  used. Measured on an Intel Core i9-14900K and an RTX 5060 Ti, per snap of one face:

  | Model | CPU: RAM, time | GPU: VRAM, RAM, time |
  |---|---|---|
  | buffalo_l (default) | 450 MB, 100 ms | 670 MiB, 1.1 GB, 19 ms |
  | buffalo_m | 460 MB, 66 ms | 580 MiB, 1.1 GB, 13 ms |
  | buffalo_sc | 230 MB, 13 ms | 260 MiB, 1.1 GB, 4 ms |
  | dlib, HOG detector | 120 MB, 57 ms | CPU only |
  | dlib, CNN detector | 200 MB, 620 ms | CPU only |

  The GPU's extra memory is NVIDIA's runtime, not the models, so the CPU is the default.
  **Use GPU** is greyed out when no usable GPU is found, or for a model that can't use
  it. Smaller models tell faces apart less reliably. dlib's HOG detector only finds
  faces turned towards the camera and at least about 80 pixels across; its CNN detector
  also finds turned faces but takes about 0.6 s per snap. The dlib models download to
  `~/.local/share/facelock/models`. dlib isn't
  installed by default, and without it its models are left out of Settings. `./install.sh
  --dlib` adds it from `dlib-bin`, a prebuilt CPU package for x86_64 and aarch64, pinned by
  hash. That's an unofficial build by [alesanfra](https://github.com/alesanfra/dlib-wheels),
  not dlib's author. It stays installed when you run `./install.sh` again.
- **Snap rate:** the daemon only analyzes frames the camera has newly delivered, so
  the interval can't go faster than the camera's real framerate.
- **Automatic camera:** picks the first physical camera and skips virtual ones such
  as OBS Virtual Camera.
- **Release camera to apps:** a switch in the panel menu, off by default. On Linux
  only one app can stream from a camera, so with it on, Facelock lets go of it when
  another app opens it, shows a notification, and the panel says which app has it. Nothing is
  watched meanwhile, so leaving doesn't lock the screen during a call. It takes the
  camera back 3 seconds after the other app closes it. The call app's first attempt to
  start the camera usually fails, because it starts streaming before Facelock can let
  go; click its camera button again. After an attempt like that Facelock waits 15
  seconds, so your retry gets the camera. Apps that only peek at the camera, such as a
  browser listing the cameras for a meeting page, cause the same short pause. On macOS this does
  nothing: apps can usually share a camera there, but that's untested with Facelock.
- **Command action:** runs with `sh -c`, with the number of other faces in
  `FACELOCK_OTHER_FACES`.
- **Eyes action:** shows a pair of giant xeyes-style eyes in the middle of the primary
  screen that follow the largest other face, assuming the camera is at the top of the
  screen and doesn't mirror its image. While they're open, the daemon snaps at the
  camera's full framerate so they keep up. With several other faces, they look at the
  largest, which is usually the closest. **Dismiss**, or double-clicking an eye, closes
  them until that face has been gone for 2 seconds and comes back. They also close by themselves once it has
  gone, and restarting the daemon, such as by unlocking or changing a setting, starts
  over. The rest of the screen stays usable, apart from clicks on the eyes themselves.
- **Minimize apps:** minimizes the chosen apps' windows on every workspace, or with
  **All open apps** every normal window, alongside the action. It restores them once
  the other face has been gone for 2 seconds, unless you turn that off or have restored
  them yourself. Windows GNOME can't match to an installed app, such as some apps
  started from a script, aren't found for the chosen apps, but are with All open apps.
  The desktop icons stay. After the screen locks, they stay minimized.
- **Reference image:** stored at `~/.local/share/facelock/reference.jpg`, readable
  only by you.

## Panel icons

The panel icon shows the state: a filled shield when only you are in view, an outline
shield when you aren't recognized, two people when someone else is looking, an eye while
starting, a crossed-out eye when off, and a warning triangle on an error. They ship with
the extension, so they look the same under every icon theme. The shields are the macOS
app's exact shapes; the others are drawn in the same style. GNOME recolors them for the
panel. To change them, edit `tools/make_icons.py`, which needs Shapely, and run it.

## Tests

```sh
python -m unittest discover -s tests
```

These need numpy and cryptography but no camera, GPU, models, network or phone. To test the gaze math:

```sh
gjs -m tests/test_gaze.js
```

## License

GPL-3.0, see [LICENSE](LICENSE). The InsightFace and dlib models are downloaded separately
and have their own licenses.

The previous Facelock, a Python and Qt application, is on the `legacy` branch.
