from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from abc import ABC

class PathElement(ABC):
    pass

@dataclass
class Constraints:
    final_velocity_meters_per_sec: Optional[float] = None
    max_velocity_meters_per_sec: Optional[float] = None
    max_acceleration_meters_per_sec2: Optional[float] = None
    max_velocity_deg_per_sec: Optional[float] = None
    max_acceleration_deg_per_sec2: Optional[float] = None

@dataclass
class RangedConstraint:
    """A constraint that applies over a contiguous range of path-domain elements.

    For translation-domain constraints (meters), the domain elements are anchors
    (TranslationTarget and Waypoint) ordered along the path. The range [start_ordinal, end_ordinal]
    refers to those anchors (1-based indexing for UI), and the effective constrained path spans
    from the segment leading into start_ordinal through the segment ending at end_ordinal.

    For rotation-domain constraints (degrees), the domain elements are rotation-bearing events
    (RotationTarget and Waypoint) ordered along the path. The range refers to these events. The
    effective constrained path spans from the anchor just before the first event through the last
    event position (at the waypoint itself or inside the segment for a RotationTarget).
    """
    key: str  # one of: max_velocity_meters_per_sec, max_acceleration_meters_per_sec2, max_velocity_deg_per_sec, max_acceleration_deg_per_sec2
    value: float
    start_ordinal: int  # 1-based ordinal within the applicable domain list
    end_ordinal: int    # inclusive, 1-based

@dataclass
class TranslationTarget(PathElement):
    x_meters : float = 0
    y_meters : float = 0
    intermediate_handoff_radius_meters : Optional[float] = None

@dataclass
class RotationTarget(PathElement):
    rotation_radians: float = 0.0
    # Position of the rotation target along the segment between the
    # previous and next anchor elements (TranslationTarget or Waypoint).
    # 0.0 corresponds to the previous anchor, 1.0 to the next anchor.
    t_ratio: float = 0.0
    profiled_rotation: bool = True

@dataclass
class Waypoint(PathElement):
    translation_target : TranslationTarget = field(default_factory=TranslationTarget)
    rotation_target : RotationTarget = field(default_factory=RotationTarget)

@dataclass
class Path:
    path_elements : List[PathElement] = field(default_factory=list)
    constraints : Constraints = field(default_factory=Constraints)
    ranged_constraints : List[RangedConstraint] = field(default_factory=list)

    def get_element(self, index: int) -> PathElement:
        if 0 <= index < len(self.path_elements):
            return self.path_elements[index]
        raise IndexError("Index out of range")

    def reorder_elements(self, new_order: List[int]):
        if len(new_order) != len(self.path_elements):
            raise ValueError("New order must match elements length")
        self.path_elements = [self.path_elements[i] for i in new_order]