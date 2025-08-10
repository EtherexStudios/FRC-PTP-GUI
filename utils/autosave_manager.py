from PySide6.QtCore import QObject, QTimer, Signal
from typing import List, Optional, Callable
import os
from .path_io import serialize_to_bytes, compute_hash, write_atomic


class AutosaveManager(QObject):
    """Manages automatic saving of path changes with debouncing."""
    
    # Signals
    save_started = Signal()  # Emitted when save operation begins
    save_completed = Signal()  # Emitted when save operation completes successfully
    save_failed = Signal(str)  # Emitted when save operation fails with error message
    status_message = Signal(str)  # Emitted for status updates
    
    def __init__(self, debounce_ms: int = 300):
        super().__init__()
        self.debounce_ms = debounce_ms
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._perform_save)
        
        # State
        self.current_path_file: Optional[str] = None
        self.last_written_hash: Optional[str] = None
        self.get_elements_callback: Optional[Callable[[], List]] = None
        self.is_saving = False
        self.paused = False
    
    def set_get_elements_callback(self, callback: Callable[[], List]):
        """Set the callback function to get current elements."""
        self.get_elements_callback = callback
    
    def set_current_path_file(self, path: str):
        """Set the current path file for saving."""
        self.current_path_file = path
        # Reset hash when switching files
        self.last_written_hash = None
    
    def on_path_changed(self):
        """Called when the path model changes. Starts/resets the debounce timer."""
        if self.paused or not self.current_path_file or not self.get_elements_callback:
            return
        
        # Reset the timer
        self.timer.stop()
        self.timer.start(self.debounce_ms)
    
    def _perform_save(self):
        """Perform the actual save operation."""
        if not self.current_path_file or not self.get_elements_callback or self.is_saving:
            return
        
        try:
            self.is_saving = True
            self.save_started.emit()
            
            # Get current elements
            elements = self.get_elements_callback()
            if not elements:
                self.status_message.emit("No elements to save")
                return
            
            # Serialize to bytes
            data = serialize_to_bytes(elements)
            
            # Check if content has actually changed
            current_hash = compute_hash(data)
            if self.last_written_hash == current_hash:
                self.status_message.emit("No changes to save")
                return
            
            # Perform atomic write
            write_atomic(self.current_path_file, data)
            
            # Update hash
            self.last_written_hash = current_hash
            
            self.save_completed.emit()
            self.status_message.emit(f"Saved to {os.path.basename(self.current_path_file)}")
            
        except Exception as e:
            error_msg = f"Save failed: {str(e)}"
            print(f"Autosave error: {e}")
            self.save_failed.emit(error_msg)
            self.status_message.emit(error_msg)
        
        finally:
            self.is_saving = False
    
    def flush_now(self):
        """Immediately save without waiting for debounce timer."""
        if self.timer.isActive():
            self.timer.stop()
        self._perform_save()
    
    def pause(self):
        """Pause autosave operations."""
        self.paused = True
        if self.timer.isActive():
            self.timer.stop()
    
    def resume(self):
        """Resume autosave operations."""
        self.paused = False
    
    def set_debounce_ms(self, ms: int):
        """Update the debounce time."""
        self.debounce_ms = ms
        # If timer is currently running, restart it with new delay
        if self.timer.isActive():
            remaining = self.timer.remainingTime()
            if remaining > 0:
                self.timer.start(min(remaining, ms))
    
    def is_dirty(self) -> bool:
        """Check if there are unsaved changes."""
        if not self.current_path_file or not self.get_elements_callback:
            return False
        
        try:
            elements = self.get_elements_callback()
            if not elements:
                return False
            
            data = serialize_to_bytes(elements)
            current_hash = compute_hash(data)
            return self.last_written_hash != current_hash
        except:
            return False