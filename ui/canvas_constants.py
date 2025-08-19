from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QColor

# Field dimensions (meters)
FIELD_LENGTH_METERS = 16.54
FIELD_WIDTH_METERS = 8.21

# Element visual constants (in meters)
# Defaults; can be overridden at runtime from config
ELEMENT_RECT_WIDTH_M = 0.60
ELEMENT_RECT_HEIGHT_M = 0.60
ELEMENT_CIRCLE_RADIUS_M = 0.1  # radius for circle elements
TRIANGLE_REL_SIZE = 0.55  # percent of the smaller rect dimension
OUTLINE_THIN_M = 0.06     # thin outline (e.g., rotation dashed)
OUTLINE_THICK_M = 0.06    # thicker outline (e.g., translation aesthetic)
CONNECT_LINE_THICKNESS_M = 0.05
HANDLE_LINK_THICKNESS_M = 0.03
HANDLE_RADIUS_M = 0.12
HANDLE_DISTANCE_M = 0.70

# Common pens
OUTLINE_EDGE_PEN = QPen(QColor("#222222"), 0.02)

# Handoff radius visualizer constants
HANDOFF_RADIUS_PEN = QPen(QColor("#FF00FF"), 0.03)  # Magenta with medium thickness
HANDOFF_RADIUS_PEN.setStyle(Qt.DotLine)  # Dotted line style

__all__ = [
    "FIELD_LENGTH_METERS",
    "FIELD_WIDTH_METERS",
    "ELEMENT_RECT_WIDTH_M",
    "ELEMENT_RECT_HEIGHT_M",
    "ELEMENT_CIRCLE_RADIUS_M",
    "TRIANGLE_REL_SIZE",
    "OUTLINE_THIN_M",
    "OUTLINE_THICK_M",
    "CONNECT_LINE_THICKNESS_M",
    "HANDLE_LINK_THICKNESS_M",
    "HANDLE_RADIUS_M",
    "HANDLE_DISTANCE_M",
    "OUTLINE_EDGE_PEN",
    "HANDOFF_RADIUS_PEN",
]
