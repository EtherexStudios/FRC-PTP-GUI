"""Canvas package public API.

This re-exports the primary view plus geometry constants so legacy imports like
``from ui.canvas import ELEMENT_RECT_WIDTH_M`` continue to work after the
refactor from a single ``canvas.py`` module to a package.
"""

from .view import CanvasView  # noqa: F401
from .constants import (  # noqa: F401
	FIELD_LENGTH_METERS,
	FIELD_WIDTH_METERS,
	ELEMENT_RECT_WIDTH_M,
	ELEMENT_RECT_HEIGHT_M,
	ELEMENT_CIRCLE_RADIUS_M,
	HANDLE_DISTANCE_M,
	HANDLE_RADIUS_M,
)

__all__ = [
	"CanvasView",
	# Field dimensions
	"FIELD_LENGTH_METERS",
	"FIELD_WIDTH_METERS",
	# Element geometry
	"ELEMENT_RECT_WIDTH_M",
	"ELEMENT_RECT_HEIGHT_M",
	"ELEMENT_CIRCLE_RADIUS_M",
	# Handle geometry
	"HANDLE_DISTANCE_M",
	"HANDLE_RADIUS_M",
]
