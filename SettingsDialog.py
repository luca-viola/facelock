from qtImports import *
import threading

class SettingsDialog(QDialog):
  useNativeDialog = True
  cWidget = None
  delaySpinbox = None
  executeCommandLineEdit = None
  processCountSpinbox = None
  trackOnStartCheckBox = None
  lockOnUnknownFacesCheckBox = None
  selectedImagePathLineEdit = None
  processCountLabel = None
  targetFaceNameLineEdit = None
  settings = None
  fps=30
  firstStart=True

  def closeEvent(self, event):
    event.ignore()
    self.reject()

  def __init__(self,settings):
    QDialog.__init__(self)
    self.settings=settings
    self.resize(self.settings.getSettingsDialogSize()[0], self.settings.getSettingsDialogSize()[1])
    self.setWindowTitle('FaceLock Settings')
    self.cWidget = QWidget(self)
    grid = QGridLayout(self.cWidget)

    position=0
    self._setupTimeoutRow(grid,position); position=position+1
    self._setupExecuteCommandRow(grid, position); position= position + 1
    self._setupTrackOnStartRow(grid, position); position= position + 1
    self._setupLockOnUnknownFacesRow(grid, position); position= position + 1
    self._setupSelectImageRow(grid, position); position= position + 1
    self._setupTargetFaceNameRow(grid, position); position= position + 1
    self._setupProcessCountFramesRow(grid, position); position= position + 1
    self._setupLineSeparator(grid, position);  position= position + 1
    self._setupSaveCancelButtonsRow(grid, position)
    self.cWidget.setLayout(grid)

  def _setupSaveCancelButtonsRow(self, grid, position):
    cancelButton = QPushButton("Cancel")
    cancelButton.clicked.connect(self.cancelSettings)
    saveButton = QPushButton("Save")
    saveButton.clicked.connect(self.saveSettings)
    buttonsHLayout = QHBoxLayout()
    buttonsHLayout.addWidget(cancelButton)
    buttonsHLayout.addWidget(saveButton)
    grid.addLayout(buttonsHLayout, position, 1)

  def _setupLineSeparator(self, grid, position):
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    grid.addWidget(line, position, 0, 1, 4)

  def _setupProcessCountFramesRow(self, grid, position):
    self.processCountLabel = QLabel("Processed frames #:")
    self.processCountSpinbox = QSpinBox()
    self.processCountSpinbox.setRange(1, self.fps)
    self.processCountSpinbox.setValue(self.settings.getProcessCountsPerFps())
    self.processCountSpinbox.setSuffix("/" + str(self.fps))
    self.processCountSpinbox.setSingleStep(1)
    self.processCountSpinbox.valueChanged.connect(self.onFpsValueChange)
    grid.addWidget(self.processCountLabel, position, 0)
    grid.addWidget(self.processCountSpinbox, position, 1)

  def _setupTargetFaceNameRow(self, grid, position):
    targetFaceNameLabel = QLabel("Target face name:")
    self.targetFaceNameLineEdit = QLineEdit(self.settings.getTargetFaceName())
    self.targetFaceNameLineEdit.textChanged.connect(self.onFaceNameTextChange)
    grid.addWidget(targetFaceNameLabel, position, 0)
    grid.addWidget(self.targetFaceNameLineEdit, position, 1)

  def _setupSelectImageRow(self, grid, position):
    selectImageLabel = QLabel("Image path:")
    self.selectedImagePathLineEdit = QLabel(self.settings.getImagePath())
    self.selectedImagePathLineEdit.setFont(
      QtGui.QFont(self.selectedImagePathLineEdit.font().family(), weight=QtGui.QFont.Bold))
    self.selectedImagePathLineEdit.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    selectImageButton = QPushButton("Select...")
    selectImageButton.setMaximumWidth(100)
    selectImageButton.clicked.connect(self.openFileNameDialog)
    buttonsHLayout = QHBoxLayout()
    buttonsHLayout.addWidget(selectImageLabel)
    buttonsHLayout.addWidget(self.selectedImagePathLineEdit)
    grid.addLayout(buttonsHLayout, position, 0)
    grid.addWidget(selectImageButton, position, 1)

  def _setupLockOnUnknownFacesRow(self, grid, position):
    lockOnUnknownFacesLabel = QLabel("Immediately lock if tracking only unknown face(s):")
    self.lockOnUnknownFacesCheckBox = QCheckBox("", self.cWidget)
    self.lockOnUnknownFacesCheckBox.stateChanged.connect(self.lockOnUnknowFacesStateChange)
    self.lockOnUnknownFacesCheckBox.setChecked(self.settings.isLockingOnUnknownFacesOnly())
    grid.addWidget(lockOnUnknownFacesLabel, position, 0)
    grid.addWidget(self.lockOnUnknownFacesCheckBox, position, 1)

  def _setupTrackOnStartRow(self, grid, position):
    trackOnStartLabel = QLabel("Immediately begin tracking at application startup:")
    self.trackOnStartCheckBox = QCheckBox("", self.cWidget)
    self.trackOnStartCheckBox.stateChanged.connect(self.trackOnStartStateChange)
    self.trackOnStartCheckBox.setChecked(self.settings.isTrackingOnStart())
    grid.addWidget(trackOnStartLabel, position, 0)
    grid.addWidget(self.trackOnStartCheckBox, position, 1)

  def _setupExecuteCommandRow(self, grid, position):
    executeCommandLabel = QLabel("Command to execute:")
    self.executeCommandLineEdit = QLineEdit(self.settings.getExecuteCommand())
    self.executeCommandLineEdit.textChanged.connect(self.onExecuteCommandTextChange)
    grid.addWidget(executeCommandLabel, position, 0)
    grid.addWidget(self.executeCommandLineEdit, position, 1)

  def _setupTimeoutRow(self, grid,position):
    delayLabel = QLabel("Delay time:")
    self.delaySpinbox = QSpinBox()
    self.delaySpinbox.setRange(1, 300)
    self.delaySpinbox.setValue(self.settings.getTimeout())
    self.delaySpinbox.setSuffix(" sec")
    self.delaySpinbox.setSingleStep(1)
    self.delaySpinbox.valueChanged.connect(self.onValueChange)
    grid.addWidget(delayLabel, position, 0)
    grid.addWidget(self.delaySpinbox, position, 1)

  def resizeEvent(self, event):
    size=event.size()
    self.settings.setSettingsDialogSize(size.width(), size.height())
    
  def cancelSettings(self):
    self.reject()

  def saveSettings(self):
    self.settings.saveSettings()
    isRunning = False
    for t in threading.enumerate():
      if t.getName()=="FACE_RECOGNITION":
        isRunning = True
        break
    if isRunning:
      quit_msg = "Stop and start tracking again to apply changes!"
      QMessageBox.warning(self, 'Message', quit_msg, QMessageBox.Ok)
    self.reject()

  def onValueChange(self):
    self.settings.setTimeout(self.delaySpinbox.value())

  def openFileNameDialog(self):    
    options = QFileDialog.Options()
    if not self.useNativeDialog:
      options |= QFileDialog.DontUseNativeDialog
    fileName, _ = QFileDialog.getOpenFileName(self,"QFileDialog.getOpenFileName()", self.settings.getImagePath(),"All Files (*);;Python Files (*.py)", options=options)
    if fileName:
      self.selectedImagePathLineEdit.setText(fileName)
      self.settings.setImagePath(fileName)     
     
  def onFpsValueChange(self):
    self.settings.setProcessCountsPerFps(self.processCountSpinbox.value())

  def onExecuteCommandTextChange(self,text):
    self.settings.setExecuteCommand(text)

  def onFaceNameTextChange(self,text):
    self.settings.setTargetFaceName(text)

  def trackOnStartStateChange(self):
    self.settings.setTrackingOnStart(self.trackOnStartCheckBox.isChecked())

  def lockOnUnknowFacesStateChange(self):
    if self.lockOnUnknownFacesCheckBox.isChecked() and not self.firstStart:
      warn_msg = "Careful! This setting, combined with a higher timeout, is more useable but brings a higher security risk: an attacker could use your photo when you are not there to keep the screen from locking."
      QMessageBox.critical(self, 'Message', warn_msg, QMessageBox.Ok)
    self.settings.setLockOnUnknownFacesOnly(self.lockOnUnknownFacesCheckBox.isChecked())
    self.firstStart = False