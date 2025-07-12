from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QLabel
from .sidebar import Sidebar

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent init
        self.setWindowTitle("FRC Path Editor")
        self.resize(1000, 600)

        central = QWidget()  # Blank container for content
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)  # Horizontal split

        # Placeholder for canvas (left)
        canvas_placeholder = QLabel("Canvas Here")
        layout.addWidget(canvas_placeholder, stretch=3)  # Wider

        # Placeholder for sidebar (right)
        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar, stretch=1)  # Narrower