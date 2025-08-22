"""Constants and enums for the sidebar module."""

from enum import Enum
from ui.canvas import FIELD_LENGTH_METERS, FIELD_WIDTH_METERS


class ElementType(Enum):
    """Enum representing different types of path elements."""
    TRANSLATION = 'translation'
    ROTATION = 'rotation'
    WAYPOINT = 'waypoint'


# Spinner metadata configuration
SPINNER_METADATA = {
    # Put rotation first so it appears at the top of Core
    'rotation_degrees': {
        'label': 'Rotation (deg)', 
        'step': 1.0, 
        'range': (-99999.0, 99999.0), 
        'removable': False, 
        'section': 'core'
    },
    'x_meters': {
        'label': 'X (m)', 
        'step': 0.05, 
        'range': (0.0, float(FIELD_LENGTH_METERS)), 
        'removable': False, 
        'section': 'core'
    },
    'y_meters': {
        'label': 'Y (m)', 
        'step': 0.05, 
        'range': (0.0, float(FIELD_WIDTH_METERS)), 
        'removable': False, 
        'section': 'core'
    },
    # Handoff radius is a core control for TranslationTarget and Waypoint
    'intermediate_handoff_radius_meters': {
        'label': 'Handoff Radius (m)', 
        'step': 0.05, 
        'range': (0, 99999), 
        'removable': False, 
        'section': 'core'
    }, 
    # Ratio along the segment between previous and next anchors for rotation elements (0..1)
    'rotation_position_ratio': {
        'label': 'Rotation Pos (0–1)', 
        'step': 0.01, 
        'range': (0.0, 1.0), 
        'removable': False, 
        'section': 'core'
    },
    # Boolean checkbox for profiled rotation
    'profiled_rotation': {
        'label': 'Profiled Rotation', 
        'type': 'checkbox', 
        'removable': False, 
        'section': 'core'
    },
    # Constraints (optional)
    'max_velocity_meters_per_sec': {
        'label': 'Max Velocity (m/s)', 
        'step': 0.1, 
        'range': (0, 99999), 
        'removable': True, 
        'section': 'constraints'
    },
    'max_acceleration_meters_per_sec2': {
        'label': 'Max Acceleration (m/s²)', 
        'step': 0.1, 
        'range': (0, 99999), 
        'removable': True, 
        'section': 'constraints'
    },
    'max_velocity_deg_per_sec': {
        'label': 'Max Rot Velocity<br/>(deg/s)', 
        'step': 1.0, 
        'range': (0, 99999), 
        'removable': True, 
        'section': 'constraints'
    },
    'max_acceleration_deg_per_sec2': {
        'label': 'Max Rot Acceleration<br/>(deg/s²)', 
        'step': 1.0, 
        'range': (0, 99999), 
        'removable': True, 
        'section': 'constraints'
    },
    'end_translation_tolerance_meters': {
        'label': 'End Translation Tol (m)',
        'step': 0.005,
        'range': (0.0, 5.0),
        'removable': True,
        'section': 'constraints'
    },
    'end_rotation_tolerance_deg': {
        'label': 'End Rotation Tol (deg)',
        'step': 0.1,
        'range': (0.0, 180.0),
        'removable': True,
        'section': 'constraints'
    }
}        

# Map UI spinner keys to model attribute names (for rotation fields in degrees)
DEGREES_TO_RADIANS_ATTR_MAP = {
    'rotation_degrees': 'rotation_radians'
}

# Path constraint keys
PATH_CONSTRAINT_KEYS = [
    # Non-ranged first for clarity in optional add menu
    'end_translation_tolerance_meters',
    'end_rotation_tolerance_deg',
    # Ranged-capable constraints
    'max_velocity_meters_per_sec',
    'max_acceleration_meters_per_sec2',
    'max_velocity_deg_per_sec',
    'max_acceleration_deg_per_sec2',
]

# Subset of constraint keys that are always stored as flat (non-ranged) values
NON_RANGED_CONSTRAINT_KEYS = [
    'end_translation_tolerance_meters',
    'end_rotation_tolerance_deg',
]
