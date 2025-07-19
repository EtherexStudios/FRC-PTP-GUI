from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from abc import ABC

@dataclass
class Translation2d:
    x : float
    y : float

@dataclass
class Rotation2d:
    radians : float

class PathElement(ABC):
    pass

@dataclass
class TranslationTarget(PathElement):
    translation : Translation2d
    final_velocity_meters_per_sec : Optional[float] = None
    max_velocity_meters_per_sec : Optional[float] = None
    max_acceleration_meters_per_sec2 : Optional[float] = None
    intermediate_handoff_radius_meters : Optional[float] = None

@dataclass
class RotationTarget(PathElement):
    rotation : Rotation2d
    translation : Translation2d
    max_velocity_rad_per_sec : Optional[float] = None
    max_acceleration_rad_per_sec2 : Optional[float] = None

@dataclass
class Waypoint(PathElement):
    rotation_target : Rotation2d
    translation_target : Translation2d

@dataclass
class Path:
    path_elements : List[PathElement] = field(default_factory=list)

    def get_element(self, index: int) -> PathElement:
        if 0 <= index < len(self.path_elements):
            return self.path_elements[index]
        raise IndexError("Index out of range")

    def reorder_elements(self, new_order: List[int]):
        if len(new_order) != len(self.path_elements):
            raise ValueError("New order must match elements length")
        self.path_elements = [self.path_elements[i] for i in new_order]