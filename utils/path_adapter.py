from typing import List, Optional
import math
from models.path_model import Path, PathElement, TranslationTarget, RotationTarget, Waypoint
from .path_io import Waypoint as SerialWaypoint, Rotation as SerialRotation


class PathModelAdapter:
    """Adapter to convert between existing path model and new serialization format."""
    
    @staticmethod
    def to_serialization_format(path: Path) -> List[SerialWaypoint | SerialRotation]:
        """Convert existing path model to serialization format."""
        elements = []
        
        for element in path.path_elements:
            if isinstance(element, TranslationTarget):
                # Convert TranslationTarget to Waypoint
                waypoint = SerialWaypoint(
                    xMeters=element.x_meters,
                    yMeters=element.y_meters,
                    rotationDegrees=None,  # TranslationTarget doesn't have rotation
                    maxVelocityMetersPerSec=element.max_velocity_meters_per_sec
                )
                elements.append(waypoint)
                
            elif isinstance(element, RotationTarget):
                # Convert RotationTarget to Rotation
                rotation = SerialRotation(
                    xMeters=element.x_meters,
                    yMeters=element.y_meters,
                    rotationDegrees=math.degrees(element.rotation_radians)
                )
                elements.append(rotation)
                
            elif isinstance(element, Waypoint):
                # Convert Waypoint to Waypoint
                waypoint = SerialWaypoint(
                    xMeters=element.translation_target.x_meters,
                    yMeters=element.translation_target.y_meters,
                    rotationDegrees=math.degrees(element.rotation_target.rotation_radians) if element.rotation_target.rotation_radians else None,
                    maxVelocityMetersPerSec=element.translation_target.max_velocity_meters_per_sec
                )
                elements.append(waypoint)
        
        return elements
    
    @staticmethod
    def from_serialization_format(elements: List[SerialWaypoint | SerialRotation]) -> Path:
        """Convert serialization format to existing path model."""
        path = Path()
        
        for element in elements:
            if isinstance(element, SerialWaypoint):
                if element.rotationDegrees is not None:
                    # Create a Waypoint with both translation and rotation
                    waypoint = Waypoint(
                        translation_target=TranslationTarget(
                            x_meters=element.xMeters,
                            y_meters=element.yMeters,
                            max_velocity_meters_per_sec=element.maxVelocityMetersPerSec
                        ),
                        rotation_target=RotationTarget(
                            x_meters=element.xMeters,
                            y_meters=element.yMeters,
                            rotation_radians=math.radians(element.rotationDegrees)
                        )
                    )
                    path.path_elements.append(waypoint)
                else:
                    # Create a TranslationTarget
                    translation = TranslationTarget(
                        x_meters=element.xMeters,
                        y_meters=element.yMeters,
                        max_velocity_meters_per_sec=element.maxVelocityMetersPerSec
                    )
                    path.path_elements.append(translation)
                    
            elif isinstance(element, SerialRotation):
                # Create a RotationTarget
                rotation = RotationTarget(
                    x_meters=element.xMeters,
                    y_meters=element.yMeters,
                    rotation_radians=math.radians(element.rotationDegrees)
                )
                path.path_elements.append(rotation)
        
        return path
    
    @staticmethod
    def get_current_elements(path: Path) -> List[SerialWaypoint | SerialRotation]:
        """Get current elements in serialization format."""
        return PathModelAdapter.to_serialization_format(path)
    
    @staticmethod
    def load_elements(path: Path, elements: List[SerialWaypoint | SerialRotation]):
        """Load elements into the existing path model."""
        new_path = PathModelAdapter.from_serialization_format(elements)
        path.path_elements.clear()
        path.path_elements.extend(new_path.path_elements)