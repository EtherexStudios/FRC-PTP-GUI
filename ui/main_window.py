from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget
import math
from .sidebar import Sidebar
from models.path_model import TranslationTarget, RotationTarget, Waypoint, Path
from .canvas import CanvasView, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
from PySide6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent init
        self.setWindowTitle("FRC Path Editor")
        self.resize(1000, 600)

        self.path = Path()  # Create model
        # Better test path: centered and on-screen with all element types
        center_x = FIELD_LENGTH_METERS / 2.0
        center_y = FIELD_WIDTH_METERS / 2.0

        self.path.path_elements.extend([
            # Left of center - TranslationTarget
            TranslationTarget(x_meters=center_x - 2.5, y_meters=center_y, intermediate_handoff_radius_meters=0.5),
            # Above center - RotationTarget (45 deg)
            RotationTarget(rotation_radians=math.radians(45), x_meters=center_x, y_meters=center_y + 1.5),
            # Center - Waypoint (rotation -30 deg)
            Waypoint(
                translation_target=TranslationTarget(x_meters=center_x, y_meters=center_y),
                rotation_target=RotationTarget(rotation_radians=math.radians(-30), x_meters=center_x, y_meters=center_y)
            ),
            # Right of center - TranslationTarget
            TranslationTarget(x_meters=center_x + 2.5, y_meters=center_y),
            # Below center - TranslationTarget
            TranslationTarget(x_meters=center_x, y_meters=center_y - 1.8),
        ])

        central = QWidget()  # Blank container for content
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)  # Horizontal split

        # Canvas (left)
        self.canvas = CanvasView()
        layout.addWidget(self.canvas, stretch=3)  # Wider

        # Placeholder for sidebar (right)
        self.sidebar = Sidebar()
        self.sidebar.set_path(self.path)
        layout.addWidget(self.sidebar, stretch=1)  # Narrower

        # Initialize canvas with path
        self.canvas.set_path(self.path)

        # Wire up interactions: sidebar <-> canvas
        self.sidebar.elementSelected.connect(self.canvas.select_index)
        self.canvas.elementSelected.connect(self.sidebar.select_index)

        # Sidebar changes -> canvas refresh
        self.sidebar.modelChanged.connect(self.canvas.refresh_from_model)
        self.sidebar.modelStructureChanged.connect(lambda: self.canvas.set_path(self.path))

        # Canvas interactions -> update model and sidebar
        self.canvas.elementMoved.connect(self._on_canvas_element_moved, Qt.QueuedConnection)
        self.canvas.elementRotated.connect(self._on_canvas_element_rotated, Qt.QueuedConnection)

    def _on_canvas_element_moved(self, index: int, x_m: float, y_m: float):
        if index < 0 or index >= len(self.path.path_elements):
            return
        # Clamp via sidebar metadata to keep UI and model consistent
        x_m = Sidebar._clamp_from_metadata('x_meters', float(x_m))
        y_m = Sidebar._clamp_from_metadata('y_meters', float(y_m))
        elem = self.path.path_elements[index]
        if isinstance(elem, TranslationTarget):
            elem.x_meters = x_m
            elem.y_meters = y_m
        elif isinstance(elem, RotationTarget):
            elem.x_meters = x_m
            elem.y_meters = y_m
        elif isinstance(elem, Waypoint):
            elem.translation_target.x_meters = x_m
            elem.translation_target.y_meters = y_m
            elem.rotation_target.x_meters = x_m
            elem.rotation_target.y_meters = y_m
        # Update only values to avoid rebuilding the UI while dragging
        self.sidebar.update_current_values_only()

    def _on_canvas_element_rotated(self, index: int, radians: float):
        if index < 0 or index >= len(self.path.path_elements):
            return
        elem = self.path.path_elements[index]
        # Clamp using sidebar metadata (degrees domain), then convert back to radians
        degrees = math.degrees(radians)
        degrees = Sidebar._clamp_from_metadata('rotation_degrees', float(degrees))
        clamped_radians = math.radians(degrees)
        if isinstance(elem, RotationTarget):
            elem.rotation_radians = clamped_radians
        elif isinstance(elem, Waypoint):
            elem.rotation_target.rotation_radians = clamped_radians
        # Update sidebar fields
        self.sidebar.update_current_values_only()