from PySide6.QtCore import QObject, QFileSystemWatcher, Signal, QTimer
from PySide6.QtWidgets import QMessageBox, QCheckBox
from typing import Optional, Dict
import os
from .path_io import compute_hash


class FileChangeWatcher(QObject):
    """Watches for external changes to path files and prompts for reload."""
    
    # Signals
    file_changed_externally = Signal(str)  # Emitted when file changes externally
    reload_requested = Signal(str)  # Emitted when user chooses to reload
    ignore_requested = Signal(str)  # Emitted when user chooses to ignore
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self._on_file_changed)
        
        # State tracking
        self.watched_files: Dict[str, str] = {}  # file_path -> last_hash
        self.ignore_once_files: set = set()  # Files to ignore once
        self.always_reload_files: set = set()  # Files to always reload
        self.prompt_visible = False
        
        # Debounce timer for file changes
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._handle_file_change)
        self.pending_change = None
    
    def watch_file(self, file_path: str, current_hash: str):
        """Start watching a file for changes."""
        if not os.path.exists(file_path):
            return
        
        # Stop watching previous file if any
        if self.watched_files:
            old_file = list(self.watched_files.keys())[0]
            self.watcher.removePath(old_file)
            self.watched_files.clear()
        
        # Start watching new file
        self.watcher.addPath(file_path)
        self.watched_files[file_path] = current_hash
    
    def stop_watching(self):
        """Stop watching all files."""
        if self.watched_files:
            for file_path in self.watched_files.keys():
                self.watcher.removePath(file_path)
            self.watched_files.clear()
    
    def _on_file_changed(self, file_path: str):
        """Called when a watched file changes."""
        # Debounce rapid file changes
        self.pending_change = file_path
        self.debounce_timer.start(100)  # 100ms debounce
    
    def _handle_file_change(self):
        """Handle the debounced file change."""
        if not self.pending_change:
            return
        
        file_path = self.pending_change
        self.pending_change = None
        
        # Check if this is a file we're watching
        if file_path not in self.watched_files:
            return
        
        # Get the new file hash
        try:
            if not os.path.exists(file_path):
                return  # File was deleted
            
            with open(file_path, 'rb') as f:
                new_content = f.read()
            new_hash = compute_hash(new_content)
            
            # Check if content actually changed
            old_hash = self.watched_files[file_path]
            if new_hash == old_hash:
                return  # No actual change
            
            # Update the hash
            self.watched_files[file_path] = new_hash
            
            # Handle the change based on user preferences
            if file_path in self.always_reload_files:
                self.reload_requested.emit(file_path)
            elif file_path in self.ignore_once_files:
                self.ignore_once_files.remove(file_path)
                # Don't do anything
            else:
                # Show prompt
                self._show_reload_prompt(file_path)
                
        except Exception as e:
            print(f"Error handling file change for {file_path}: {e}")
    
    def _show_reload_prompt(self, file_path: str):
        """Show dialog asking user what to do about external changes."""
        if self.prompt_visible:
            return
        
        self.prompt_visible = True
        
        # Create dialog
        dialog = QMessageBox()
        dialog.setWindowTitle("File Changed Externally")
        dialog.setText(f"The file '{os.path.basename(file_path)}' has been modified outside the application.")
        dialog.setInformativeText("What would you like to do?")
        
        # Add checkboxes
        ignore_once_cb = QCheckBox("Ignore this change")
        always_reload_cb = QCheckBox("Always reload this file")
        
        # Add buttons
        reload_button = dialog.addButton("Reload", QMessageBox.AcceptRole)
        ignore_button = dialog.addButton("Ignore", QMessageBox.RejectRole)
        
        # Set default button
        dialog.setDefaultButton(reload_button)
        
        # Show dialog
        result = dialog.exec()
        
        # Handle result
        if result == QMessageBox.Accepted:
            # Reload
            self.reload_requested.emit(file_path)
        else:
            # Ignore
            self.ignore_requested.emit(file_path)
        
        # Handle checkboxes
        if ignore_once_cb.isChecked():
            self.ignore_once_files.add(file_path)
        if always_reload_cb.isChecked():
            self.always_reload_files.add(file_path)
        
        self.prompt_visible = False
    
    def update_file_hash(self, file_path: str, new_hash: str):
        """Update the stored hash for a watched file."""
        if file_path in self.watched_files:
            self.watched_files[file_path] = new_hash
    
    def pause_watching(self):
        """Pause file watching temporarily."""
        if self.watched_files:
            for file_path in self.watched_files.keys():
                self.watcher.removePath(file_path)
    
    def resume_watching(self):
        """Resume file watching."""
        if self.watched_files:
            for file_path in self.watched_files.keys():
                if os.path.exists(file_path):
                    self.watcher.addPath(file_path)