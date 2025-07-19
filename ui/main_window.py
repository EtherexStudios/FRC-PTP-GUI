from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QLabel
from .sidebar import Sidebar
from models.path_model import Translation2d, Rotation2d, TranslationTarget, RotationTarget, Waypoint, Path

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent init
        self.setWindowTitle("FRC Path Editor")
        self.resize(1000, 600)

        self.path = Path()  # Create model
        # Test add (temporary, remove later)

        self.path.path_elements.append(TranslationTarget(translation=Translation2d(9,10), intermediate_handoff_radius_meters=2))
        self.path.path_elements.append(TranslationTarget(translation=Translation2d(10,10)))
        self.path.path_elements.append(TranslationTarget(translation=Translation2d(11,10)))
        self.path.path_elements.append(Waypoint(translation_target=TranslationTarget(translation=Translation2d(12,21)), rotation_target=RotationTarget(rotation=Rotation2d(1), translation=Translation2d(12,21))))


        central = QWidget()  # Blank container for content
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)  # Horizontal split

        # Placeholder for canvas (left)
        canvas_placeholder = QLabel("Canvas Here")
        layout.addWidget(canvas_placeholder, stretch=3)  # Wider

        # Placeholder for sidebar (right)
        self.sidebar = Sidebar()
        self.sidebar.set_path(self.path)
        layout.addWidget(self.sidebar, stretch=1)  # Narrower