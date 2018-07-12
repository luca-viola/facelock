#!/usr/bin/env python3
import sys
import os
import getopt

from qtImports import *

from settings import Settings
from AboutDialog import AboutDialog
from SettingsDialog import SettingsDialog
from SystemTrayGUIBuilder import SystemTrayGUIBuilder
from CameraProbe import CameraProbe
from FaceRecognitionBuilder import FaceRecognitionBuilder
from ConfigurationChecker import ConfigurationChecker
from __init__ import __version__

from nohup import nohup

detach = False

def usage():
  print('facelock.py [-v] [-h] [-d]')
  print('  -v | --version : print version')
  print('  -h | --help    : print this message')
  print('  -d | --detach  : go in background and detach from the tty')


def main():
  os.chdir(os.path.dirname(sys.argv[0]))

  app = QApplication(sys.argv)
  QApplication.setQuitOnLastWindowClosed(False)

  settings=Settings('facelock')

  aboutDialog = AboutDialog()
  settingsDialog = SettingsDialog(settings)

  ConfigurationChecker(settingsDialog).fixConfiguration()

  cameraProbe = CameraProbe()

  faceRecognitionBuilder=FaceRecognitionBuilder()\
    .withSettings(settings)\
    .withCameraProperties(cameraProbe.getFps(),
                          cameraProbe.getWidth(),
                          cameraProbe.getHeight())

  
  trayIconGUI = SystemTrayGUIBuilder().\
    withSettings(settings).\
    withAboutDialog(aboutDialog).\
    withSettingsDialog(settingsDialog).\
    withFaceRecognitionBuilder(faceRecognitionBuilder).\
    build()
  
  trayIconGUI.show()
  app.exec_()


argv = sys.argv[1:]

try:
  opts, args = getopt.getopt(argv, "hvd", ["detach", "help", "version"])
except getopt.GetoptError:
  usage()
  sys.exit(2)
for opt, arg in opts:
  if opt in ('-h', '--help'):
    usage()
    sys.exit()
  elif opt in ("-v", "--version"):
    print("Version: "+__version__)
    sys.exit()
  elif opt in ("-d", "--detach"):
    detach = True


if __name__ == '__main__':
    if detach:
      nohup(main)
    else:
      main()