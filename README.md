# Face Guard

A GNOME Shell extension that watches the camera with InsightFace `buffalo_l`.

- **Your face is missing:** locks the screen after a grace period.
- **Your face and another are in view:** runs the action you choose (lock, switch
  workspace, run a command, notify, or show giant eyes), and can also minimize the
  apps you pick.

This is a convenience guard, not authentication. It has no liveness check, so a
photo of you passes as you. Your normal unlock password stays the real security.

## Install

```sh
./install.sh
```

This creates the exact `faceguard` conda environment from `environment.yml` (several
GB, and it needs a C++ compiler to build insightface) and downloads the default
`buffalo_l` models to `~/.insightface/models` if they're missing. To use another
environment, pass its python as an argument. Face Guard runs on the CPU by default; an
NVIDIA GPU is optional.

On Wayland, log out and back in once after the first install, then run:

```sh
gnome-extensions enable faceguard@lviola
```

Open Settings from the shield icon in the top bar, set a reference image with
**Take Photo** or **Choose File**, then turn on **Watch camera**.

## macOS

The `macos` folder has a menu bar app that uses the same daemon. See [macos/README.md](macos/README.md).

## How it works

GNOME extensions run inside the shell and can't load a GPU model, so the work is
split in two:

| Part | Does |
|---|---|
| `extension/extension.js`, `actions.js`, `daemonClient.js` | Panel icon, starts and stops the daemon, carries out actions |
| `extension/eyes.js`, `gaze.js` | The giant eyes overlay, and where its pupils point |
| `extension/icons/`, `tools/make_icons.py` | The panel icons, and the script that draws them |
| `extension/prefs.js` | Settings window and reference photo capture |
| `extension/daemon/faceguard_daemon.py` | Entry point: reads the arguments and connects the parts below |
| `extension/daemon/camera.py`, `capture.py` | Finding and reading cameras, and the reference photo preview |
| `extension/daemon/sharing.py` | Letting go of the camera while another app uses it |
| `extension/daemon/backends/` | Face-recognition models behind one small interface (`base.py`) |
| `extension/daemon/recognition.py`, `monitor.py`, `enrollment.py` | Telling you from others, the watch loop, and storing the reference |
| `extension/daemon/protocol.py`, `errors.py`, `files.py` | Messages to the extension, exit codes, and private files |
| `extension/daemon/policy.py` | Decides when to trigger, with no camera or model dependency |

The camera is off whenever the screen is locked: GNOME disables the extension on
lock, which kills the daemon. It starts again after you unlock, and the absence
grace period starts over.

## Behavior worth knowing

- **Allow collaboration:** a switch in the panel menu, also on **Ctrl+Alt+C**, for when someone is
  meant to look at your screen. The menu shows the shortcut under the switch. It turns off the actions for another face (lock, workspace, command,
  notify, eyes, minimized apps) but not the lock when your own face goes away. It isn't saved: it
  starts off after every unlock. Turning it on undoes what another face already set off, and turning
  it off while someone is still in view applies the action straight away. To change the shortcut:
  `gsettings --schemadir ~/.local/share/gnome-shell/extensions/faceguard@lviola/schemas set
  org.gnome.shell.extensions.faceguard toggle-collaboration "['<Super>c']"`. After updating, run
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
  `~/.local/share/faceguard/models`. The environment has dlib's CPU build: conda-forge's
  GPU build needs a newer cuDNN than onnxruntime-gpu is installed with. With another
  Python that lacks dlib, its models are left out of Settings.
- **Snap rate:** the daemon only analyzes frames the camera has newly delivered, so
  the interval can't go faster than the camera's real framerate.
- **Automatic camera:** picks the first physical camera and skips virtual ones such
  as OBS Virtual Camera.
- **Release camera to apps:** a switch in the panel menu, off by default. On Linux
  only one app can stream from a camera, so with it on, Face Guard lets go of it when
  another app opens it, and the panel says which app has it. Nothing is
  watched meanwhile, so leaving doesn't lock the screen during a call. It takes the
  camera back 3 seconds after the other app closes it. The call app's first attempt to
  start the camera usually fails, because it starts streaming before Face Guard can let
  go; click its camera button again. After an attempt like that Face Guard waits 15
  seconds, so your retry gets the camera. Apps that only peek at the camera, such as a
  browser listing the cameras for a meeting page, cause the same short pause. macOS
  shares cameras between apps, so this doesn't apply there.
- **Command action:** runs with `sh -c`, with the number of other faces in
  `FACEGUARD_OTHER_FACES`.
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
- **Reference image:** stored at `~/.local/share/faceguard/reference.jpg`, readable
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

These need numpy but no camera, GPU or models. To test the gaze math:

```sh
gjs -m tests/test_gaze.js
```
