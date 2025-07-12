from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QLabel
from .sidebar import Sidebar
from models.path_model import PathModel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent init
        self.setWindowTitle("FRC Path Editor")
        self.resize(1000, 600)

        self.model = PathModel()  # Create model
        # Test add (temporary, remove later)
        self.model.add_point(0, 0, 'translation')
        self.model.add_point(1, 1, 'waypoint')

        central = QWidget()  # Blank container for content
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)  # Horizontal split

        # Placeholder for canvas (left)
        canvas_placeholder = QLabel("Canvas Here")
        layout.addWidget(canvas_placeholder, stretch=3)  # Wider

        # Placeholder for sidebar (right)
        self.sidebar = Sidebar(self.model)
        layout.addWidget(self.sidebar, stretch=1)  # Narrower