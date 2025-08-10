from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QFileDialog, QMenuBar, QMenu, QDialog
from PySide6.QtGui import QAction
import math
import os
from .sidebar import Sidebar
from models.path_model import TranslationTarget, RotationTarget, Waypoint, Path
from .canvas import CanvasView, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
from typing import Tuple
from PySide6.QtCore import Qt, QTimer
from utils.project_manager import ProjectManager
from .config_dialog import ConfigDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent init
        self.setWindowTitle("FRC Path Editor")
        self.resize(1000, 600)
        self.project_manager = ProjectManager()
        self.path = Path()  # start empty; will be replaced on project load

        central = QWidget()  # Blank container for content
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)  # Horizontal split

        # Canvas (left)
        # Initialize canvas with default robot dims; will update after config load
        self.canvas = CanvasView()
        layout.addWidget(self.canvas, stretch=3)  # Wider

        # Placeholder for sidebar (right)
        self.sidebar = Sidebar()
        # Provide project manager to sidebar for config defaults
        self.sidebar.project_manager = self.project_manager
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
        # Handle end-of-drag to fix rotation ordering once user releases
        self.canvas.elementDragFinished.connect(self._on_canvas_drag_finished, Qt.QueuedConnection)

        # Auto-save debounce timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(300)
        self._autosave_timer.timeout.connect(self._do_autosave)

        # Hook autosave on model changes
        self.sidebar.modelChanged.connect(self._schedule_autosave)
        self.sidebar.modelStructureChanged.connect(self._schedule_autosave)
        self.canvas.elementDragFinished.connect(self._schedule_autosave)

        # Build menubar
        self._build_menu_bar()
        
        # Create status bar for current path display
        self.statusBar = self.statusBar()
        self.statusBar.showMessage("No path loaded")

        # Startup: load last project or prompt
        QTimer.singleShot(0, self._startup_load)

    # ---------------- Menu Bar ----------------
    def _build_menu_bar(self):
        bar: QMenuBar = self.menuBar()
        # Ensure menu bar is visible
        bar.setVisible(True)
        bar.setNativeMenuBar(False)  # Force Qt menu bar instead of native macOS menu
        
        # Project menu - for opening and managing projects
        project_menu: QMenu = bar.addMenu("Project")
        self.action_open_project = QAction("Open Project…", self)
        self.action_open_project.triggered.connect(self._action_open_project)
        project_menu.addAction(self.action_open_project)
        
        # Recent Projects submenu
        self.menu_recent_projects: QMenu = project_menu.addMenu("Recent Projects")
        self.menu_recent_projects.aboutToShow.connect(self._populate_recent_projects)
        
        # Path menu - for managing paths
        path_menu: QMenu = bar.addMenu("Path")
        
        # Current Path display (read-only)
        self.action_current_path = QAction("Current: (No Path)", self)
        self.action_current_path.setEnabled(False)  # Make it read-only
        path_menu.addAction(self.action_current_path)
        
        path_menu.addSeparator()  # Add a separator line
        
        # Load Path submenu (dynamic)
        self.menu_load_path: QMenu = path_menu.addMenu("Load Path")
        self.menu_load_path.aboutToShow.connect(self._populate_load_path_menu)

        # Create New Path action
        self.action_new_path = QAction("Create New Path", self)
        self.action_new_path.triggered.connect(self._action_create_new_path)
        path_menu.addAction(self.action_new_path)

        # Save As…
        self.action_save_as = QAction("Save Path As…", self)
        self.action_save_as.triggered.connect(self._action_save_as)
        path_menu.addAction(self.action_save_as)
        
        # Delete Path action (opens dialog)
        self.action_delete_path = QAction("Delete Paths...", self)
        self.action_delete_path.triggered.connect(self._show_delete_path_dialog)
        path_menu.addAction(self.action_delete_path)
        
        # Settings menu - for configuration
        settings_menu: QMenu = bar.addMenu("Settings")
        self.action_edit_config = QAction("Edit Config…", self)
        self.action_edit_config.triggered.connect(self._action_edit_config)
        settings_menu.addAction(self.action_edit_config)
        
        # Debug: print menu bar info
        print(f"Menu bar created: {bar.isVisible()}, {bar.height()}, {bar.width()}")
        print(f"Menu bar actions: {[action.text() for action in bar.actions()]}")
        # Force menu bar to be visible and sized properly
        self.menuBar().setVisible(True)
        self.menuBar().setMinimumHeight(30)

    def _populate_load_path_menu(self):
        self.menu_load_path.clear()
        files = self.project_manager.list_paths()
        if not files:
            a = QAction("(No paths)", self)
            a.setEnabled(False)
            self.menu_load_path.addAction(a)
            return
        for fname in files:
            act = QAction(fname, self)
            act.triggered.connect(lambda checked=False, f=fname: self._load_path_file(f))
            self.menu_load_path.addAction(act)

    def _populate_recent_projects(self):
        self.menu_recent_projects.clear()
        recents = self.project_manager.recent_projects()
        if not recents:
            a = QAction("(No recent projects)", self)
            a.setEnabled(False)
            self.menu_recent_projects.addAction(a)
            return
        for d in recents:
            label = d
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, dirpath=d: self._open_recent_project(dirpath))
            self.menu_recent_projects.addAction(act)

    def _show_delete_path_dialog(self):
        """Show a dialog for selecting and deleting paths"""
        if not self.project_manager.has_valid_project():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Project", "Please open a project first.")
            return
            
        files = self.project_manager.list_paths()
        if not files:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Paths", "No paths found to delete.")
            return
        
        # Create a custom dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel, QScrollArea, QWidget
        from PySide6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Paths")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Header
        header_label = QLabel("Select paths to delete:")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)
        
        # Scrollable area for checkboxes
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Create checkboxes for each path
        checkboxes = {}
        for fname in files:
            cb = QCheckBox(fname)
            # Mark current path with an indicator
            if fname == self.project_manager.current_path_file:
                cb.setText(f"✓ {fname} (Current)")
                cb.setStyleSheet("color: #d32f2f; font-weight: bold;")
            checkboxes[fname] = cb
            scroll_layout.addWidget(cb)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Select All/None buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb in checkboxes.values()])
        
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(lambda: [cb.setChecked(False) for cb in checkboxes.values()])
        
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch()
        
        # Delete and Cancel buttons
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")
        delete_btn.clicked.connect(lambda: self._delete_paths_from_dialog(checkboxes, dialog))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addWidget(delete_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec()

    # ---------------- Startup and Actions ----------------
    def _startup_load(self):
        if self.project_manager.load_last_project() and self.project_manager.has_valid_project():
            # Load config and apply canvas dims
            cfg = self.project_manager.load_config()
            self._apply_robot_dims_from_config(cfg)
            # Load last or first or create
            path, filename = self.project_manager.load_last_or_first_or_create()
            self._set_path_model(path)
            # Update the current path display after startup
            self._update_current_path_display()
        else:
            # No valid project – show file dialog
            self._action_open_project(force_dialog=True)

    def _apply_robot_dims_from_config(self, cfg):
        try:
            length_m = float(cfg.get("robot_length_meters", 0.60) or 0.60)
            width_m = float(cfg.get("robot_width_meters", 0.60) or 0.60)
        except Exception:
            length_m, width_m = 0.60, 0.60
        self.canvas.set_robot_dimensions(length_m, width_m)

    def _action_open_project(self, force_dialog: bool = False):
        directory = None
        if not force_dialog and self.project_manager.has_valid_project():
            directory = self.project_manager.project_dir
        if directory is None:
            directory = QFileDialog.getExistingDirectory(self, "Open Project Directory")
            if not directory:
                # Keep empty path visible
                self._set_path_model(Path())
                return
        self.project_manager.set_project_dir(directory)
        cfg = self.project_manager.load_config()
        self._apply_robot_dims_from_config(cfg)
        path, filename = self.project_manager.load_last_or_first_or_create()
        self._set_path_model(path)
        # Update the current path display after opening project
        self._update_current_path_display()

    def _open_recent_project(self, directory: str):
        if not directory:
            return
        self.project_manager.set_project_dir(directory)
        cfg = self.project_manager.load_config()
        self._apply_robot_dims_from_config(cfg)
        path, filename = self.project_manager.load_last_or_first_or_create()
        self._set_path_model(path)
        # Update the current path display after opening recent project
        self._update_current_path_display()

    def _action_edit_config(self):
        cfg = self.project_manager.load_config()
        dlg = ConfigDialog(self, cfg, on_change=self._on_config_live_change)
        if dlg.exec() == QDialog.Accepted:
            new_cfg = dlg.get_values()
            self.project_manager.save_config(new_cfg)
            # Apply to canvas if robot dims changed
            self._apply_robot_dims_from_config(self.project_manager.config)
            # Sidebar will use defaults from project_manager when adding optionals

            # Refresh sidebar for current selection so defaults/UI reflect changes
            self.sidebar.refresh_current_selection()

    def _on_config_live_change(self, key: str, value: float):
        # Persist to config immediately
        self.project_manager.save_config({key: value})
        if key in ("robot_length_meters", "robot_width_meters"):
            self._apply_robot_dims_from_config(self.project_manager.config)
        # For optional defaults, no immediate changes unless fields are being added later.
        # Still refresh visible sidebar to reflect any fields that might show defaults.
        self.sidebar.refresh_current_selection()

    def _load_path_file(self, filename: str):
        p = self.project_manager.load_path(filename)
        if p is None:
            return
        self._set_path_model(p)
        # Update the current path display after loading a path
        self._update_current_path_display()

    def _action_save_as(self):
        if not self.project_manager.get_paths_dir():
            # Need project first
            self._action_open_project(force_dialog=True)
            if not self.project_manager.get_paths_dir():
                return
        base_dir = self.project_manager.get_paths_dir()
        suggested = self.project_manager.current_path_file or "untitled.json"
        file_tuple = QFileDialog.getSaveFileName(self, "Save Path As", _os.path.join(base_dir, suggested), "JSON Files (*.json)")
        filepath = file_tuple[0]
        if not filepath:
            return
        # Normalize to project paths folder
        try:
            import os as _os
            folder, name = _os.path.split(filepath)
            if _os.path.abspath(folder) != _os.path.abspath(base_dir):
                # Force save into paths dir
                name = name or suggested
                filepath = _os.path.join(base_dir, name)
        except Exception:
            pass
        # Save
        try:
            import os as _os
            filename = _os.path.basename(filepath)
            self.project_manager.save_path(self.path, filename)
        except Exception:
            pass

    def _action_create_new_path(self):
        """Create a new blank path and clear the current model"""
        # Create a new empty path
        new_path = Path()
        self._set_path_model(new_path)
        
        # If we have a valid project, save it as a new file
        if self.project_manager.has_valid_project():
            # Prompt user for filename
            from PySide6.QtWidgets import QInputDialog
            filename, ok = QInputDialog.getText(
                self, "Create New Path", 
                "Enter path name:", 
                text="new_path"
            )
            
            if ok and filename:
                # Add .json extension if not present
                if not filename.endswith('.json'):
                    filename += '.json'
                
                # Check if file already exists
                if os.path.exists(os.path.join(self.project_manager.project_dir, "paths", filename)):
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "File Exists", f"A path named '{filename}' already exists. Please choose a different name.")
                    return
                
                # Save the new path
                self.project_manager.save_path(new_path, filename)
                # Refresh the load path menu
                self._populate_load_path_menu()
            else:
                # User cancelled, just show the empty path without saving
                print("User cancelled path creation")
        else:
            # No project open, just show the empty path
            print("No project open - showing empty path")

    def _delete_paths_from_dialog(self, checkboxes: dict, dialog: QDialog):
        """Delete the selected paths from the dialog after confirmation"""
        # Get selected paths from checkboxes
        selected_paths = [fname for fname, cb in checkboxes.items() if cb.isChecked()]
        
        if not selected_paths:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Selection", "Please select at least one path to delete.")
            return
        
        # Check if current path is being deleted
        current_path_deleted = False
        if self.project_manager.current_path_file in selected_paths:
            current_path_deleted = True
        
        # Show confirmation dialog
        from PySide6.QtWidgets import QMessageBox
        if len(selected_paths) == 1:
            msg = f"Are you sure you want to delete '{selected_paths[0]}'?"
            if current_path_deleted:
                msg += "\n\n⚠️  This will close the currently open path."
        else:
            msg = f"Are you sure you want to delete {len(selected_paths)} paths?\n\n" + "\n".join(f"• {path}" for path in selected_paths)
            if current_path_deleted:
                msg += "\n\n⚠️  This will close the currently open path."
        
        reply = QMessageBox.question(
            self, "Confirm Deletion", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No  # Default to No for safety
        )
        
        if reply == QMessageBox.Yes:
            # Delete the selected paths
            deleted_count = 0
            
            for path_name in selected_paths:
                if self.project_manager.delete_path(path_name):
                    deleted_count += 1
            
            # Show result
            if deleted_count == 1:
                QMessageBox.information(self, "Path Deleted", f"Successfully deleted '{selected_paths[0]}'")
            else:
                QMessageBox.information(self, "Paths Deleted", f"Successfully deleted {deleted_count} paths")
            
            # Close the dialog
            dialog.accept()
            
            # Handle current path deletion
            if current_path_deleted:
                self._handle_current_path_deleted()
            
            # Refresh the load path menu since we no longer have a delete menu
            self._populate_load_path_menu()

    def _handle_current_path_deleted(self):
        """Handle the case where the currently open path was deleted"""
        # Clear the current path
        self._set_path_model(Path())
        self._update_current_path_display()
        
        # Check if there are other paths available
        available_paths = self.project_manager.list_paths()
        
        if not available_paths:
            # No paths left - just inform the user
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, 
                "No Paths Available", 
                "The current path was deleted and no other paths are available.\n\n"
                "You can create a new path or open a different project."
            )
            return
        
        # Ask user if they want to load another path
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Current Path Deleted",
            f"The current path was deleted.\n\n"
            f"There are {len(available_paths)} other paths available.\n\n"
            "Would you like to load one of them?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes  # Default to Yes for convenience
        )
        
        if reply == QMessageBox.Yes:
            # Show path selection dialog
            self._show_path_selection_dialog()
        else:
            # User chose to continue without a path
            QMessageBox.information(
                self,
                "No Path Loaded",
                "You can create a new path or load an existing one from the Path menu."
            )

    def _show_path_selection_dialog(self):
        """Show a dialog for selecting which path to load"""
        available_paths = self.project_manager.list_paths()
        if not available_paths:
            return
        
        # Create a simple selection dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem
        from PySide6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Path to Load")
        dialog.setModal(True)
        dialog.resize(350, 250)
        
        layout = QVBoxLayout(dialog)
        
        # Header
        header_label = QLabel("Select a path to load:")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)
        
        # List of available paths
        path_list = QListWidget()
        for path_name in available_paths:
            item = QListWidgetItem(path_name)
            path_list.addItem(item)
        
        # Select the first item by default
        if path_list.count() > 0:
            path_list.setCurrentRow(0)
        
        layout.addWidget(path_list)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Load and Cancel buttons
        load_btn = QPushButton("Load Selected")
        load_btn.setStyleSheet("background-color: #4caf50; color: white; font-weight: bold;")
        load_btn.clicked.connect(lambda: self._load_selected_path_from_dialog(path_list, dialog))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(load_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec()

    def _load_selected_path_from_dialog(self, path_list, dialog):
        """Load the selected path from the path selection dialog"""
        current_item = path_list.currentItem()
        if not current_item:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Selection", "Please select a path to load.")
            return
        
        selected_path = current_item.text()
        
        # Load the selected path
        path = self.project_manager.load_path(selected_path)
        if path is not None:
            self._set_path_model(path)
            self._update_current_path_display()
            dialog.accept()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to load path '{selected_path}'.")

    def _set_path_model(self, path: Path):
        self.path = path
        self.sidebar.set_path(self.path)
        self.canvas.set_path(self.path)
        # Update the current path display
        self._update_current_path_display()
        # Save immediately to ensure file exists
        self._schedule_autosave()

    def _update_current_path_display(self):
        """Update the current path display in the menu, window title, and status bar"""
        if hasattr(self, 'action_current_path'):
            if self.project_manager.has_valid_project() and self.project_manager.current_path_file:
                # Show the current path filename
                path_name = self.project_manager.current_path_file
                if path_name.endswith('.json'):
                    path_name = path_name[:-5]  # Remove .json extension for display
                self.action_current_path.setText(f"Current: {path_name}")
                
                # Update window title to show current project and path
                project_name = os.path.basename(self.project_manager.project_dir)
                self.setWindowTitle(f"FRC Path Planning - {project_name} - {path_name}")
                
                # Update status bar
                if hasattr(self, 'statusBar'):
                    self.statusBar.showMessage(f"Current Path: {path_name} | Project: {project_name}")
            else:
                # No project or no current path
                self.action_current_path.setText("Current: (No Path)")
                self.setWindowTitle("FRC Path Planning")
                
                # Update status bar
                if hasattr(self, 'statusBar'):
                    self.statusBar.showMessage("No path loaded")

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
        # defer autosave until drag finished; handled by elementDragFinished

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
        # Debounced autosave on rotation changes
        self._schedule_autosave()

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

    # ---------------- Autosave ----------------
    def _schedule_autosave(self):
        # Coalesce frequent updates
        self._autosave_timer.start()

    def _do_autosave(self):
        # Ensure project dir exists before saving
        if not self.project_manager.has_valid_project():
            return
        self.project_manager.save_path(self.path)