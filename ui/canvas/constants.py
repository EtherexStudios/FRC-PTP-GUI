"""Constants for the canvas module (field + element geometry in meters)."""
from __future__ import annotations
from PySide6.QtGui import QPen, QColor
from PySide6.QtCore import Qt

FIELD_LENGTH_METERS = 16.54
FIELD_WIDTH_METERS = 8.21

# Element visual constants (in meters)
ELEMENT_RECT_WIDTH_M = 0.60
ELEMENT_RECT_HEIGHT_M = 0.60
ELEMENT_CIRCLE_RADIUS_M = 0.1
TRIANGLE_REL_SIZE = 0.55
OUTLINE_THIN_M = 0.06
OUTLINE_THICK_M = 0.06
CONNECT_LINE_THICKNESS_M = 0.05
HANDLE_LINK_THICKNESS_M = 0.03
HANDLE_RADIUS_M = 0.12
# Shorten rotation handle distance by 35% (from 0.70 to ~0.455)
HANDLE_DISTANCE_M = 0.455

OUTLINE_EDGE_PEN = QPen(QColor("#222222"), 0.02)
HANDOFF_RADIUS_PEN = QPen(QColor("#FF00FF"), 0.03)
HANDOFF_RADIUS_PEN.setStyle(Qt.DotLine)
