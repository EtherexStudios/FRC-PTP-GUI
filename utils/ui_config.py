import json
import os
from typing import Dict, Any, Optional
from pathlib import Path


class UIConfigManager:
    """Manages UI configuration loading, saving, and validation."""
    
    DEFAULT_CONFIG = {
        "elementDimensions": {
            "waypoint": {"widthMeters": 0.25, "heightMeters": 0.25},
            "rotation": {"widthMeters": 0.35, "heightMeters": 0.10}
        },
        "lastProjectDir": None,
        "lastOpenedPath": None,
        "autosave": {
            "debounceMs": 300
        },
        "floatPrecision": None
    }
    
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "app.json"
        self._config = None
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file or create default if missing."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                # Validate and merge with defaults
                self._validate_and_merge_config()
            else:
                # Create default config
                self._config = self.DEFAULT_CONFIG.copy()
                self._ensure_config_dir()
                self._save_config()
        except Exception as e:
            print(f"Error loading UI config: {e}")
            # Fall back to defaults
            self._config = self.DEFAULT_CONFIG.copy()
    
    def _validate_and_merge_config(self):
        """Validate loaded config and merge with defaults for missing keys."""
        if not isinstance(self._config, dict):
            self._config = self.DEFAULT_CONFIG.copy()
            return
        
        # Ensure all required top-level keys exist
        for key, default_value in self.DEFAULT_CONFIG.items():
            if key not in self._config:
                self._config[key] = default_value
            elif isinstance(default_value, dict) and isinstance(self._config[key], dict):
                # Recursively merge nested dictionaries
                for nested_key, nested_default in default_value.items():
                    if nested_key not in self._config[key]:
                        self._config[key][nested_key] = nested_default
    
    def _ensure_config_dir(self):
        """Ensure the configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _save_config(self):
        """Save current configuration to file."""
        try:
            self._ensure_config_dir()
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving UI config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """Set a configuration value."""
        keys = key.split('.')
        config = self._config
        
        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        
        # Save immediately
        self._save_config()
    
    def get_element_dimensions(self, element_type: str) -> Dict[str, float]:
        """Get dimensions for a specific element type."""
        return self.get(f"elementDimensions.{element_type}", {})
    
    def get_autosave_debounce_ms(self) -> int:
        """Get autosave debounce time in milliseconds."""
        return self.get("autosave.debounceMs", 300)
    
    def get_last_project_dir(self) -> Optional[str]:
        """Get the last selected project directory."""
        return self.get("lastProjectDir")
    
    def set_last_project_dir(self, directory: str):
        """Set the last selected project directory."""
        self.set("lastProjectDir", directory)
    
    def get_last_opened_path(self) -> Optional[str]:
        """Get the last opened path file."""
        return self.get("lastOpenedPath")
    
    def set_last_opened_path(self, path: str):
        """Set the last opened path file."""
        self.set("lastOpenedPath", path)
    
    def reload(self):
        """Reload configuration from disk."""
        self._load_config()