"""
Undo/Redo system for path and config edits in the FRC Path Planning GUI.

This system uses the Command pattern to capture changes and allow undo/redo operations.
It supports both path modifications and configuration changes.
"""

from __future__ import annotations
import copy
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING
from dataclasses import replace

if TYPE_CHECKING:
    from models.path_model import Path
    from utils.project_manager import ProjectManager

class Command(ABC):
    """Abstract base class for all undoable commands."""
    
    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        pass
    
    @abstractmethod
    def undo(self) -> None:
        """Undo the command."""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get a human-readable description of the command."""
        pass


class PathCommand(Command):
    """Command for path modifications."""
    
    def __init__(
        self,
        path_ref: 'Path',
        old_state: 'Path',
        new_state: 'Path',
        description: str,
        on_change_callback: Optional[Callable[[], None]] = None
    ):
        self.path_ref = path_ref
        self.old_state = copy.deepcopy(old_state)
        self.new_state = copy.deepcopy(new_state)
        self.description = description
        self.on_change_callback = on_change_callback
    
    def execute(self) -> None:
        """Apply the new state to the path."""
        self.path_ref.path_elements = copy.deepcopy(self.new_state.path_elements)
        self.path_ref.constraints = copy.deepcopy(self.new_state.constraints)
        if self.on_change_callback:
            self.on_change_callback()
    
    def undo(self) -> None:
        """Revert to the old state."""
        self.path_ref.path_elements = copy.deepcopy(self.old_state.path_elements)
        self.path_ref.constraints = copy.deepcopy(self.old_state.constraints)
        if self.on_change_callback:
            self.on_change_callback()
    
    def get_description(self) -> str:
        return self.description


class ConfigCommand(Command):
    """Command for configuration modifications."""
    
    def __init__(
        self,
        project_manager: 'ProjectManager',
        old_config: Dict[str, Any],
        new_config: Dict[str, Any],
        description: str,
        on_change_callback: Optional[Callable[[], None]] = None
    ):
        self.project_manager = project_manager
        self.old_config = copy.deepcopy(old_config)
        self.new_config = copy.deepcopy(new_config)
        self.description = description
        self.on_change_callback = on_change_callback
    
    def execute(self) -> None:
        """Apply the new configuration."""
        self.project_manager.config = copy.deepcopy(self.new_config)
        self.project_manager.save_config()
        if self.on_change_callback:
            self.on_change_callback()
    
    def undo(self) -> None:
        """Revert to the old configuration."""
        self.project_manager.config = copy.deepcopy(self.old_config)
        self.project_manager.save_config()
        if self.on_change_callback:
            self.on_change_callback()
    
    def get_description(self) -> str:
        return self.description


class CompoundCommand(Command):
    """Command that contains multiple sub-commands to be executed/undone together."""
    
    def __init__(self, commands: List[Command], description: str):
        self.commands = commands.copy()
        self.description = description
    
    def execute(self) -> None:
        """Execute all sub-commands in order."""
        for command in self.commands:
            command.execute()
    
    def undo(self) -> None:
        """Undo all sub-commands in reverse order."""
        for command in reversed(self.commands):
            command.undo()
    
    def get_description(self) -> str:
        return self.description


class UndoRedoManager:
    """
    Manages undo/redo operations for the application.
    
    Maintains two stacks: undo_stack and redo_stack.
    When a new command is executed, the redo_stack is cleared.
    """
    
    def __init__(self, max_history: int = 50):
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []
        self.max_history = max_history
        self._callbacks: List[Callable[[], None]] = []
    
    def add_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback to be called when undo/redo state changes."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_state_changed(self) -> None:
        """Notify all callbacks that the undo/redo state has changed."""
        for callback in self._callbacks:
            try:
                callback()
            except Exception:
                pass  # Ignore callback errors
    
    def execute_command(self, command: Command) -> None:
        """
        Execute a command and add it to the undo stack.
        This clears the redo stack.
        """
        command.execute()
        self.undo_stack.append(command)
        
        # Limit the size of the undo stack
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        
        # Clear redo stack when a new command is executed
        self.redo_stack.clear()
        
        self._notify_state_changed()
    
    def can_undo(self) -> bool:
        """Check if undo is possible."""
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Check if redo is possible."""
        return len(self.redo_stack) > 0
    
    def undo(self) -> Optional[Command]:
        """
        Undo the last command.
        Returns the command that was undone, or None if no undo was possible.
        """
        if not self.can_undo():
            return None
        
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        
        self._notify_state_changed()
        return command
    
    def redo(self) -> Optional[Command]:
        """
        Redo the last undone command.
        Returns the command that was redone, or None if no redo was possible.
        """
        if not self.can_redo():
            return None
        
        command = self.redo_stack.pop()
        command.execute()
        self.undo_stack.append(command)
        
        self._notify_state_changed()
        return command
    
    def get_undo_description(self) -> Optional[str]:
        """Get the description of the command that would be undone."""
        if not self.can_undo():
            return None
        return self.undo_stack[-1].get_description()
    
    def get_redo_description(self) -> Optional[str]:
        """Get the description of the command that would be redone."""
        if not self.can_redo():
            return None
        return self.redo_stack[-1].get_description()
    
    def clear(self) -> None:
        """Clear both undo and redo stacks."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._notify_state_changed()
    
    def get_history_size(self) -> tuple[int, int]:
        """Get the sizes of undo and redo stacks."""
        return len(self.undo_stack), len(self.redo_stack)
