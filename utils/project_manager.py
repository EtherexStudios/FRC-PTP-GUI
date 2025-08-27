from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QSettings

from models.path_model import Path, PathElement, RotationTarget, TranslationTarget, Waypoint, RangedConstraint


DEFAULT_CONFIG: Dict[str, float] = {
    "robot_length_meters": 0.5,
    "robot_width_meters": 0.5,
    # Defaults for constraints and other tunables
    "default_max_velocity_meters_per_sec": 4.5,
    "default_max_acceleration_meters_per_sec2": 7.0,
    "default_intermediate_handoff_radius_meters": 0.2,
    "default_max_velocity_deg_per_sec": 720.0,
    "default_max_acceleration_deg_per_sec2": 1500.0,
    "default_end_translation_tolerance_meters": 0.03,
    "default_end_rotation_tolerance_deg": 2.0
}

EXAMPLE_CONFIG: Dict[str, float] = {
    "robot_length_meters": 0.5,
    "robot_width_meters": 0.5,
    "default_max_velocity_meters_per_sec": 4.5,
    "default_max_acceleration_meters_per_sec2": 7.0,
    "default_intermediate_handoff_radius_meters": 0.2,
    "default_max_velocity_deg_per_sec": 720.0,
    "default_max_acceleration_deg_per_sec2": 1500.0,
    "default_end_translation_tolerance_meters": 0.03,
    "default_end_rotation_tolerance_deg": 2.0
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
        # Prefer "default_"-prefixed key, fallback to raw key for legacy or special cases
        value = self.config.get(f"default_{key}")
        if value is None:
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
    def _serialize_path(self, path: Path) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for elem in path.path_elements:
            if isinstance(elem, TranslationTarget):
                d: Dict[str, Any] = {
                    "type": "translation",
                    "x_meters": float(elem.x_meters),
                    "y_meters": float(elem.y_meters),
                }
                # Per-element optional handoff radius
                if elem.intermediate_handoff_radius_meters is not None:
                    d["intermediate_handoff_radius_meters"] = float(elem.intermediate_handoff_radius_meters)
                items.append(d)
            elif isinstance(elem, RotationTarget):
                d = {
                    "type": "rotation",
                    "rotation_radians": float(elem.rotation_radians),
                    # Represent position along the segment as a ratio in [0,1]
                    "t_ratio": float(getattr(elem, "t_ratio", 0.0)),
                    "profiled_rotation": bool(getattr(elem, "profiled_rotation", True)),
                }
                items.append(d)
            elif isinstance(elem, Waypoint):
                td = {
                    "x_meters": float(elem.translation_target.x_meters),
                    "y_meters": float(elem.translation_target.y_meters),
                }
                if elem.translation_target.intermediate_handoff_radius_meters is not None:
                    td["intermediate_handoff_radius_meters"] = float(elem.translation_target.intermediate_handoff_radius_meters)

                rd = {
                    "rotation_radians": float(elem.rotation_target.rotation_radians),
                    # Note: t_ratio is not included for waypoint rotation targets as they are positioned at the waypoint location
                    "profiled_rotation": bool(getattr(elem.rotation_target, "profiled_rotation", True)),
                }

                items.append({
                    "type": "waypoint",
                    "translation_target": td,
                    "rotation_target": rd,
                })
            else:
                # Unknown type – skip
                continue
        # Build constraints section only with non-None values
        # If a key has ranged constraints, omit it from the flat constraints block
        constraints_obj: Dict[str, Any] = {}

        # Determine which constraint keys are ranged so we can exclude them from flat constraints
        ranged_keys: set[str] = set()
        try:
            for rc in (getattr(path, 'ranged_constraints', []) or []):
                if isinstance(rc, RangedConstraint) and rc.key in (
                    "max_velocity_meters_per_sec",
                    "max_acceleration_meters_per_sec2",
                    "max_velocity_deg_per_sec",
                    "max_acceleration_deg_per_sec2",
                ):
                    ranged_keys.add(rc.key)
        except Exception:
            ranged_keys = set()

        if hasattr(path, 'constraints') and path.constraints is not None:
            c = path.constraints
            # translation constraints
            for name in [
                "max_velocity_meters_per_sec",
                "max_acceleration_meters_per_sec2",
                "end_translation_tolerance_meters",
            ]:
                if name in ranged_keys:
                    continue
                val = getattr(c, name, None)
                if val is not None:
                    constraints_obj[name] = float(val)
            # rotation constraints (deg-domain)
            for name in [
                "max_velocity_deg_per_sec",
                "max_acceleration_deg_per_sec2",
                "end_rotation_tolerance_deg",
            ]:
                if name in ranged_keys:
                    continue
                val = getattr(c, name, None)
                if val is not None:
                    constraints_obj[name] = float(val)
        # Ranged constraints block (grouped by type/key)
        ranged_grouped: Dict[str, List[Dict[str, Any]]] = {}
        try:
            for rc in (getattr(path, 'ranged_constraints', []) or []):
                if not isinstance(rc, RangedConstraint):
                    continue
                if rc.key not in (
                    "max_velocity_meters_per_sec",
                    "max_acceleration_meters_per_sec2",
                    "max_velocity_deg_per_sec",
                    "max_acceleration_deg_per_sec2",
                ):
                    continue
                try:
                    start_zero_based = int(rc.start_ordinal) - 1
                    end_zero_based = int(rc.end_ordinal) - 1
                    if start_zero_based < 0:
                        start_zero_based = 0
                    if end_zero_based < 0:
                        end_zero_based = 0
                except Exception:
                    start_zero_based = 0
                    end_zero_based = 0
                entry = {
                    "value": float(rc.value),
                    "start_ordinal": start_zero_based,
                    "end_ordinal": end_zero_based,
                }
                ranged_grouped.setdefault(str(rc.key), []).append(entry)
        except Exception:
            ranged_grouped = {}
        # Merge ranged constraints under the single "constraints" object
        # Each ranged-capable key will store a list of range entries under its key
        if ranged_grouped:
            for k, arr in ranged_grouped.items():
                constraints_obj[k] = arr

        # Compose top-level JSON object with unified constraints
        result: Dict[str, Any] = {}
        if constraints_obj:
            result["constraints"] = constraints_obj
        result["path_elements"] = items
        return result

    def _deserialize_path(self, data: Any) -> Path:
        path = Path()
        # Support legacy list-only format
        if isinstance(data, list):
            items = data
        else:
            if not isinstance(data, dict):
                return path
            # Load constraints block if present
            constraints_block = data.get("constraints", {}) or {}
            if isinstance(constraints_block, dict) and hasattr(path, 'constraints') and path.constraints is not None:
                for name in [
                    "default_max_velocity_meters_per_sec",
                    "default_max_acceleration_meters_per_sec2",
                    "default_end_translation_tolerance_meters",
                    "default_max_velocity_deg_per_sec",
                    "default_max_acceleration_deg_per_sec2",
                    "default_end_rotation_tolerance_deg",
                ]:
                    if name in constraints_block:
                        setattr(path.constraints, name, self._opt_float(constraints_block.get(name)))
            # Defer ranged constraints parsing until after path elements are loaded
            # Unify: allow ranged constraints to be provided under constraints[key] as a list
            ranged_block_list: List[Dict[str, Any]] = []
            # From unified constraints block
            try:
                if isinstance(constraints_block, dict):
                    for k, v in constraints_block.items():
                        if isinstance(v, list):
                            for entry in v:
                                if isinstance(entry, dict):
                                    e2 = dict(entry)
                                    e2["key"] = k
                                    ranged_block_list.append(e2)
            except Exception:
                pass
            ranged_block = ranged_block_list
            items = data.get("path_elements", []) if isinstance(data.get("path_elements", []), list) else []
        # Load path elements
        # First pass: create elements (support both new and legacy formats)
        for item in items:
            try:
                if not isinstance(item, dict):
                    continue
                typ = item.get("type")
                if typ == "translation":
                    handoff_radius = self._opt_float(item.get("intermediate_handoff_radius_meters"))
                    if handoff_radius is None:
                        # Use default from config if not specified in the saved path
                        handoff_radius = self.get_default_optional_value("intermediate_handoff_radius_meters")
                    el = TranslationTarget(
                        x_meters=float(item.get("x_meters", 0.0)),
                        y_meters=float(item.get("y_meters", 0.0)),
                        intermediate_handoff_radius_meters=handoff_radius,
                    )
                    path.path_elements.append(el)
                elif typ == "rotation":
                    # New format prefers t_ratio; fall back to legacy x/y if present
                    t_ratio_val = item.get("t_ratio")
                    profiled_rotation_val = bool(item.get("profiled_rotation", True))
                    if t_ratio_val is not None:
                        el = RotationTarget(
                            rotation_radians=float(item.get("rotation_radians", 0.0)),
                            t_ratio=float(t_ratio_val),
                            profiled_rotation=profiled_rotation_val,
                        )
                    else:
                        el = RotationTarget(
                            rotation_radians=float(item.get("rotation_radians", 0.0)),
                            t_ratio=0.0,
                            profiled_rotation=profiled_rotation_val,
                        )
                        # Stash legacy position for a second-pass conversion to t_ratio
                        try:
                            setattr(el, "_legacy_pos", (
                                float(item.get("x_meters", 0.0)),
                                float(item.get("y_meters", 0.0)),
                            ))
                        except Exception:
                            pass
                    path.path_elements.append(el)
                elif typ == "waypoint":
                    tt = item.get("translation_target", {}) or {}
                    rt = item.get("rotation_target", {}) or {}
                    # Waypoint rotation target: t_ratio is always 0.0 (rotation at waypoint position)
                    profiled_rotation_val = bool(rt.get("profiled_rotation", True))
                    if "t_ratio" in rt:
                        # Legacy support: if t_ratio is present, use it but prefer 0.0 for waypoints
                        rot = RotationTarget(
                            rotation_radians=float(rt.get("rotation_radians", 0.0)),
                            t_ratio=float(rt.get("t_ratio", 0.0)),
                            profiled_rotation=profiled_rotation_val,
                        )
                    else:
                        # Standard waypoint: rotation at waypoint position (t_ratio = 0.0)
                        rot = RotationTarget(
                            rotation_radians=float(rt.get("rotation_radians", 0.0)),
                            t_ratio=0.0,
                            profiled_rotation=profiled_rotation_val,
                        )
                        # Legacy position support for very old formats
                        try:
                            if "x_meters" in rt or "y_meters" in rt:
                                setattr(rot, "_legacy_pos", (
                                    float(rt.get("x_meters", 0.0)),
                                    float(rt.get("y_meters", 0.0)),
                                ))
                        except Exception:
                            pass
                    handoff_radius = self._opt_float(tt.get("intermediate_handoff_radius_meters"))
                    if handoff_radius is None:
                        # Use default from config if not specified in the saved path
                        handoff_radius = self.get_default_optional_value("intermediate_handoff_radius_meters")
                    el = Waypoint(
                        translation_target=TranslationTarget(
                            x_meters=float(tt.get("x_meters", 0.0)),
                            y_meters=float(tt.get("y_meters", 0.0)),
                            intermediate_handoff_radius_meters=handoff_radius,
                        ),
                        rotation_target=rot,
                    )
                    path.path_elements.append(el)
                else:
                    continue
            except Exception:
                # Skip malformed entries
                continue
        # Second pass: convert any legacy rotation x/y to t_ratio using neighbors
        try:
            for idx, element in enumerate(path.path_elements):
                target = None
                if isinstance(element, RotationTarget):
                    target = element
                elif isinstance(element, Waypoint):
                    target = element.rotation_target
                if target is None:
                    continue
                if hasattr(target, "_legacy_pos") and not hasattr(target, "_legacy_converted"):
                    legacy = getattr(target, "_legacy_pos", None)
                    if legacy is None:
                        continue
                    rx, ry = legacy
                    # find prev and next anchors (TranslationTarget or Waypoint)
                    # prev
                    prev_pos = None
                    for i in range(idx - 1, -1, -1):
                        e = path.path_elements[i]
                        if isinstance(e, TranslationTarget):
                            prev_pos = (float(e.x_meters), float(e.y_meters))
                            break
                        if isinstance(e, Waypoint):
                            prev_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                            break
                    # next
                    next_pos = None
                    for j in range(idx + 1, len(path.path_elements)):
                        e = path.path_elements[j]
                        if isinstance(e, TranslationTarget):
                            next_pos = (float(e.x_meters), float(e.y_meters))
                            break
                        if isinstance(e, Waypoint):
                            next_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                            break
                    if prev_pos is None or next_pos is None:
                        setattr(target, "t_ratio", 0.0)
                    else:
                        ax, ay = prev_pos
                        bx, by = next_pos
                        dx = bx - ax
                        dy = by - ay
                        denom = dx * dx + dy * dy
                        if denom <= 0.0:
                            t = 0.0
                        else:
                            t = ((rx - ax) * dx + (ry - ay) * dy) / denom
                            if t < 0.0:
                                t = 0.0
                            elif t > 1.0:
                                t = 1.0
                        setattr(target, "t_ratio", float(t))
                    # mark converted
                    try:
                        delattr(target, "_legacy_pos")
                    except Exception:
                        pass
                    setattr(target, "_legacy_converted", True)
        except Exception:
            pass
        # Now that path elements are available, parse ranged constraints with domain-aware conversion
        try:
            # Normalize ranged block into a list of {key,value,start_ordinal,end_ordinal}
            normalized: List[Dict[str, Any]] = []
            if isinstance(ranged_block, list):
                normalized = [entry for entry in ranged_block if isinstance(entry, dict)]
            elif isinstance(ranged_block, dict):
                for k, arr in ranged_block.items():
                    if not isinstance(arr, list):
                        continue
                    for entry in arr:
                        if not isinstance(entry, dict):
                            continue
                        e2 = dict(entry)
                        e2["key"] = k
                        normalized.append(e2)

            # Compute domain sizes
            anchor_count = 0  # Translation anchors: TranslationTarget or Waypoint
            rotation_event_count = 0  # Rotation events: RotationTarget or Waypoint
            for e in path.path_elements:
                if isinstance(e, TranslationTarget) or isinstance(e, Waypoint):
                    anchor_count += 1
                if isinstance(e, RotationTarget) or isinstance(e, Waypoint):
                    rotation_event_count += 1

            for entry in normalized:
                key = str(entry.get("key", ""))
                if key not in (
                    "max_velocity_meters_per_sec",
                    "max_acceleration_meters_per_sec2",
                    "max_velocity_deg_per_sec",
                    "max_acceleration_deg_per_sec2",
                ):
                    continue
                value = self._opt_float(entry.get("value"))
                start_ord = entry.get("start_ordinal")
                end_ord = entry.get("end_ordinal")
                try:
                    if value is None:
                        continue
                    start_int = int(start_ord) if start_ord is not None else 0
                    end_int = int(end_ord) if end_ord is not None else 0

                    # Choose applicable domain size
                    if key in ("max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2"):
                        domain_size = anchor_count
                    else:
                        domain_size = rotation_event_count

                    # Heuristics to map stored indices to internal 1-based ordinals
                    if domain_size > 0 and 0 <= start_int <= domain_size - 1 and 0 <= end_int <= domain_size - 1:
                        start_int += 1
                        end_int += 1
                    elif domain_size > 0 and 1 <= start_int <= domain_size and 1 <= end_int <= domain_size:
                        pass
                    elif start_int == 0 or end_int == 0:
                        start_int += 1
                        end_int += 1
                    rc = RangedConstraint(
                        key=key,
                        value=float(value),
                        start_ordinal=start_int,
                        end_ordinal=end_int,
                    )
                    path.ranged_constraints.append(rc)
                except Exception:
                    continue
        except Exception:
            pass
        return path

    @staticmethod
    def _opt_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
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
                RotationTarget(rotation_radians=0.0, t_ratio=0.5, profiled_rotation=True),
                Waypoint(
                    translation_target=TranslationTarget(x_meters=6.0, y_meters=4.0),
                    rotation_target=RotationTarget(rotation_radians=0.5, t_ratio=0.0, profiled_rotation=True),
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
                RotationTarget(rotation_radians=1.2, t_ratio=0.5, profiled_rotation=True),
                TranslationTarget(x_meters=12.5, y_meters=3.0),
            ])
            with open(os.path.join(paths_dir, "example_b.json"), "w", encoding="utf-8") as f:
                json.dump(self._serialize_path(path2), f, indent=2)
        except Exception:
            pass


