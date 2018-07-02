# facelock
A python application to lock the screen when it does not see you anymore in front of the camera

## install
```
pip install -r requirements.txt
```
=======
![Facelock logo](logo.png)

A python 3 application that will lock the computer screen when you
leave, and the camera won't detect **_your_** face in front of it
anymore for a specified interval of time.

### The idea
Locking the computer automatically is always painful. You can put a 
10 second screensaver timeout, but if you stop using the mouse and the
keyboard, for whatever reason, it becomes pretty annoying pretty fast.
In the past, to protect my sessions from intrusions I wrote a script
that locked the screen when the signal strength of my bluetooth 
devices (phone or smartwatch) would drop under a specified
threshold (typically, when I walked away). This worked well as 
long as I had a Linux workstation, now that I have been forced on a
macbook I **really** do not want to learn ObSolete/X apis in 
Objective C.. I can come with better ways to waste my time.

Thinking and rethinking about zero-hassle ways to do this, I had
a new idea: have the camera detect constantly **my** face in front
of the screen, and when it does not see it anymore, lock it.

### How it works 
This is based on [dlib](http://dlib.net/), a machine learning C++ library
that has incredible facial recognition features. In Python you can
find a package called face_recognition that wraps dlib.
Python was a natural choice to avoid having to do this in C++, as
I am not really keen on the idea to learn any OSX specific stuff.
The software goes in background and opens a Qt5 gui using a system tray
icon. It uses opencv to read the camera frames, and it will perform a
face recognition on the camera frames against a reference image.
When the target face is not present anymore in the camera frames,
it will launch a configurable command (typically to lock the screen).

One of the main selling points of dlib is that its face recognition 
algorithms do not need training: just **one** image will suffice.

**Warning**:
On the first run facelock will check that there is a proper face image
set in the preferences, otherwise it will prompt you to select one.
It will similarly warn you of a missing external command to lock the screen
in the settings (see below for how to set this on specific OSes).
The image should be a clear front view picture of you, and that is
usually enough. You can tune it and try different pictures (set them
on the _Settings_ panel) and the Calibration utility.

### Calibration
Included in the repository there is a small utility called 'Calibration'.
This can be launched from Facelock main menu, and will show a visual
feedback on the face recognition process: it can be used to verify that
the camera is working properly, the image is not doo dark, or the best
angles to position the laptop or the camera.

To exit from the calibration window, press the '**q**' when the window
is in focus.

### How to install it on OS/X 

The prerequisite is to have the brew package manager installed.

**(NEW)** Consider the `install.sh` script in the `osx` folder, that will try
to do all the necessary installation steps automatically. In case of problems,
refer to the description of the necessary steps in this paragraph.
To use the script, go to the facelock git repository that you have cloned,
then type

`cd osx`

`./install.sh`

**Manual installation**

First thing you need python 3: 

`brew install python3`

Then install opencv

`brew install opencv`

Opencv is best installed from the package manager _brew_. If you don't and
use `pip install opencv_python` instead, this version will bring a private
installation of the qt5 libraries which will conflict with the ones installed
regularly.

Finally, install the proper requirements from the facelock directory 

`sudo pip3 install -r requirements_osx.txt`

and this should be about it.

Run it with 

`python3 ./facelock.py`

The first time that it runs, it will generate a configuration file in a 
OS-compliant conventions fashion. Since the imagepath configuration will
be empty, you will be prompted to select an image.

You can find an example of the command to launch to lock the screen for
OS/X and Fedora+Cinnamon in the **facelock.conf** file, copy its contents
in the screen settings panel in **Command to execute** .

Save the settings and start the tracking from the facelock popup menu. 

In order to lock the screen on osx, you can configure the command to execute
as:

`/bin/echo 'tell application "Finder" to sleep' | /usr/bin/osascript`
 
#### Build an OSX .app package (new)
In the `osx/` folder there is a utility called `makeapp`. Using it, it's
possible to  generate a proper OSX app package, to launch the
application from the finder or pin it to the dock. Everytime that the 
app is updated from git makeapp must be used to regenerate it.

`cd osx`

`./makeapp`

#### Experimental: disable the Python Rocket icon on the Dock (new)
There is an experimental script that will attempt to disable the python
rocket icon by detecting the Info.plist descriptor of the python launcher
app and inserting an LSUIElement set to **true**.

In order to start it, 

`cd osx`

`./undock_python.sh`

The original Info.plist file will be backed up in the current directory
in Info.plist.bck .

### How to install it on Linux
The linux installation should be pretty straightforward. Use your package
manager to install python3, for example with 

`# dnf install python3`
(fedora)

`# yum install python3`
(redhat)

`# apt-get install python3`
(debian/ubuntu)

after this, running

`# pip3 install -r requirements.txt`

should do the trick. Your mileage may vary according to the distribution 
used, especially for PyQt5 and opencv-python: sometimes it is preferable
to install those dependencies through the package manager and not pip.

In order to lock the screen on linux, you can set as _command to run_ 
(in the Settings panel) the one local to your distribution / graphic 
environment.

For example, for cinnamon the command to set would be:

`/usr/bin/cinnamon-screensaver-command  --lock`
