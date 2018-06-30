#!/usr/local/bin/python3
import sys
import os

from qtImports import *

from settings import Settings
from AboutDialog import AboutDialog
from SettingsDialog import SettingsDialog
from SystemTrayGUIBuilder import SystemTrayGUIBuilder
from CameraProbe import CameraProbe
from FaceRecognitionBuilder import FaceRecognitionBuilder
from ConfigurationChecker import ConfigurationChecker
from nohup import nohup

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

if __name__ == '__main__':
    nohup(main)
