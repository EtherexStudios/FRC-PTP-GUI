"""Transport controls for simulation playback."""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QSlider, QLabel, 
    QGraphicsProxyWidget, QGraphicsItem
)
from PySide6.QtCore import Qt, Signal, QTimer


class TransportControls(QWidget):
    """Transport controls widget for simulation playback."""
    
    # Signals
    play_toggled = Signal()
    seek_requested = Signal(float)  # time in seconds
    slider_pressed = Signal()
    slider_released = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize transport controls.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._total_time_s: float = 0.0
        self._current_time_s: float = 0.0
        self._is_playing: bool = False
        
        self._init_ui()
        
    def _init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)
        
        # Play/pause button
        self.play_button = QPushButton()
        self.play_button.setText("▶")
        self.play_button.setFixedWidth(28)
        self.play_button.clicked.connect(self._on_play_clicked)
        
        # Time slider
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 0)
        self.time_slider.setSingleStep(10)
        self.time_slider.setPageStep(100)
        self.time_slider.valueChanged.connect(self._on_slider_changed)
        self.time_slider.sliderPressed.connect(lambda: self.slider_pressed.emit())
        self.time_slider.sliderReleased.connect(lambda: self.slider_released.emit())
        
        # Time label
        self.time_label = QLabel("0.00 / 0.00 s")
        self.time_label.setFixedWidth(110)
        
        layout.addWidget(self.play_button)
        layout.addWidget(self.time_slider, 1)
        layout.addWidget(self.time_label)
        
    def set_total_time(self, total_time_s: float) -> None:
        """
        Set the total simulation time.
        
        Args:
            total_time_s: Total time in seconds
        """
        self._total_time_s = total_time_s
        self.time_slider.blockSignals(True)
        self.time_slider.setRange(0, int(round(total_time_s * 1000.0)))
        self.time_slider.blockSignals(False)
        self._update_time_label()
        
    def set_current_time(self, current_time_s: float) -> None:
        """
        Set the current playback time.
        
        Args:
            current_time_s: Current time in seconds
        """
        self._current_time_s = current_time_s
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(round(current_time_s * 1000.0)))
        self.time_slider.blockSignals(False)
        self._update_time_label()
        
    def set_playing(self, is_playing: bool) -> None:
        """
        Set the playing state.
        
        Args:
            is_playing: Whether simulation is playing
        """
        self._is_playing = is_playing
        self.play_button.setText("⏸" if is_playing else "▶")
        
    def reset(self) -> None:
        """Reset transport controls to initial state."""
        self._total_time_s = 0.0
        self._current_time_s = 0.0
        self._is_playing = False
        self.play_button.setText("▶")
        self.time_slider.setRange(0, 0)
        self.time_label.setText("0.00 / 0.00 s")
        
    def _on_play_clicked(self) -> None:
        """Handle play/pause button click."""
        self.play_toggled.emit()
        
    def _on_slider_changed(self, value: int) -> None:
        """Handle slider value change."""
        time_s = float(value) / 1000.0
        self._current_time_s = time_s
        self._update_time_label()
        self.seek_requested.emit(time_s)
        
    def _update_time_label(self) -> None:
        """Update the time display label."""
        self.time_label.setText(f"{self._current_time_s:.2f} / {self._total_time_s:.2f} s")
        

class TransportControlsProxy:
    """Manages the transport controls as a graphics proxy in the scene."""
    
    def __init__(self, scene) -> None:
        """
        Initialize transport controls proxy.
        
        Args:
            scene: QGraphicsScene to add controls to
        """
        self.scene = scene
        self.widget = TransportControls()
        
        # Create proxy widget
        self.proxy = QGraphicsProxyWidget()
        self.proxy.setWidget(self.widget)
        self.proxy.setZValue(30)
        # Keep fixed pixel size on screen
        self.proxy.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.scene.addItem(self.proxy)
        
    def position_in_view(self, view_rect) -> None:
        """
        Position the controls in the view.
        
        Args:
            view_rect: QRect of the viewport
        """
        try:
            # Place 12 px from bottom-left
            px = view_rect.left() + 12
            py = view_rect.bottom() - 12 - (self.widget.height() if self.widget else 28)
            # This positioning would need the view's mapToScene method
            # For now, just set a position
            self.proxy.setPos(px, py)
        except Exception:
            pass