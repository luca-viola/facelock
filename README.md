# Face Guard

A GNOME Shell extension that watches the camera with InsightFace `buffalo_l`.

- **Your face is missing:** locks the screen after a grace period.
- **Your face and another are in view:** runs the action you choose (lock, switch
  workspace, run a command, or notify).

This is a convenience guard, not authentication. It has no liveness check, so a
photo of you passes as you. Your normal unlock password stays the real security.

## Install

```sh
./install.sh
```

This creates a pinned `faceguard` conda environment from `environment.yml` (several
GB, and it needs a C++ compiler to build insightface), downloads the `buffalo_l`
models to `~/.insightface/models` if they're missing, and warms up the GPU cache so
the first start isn't slow. To use another environment, pass its python as an
argument. It needs an NVIDIA GPU for full speed, and otherwise runs on the CPU with
a warning.

On Wayland, log out and back in once after the first install, then run:

```sh
gnome-extensions enable faceguard@lviola
```

Open Settings from the shield icon in the top bar, set a reference image with
**Take Photo** or **Choose File**, then turn on **Watch camera**.

## How it works

GNOME extensions run inside the shell and can't load a GPU model, so the work is
split in two:

| Part | Does |
|---|---|
| `extension/extension.js`, `actions.js`, `daemonClient.js` | Panel icon, starts and stops the daemon, carries out actions |
| `extension/prefs.js` | Settings window and reference photo capture |
| `extension/daemon/faceguard_daemon.py` | Camera and buffalo_l, sends JSON events to the extension |
| `extension/daemon/policy.py` | Decides when to trigger, with no camera or model dependency |

The camera is off whenever the screen is locked: GNOME disables the extension on
lock, which kills the daemon. It starts again after you unlock, and the absence
grace period starts over.

## Behavior worth knowing

- **Face at a bad angle:** if only an unrecognized face is in view, that counts as
  you being absent, not as an intruder. An intruder needs your face matched in the
  same frame.
- **Tuning:** the panel menu shows the live match score. Set the match threshold
  below your usual score and well above a stranger's.
- **Snap rate:** the daemon only analyzes frames the camera has newly delivered, so
  the interval can't go faster than the camera's real framerate.
- **Automatic camera:** picks the first physical camera and skips virtual ones such
  as OBS Virtual Camera.
- **Command action:** runs with `sh -c`, with the number of other faces in
  `FACEGUARD_OTHER_FACES`.
- **Reference image:** stored at `~/.local/share/faceguard/reference.jpg`, readable
  only by you.

## Tests

```sh
python -m unittest discover -s faceguard/tests
```

These need numpy but no camera, GPU or models.
