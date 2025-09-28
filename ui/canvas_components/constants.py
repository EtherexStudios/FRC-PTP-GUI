"""Canvas constants and configuration."""

from PySide6.QtGui import QPen, QColor

# Field dimensions
FIELD_LENGTH_METERS: float = 16.54
FIELD_WIDTH_METERS: float = 8.21

# Element visual constants (in meters)
ELEMENT_RECT_WIDTH_M: float = 0.60
ELEMENT_RECT_HEIGHT_M: float = 0.60
ELEMENT_CIRCLE_RADIUS_M: float = 0.1  # radius for circle elements
TRIANGLE_REL_SIZE: float = 0.55  # percent of the smaller rect dimension
OUTLINE_THIN_M: float = 0.06     # thin outline (e.g., rotation dashed)
OUTLINE_THICK_M: float = 0.06    # thicker outline (e.g., translation aesthetic)
CONNECT_LINE_THICKNESS_M: float = 0.05
HANDLE_LINK_THICKNESS_M: float = 0.03
HANDLE_RADIUS_M: float = 0.12
HANDLE_DISTANCE_M: float = 0.70

# Pens
OUTLINE_EDGE_PEN = QPen(QColor("#222222"), 0.02)
HANDOFF_RADIUS_PEN = QPen(QColor("#FF00FF"), 0.03)  # Magenta with medium thickness
HANDOFF_RADIUS_PEN.setStyle(QPen.DotLine)  # Dotted line style