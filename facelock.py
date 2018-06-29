#!/usr/local/bin/python3
import sys

from settings import Settings

from qtImports import *

from AboutDialog import AboutDialog
from SettingsDialog import SettingsDialog
from SystemTrayGUIBuilder import SystemTrayGUIBuilder
from QtSystemTrayVisualFeedback import QtSystemTrayVisualFeedback
from CameraProbe import CameraProbe
from FaceRecognitionBuilder import FaceRecognitionBuilder

from nohup import nohup


def main():
  app = QApplication(sys.argv)
  QApplication.setQuitOnLastWindowClosed(False)

  settings=Settings('facelock')

  if settings.getImagePath()=='':
    quit_msg = "You need to provide an image with the face to track in the Settings panel."
    settings.setTrackingOnStart(False)
    QMessageBox.warning(None, 'Message', quit_msg, QMessageBox.Ok)

  aboutDialog = AboutDialog()
  settingsDialog = SettingsDialog(settings)

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
