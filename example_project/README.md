# Example FRC Path Project

This is a test project directory for the FRC Path Editor application.

## Structure
```
example_project/
├── config.json              # Robot configuration and default values
├── paths/                   # Path files directory
│   ├── simple_path.json     # Basic path with translation, rotation, and waypoint
│   ├── advanced_path.json   # Complex path with multiple elements
│   └── empty_path.json      # Empty path for testing
└── README.md                # This file
```

## How to Use

1. **Open the FRC Path Editor application**
2. **Go to Project > Open Project...**
3. **Navigate to and select this `example_project` directory**
4. **The application will load the config and available paths**

## Available Paths

### simple_path.json
- Basic path demonstrating all three element types
- Translation target with velocity settings
- Rotation target with angular velocity limits
- Waypoint combining both translation and rotation
- Final translation with handoff radius

### advanced_path.json
- More complex path with multiple waypoints
- Various optional properties set
- Different velocity and acceleration values
- Negative rotation angles

### empty_path.json
- Empty path for testing path creation
- Start with this to build your own path from scratch

## Config Values

The `config.json` contains:
- **Robot dimensions**: 0.70m × 0.62m
- **Default velocities**: 1.0-3.0 m/s
- **Default accelerations**: 2.5 m/s²
- **Default angular velocities**: 180-360 deg/s
- **Default handoff radius**: 0.4m

## Testing Features

- **Load different paths** using Project > Load Path
- **Edit config** using Project > Edit Config
- **Save paths** using Project > Save Path As...
- **Switch between projects** using Project > Recent Projects
- **Auto-save** happens automatically on changes
- **Robot dimensions** update canvas display immediately

## File Format

All paths use the JSON format that mirrors the `path_model.py` structure:
- `type`: "translation", "rotation", or "waypoint"
- Element-specific properties (x_meters, y_meters, etc.)
- Optional properties only included when not None
