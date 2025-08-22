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


# TODO: ADD INITAL VELO AS A PROPERTY OF THE FIRST ELEMENT IN THE PATH AND USE IT TO SET THE INITIAL VELOCITY OF THE ROBOT IN THE SIMULATION
# TODO: MAKE IT SO THE LAST ELEMENT IN THE PATH IS THE FINAL VELOCITY OF THE ROBOT IN THE SIMULATION AND FOR THE JSON 
# these should be seperate spinners from the core and optional dropdowns
# no other elements need it or should have it as a property
# these properties should be removed from the config.json file and be set to zero by default for both. 
# each path.json should have a final and initial velocity property that is set to zero by default at the top of the file, sperate from any other properties. 