from qtImports import *
import os
import sys


class ConfigurationChecker(object):
  settings = None
  settingsDialog = None
  filePath = ''
  fileName = ''

  def __init__(self,settingsDialog):
    self.settingsDialog = settingsDialog
    self.settings = settingsDialog.settings

  def fixConfiguration(self):
      self._checkAndSetImagePath()
      self._checkAndSetCommandToExecute()

  def _checkAndSetImagePath(self):
    if self.settings.getImagePath() == '':
      quit_msg = "You need to provide an image with the face to be tracked in the Settings panel."
      QMessageBox.critical(None, 'Message', quit_msg, QMessageBox.Ok)
      self.settingsDialog.openFileNameDialog()
      self.settingsDialog.saveSettings()

  def _checkAndSetCommandToExecute(self):
    if self.settings.getExecuteCommand() == '':
      installDir=os.path.realpath(".")
      lockscriptPath=installDir+"/"+"lockscreen.sh"
      self.settings.setExecuteCommand(lockscriptPath)
      self.settingsDialog.executeCommandLineEdit.setText(lockscriptPath)
      self.settings.saveSettings()
