"""Element manager component for handling path element operations."""

import math
from typing import List, Tuple, Optional, Any
from PySide6.QtCore import QObject, Signal
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint
from ui.canvas import FIELD_LENGTH_METERS, FIELD_WIDTH_METERS, ELEMENT_RECT_WIDTH_M, ELEMENT_RECT_HEIGHT_M
from ..utils import ElementType, get_element_position, get_neighbor_positions, get_element_bounding_radius, clamp_from_metadata, get_safe_position_for_rotation


class ElementManager(QObject):
    """Manages path element operations including add, remove, reorder, and type changes."""
    
    # Signals
    elementAdded = Signal(int, object)  # index, element
    elementRemoved = Signal(int, object)  # index, element
    elementTypeChanged = Signal(int, object, object)  # index, old_element, new_element
    elementsReordered = Signal(list)  # new_order indices
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Optional[Path] = None
        self.project_manager = None  # Set externally for config access
        
    def set_path(self, path: Path):
        """Set the path to manage."""
        self.path = path
        
    def create_translation_target(self, x_meters: float, y_meters: float, intermediate_handoff_radius_meters: Optional[float] = None) -> TranslationTarget:
        """Create a TranslationTarget with proper default handoff radius from config."""
        if intermediate_handoff_radius_meters is None:
            try:
                default_val = self.project_manager.get_default_optional_value('intermediate_handoff_radius_meters') if self.project_manager else None
                intermediate_handoff_radius_meters = default_val
            except Exception:
                intermediate_handoff_radius_meters = None
        
        return TranslationTarget(
            x_meters=x_meters,
            y_meters=y_meters,
            intermediate_handoff_radius_meters=intermediate_handoff_radius_meters
        )

    def create_waypoint(
        self,
        x_meters: float,
        y_meters: float,
        *,
        intermediate_handoff_radius_meters: Optional[float] = None,
        rotation_radians: float = 0.0,
        t_ratio: float = 0.0,
        profiled_rotation: bool = True,
    ) -> Waypoint:
        """Create a Waypoint ensuring the translation target's handoff radius defaults from config."""
        tt = self.create_translation_target(
            x_meters=x_meters,
            y_meters=y_meters,
            intermediate_handoff_radius_meters=intermediate_handoff_radius_meters,
        )
        rt = RotationTarget(
            rotation_radians=rotation_radians,
            t_ratio=t_ratio,
            profiled_rotation=profiled_rotation,
        )
        return Waypoint(translation_target=tt, rotation_target=rt)
        
    def get_robot_dimensions(self) -> Tuple[float, float]:
        """Return (length_m, width_m) for rectangle-based elements."""
        length_m = float(ELEMENT_RECT_WIDTH_M)
        width_m = float(ELEMENT_RECT_HEIGHT_M)
        try:
            if self.project_manager is not None and getattr(self.project_manager, 'config', None):
                cfg = self.project_manager.config
                length_m = float(cfg.get('robot_length_meters', length_m))
                width_m = float(cfg.get('robot_width_meters', width_m))
        except Exception:
            pass
        return length_m, width_m
        
    def propose_non_overlapping_position(self, base_x: float, base_y: float, new_type: ElementType) -> Tuple[float, float]:
        """Find a nearby position to base_x/base_y that avoids significant overlap with existing elements."""
        if self.path is None or not getattr(self.path, 'path_elements', None):
            # Clamp to field bounds and return
            return (
                clamp_from_metadata('x_meters', float(base_x)),
                clamp_from_metadata('y_meters', float(base_y)),
            )

        # Build list of existing positions and their radii
        existing: List[Tuple[float, float, float]] = []
        try:
            for i, el in enumerate(self.path.path_elements):
                px, py = get_element_position(el, i, self.path.path_elements)
                length_m, width_m = self.get_robot_dimensions()
                r = get_element_bounding_radius(el, length_m, width_m)
                existing.append((float(px), float(py), float(r)))
        except Exception:
            pass

        # Get radius for new element type
        length_m, width_m = self.get_robot_dimensions()
        if new_type == ElementType.TRANSLATION:
            from ui.canvas import ELEMENT_CIRCLE_RADIUS_M
            new_r = float(ELEMENT_CIRCLE_RADIUS_M)
        else:  # Waypoint or Rotation
            new_r = float(math.hypot(length_m / 2.0, width_m / 2.0))
            
        margin = 0.10  # small visual gap

        def _is_clear(x: float, y: float) -> bool:
            for (ox, oy, orad) in existing:
                dx = x - ox
                dy = y - oy
                if dx * dx + dy * dy < (new_r + orad + margin) ** 2:
                    return False
            return True

        # First try base
        bx = clamp_from_metadata('x_meters', float(base_x))
        by = clamp_from_metadata('y_meters', float(base_y))
        if _is_clear(bx, by):
            return bx, by

        # Try offsets in expanding rings around base
        from ui.canvas import ELEMENT_CIRCLE_RADIUS_M
        step = max(new_r * 2.0, max(length_m, width_m) * 0.6, float(ELEMENT_CIRCLE_RADIUS_M) * 2.0) + margin
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
            (2, 0), (-2, 0), (0, 2), (0, -2),
        ]
        for ring in range(1, 4):
            dist = step * ring
            for dx_unit, dy_unit in directions:
                x = clamp_from_metadata('x_meters', bx + dx_unit * dist)
                y = clamp_from_metadata('y_meters', by + dy_unit * dist)
                if _is_clear(x, y):
                    return x, y

        # Fallback: return base clamped
        return bx, by
        
    def add_element(self, element_type: ElementType, insert_pos: int, current_selection_idx: Optional[int] = None) -> int:
        """Add a new element at the specified position."""
        if self.path is None:
            return -1
            
        # Enforce rotation cannot be at start/end
        if element_type == ElementType.ROTATION:
            if insert_pos == 0:
                insert_pos = 1
            if insert_pos == len(self.path.path_elements):
                insert_pos = max(0, len(self.path.path_elements) - 1)
            if len(self.path.path_elements) == 0:
                # Cannot add rotation as the first element; switch to translation
                element_type = ElementType.TRANSLATION
                
        # Get default position based on current selection
        x0, y0 = self._get_default_position_for_new_element(current_selection_idx)
        
        # Propose a non-overlapping position
        x0, y0 = self.propose_non_overlapping_position(x0, y0, element_type)
        
        # Create the new element
        if element_type == ElementType.TRANSLATION:
            new_elem = self.create_translation_target(x_meters=x0, y_meters=y0)
        elif element_type == ElementType.WAYPOINT:
            new_elem = self.create_waypoint(
                x_meters=x0,
                y_meters=y0,
                intermediate_handoff_radius_meters=None,
                rotation_radians=0.0,
                t_ratio=0.0,
                profiled_rotation=True,
            )
        else:  # ROTATION
            t_choice = self._find_good_t_ratio_for_rotation(insert_pos, x0, y0)
            new_elem = RotationTarget(rotation_radians=0.0, t_ratio=float(t_choice), profiled_rotation=True)
            
        # Insert the element
        self.path.path_elements.insert(insert_pos, new_elem)
        
        # Repair any invalid placements
        self.repair_rotation_at_ends()
        
        # Find the new index by identity
        identity = id(new_elem)
        new_index = next((i for i, e in enumerate(self.path.path_elements) if id(e) == identity), insert_pos)
        
        self.elementAdded.emit(new_index, new_elem)
        return new_index
        
    def remove_element(self, idx: int) -> Optional[Any]:
        """Remove an element at the specified index."""
        if self.path is None or idx < 0 or idx >= len(self.path.path_elements):
            return None
            
        removed = self.path.path_elements.pop(idx)
        
        # After removal, ensure we do not end with rotation at start or end
        self.repair_rotation_at_ends()
        
        self.elementRemoved.emit(idx, removed)
        return removed
        
    def change_element_type(self, idx: int, new_type: ElementType) -> bool:
        """Change the type of an element at the specified index."""
        if self.path is None or idx < 0 or idx >= len(self.path.path_elements):
            return False
            
        prev = self.path.path_elements[idx]
        
        # Determine current type
        prev_type = (
            ElementType.TRANSLATION if isinstance(prev, TranslationTarget)
            else ElementType.ROTATION if isinstance(prev, RotationTarget)
            else ElementType.WAYPOINT if isinstance(prev, Waypoint)
            else None
        )
        
        if prev_type == new_type:
            return False
            
        # Prevent creating rotation at ends unless the current element already is rotation
        if new_type == ElementType.ROTATION and prev_type != ElementType.ROTATION:
            if idx == 0 or idx == len(self.path.path_elements) - 1:
                return False
                
        # Create the new element based on type conversion logic
        new_elem = self._convert_element_type(prev, prev_type, new_type, idx)
        
        # Replace the element
        self.path.path_elements[idx] = new_elem
        
        # Ensure rotations are ordered correctly
        if new_type == ElementType.ROTATION:
            self.check_and_swap_rotation_targets()
            
        self.elementTypeChanged.emit(idx, prev, new_elem)
        return True
        
    def reorder_elements(self, new_order: List[int]):
        """Reorder elements based on new order indices."""
        if self.path is None:
            return
            
        # Apply order to model
        old_elements = self.path.path_elements[:]
        self.path.path_elements = [old_elements[i] for i in new_order if i < len(old_elements)]
        
        # Repair any invalid placements
        self.repair_rotation_at_ends()
        
        self.elementsReordered.emit(new_order)
        
    def repair_rotation_at_ends(self):
        """Ensure rotation elements are not at the start or end of the path."""
        if self.path is None or not self.path.path_elements:
            return
            
        elems = self.path.path_elements
        
        # Repair start
        if isinstance(elems[0], RotationTarget):
            non_rots = sum(1 for e in elems if not isinstance(e, RotationTarget))
            if non_rots > 1:
                # Swap with the first non_rot
                swap_idx = next((i for i, e in enumerate(elems) if not isinstance(e, RotationTarget)), None)
                if swap_idx is not None:
                    elems[0], elems[swap_idx] = elems[swap_idx], elems[0]
            else:
                # Convert start to Waypoint
                old = elems[0]
                x_pos, y_pos = get_safe_position_for_rotation(old, elems, 0)
                elems[0] = self.create_waypoint(
                    x_meters=float(x_pos),
                    y_meters=float(y_pos),
                    rotation_radians=float(getattr(old, 'rotation_radians', 0.0)),
                    t_ratio=float(getattr(old, 't_ratio', 0.0)),
                    profiled_rotation=bool(getattr(old, 'profiled_rotation', True)),
                )
                
        # Repair end
        if elems and isinstance(elems[-1], RotationTarget):
            non_rots = sum(1 for e in elems if not isinstance(e, RotationTarget))
            if non_rots > 1:
                # Swap with the last non_rot
                swap_idx = next((len(elems) - 1 - i for i, e in enumerate(reversed(elems)) if not isinstance(e, RotationTarget)), None)
                if swap_idx is not None:
                    elems[-1], elems[swap_idx] = elems[swap_idx], elems[-1]
            else:
                # Convert end to Waypoint
                old = elems[-1]
                x_pos, y_pos = get_safe_position_for_rotation(old, elems, len(elems) - 1)
                elems[-1] = self.create_waypoint(
                    x_meters=float(x_pos),
                    y_meters=float(y_pos),
                    rotation_radians=float(getattr(old, 'rotation_radians', 0.0)),
                    t_ratio=float(getattr(old, 't_ratio', 0.0)),
                    profiled_rotation=bool(getattr(old, 'profiled_rotation', True)),
                )
                
    def check_and_swap_rotation_targets(self):
        """Ensure rotation targets between anchors are ordered by their t_ratio."""
        if self.path is None or len(self.path.path_elements) < 3:
            return

        elems = self.path.path_elements

        # Collect indices of anchor elements
        anchor_indices = [i for i, e in enumerate(elems) if isinstance(e, (TranslationTarget, Waypoint))]
        if len(anchor_indices) < 2:
            return

        changed = False

        # Iterate over each consecutive anchor pair
        for seg_idx in range(len(anchor_indices) - 1):
            start_idx = anchor_indices[seg_idx]
            end_idx = anchor_indices[seg_idx + 1]

            # Gather rotation elements between anchors
            between_indices = [j for j in range(start_idx + 1, end_idx) if isinstance(elems[j], RotationTarget)]
            if len(between_indices) < 2:
                continue

            # Desired order based on t_ratio
            try:
                desired_order = sorted(between_indices, key=lambda j: float(getattr(elems[j], 't_ratio', 0.0)))
            except Exception:
                desired_order = between_indices[:]

            if between_indices == desired_order:
                continue

            changed = True

            # Extract the rotation elements in desired order
            desired_elements = [elems[idx] for idx in desired_order]

            # Remove all rotation elements between anchors
            for j in reversed(between_indices):
                elems.pop(j)

            # Re-insert in correct order
            insert_at = start_idx + 1
            for el in desired_elements:
                elems.insert(insert_at, el)
                insert_at += 1

            break

        return changed
        
    def _get_default_position_for_new_element(self, current_selection_idx: Optional[int]) -> Tuple[float, float]:
        """Get default position for a new element based on current selection."""
        if current_selection_idx is None or current_selection_idx < 0 or current_selection_idx >= len(self.path.path_elements):
            # Default to center field
            return float(FIELD_LENGTH_METERS / 2.0), float(FIELD_WIDTH_METERS / 2.0)
            
        e = self.path.path_elements[current_selection_idx]
        if isinstance(e, TranslationTarget):
            return float(e.x_meters), float(e.y_meters)
        if isinstance(e, Waypoint):
            return float(e.translation_target.x_meters), float(e.translation_target.y_meters)
        if isinstance(e, RotationTarget):
            # For rotations, compute position between neighbors
            x, y = get_element_position(e, current_selection_idx, self.path.path_elements)
            return float(x), float(y)
            
        return float(FIELD_LENGTH_METERS / 2.0), float(FIELD_WIDTH_METERS / 2.0)
        
    def _find_good_t_ratio_for_rotation(self, insert_pos: int, x0: float, y0: float) -> float:
        """Find a good t_ratio for a new rotation element to avoid overlap."""
        # Determine anchor positions relative to the insertion point
        prev_pos = None
        next_pos = None
        
        try:
            # Scan backward from insert_pos-1 for previous anchor
            for i in range(insert_pos - 1, -1, -1):
                el = self.path.path_elements[i]
                if isinstance(el, TranslationTarget):
                    prev_pos = (float(el.x_meters), float(el.y_meters))
                    break
                if isinstance(el, Waypoint):
                    prev_pos = (float(el.translation_target.x_meters), float(el.translation_target.y_meters))
                    break
            # Scan forward from insert_pos for next anchor
            for i in range(insert_pos, len(self.path.path_elements)):
                el = self.path.path_elements[i]
                if isinstance(el, TranslationTarget):
                    next_pos = (float(el.x_meters), float(el.y_meters))
                    break
                if isinstance(el, Waypoint):
                    next_pos = (float(el.translation_target.x_meters), float(el.translation_target.y_meters))
                    break
        except Exception:
            pass
            
        if prev_pos is None or next_pos is None:
            return 0.5
            
        # Project current position onto the line segment
        ax, ay = prev_pos
        bx, by = next_pos
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 0.0:
            return 0.5
            
        t_base = ((x0 - ax) * dx + (y0 - ay) * dy) / denom
        t_base = max(0.0, min(1.0, t_base))
        
        # TODO: Add logic to find a clear position along the segment
        # For now, just return the projected value
        return float(t_base)
        
    def _convert_element_type(self, prev: Any, prev_type: ElementType, new_type: ElementType, idx: int) -> Any:
        """Convert an element from one type to another."""
        # Gather all attributes from TranslationTarget and RotationTarget
        translation_attrs = ['x_meters', 'y_meters', 'intermediate_handoff_radius_meters']
        rotation_attrs = ['rotation_radians', 't_ratio']

        translation_values = {attr: getattr(prev, attr, None) for attr in translation_attrs}
        rotation_values = {attr: getattr(prev, attr, None) for attr in rotation_attrs}

        if prev_type == ElementType.WAYPOINT:
            if new_type == ElementType.TRANSLATION:
                return prev.translation_target
            else:  # ROTATION
                return prev.rotation_target
                
        elif new_type == ElementType.ROTATION:
            return RotationTarget(
                rotation_radians=rotation_values['rotation_radians'] if rotation_values['rotation_radians'] else 0.0,
                t_ratio=rotation_values['t_ratio'] if rotation_values['t_ratio'] is not None else 0.5,
                profiled_rotation=True,
            )
            
        elif new_type == ElementType.TRANSLATION:
            # If converting from a RotationTarget, place at the rotation's implied position
            if prev_type == ElementType.ROTATION:
                x_new, y_new = get_element_position(prev, idx, self.path.path_elements)
            else:
                x_new = float(translation_values['x_meters'] or 0.0)
                y_new = float(translation_values['y_meters'] or 0.0)
                
            return self.create_translation_target(
                x_new,
                y_new,
                translation_values['intermediate_handoff_radius_meters']
            )
            
        elif new_type == ElementType.WAYPOINT:
            if prev_type == ElementType.TRANSLATION:
                # Recreate translation target to ensure handoff radius default is applied
                tt = self.create_translation_target(
                    float(getattr(prev, 'x_meters', 0.0)),
                    float(getattr(prev, 'y_meters', 0.0)),
                    getattr(prev, 'intermediate_handoff_radius_meters', None),
                )
                return Waypoint(translation_target=tt)
            else:  # ROTATION
                # Create waypoint at the rotation's implied position
                x_new, y_new = get_element_position(prev, idx, self.path.path_elements)
                tt = self.create_translation_target(x_meters=x_new, y_meters=y_new)
                return Waypoint(rotation_target=prev, translation_target=tt)
