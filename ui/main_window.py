from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QMenuBar, QAction, QFileDialog, QMessageBox
from ui.path_canvas import PathCanvas
from ui.params_sidebar import ParamsSidebar
from models.path_model import PathModel
from utils.json_utils import export_json, import_json

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent constructor
        self.setWindowTitle("FRC Path Editor")  # Title bar
        self.resize(1000, 600)  # Starting size

        self.model = PathModel()  # Create data model

        # Central area
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)  # Horizontal split

        self.canvas = PathCanvas(self.model)  # Left: Canvas
        layout.addWidget(self.canvas, stretch=3)  # 3x wider

        self.sidebar = ParamsSidebar(self.model)  # Right: Sidebar
        layout.addWidget(self.sidebar, stretch=1)

        # Menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        export_action = QAction("Export JSON", self)
        export_action.triggered.connect(self.export_path)  # Connect to function
        file_menu.addAction(export_action)
        # Add import similarly

        # Connect canvas signal to sidebar
        self.canvas.point_selected.connect(self.sidebar.load_params)

    def export_path(self):
        file_path = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON (*.json)")[0]
        if file_path:
            export_json(self.model, file_path)
            QMessageBox.information(self, "Success", "Path saved!")