# facelock
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


> ####WARNING:  
> when you press "stop tracking" from the facelock menu,the python script
> will try to free the resources  allocated from opencv with 
> VideoCapture.release(), as per opencv's examples. While this works
> perfectly on linux, on OSX __it will often crash the application__ with
> a SIGSEGV or a
> 
>'NSInvalidArgumentException', reason: '-[NSTaggedPointerString unlock]: 
> unrecognized selector sent to instance
> 
> This seems to be a problem of opencv.


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
used, especially for PyQt5 and opencv-python: in some distributions it 
might be preferable to install those dependencies through the package
manager and not pip.

> **NOTE**: on some desktop environments, like Gnome 3 Shell , you might need
some extra extension to be able to see the facelock icon. 

For example, on fedora with Gnome 3, run
 
`sudo dnf install gnome-shell-extension-topicons-plus.noarch`  

On Enlightment, select "Create new Systray" from the desktop menu.
 
### First run

The first time that facelock runs, it will generate a configuration file in a 
OS-compliant conventions fashion. Since the imagepath configuration will
be empty, you will be prompted to select an image.

At first run or when the 'command to execute setting' is empty, facelock 
will automatically configure a path to the lockscreen.sh script, that will
lock the screen in a multiplatform fashion (see paragraph). 

Have a look at the settings panel and start the tracking from the facelock
popup menu. 

### The Settings Panel

**Delay time** : The timeout to lock the screen if the target face 
is not seen for the the specified amount of seconds.

**Command to execute** : A command to execute. Can be any command, it defaults 
to <FACELOCK_HOME>/lockscreen.sh .

**Immediately begin tracking at application startup** : This will start 
looking for the target face as soon as the application starts.

**Immediately lock if tracking only unknown faces** : This allows you to 
have a higher timeout, but lock instantly if an unknown face is detected
in front of the computer.   

> **Warning**: this could have security consequences, especially on high timeouts.

**Image Path** : The target face image.

**Target face name** : a label for the target face. It will be shown when
doing calibration, in an highlighted red box surrounding the target face.  
Non matching faces will be labeled as "unknown".

**Processed frames #** : This will start the face recognition every n frames 
out of the maximum camera frame rate per second. It is useful to impact less
on the cpu.

### The lockscreen.sh script

This script is the default command to be launched on a timeout. It will try
to detect the  enviroment in which it is running and launch the according
command to lock the screen.

So far, the working environments are

- Gnome
- Kde
- Mate
- Cinnamon
- Aqua (macOS' desktop)

In all the other cases it will try to fallback on the generic command `xlock`, 
that will therefore have to be available on the path. 
For example, on fedora, do 

`sudo dnf install xlockmore`

to obtain it.

Make sure that for each environment you need, the specific lock screen commands
are installed, e.g. cinnamon-screensaver, mate-screensaver, etc.
