"""Transport (playback) controls overlay widget builder for the canvas."""
from __future__ import annotations
from typing import Optional, Callable
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSlider, QLabel, QGraphicsProxyWidget, QGraphicsItem
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPen, QColor

class TransportControls:
    def __init__(self, canvas_view: 'CanvasView'):
        self.canvas_view = canvas_view
        self.proxy: Optional[QGraphicsProxyWidget] = None
        self.widget: Optional[QWidget] = None
        self.btn: Optional[QPushButton] = None
        self.slider: Optional[QSlider] = None
        self.label: Optional[QLabel] = None

    def ensure(self):
        if self.widget is not None:
            return
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(6,4,6,4)
        layout.setSpacing(8)
        btn = QPushButton("▶")
        btn.setFixedWidth(28)
        btn.clicked.connect(self.canvas_view._toggle_play_pause)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0,0)
        slider.setSingleStep(10)
        slider.setPageStep(100)
        slider.valueChanged.connect(self.canvas_view._on_slider_changed)
        slider.sliderPressed.connect(self.canvas_view._on_slider_pressed)
        slider.sliderReleased.connect(self.canvas_view._on_slider_released)
        lbl = QLabel("0.00 / 0.00 s")
        lbl.setFixedWidth(110)
        layout.addWidget(btn); layout.addWidget(slider,1); layout.addWidget(lbl)
        proxy = QGraphicsProxyWidget(); proxy.setWidget(w)
        proxy.setZValue(30)
        proxy.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.canvas_view.graphics_scene.addItem(proxy)
        self.proxy, self.widget, self.btn, self.slider, self.label = proxy, w, btn, slider, lbl
        QTimer.singleShot(0, self.position)

    def position(self):
        if self.proxy is None:
            return
        view_rect: QRect = self.canvas_view.viewport().rect()
        px = view_rect.left() + 12
        py = view_rect.bottom() - 12 - (self.widget.height() if self.widget else 28)
        scene_pos = self.canvas_view.mapToScene(px, py)
        self.proxy.setPos(scene_pos)
