from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, QRect, QPoint
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QGraphicsItem, QGraphicsProxyWidget, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget


class TransportControls:
    def __init__(self, canvas_view: 'CanvasView'):
        self.canvas_view = canvas_view
        self._transport_proxy: Optional[QGraphicsProxyWidget] = None
        self._transport_widget: Optional[QWidget] = None
        self._transport_btn: Optional[QPushButton] = None
        self._transport_slider: Optional[QSlider] = None
        self._transport_label: Optional[QLabel] = None

    # Wiring helpers to expose internals to CanvasView for compatibility
    @property
    def proxy(self) -> Optional[QGraphicsProxyWidget]:
        return self._transport_proxy

    @property
    def widget(self) -> Optional[QWidget]:
        return self._transport_widget

    @property
    def button(self) -> Optional[QPushButton]:
        return self._transport_btn

    @property
    def slider(self) -> Optional[QSlider]:
        return self._transport_slider

    @property
    def label(self) -> Optional[QLabel]:
        return self._transport_label

    def build(self):
        if self._transport_widget is not None:
            return
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        btn = QPushButton()
        btn.setText("▶")
        btn.setFixedWidth(28)
        btn.clicked.connect(self.canvas_view._toggle_play_pause)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 0)
        slider.setSingleStep(10)
        slider.setPageStep(100)
        slider.valueChanged.connect(self.canvas_view._on_slider_changed)
        slider.sliderPressed.connect(self.canvas_view._on_slider_pressed)
        slider.sliderReleased.connect(self.canvas_view._on_slider_released)

        lbl = QLabel("0.00 / 0.00 s")
        lbl.setFixedWidth(110)

        layout.addWidget(btn)
        layout.addWidget(slider, 1)
        layout.addWidget(lbl)

        proxy = QGraphicsProxyWidget()
        proxy.setWidget(w)
        proxy.setZValue(30)
        # Keep fixed pixel size on screen
        proxy.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.canvas_view.graphics_scene.addItem(proxy)

        self._transport_proxy = proxy
        self._transport_widget = w
        self._transport_btn = btn
        self._transport_slider = slider
        self._transport_label = lbl

        # Initial placement
        QTimer.singleShot(0, self.position)

    def position(self):
        if self._transport_proxy is None:
            return
        view_rect: QRect = self.canvas_view.viewport().rect()
        # place 12 px from bottom-left
        px = view_rect.left() + 12
        py = view_rect.bottom() - 12 - (self._transport_widget.height() if self._transport_widget else 28)
        # Map to scene
        scene_pos = self.canvas_view.mapToScene(QPoint(int(px), int(py)))
        self._transport_proxy.setPos(scene_pos)

__all__ = ["TransportControls"]
