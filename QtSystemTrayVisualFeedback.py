from VisualFeedback import VisualFeedback
from qtImports import *

class QtSystemTrayVisualFeedback(VisualFeedback):
  qtSystemTrayIcon = None
  
  def __init__(self, qtSystemTrayIcon):
    if isinstance(qtSystemTrayIcon, QSystemTrayIcon):
      self.qtSystemTrayIcon = qtSystemTrayIcon
    else:
      raise Exception('qtSystemTrayIcon is not of type QSystemTrayIcon')
    
  def idle(self):
    self.qtSystemTrayIcon.setIcon(QIcon("tray.png"))

  def ok(self):
    self.qtSystemTrayIcon.setIcon(QIcon("tray1.png"))

  def warn(self):
    self.qtSystemTrayIcon.setIcon(QIcon("tray3.png"))

  def critical(self):
    self.qtSystemTrayIcon.setIcon(QIcon("tray4.png"))

  def ko(self):
    self.qtSystemTrayIcon.setIcon(QIcon("tray2.png"))

  def busy(self):
    self.qtSystemTrayIcon.setIcon(QIcon("tray5.png"))
