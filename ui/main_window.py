from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QMenuBar, QMenu, QAction, QVBoxLayout, QComboBox, QLabel, QStatusBar, QMessageBox
import math
import os
import json
from .sidebar import Sidebar
from models.path_model import TranslationTarget, RotationTarget, Waypoint, Path
from .canvas import CanvasView, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
from typing import Tuple, Optional
from PySide6.QtCore import Qt, QTimer
from utils.ui_config import UIConfigManager
from utils.autosave_manager import AutosaveManager
from utils.project_manager import ProjectManager
from utils.file_watcher import FileChangeWatcher
from utils.path_adapter import PathModelAdapter
from utils.path_io import deserialize, serialize_to_bytes, compute_hash

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent init
        self.setWindowTitle("FRC Path Editor")
        self.resize(1000, 600)

        # Initialize managers
        self._init_managers()
        
        # Create path model
        self.path = Path()
        self.current_path_file: Optional[str] = None
        
        # Create UI
        self._create_ui()
        self._create_menu_bar()
        self._create_status_bar()
        
        # Initialize with test data if no project
        self._init_test_path()
        
        # Wire up signals
        self._wire_up_signals()
        
        # Load last project if available
        self._load_last_project()
    
    def _init_managers(self):
        """Initialize utility managers."""
        # UI config manager (will be set to project-specific config when project is selected)
        self.ui_config_manager = None
        
        # Project manager
        self.project_manager = ProjectManager(self)
        self.project_manager.project_selected.connect(self._on_project_selected)
        self.project_manager.path_opened.connect(self._on_path_opened)
        
        # Autosave manager
        self.autosave_manager = AutosaveManager()
        self.autosave_manager.set_get_elements_callback(self._get_current_elements)
        self.autosave_manager.status_message.connect(self._show_status_message)
        self.autosave_manager.save_started.connect(self._on_autosave_started)
        self.autosave_manager.save_completed.connect(self._on_autosave_completed)
        self.autosave_manager.save_failed.connect(self._on_autosave_failed)
        
        # File watcher
        self.file_watcher = FileChangeWatcher(self)
        self.file_watcher.reload_requested.connect(self._on_file_watcher_reload_requested)
        self.file_watcher.ignore_requested.connect(self._ignore_file_change)
    
    def _create_ui(self):
        """Create the main UI components."""
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        
        # Top toolbar for path selection
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("Current Path:"))
        
        self.path_combo = QComboBox()
        self.path_combo.setMinimumWidth(200)
        self.path_combo.currentTextChanged.connect(self._on_path_combo_changed)
        toolbar_layout.addWidget(self.path_combo)
        
        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)
        
        # Main content layout
        content_layout = QHBoxLayout()
        
        # Canvas (left)
        self.canvas = CanvasView()
        content_layout.addWidget(self.canvas, stretch=3)
        
        # Sidebar (right)
        self.sidebar = Sidebar()
        self.sidebar.set_path(self.path)
        content_layout.addWidget(self.sidebar, stretch=1)
        
        main_layout.addLayout(content_layout)
    
    def _create_menu_bar(self):
        """Create the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        # Project actions
        select_project_action = QAction("&Select Project Directory...", self)
        select_project_action.triggered.connect(self._select_project_directory)
        file_menu.addAction(select_project_action)
        
        open_path_action = QAction("&Open Path...", self)
        open_path_action.triggered.connect(self._open_path_file)
        self.open_path_action = open_path_action
        file_menu.addAction(open_path_action)
        
        file_menu.addSeparator()
        
        reload_action = QAction("&Reload Current Path", self)
        reload_action.triggered.connect(self._reload_current_path)
        self.reload_action = reload_action
        file_menu.addAction(reload_action)
        
        # Initially disable path-related actions
        self.open_path_action.setEnabled(False)
        self.reload_action.setEnabled(False)
    
    def _create_status_bar(self):
        """Create the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
    
    def _init_test_path(self):
        """Initialize with test path data."""
        center_x = FIELD_LENGTH_METERS / 2.0
        center_y = FIELD_WIDTH_METERS / 2.0

        self.path.path_elements.extend([
            # Left of center - TranslationTarget
            TranslationTarget(x_meters=center_x - 2.5, y_meters=center_y, intermediate_handoff_radius_meters=0.5),
            # Above center - RotationTarget (45 deg)
            RotationTarget(rotation_radians=math.radians(45), x_meters=center_x, y_meters=center_y + 1.5),
            # Center - Waypoint (rotation -30 deg)
            Waypoint(
                translation_target=TranslationTarget(x_meters=center_x+1, y_meters=center_y),
                rotation_target=RotationTarget(rotation_radians=math.radians(-30), x_meters=center_x, y_meters=center_y)
            ),
            # Right of center - TranslationTarget
            TranslationTarget(x_meters=center_x + 2.5, y_meters=center_y),
            # Below center - TranslationTarget
            TranslationTarget(x_meters=center_x, y_meters=center_y - 1.8),
        ])
        
        # Initialize canvas and sidebar
        self.canvas.set_path(self.path)
        self.sidebar.set_path(self.path)
    
    def _wire_up_signals(self):
        """Wire up all the signal connections."""
        # Sidebar <-> Canvas interactions
        self.sidebar.elementSelected.connect(self.canvas.select_index)
        self.canvas.elementSelected.connect(self.sidebar.select_index)

        # Sidebar changes -> canvas refresh
        self.sidebar.modelChanged.connect(self._on_path_model_changed)
        self.sidebar.modelStructureChanged.connect(self._on_path_structure_changed)

        # Canvas interactions -> update model and sidebar
        self.canvas.elementMoved.connect(self._on_canvas_element_moved, Qt.QueuedConnection)
        self.canvas.elementRotated.connect(self._on_canvas_element_rotated, Qt.QueuedConnection)
        self.canvas.elementDragFinished.connect(self._on_canvas_drag_finished, Qt.QueuedConnection)
    
    def _load_last_project(self):
        """Load the last opened project if available."""
        # This will be implemented when we have a global config
        pass
    
    # Project management methods
    def _select_project_directory(self):
        """Handle project directory selection."""
        if self.project_manager.select_project_directory(self):
            self._show_status_message("Project selected successfully")
    
    def _on_project_selected(self, project_dir: str):
        """Called when a project directory is selected."""
        # Initialize UI config manager for this project
        self.ui_config_manager = UIConfigManager(project_dir)
        
        # Update autosave debounce time
        debounce_ms = self.ui_config_manager.get_autosave_debounce_ms()
        self.autosave_manager.set_debounce_ms(debounce_ms)
        
        # Enable path-related actions
        self.open_path_action.setEnabled(True)
        self.reload_action.setEnabled(True)
        
        # Update path combo with available paths
        self._update_path_combo()
        
        # Update status
        self._show_status_message(f"Project: {os.path.basename(project_dir)}")
        
        # Try to load last opened path
        last_path = self.ui_config_manager.get_last_opened_path()
        if last_path and os.path.exists(last_path):
            self._load_path_file(last_path)
    
    def _on_path_opened(self, file_path: str):
        """Called when a path file is opened through the project manager."""
        self._load_path_file(file_path)
    
    def _update_path_combo(self):
        """Update the path combo box with available paths."""
        self.path_combo.clear()
        self.path_combo.addItem("-- Select Path --")
        
        path_files = self.project_manager.list_path_files()
        for name, _ in path_files:
            self.path_combo.addItem(name)
    
    def _open_path_file(self):
        """Open the path file selection dialog."""
        selected_path = self.project_manager.open_path_file(self)
        if selected_path:
            self._load_path_file(selected_path)
    
    def _on_path_combo_changed(self, path_name: str):
        """Handle path combo box selection change."""
        if path_name == "-- Select Path --" or not path_name:
            return
        
        # Find the full path for the selected name
        path_files = self.project_manager.list_path_files()
        for name, full_path in path_files:
            if name == path_name:
                self._load_path_file(full_path)
                break
    
    def _load_path_file(self, file_path: str):
        """Load a path file."""
        try:
            # Check if current path is dirty and needs saving
            if self.autosave_manager.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Save Changes?",
                    "The current path has unsaved changes. Save before loading new path?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                
                if reply == QMessageBox.Yes:
                    self.autosave_manager.flush_now()
                elif reply == QMessageBox.Cancel:
                    return
            
            # Load the file
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Deserialize
            elements = deserialize(data)
            
            # Convert to path model
            new_path = PathModelAdapter.from_serialization_format(elements)
            
            # Replace current path
            self.path.path_elements.clear()
            self.path.path_elements.extend(new_path.path_elements)
            
            # Update UI
            self.canvas.set_path(self.path)
            self.sidebar.set_path(self.path)
            
            # Set current path file for autosave
            self.current_path_file = file_path
            self.autosave_manager.set_current_path_file(file_path)
            
            # Start watching the file
            current_hash = compute_hash(serialize_to_bytes(elements))
            self.file_watcher.watch_file(file_path, current_hash)
            
            # Update path combo selection
            filename = os.path.basename(file_path)
            path_name = os.path.splitext(filename)[0]
            index = self.path_combo.findText(path_name)
            if index >= 0:
                self.path_combo.setCurrentIndex(index)
            
            # Update UI config
            if self.ui_config_manager:
                self.ui_config_manager.set_last_opened_path(file_path)
            
            self._show_status_message(f"Loaded: {path_name}")
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading Path",
                f"Failed to load path file:\n{str(e)}"
            )
            print(f"Error loading path file: {e}")
    
    def _reload_current_path(self):
        """Reload the currently opened path file."""
        if self.current_path_file and os.path.exists(self.current_path_file):
            # Pause autosave to prevent ping-pong
            self.autosave_manager.pause()
            self.file_watcher.pause_watching()
            
            try:
                self._load_path_file(self.current_path_file)
            finally:
                # Resume autosave and file watching
                self.autosave_manager.resume()
                self.file_watcher.resume_watching()
    
    def _ignore_file_change(self, file_path: str):
        """Handle user choosing to ignore a file change."""
        # Update the hash to prevent further prompts
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            new_hash = compute_hash(content)
            self.file_watcher.update_file_hash(file_path, new_hash)
        except Exception as e:
            print(f"Error updating file hash: {e}")
    
    def _on_file_watcher_reload_requested(self, file_path: str):
        """Handle file watcher requesting a reload."""
        if file_path == self.current_path_file:
            self._reload_current_path()
    
    # Autosave signal handlers
    def _on_autosave_started(self):
        """Called when autosave operation starts."""
        self.status_bar.showMessage("Saving...")
    
    def _on_autosave_completed(self):
        """Called when autosave operation completes successfully."""
        self.status_bar.showMessage("Saved successfully")
    
    def _on_autosave_failed(self, error_message: str):
        """Called when autosave operation fails."""
        self.status_bar.showMessage(f"Save failed: {error_message}")
        # Show error dialog
        QMessageBox.warning(
            self,
            "Autosave Failed",
            f"Failed to save changes:\n{error_message}"
        )
    
    # Path model change handling
    def _on_path_model_changed(self):
        """Called when the path model changes."""
        # Refresh canvas
        self.canvas.refresh_from_model()
        
        # Trigger autosave
        if self.current_path_file:
            self.autosave_manager.on_path_changed()
    
    def _on_path_structure_changed(self):
        """Called when the path model structure changes (add/remove/reorder)."""
        # Update canvas with new path
        self.canvas.set_path(self.path)
        
        # Trigger autosave
        if self.current_path_file:
            self.autosave_manager.on_path_changed()
    
    def _get_current_elements(self):
        """Get current elements for autosave."""
        return PathModelAdapter.get_current_elements(self.path)
    
    # Status and utility methods
    def _show_status_message(self, message: str):
        """Show a status message."""
        self.status_bar.showMessage(message)
        print(f"Status: {message}")

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
            # For rotation targets, keep them constrained on the segment between neighbors
            proj = self._project_point_between_neighbors(index, x_m, y_m)
            elem.x_meters, elem.y_meters = proj
        elif isinstance(elem, Waypoint):
            elem.translation_target.x_meters = x_m
            elem.translation_target.y_meters = y_m
            elem.rotation_target.x_meters = x_m
            elem.rotation_target.y_meters = y_m

        self.sidebar.update_current_values_only()
        # Emit path model changed signal for autosave
        self._on_path_model_changed()

    def _on_canvas_element_rotated(self, index: int, radians: float):
        if index < 0 or index >= len(self.path.path_elements):
            return
        elem = self.path.path_elements[index]
        # Clamp using sidebar metadata (degrees domain), then convert back to radians
        degrees = math.degrees(radians)
        degrees = Sidebar._clamp_from_metadata('rotation_degrees', float(degrees))
        clamped_radians = math.radians(radians)
        if isinstance(elem, RotationTarget):
            elem.rotation_radians = clamped_radians
        elif isinstance(elem, Waypoint):
            elem.rotation_target.rotation_radians = clamped_radians
        # Update sidebar fields
        self.sidebar.update_current_values_only()
        # Emit path model changed signal for autosave
        self._on_path_model_changed()

    def _reproject_all_rotation_positions(self):
        if self.path is None:
            return
        for idx, e in enumerate(self.path.path_elements):
            if isinstance(e, RotationTarget):
                # Project using current model state
                x_m, y_m = self._project_point_between_neighbors(idx, e.x_meters, e.y_meters)
                e.x_meters, e.y_meters = x_m, y_m

    def _project_point_between_neighbors(self, index: int, x_m: float, y_m: float) -> Tuple[float, float]:
        # Find previous and next translation/waypoint elements
        prev_pos = None
        for i in range(index - 1, -1, -1):
            e = self.path.path_elements[i]
            if isinstance(e, (TranslationTarget, Waypoint)):
                prev_pos = (e.x_meters, e.y_meters) if isinstance(e, TranslationTarget) else (
                    e.translation_target.x_meters, e.translation_target.y_meters)
                break
        next_pos = None
        for i in range(index + 1, len(self.path.path_elements)):
            e = self.path.path_elements[i]
            if isinstance(e, (TranslationTarget, Waypoint)):
                next_pos = (e.x_meters, e.y_meters) if isinstance(e, TranslationTarget) else (
                    e.translation_target.x_meters, e.translation_target.y_meters)
                break
        if prev_pos is None or next_pos is None:
            return x_m, y_m
        ax, ay = prev_pos
        bx, by = next_pos
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 0.0:
            return x_m, y_m
        t = ((x_m - ax) * dx + (y_m - ay) * dy) / denom
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        # Final clamp to field limits
        proj_x = Sidebar._clamp_from_metadata('x_meters', proj_x)
        proj_y = Sidebar._clamp_from_metadata('y_meters', proj_y)
        return proj_x, proj_y

    def _on_canvas_drag_finished(self, index: int):
        """Called once per item when the user releases the mouse after dragging."""
        if index < 0 or index >= len(self.path.path_elements):
            return
        # Remember which element was dragged so we can re-select it after any reordering
        dragged_elem = self.path.path_elements[index]

        # Re-evaluate rotation order now that the drag is complete
        self.sidebar._check_and_swap_rotation_targets()

        # Attempt to restore selection for the dragged element
        try:
            new_index = self.path.path_elements.index(dragged_elem)
        except ValueError:
            new_index = -1
        if new_index >= 0:
            self.sidebar.select_index(new_index)
        
        # Emit path model changed signal for autosave
        self._on_path_model_changed()