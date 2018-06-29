from qtImports import *
from QtSystemTrayVisualFeedback import QtSystemTrayVisualFeedback
import os
import platform
import subprocess

class SystemTrayGUIBuilder(object):
  systemTrayGUI = None
  settings = None
  aboutDialog = None
  settingsDialog = None
  faceRecognitionBuilder = None
  
  def __init__(self):
    self.systemTrayGUI = None

  def withSettings(self, settings):
    self.settings = settings
    return self

  def withAboutDialog(self, aboutDialog):
    self.aboutDialog = aboutDialog
    return self

  def withSettingsDialog(self, settingsDialog):
    self.settingsDialog = settingsDialog
    return self

  def withFaceRecognitionBuilder(self, faceRecognitionBuilder):
    self.faceRecognitionBuilder = faceRecognitionBuilder
    return self

  def build(self):
    self.systemTrayGUI = _SystemTrayGUI(self.settings, self.aboutDialog, self.settingsDialog,self.faceRecognitionBuilder)
    return self.systemTrayGUI

class _SystemTrayGUI(QSystemTrayIcon):
  about = None
  settingsGui = None
  settings = None
  faceRecognition = None
  faceRecognitionBuilder = None
  starTrackingAction = None
  stopTrackingAction = None
  visualFeedback = None
  
  def __init__(self, settings, aboutDialog, settingsDialog, faceRecognitionBuilder, parent=None):
      self.settings=settings
      self.about = aboutDialog
      self.settingsGui = settingsDialog
      self.faceRecognitionBuilder = faceRecognitionBuilder
      self.visualFeedback = QtSystemTrayVisualFeedback(self)

      idleIcon = QIcon("tray.png")
      QSystemTrayIcon.__init__(self, idleIcon, parent)
    
      menu = QMenu(parent)
      menu.addAction(QAction("About FaceLock...",self,triggered=self.openAbout))
      menu.addSeparator()
      self.startTrackingAction=QAction("Start Tracking",self,triggered=self.startTracking)
      menu.addAction(self.startTrackingAction)
      self.stopTrackingAction = QAction("Stop Tracking",self,triggered=self.stopTracking)
      self.stopTrackingAction.setEnabled(False)
      menu.addAction(self.stopTrackingAction)
      menu.addAction(QAction("Settings...",self,triggered=self.openSettings))
      menu.addSeparator()
      menu.addAction(QAction("Calibration...",self,triggered=self.openCalibration))
      menu.addSeparator()
      menu.addAction(QAction("Quit FaceLock",self,triggered=self.exit))
      self.setContextMenu(menu)
      if self.settings.isTrackingOnStart():
        self.startTracking()
    
  def openCalibration(self):
    system=platform.system()
    path = os.getcwd()
    if system=='Linux' and self.faceRecognition!=None and self.faceRecognition.isRunning():
      msg = "Stop tracking before running calibration."
      QMessageBox.critical(None, 'Message', msg, QMessageBox.Ok)
    else:
      os.system(path + "/calibration.py")

  def toggleMutualExclusiveStartStopAction(self,isStartEnabled):
    self.startTrackingAction.setEnabled(isStartEnabled)
    self.stopTrackingAction.setEnabled(not isStartEnabled)

  def startTracking(self):
    self.toggleMutualExclusiveStartStopAction(False)
    self.faceRecognition = self.faceRecognitionBuilder.withVisualFeedback(self.visualFeedback).build()
    self.faceRecognition.start()

  def stopTracking(self):
    self.toggleMutualExclusiveStartStopAction(True)
    self.faceRecognition.quit()
    self.faceRecognition.freeResources()
    self.visualFeedback.idle()

  def toggleCamera(self):
    self.faceRecognition.toggle()

  def openSettings(self):
    self.settingsGui.show()

  def openAbout(self):
    self.about.exec_()

  def exit(self):
    QtCore.QCoreApplication.exit()
