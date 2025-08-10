import os
import json
from pathlib import Path
from typing import List, Optional, Tuple
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import QObject, Signal


class ProjectManager(QObject):
    """Manages project directory selection and path file operations."""
    
    # Signals
    project_selected = Signal(str)  # Emitted when a project directory is selected
    path_opened = Signal(str)  # Emitted when a path file is opened
    project_closed = Signal()  # Emitted when project is closed
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_project_dir: Optional[str] = None
        self.paths_dir: Optional[str] = None
        self.ui_config_dir: Optional[str] = None
    
    def select_project_directory(self, parent_widget) -> bool:
        """Open dialog to select project directory and validate structure."""
        dialog = QFileDialog(parent_widget)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setWindowTitle("Select Project Directory")
        
        if dialog.exec() == QFileDialog.Accepted:
            selected_dir = dialog.selectedFiles()[0]
            if self._validate_project_directory(selected_dir):
                self._set_project_directory(selected_dir)
                return True
            else:
                QMessageBox.warning(
                    parent_widget,
                    "Invalid Project Directory",
                    "The selected directory must contain a 'paths/' subdirectory.\n\n"
                    "Creating required structure..."
                )
                # Try to create the required structure
                if self._create_project_structure(selected_dir):
                    self._set_project_directory(selected_dir)
                    return True
                else:
                    QMessageBox.critical(
                        parent_widget,
                        "Failed to Create Project",
                        "Could not create required project structure."
                    )
                    return False
        return False
    
    def _validate_project_directory(self, directory: str) -> bool:
        """Validate that the directory has the required structure."""
        paths_dir = os.path.join(directory, "paths")
        return os.path.isdir(paths_dir)
    
    def _create_project_structure(self, directory: str) -> bool:
        """Create the required project directory structure."""
        try:
            paths_dir = os.path.join(directory, "paths")
            ui_config_dir = os.path.join(directory, "ui-config")
            
            # Create directories
            os.makedirs(paths_dir, exist_ok=True)
            os.makedirs(ui_config_dir, exist_ok=True)
            
            # Create default app.json if it doesn't exist
            app_json_path = os.path.join(ui_config_dir, "app.json")
            if not os.path.exists(app_json_path):
                default_config = {
                    "elementDimensions": {
                        "waypoint": {"widthMeters": 0.25, "heightMeters": 0.25},
                        "rotation": {"widthMeters": 0.35, "heightMeters": 0.10}
                    },
                    "lastProjectDir": None,
                    "lastOpenedPath": None,
                    "autosave": {"debounceMs": 300},
                    "floatPrecision": None
                }
                with open(app_json_path, 'w') as f:
                    json.dump(default_config, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error creating project structure: {e}")
            return False
    
    def _set_project_directory(self, directory: str):
        """Set the current project directory and update paths."""
        self.current_project_dir = directory
        self.paths_dir = os.path.join(directory, "paths")
        self.ui_config_dir = os.path.join(directory, "ui-config")
        self.project_selected.emit(directory)
    
    def get_project_directory(self) -> Optional[str]:
        """Get the current project directory."""
        return self.current_project_dir
    
    def get_paths_directory(self) -> Optional[str]:
        """Get the paths subdirectory."""
        return self.paths_dir
    
    def get_ui_config_directory(self) -> Optional[str]:
        """Get the ui-config subdirectory."""
        return self.ui_config_dir
    
    def list_path_files(self) -> List[Tuple[str, str]]:
        """List available path files with names and full paths."""
        if not self.paths_dir:
            return []
        
        try:
            path_files = []
            for file_path in Path(self.paths_dir).glob("*.json"):
                if file_path.is_file():
                    name = file_path.stem  # filename without extension
                    full_path = str(file_path.absolute())
                    path_files.append((name, full_path))
            
            # Sort by name
            path_files.sort(key=lambda x: x[0])
            return path_files
        except Exception as e:
            print(f"Error listing path files: {e}")
            return []
    
    def open_path_file(self, parent_widget) -> Optional[str]:
        """Open dialog to select and open a path file."""
        if not self.paths_dir:
            QMessageBox.warning(
                parent_widget,
                "No Project Selected",
                "Please select a project directory first."
            )
            return None
        
        path_files = self.list_path_files()
        if not path_files:
            QMessageBox.information(
                parent_widget,
                "No Path Files",
                "No path files found in the project.\n\n"
                "Create a new path file to get started."
            )
            return None
        
        # Create a simple selection dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout
        
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle("Open Path File")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # List widget
        list_widget = QListWidget()
        for name, _ in path_files:
            list_widget.addItem(name)
        layout.addWidget(list_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        open_button = QPushButton("Open")
        cancel_button = QPushButton("Cancel")
        button_layout.addWidget(open_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Wire up signals
        open_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        
        # Handle selection
        selected_path = None
        if dialog.exec() == QDialog.Accepted:
            current_row = list_widget.currentRow()
            if current_row >= 0:
                selected_path = path_files[current_row][1]
        
        if selected_path:
            self.path_opened.emit(selected_path)
            return selected_path
        
        return None
    
    def create_new_path_file(self, parent_widget, filename: str) -> Optional[str]:
        """Create a new empty path file."""
        if not self.paths_dir:
            return None
        
        try:
            # Ensure filename has .json extension
            if not filename.endswith('.json'):
                filename += '.json'
            
            file_path = os.path.join(self.paths_dir, filename)
            
            # Check if file already exists
            if os.path.exists(file_path):
                QMessageBox.warning(
                    parent_widget,
                    "File Exists",
                    f"A file named '{filename}' already exists."
                )
                return None
            
            # Create empty path file
            empty_path = []
            with open(file_path, 'w') as f:
                json.dump(empty_path, f)
            
            return file_path
            
        except Exception as e:
            QMessageBox.critical(
                parent_widget,
                "Error",
                f"Failed to create path file: {str(e)}"
            )
            return None
    
    def close_project(self):
        """Close the current project."""
        self.current_project_dir = None
        self.paths_dir = None
        self.ui_config_dir = None
        self.project_closed.emit()
    
    def is_project_open(self) -> bool:
        """Check if a project is currently open."""
        return self.current_project_dir is not None