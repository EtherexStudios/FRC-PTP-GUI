from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QSettings

from models.path_model import Path, PathElement, RotationTarget, TranslationTarget, Waypoint


DEFAULT_CONFIG: Dict[str, float] = {
    "robot_length_meters": 0.60,
    "robot_width_meters": 0.60,
    # Optional property defaults (degrees where applicable)
    "final_velocity_meters_per_sec": 0.0,
    "max_velocity_meters_per_sec": 0.0,
    "max_acceleration_meters_per_sec2": 0.0,
    "intermediate_handoff_radius_meters": 0.0,
    "max_velocity_deg_per_sec": 0.0,
    "max_acceleration_deg_per_sec2": 0.0,
}

EXAMPLE_CONFIG: Dict[str, float] = {
    "robot_length_meters": 0.70,
    "robot_width_meters": 0.62,
    "final_velocity_meters_per_sec": 1.0,
    "max_velocity_meters_per_sec": 3.0,
    "max_acceleration_meters_per_sec2": 2.5,
    "intermediate_handoff_radius_meters": 0.4,
    "max_velocity_deg_per_sec": 180.0,
    "max_acceleration_deg_per_sec2": 360.0,
}


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class ProjectManager:
    """Handles project directory, config.json, and path JSON load/save.

    Persists last project dir and last opened path via QSettings.
    """

    SETTINGS_ORG = "FRC-PTP-GUI"
    SETTINGS_APP = "FRC-PTP-GUI"
    KEY_LAST_PROJECT_DIR = "project/last_project_dir"
    KEY_LAST_PATH_FILE = "project/last_path_file"
    KEY_RECENT_PROJECTS = "project/recent_projects"

    def __init__(self):
        self.settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
        self.project_dir: Optional[str] = None
        self.config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.current_path_file: Optional[str] = None  # filename like "example.json"

    # --------------- Project directory ---------------
    def set_project_dir(self, directory: str) -> None:
        directory = os.path.abspath(directory)
        self.project_dir = directory
        self.settings.setValue(self.KEY_LAST_PROJECT_DIR, directory)
        self.ensure_project_structure()
        # Track recents only after ensuring structure exists
        self._add_recent_project(directory)
        self.load_config()

    def get_paths_dir(self) -> Optional[str]:
        if not self.project_dir:
            return None
        return os.path.join(self.project_dir, "paths")

    def ensure_project_structure(self) -> None:
        if not self.project_dir:
            return
        _ensure_dir(self.project_dir)
        paths_dir = os.path.join(self.project_dir, "paths")
        _ensure_dir(paths_dir)
        # Create default config if missing
        cfg_path = os.path.join(self.project_dir, "config.json")
        if not os.path.exists(cfg_path):
            self.save_config(DEFAULT_CONFIG.copy())
        # Create example files if paths folder empty
        try:
            if not os.listdir(paths_dir):
                self._create_example_paths(paths_dir)
        except Exception:
            pass

    def has_valid_project(self) -> bool:
        if not self.project_dir:
            return False
        cfg = os.path.join(self.project_dir, "config.json")
        paths = os.path.join(self.project_dir, "paths")
        return os.path.isdir(self.project_dir) and os.path.isfile(cfg) and os.path.isdir(paths)

    def load_last_project(self) -> bool:
        last_dir = self.settings.value(self.KEY_LAST_PROJECT_DIR, type=str)
        if not last_dir:
            return False
        # Validate without creating any files. Only accept if already valid.
        cfg = os.path.join(last_dir, "config.json")
        paths = os.path.join(last_dir, "paths")
        if os.path.isdir(last_dir) and os.path.isfile(cfg) and os.path.isdir(paths):
            self.set_project_dir(last_dir)
            return True
        return False

    # --------------- Recent Projects ---------------
    def recent_projects(self) -> List[str]:
        raw = self.settings.value(self.KEY_RECENT_PROJECTS)
        if not raw:
            return []
        # QSettings may return list or str
        if isinstance(raw, list):
            items = [str(x) for x in raw]
        else:
            try:
                items = json.loads(str(raw))
                if not isinstance(items, list):
                    items = []
            except Exception:
                items = []
        # Filter only existing dirs
        items = [p for p in items if isinstance(p, str) and os.path.isdir(p)]
        # unique while preserving order
        seen = set()
        uniq = []
        for p in items:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return uniq[:10]

    def _add_recent_project(self, directory: str) -> None:
        if not directory:
            return
        items = self.recent_projects()
        # move to front
        items = [d for d in items if d != directory]
        items.insert(0, directory)
        items = items[:10]
        # Store as JSON string to be robust
        try:
            self.settings.setValue(self.KEY_RECENT_PROJECTS, json.dumps(items))
        except Exception:
            pass

    # --------------- Config ---------------
    def load_config(self) -> Dict[str, Any]:
        if not self.project_dir:
            return self.config
        cfg_path = os.path.join(self.project_dir, "config.json")
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # Merge onto defaults so missing keys get defaults
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(data)
                    self.config = merged
        except Exception:
            # Keep existing config on error
            pass
        return self.config

    def save_config(self, new_config: Optional[Dict[str, Any]] = None) -> None:
        if new_config is not None:
            self.config.update(new_config)
        if not self.project_dir:
            return
        cfg_path = os.path.join(self.project_dir, "config.json")
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def get_default_optional_value(self, key: str) -> Optional[float]:
        # Returns configured default if present, else None
        value = self.config.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    # --------------- Paths listing ---------------
    def list_paths(self) -> List[str]:
        paths_dir = self.get_paths_dir()
        if not paths_dir or not os.path.isdir(paths_dir):
            return []
        files = [f for f in os.listdir(paths_dir) if f.lower().endswith(".json")]
        files.sort()
        return files

    # --------------- Path IO ---------------
    def load_path(self, filename: str) -> Optional[Path]:
        """Load a path from the paths directory by filename (e.g., 'my_path.json')."""
        paths_dir = self.get_paths_dir()
        if not self.project_dir or not paths_dir:
            return None
        filepath = os.path.join(paths_dir, filename)
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            path = self._deserialize_path(data)
            self.current_path_file = filename
            # Remember in settings
            self.settings.setValue(self.KEY_LAST_PATH_FILE, filename)
            return path
        except Exception:
            return None

    def save_path(self, path: Path, filename: Optional[str] = None) -> Optional[str]:
        """Save path to filename in the paths dir. If filename is None, uses current_path_file
        or creates 'untitled.json'. Returns the filename used on success.
        """
        if filename is None:
            filename = self.current_path_file
        if filename is None:
            filename = "untitled.json"
        paths_dir = self.get_paths_dir()
        if not self.project_dir or not paths_dir:
            return None
        _ensure_dir(paths_dir)
        filepath = os.path.join(paths_dir, filename)
        try:
            serialized = self._serialize_path(path)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2)
            self.current_path_file = filename
            self.settings.setValue(self.KEY_LAST_PATH_FILE, filename)
            return filename
        except Exception:
            return None

    def delete_path(self, filename: str) -> bool:
        """Delete a path file from the paths directory. Returns True if successful."""
        paths_dir = self.get_paths_dir()
        if not self.project_dir or not paths_dir:
            return False
        filepath = os.path.join(paths_dir, filename)
        if not os.path.isfile(filepath):
            return False
        try:
            os.remove(filepath)
            # If this was the current path, clear it
            if self.current_path_file == filename:
                self.current_path_file = None
                self.settings.remove(self.KEY_LAST_PATH_FILE)
            return True
        except Exception:
            return False

    def load_last_or_first_or_create(self) -> Tuple[Path, str]:
        """Attempt to load last path (from settings). If unavailable, load first available
        path in directory. If none exist, create 'untitled.json' empty path and return it.
        Returns (Path, filename).
        """
        # Try last used
        last_file = self.settings.value(self.KEY_LAST_PATH_FILE, type=str)
        if last_file:
            p = self.load_path(last_file)
            if p is not None:
                return p, last_file
        # Try first available
        files = self.list_paths()
        if files:
            first = files[0]
            p = self.load_path(first)
            if p is not None:
                return p, first
        # Create a new empty path
        new_path = Path()
        used = self.save_path(new_path, "untitled.json")
        if used is None:
            used = "untitled.json"
        return new_path, used

    # --------------- Serialization helpers ---------------
    def _serialize_path(self, path: Path) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for elem in path.path_elements:
            if isinstance(elem, TranslationTarget):
                d: Dict[str, Any] = {
                    "type": "translation",
                    "x_meters": float(elem.x_meters),
                    "y_meters": float(elem.y_meters),
                }
                # Optionals
                if elem.final_velocity_meters_per_sec is not None:
                    d["final_velocity_meters_per_sec"] = float(elem.final_velocity_meters_per_sec)
                if elem.max_velocity_meters_per_sec is not None:
                    d["max_velocity_meters_per_sec"] = float(elem.max_velocity_meters_per_sec)
                if elem.max_acceleration_meters_per_sec2 is not None:
                    d["max_acceleration_meters_per_sec2"] = float(elem.max_acceleration_meters_per_sec2)
                if elem.intermediate_handoff_radius_meters is not None:
                    d["intermediate_handoff_radius_meters"] = float(elem.intermediate_handoff_radius_meters)
                items.append(d)
            elif isinstance(elem, RotationTarget):
                d = {
                    "type": "rotation",
                    "rotation_radians": float(elem.rotation_radians),
                    "x_meters": float(elem.x_meters),
                    "y_meters": float(elem.y_meters),
                }
                if elem.max_velocity_rad_per_sec is not None:
                    d["max_velocity_rad_per_sec"] = float(elem.max_velocity_rad_per_sec)
                if elem.max_acceleration_rad_per_sec2 is not None:
                    d["max_acceleration_rad_per_sec2"] = float(elem.max_acceleration_rad_per_sec2)
                items.append(d)
            elif isinstance(elem, Waypoint):
                td = {
                    "x_meters": float(elem.translation_target.x_meters),
                    "y_meters": float(elem.translation_target.y_meters),
                }
                if elem.translation_target.final_velocity_meters_per_sec is not None:
                    td["final_velocity_meters_per_sec"] = float(elem.translation_target.final_velocity_meters_per_sec)
                if elem.translation_target.max_velocity_meters_per_sec is not None:
                    td["max_velocity_meters_per_sec"] = float(elem.translation_target.max_velocity_meters_per_sec)
                if elem.translation_target.max_acceleration_meters_per_sec2 is not None:
                    td["max_acceleration_meters_per_sec2"] = float(elem.translation_target.max_acceleration_meters_per_sec2)
                if elem.translation_target.intermediate_handoff_radius_meters is not None:
                    td["intermediate_handoff_radius_meters"] = float(elem.translation_target.intermediate_handoff_radius_meters)

                rd = {
                    "rotation_radians": float(elem.rotation_target.rotation_radians),
                    "x_meters": float(elem.rotation_target.x_meters),
                    "y_meters": float(elem.rotation_target.y_meters),
                }
                if elem.rotation_target.max_velocity_rad_per_sec is not None:
                    rd["max_velocity_rad_per_sec"] = float(elem.rotation_target.max_velocity_rad_per_sec)
                if elem.rotation_target.max_acceleration_rad_per_sec2 is not None:
                    rd["max_acceleration_rad_per_sec2"] = float(elem.rotation_target.max_acceleration_rad_per_sec2)

                items.append({
                    "type": "waypoint",
                    "translation_target": td,
                    "rotation_target": rd,
                })
            else:
                # Unknown type – skip
                continue
        return items

    def _deserialize_path(self, data: Any) -> Path:
        path = Path()
        if not isinstance(data, list):
            return path
        for item in data:
            try:
                if not isinstance(item, dict):
                    continue
                typ = item.get("type")
                if typ == "translation":
                    el = TranslationTarget(
                        x_meters=float(item.get("x_meters", 0.0)),
                        y_meters=float(item.get("y_meters", 0.0)),
                        final_velocity_meters_per_sec=self._opt_float(item.get("final_velocity_meters_per_sec")),
                        max_velocity_meters_per_sec=self._opt_float(item.get("max_velocity_meters_per_sec")),
                        max_acceleration_meters_per_sec2=self._opt_float(item.get("max_acceleration_meters_per_sec2")),
                        intermediate_handoff_radius_meters=self._opt_float(item.get("intermediate_handoff_radius_meters")),
                    )
                    path.path_elements.append(el)
                elif typ == "rotation":
                    el = RotationTarget(
                        rotation_radians=float(item.get("rotation_radians", 0.0)),
                        x_meters=float(item.get("x_meters", 0.0)),
                        y_meters=float(item.get("y_meters", 0.0)),
                        max_velocity_rad_per_sec=self._opt_float(item.get("max_velocity_rad_per_sec")),
                        max_acceleration_rad_per_sec2=self._opt_float(item.get("max_acceleration_rad_per_sec2")),
                    )
                    path.path_elements.append(el)
                elif typ == "waypoint":
                    tt = item.get("translation_target", {}) or {}
                    rt = item.get("rotation_target", {}) or {}
                    el = Waypoint(
                        translation_target=TranslationTarget(
                            x_meters=float(tt.get("x_meters", 0.0)),
                            y_meters=float(tt.get("y_meters", 0.0)),
                            final_velocity_meters_per_sec=self._opt_float(tt.get("final_velocity_meters_per_sec")),
                            max_velocity_meters_per_sec=self._opt_float(tt.get("max_velocity_meters_per_sec")),
                            max_acceleration_meters_per_sec2=self._opt_float(tt.get("max_acceleration_meters_per_sec2")),
                            intermediate_handoff_radius_meters=self._opt_float(tt.get("intermediate_handoff_radius_meters")),
                        ),
                        rotation_target=RotationTarget(
                            rotation_radians=float(rt.get("rotation_radians", 0.0)),
                            x_meters=float(rt.get("x_meters", 0.0)),
                            y_meters=float(rt.get("y_meters", 0.0)),
                            max_velocity_rad_per_sec=self._opt_float(rt.get("max_velocity_rad_per_sec")),
                            max_acceleration_rad_per_sec2=self._opt_float(rt.get("max_acceleration_rad_per_sec2")),
                        ),
                    )
                    path.path_elements.append(el)
                else:
                    continue
            except Exception:
                # Skip malformed entries
                continue
        return path

    @staticmethod
    def _opt_float(value: Any) -> Optional[float]:
        if value is None:
            return None

    # --------------- Example content ---------------
    def _create_example_paths(self, paths_dir: str) -> None:
        """Populate example config and a couple of path files."""
        # Overwrite config with example to showcase values
        try:
            self.save_config(EXAMPLE_CONFIG.copy())
        except Exception:
            pass
        # Two example paths
        try:
            path1 = Path()
            path1.path_elements.extend([
                TranslationTarget(x_meters=2.0, y_meters=2.0),
                RotationTarget(rotation_radians=0.0, x_meters=4.0, y_meters=3.0),
                Waypoint(
                    translation_target=TranslationTarget(x_meters=6.0, y_meters=4.0),
                    rotation_target=RotationTarget(rotation_radians=0.5, x_meters=6.0, y_meters=4.0),
                ),
                TranslationTarget(x_meters=10.0, y_meters=6.0),
            ])
            with open(os.path.join(paths_dir, "example_a.json"), "w", encoding="utf-8") as f:
                json.dump(self._serialize_path(path1), f, indent=2)
        except Exception:
            pass
        try:
            path2 = Path()
            path2.path_elements.extend([
                TranslationTarget(x_meters=1.0, y_meters=7.5),
                TranslationTarget(x_meters=5.0, y_meters=6.0),
                RotationTarget(rotation_radians=1.2, x_meters=8.0, y_meters=4.0),
                TranslationTarget(x_meters=12.5, y_meters=3.0),
            ])
            with open(os.path.join(paths_dir, "example_b.json"), "w", encoding="utf-8") as f:
                json.dump(self._serialize_path(path2), f, indent=2)
        except Exception:
            pass
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


