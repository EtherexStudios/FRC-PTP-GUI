from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import json
import os
import hashlib


@dataclass
class Waypoint:
    """Waypoint element with required and optional fields."""
    type: str = "waypoint"
    xMeters: float = 0.0
    yMeters: float = 0.0
    rotationDegrees: Optional[float] = None
    maxVelocityMetersPerSec: Optional[float] = None

    def __post_init__(self):
        if self.type != "waypoint":
            raise ValueError("Waypoint type must be 'waypoint'")


@dataclass
class Rotation:
    """Rotation element with required fields."""
    type: str = "rotation"
    xMeters: float = 0.0
    yMeters: float = 0.0
    rotationDegrees: float = 0.0

    def __post_init__(self):
        if self.type != "rotation":
            raise ValueError("Rotation type must be 'rotation'")


def serialize(elements: List[Waypoint | Rotation]) -> List[Dict[str, Any]]:
    """Serialize elements to JSON-compatible dicts, omitting None values."""
    result = []
    for element in elements:
        # Convert dataclass to dict
        element_dict = asdict(element)
        # Remove None values
        cleaned_dict = {k: v for k, v in element_dict.items() if v is not None}
        result.append(cleaned_dict)
    return result


def deserialize(raw: List[Dict[str, Any]]) -> List[Waypoint | Rotation]:
    """Deserialize raw JSON data to element objects with validation."""
    elements = []
    
    for i, element_data in enumerate(raw):
        if not isinstance(element_data, dict):
            raise ValueError(f"Element {i} is not a dictionary")
        
        element_type = element_data.get("type")
        if not element_type:
            raise ValueError(f"Element {i} missing required 'type' field")
        
        try:
            if element_type == "waypoint":
                # Validate required fields
                if "xMeters" not in element_data:
                    raise ValueError(f"Waypoint {i} missing required 'xMeters' field")
                if "yMeters" not in element_data:
                    raise ValueError(f"Waypoint {i} missing required 'yMeters' field")
                
                # Create waypoint with defaults for optional fields
                waypoint = Waypoint(
                    xMeters=float(element_data["xMeters"]),
                    yMeters=float(element_data["yMeters"]),
                    rotationDegrees=element_data.get("rotationDegrees"),
                    maxVelocityMetersPerSec=element_data.get("maxVelocityMetersPerSec")
                )
                elements.append(waypoint)
                
            elif element_type == "rotation":
                # Validate required fields
                if "xMeters" not in element_data:
                    raise ValueError(f"Rotation {i} missing required 'xMeters' field")
                if "yMeters" not in element_data:
                    raise ValueError(f"Rotation {i} missing required 'yMeters' field")
                if "rotationDegrees" not in element_data:
                    raise ValueError(f"Rotation {i} missing required 'rotationDegrees' field")
                
                # Create rotation element
                rotation = Rotation(
                    xMeters=float(element_data["xMeters"]),
                    yMeters=float(element_data["yMeters"]),
                    rotationDegrees=float(element_data["rotationDegrees"])
                )
                elements.append(rotation)
                
            else:
                raise ValueError(f"Element {i} has unknown type '{element_type}'")
                
        except (ValueError, TypeError) as e:
            raise ValueError(f"Element {i} validation error: {e}")
    
    return elements


def write_atomic(path: str, data: bytes) -> None:
    """Write data atomically using temporary file and os.replace."""
    temp_path = f"{path}.tmp"
    
    try:
        # Write to temporary file
        with open(temp_path, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic replace
        os.replace(temp_path, path)
        
    except Exception as e:
        # Clean up temp file on error
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except:
            pass
        raise e


def serialize_to_bytes(elements: List[Waypoint | Rotation]) -> bytes:
    """Serialize elements to JSON bytes."""
    data = serialize(elements)
    return json.dumps(data, separators=(',', ':')).encode('utf-8')


def compute_hash(data: bytes) -> str:
    """Compute SHA-256 hash of data."""
    return hashlib.sha256(data).hexdigest()