# facelock
A python 3 application to lock the screen when you leave 
your seat and the camera cannot detect **_your_** face  anymore
in front of it.

### The idea
Locking the computer automatically is always painful. You can put a 
10 second screensaver timeout, but if you stop using the mouse and the
keyboard for whatever reason it becomes pretty annoying.
Or I used a script that locked the screen when the signal strength
of my bluetooth devices (phone or smartwatch) would drop to a certain
threshold (meaning I am walking away). This worked well as long as
I had a Linux workstation, now that I have been forced on a macbook 
I **really** do not want to learn ObSolete/X apis.. I have better 
ways to waste my time.

So here is the last idea: have the camera detect constantly **my** face
in front of the screen, and when it does not see it anymore, lock the
screen.

### How it works 
This is based on [dlib](http://dlib.net/), a machine learning C++ library
that has incredible facial recognition features. Python has a package,
face_recognition , which wraps dlib.
The software goes in background and opens a Qt5 gui using a system tray
icon. It uses opencv to read the camera frames, and it will perform a
face recognition on the camera frames against a reference image.
When the match is not present anymore, it will launch a command
(typically to lock the screen).

### How to install it on OS/X
First you need python 3: 

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

Save the settings and start tracking it.

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

