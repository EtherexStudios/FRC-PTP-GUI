import faulthandler
faulthandler.enable()

import gc
gc.disable()

import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow  # Import your class

app = QApplication(sys.argv)
window = MainWindow()  # Use custom class
window.show()
sys.exit(app.exec())