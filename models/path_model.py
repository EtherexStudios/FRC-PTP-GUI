from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from abc import ABC

class PathElement(ABC):
    pass

@dataclass
class Constraints:
    initial_velocity_meters_per_sec: Optional[float] = None
    final_velocity_meters_per_sec: Optional[float] = None
    max_velocity_meters_per_sec: Optional[float] = None
    max_acceleration_meters_per_sec2: Optional[float] = None
    max_velocity_deg_per_sec: Optional[float] = None
    max_acceleration_deg_per_sec2: Optional[float] = None

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

    def get_element(self, index: int) -> PathElement:
        if 0 <= index < len(self.path_elements):
            return self.path_elements[index]
        raise IndexError("Index out of range")

    def reorder_elements(self, new_order: List[int]):
        if len(new_order) != len(self.path_elements):
            raise ValueError("New order must match elements length")
        self.path_elements = [self.path_elements[i] for i in new_order]