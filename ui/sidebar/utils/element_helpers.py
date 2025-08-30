"""Helper functions for element position calculations and manipulation."""

import math
from typing import Optional, Tuple, Any, List
from models.path_model import TranslationTarget, RotationTarget, Waypoint
from ui.canvas import ELEMENT_CIRCLE_RADIUS_M, ELEMENT_RECT_WIDTH_M, ELEMENT_RECT_HEIGHT_M
from .constants import SPINNER_METADATA


def get_translation_position(element: Any) -> Tuple[float, float]:
    """Get the translation position (x, y) from a TranslationTarget or Waypoint element."""
    if isinstance(element, TranslationTarget):
        return float(element.x_meters), float(element.y_meters)
    elif isinstance(element, Waypoint):
        return float(element.translation_target.x_meters), float(element.translation_target.y_meters)
    else:
        return 0.0, 0.0


def clamp_from_metadata(key: str, value: float) -> float:
    """Clamp a value based on metadata range constraints."""
    meta = SPINNER_METADATA.get(key, {})
    value_min, value_max = meta.get('range', (None, None))
    if value_min is None or value_max is None:
        return value
    if value < value_min:
        return value_min
    if value > value_max:
        return value_max
    return value


def get_element_position(element: Any, idx: int, path_elements: List[Any]) -> Tuple[float, float]:
    """Return model-space center position for an element."""
    if isinstance(element, (TranslationTarget, Waypoint)):
        return get_translation_position(element)
    if isinstance(element, RotationTarget):
        prev_pos, next_pos = get_neighbor_positions(idx, path_elements)
        if prev_pos is None or next_pos is None:
            return 0.0, 0.0
        ax, ay = prev_pos
        bx, by = next_pos
        try:
            t = float(getattr(element, 't_ratio', 0.0))
        except Exception:
            t = 0.0
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        return ax + t * (bx - ax), ay + t * (by - ay)
    return 0.0, 0.0


def get_neighbor_positions(idx: int, path_elements: List[Any]) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
    """Get positions of neighboring anchor elements (TranslationTarget or Waypoint)."""
    # prev
    prev_pos = None
    for i in range(idx - 1, -1, -1):
        e = path_elements[i]
        if isinstance(e, (TranslationTarget, Waypoint)):
            prev_pos = get_translation_position(e)
            break
    # next
    next_pos = None
    for i in range(idx + 1, len(path_elements)):
        e = path_elements[i]
        if isinstance(e, (TranslationTarget, Waypoint)):
            next_pos = get_translation_position(e)
            break
    return prev_pos, next_pos


def get_element_bounding_radius(element: Any, robot_length_m: float, robot_width_m: float) -> float:
    """Get the bounding radius for an element based on its type."""
    if isinstance(element, TranslationTarget):
        return float(ELEMENT_CIRCLE_RADIUS_M)
    if isinstance(element, Waypoint) or isinstance(element, RotationTarget):
        return float(math.hypot(robot_length_m / 2.0, robot_width_m / 2.0))
    return 0.3


def project_point_between_neighbors(
    idx: int, 
    x_m: float, 
    y_m: float, 
    path_elements: List[Any]
) -> Tuple[float, float]:
    """Project a point onto the line between neighboring anchor elements."""
    prev_pos, next_pos = get_neighbor_positions(idx, path_elements)
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
    proj_x = clamp_from_metadata('x_meters', proj_x)
    proj_y = clamp_from_metadata('y_meters', proj_y)
    return proj_x, proj_y


def get_safe_position_for_rotation(rotation_target, elems, index) -> Tuple[float, float]:
    """Get a safe position for converting a RotationTarget to TranslationTarget.
    
    Args:
        rotation_target: The RotationTarget being converted
        elems: List of all path elements
        index: Index of the rotation_target in elems
        
    Returns:
        Tuple[float, float]: (x_meters, y_meters) position
    """
    # Try to find a nearby anchor element with position
    for offset in [1, -1, 2, -2]:
        nearby_idx = index + offset
        if 0 <= nearby_idx < len(elems):
            elem = elems[nearby_idx]
            if isinstance(elem, TranslationTarget):
                return elem.x_meters, elem.y_meters
            elif isinstance(elem, Waypoint):
                return elem.translation_target.x_meters, elem.translation_target.y_meters
    
    # If no nearby position found, use a reasonable default
    # Try to get field center or a reasonable starting position
    field_center_x = 8.0  # Rough center of FRC field (FIELD_LENGTH_METERS / 2)
    field_center_y = 4.0  # Rough center of FRC field (FIELD_WIDTH_METERS / 2)
    return field_center_x, field_center_y
