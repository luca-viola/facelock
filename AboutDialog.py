from qtImports import *
from __init__ import __version__

class AboutDialog(QMessageBox):
  def closeEvent(self, event):
    event.ignore()
    self.hide()
    self.reject()

  def __init__(self):
    QMessageBox.__init__(self)
    self.hide()
    message="""This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>."""

    self.setIcon(QMessageBox.Information)
    self.setWindowTitle("About FaceLock")
    self.setText("FaceLock &copy; 2018 by Luca Viola <br />Version: <b>"+__version__+"</b><br/><br/>🔒 Locks the screen automatically when you walk away!")
    self.setInformativeText('<a href="mailto:luca.viola@gmail.com">luca.viola@gmail.com</a>')
    self.setTextFormat(Qt.RichText)
    self.setDetailedText(message)
    self.setTextInteractionFlags(Qt.TextSelectableByMouse)
