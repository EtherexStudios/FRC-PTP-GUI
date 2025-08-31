"""Transport (playback) controls overlay widget builder for the canvas."""
from __future__ import annotations
from typing import Optional, Callable, TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSlider, QLabel, QGraphicsProxyWidget, QGraphicsItem
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPen, QColor

if TYPE_CHECKING:
    from ui.canvas.view import CanvasView

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
        # Ensure overlay host is transparent (no unintended grey background)
        try:
            w.setAttribute(Qt.WA_TranslucentBackground, True)
            w.setAutoFillBackground(False)
            w.setStyleSheet("background: transparent; border: none;")
        except Exception:
            pass
        layout = QHBoxLayout(w)
        layout.setContentsMargins(8,6,8,6)
        layout.setSpacing(10)

        # Outer container to visually match sidebar rounded rows
        container = QWidget()
        try:
            container.setObjectName("transportContainer")
        except Exception:
            pass
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(8,6,8,6)
        container_layout.setSpacing(8)
        try:
            container.setStyleSheet(
                """
                QWidget#transportContainer {
                    background-color: #2a2a2a;
                    border: 1px solid #3b3b3b;
                    border-radius: 6px;
                }
                """
            )
        except Exception:
            pass

        btn = QPushButton("▶")
        btn.setFixedWidth(28)
        btn.clicked.connect(self.canvas_view._toggle_play_pause)
        try:
            btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 4px; }")
        except Exception:
            pass

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0,0)
        slider.setSingleStep(1)  # Fine control: 1ms steps
        slider.setPageStep(10)  # Fine page control: 10ms steps
        # Style slider to be cleaner and closer to sidebar range visuals
        try:
            slider.setStyleSheet(
                """
                QSlider::groove:horizontal {
                    border: 1px solid #3b3b3b;
                    height: 6px;
                    background: #444444;
                    border-radius: 3px;
                    margin: 0 8px;
                }
                QSlider::sub-page:horizontal {
                    background: #15c915;
                    border: 1px solid #15c915;
                    height: 6px;
                    border-radius: 3px;
                    margin: 0 8px;
                }
                QSlider::add-page:horizontal {
                    background: #444444;
                    border: 1px solid #3b3b3b;
                    height: 6px;
                    border-radius: 3px;
                    margin: 0 8px;
                }
                QSlider::handle:horizontal {
                    background: #dddddd;
                    border: 1px solid #222222;
                    width: 14px;
                    height: 14px;
                    margin: -6px 0; /* center over the groove */
                    border-radius: 4px;
                }
                QSlider::handle:horizontal:hover {
                    background: #ffffff;
                }
                """
            )
        except Exception:
            pass

        slider.valueChanged.connect(self.canvas_view._on_slider_changed)
        slider.sliderPressed.connect(self.canvas_view._on_slider_pressed)
        slider.sliderReleased.connect(self.canvas_view._on_slider_released)

        lbl = QLabel("0.00 / 0.00 s")
        lbl.setFixedWidth(110)
        try:
            lbl.setStyleSheet("color: #f0f0f0;")
        except Exception:
            pass

        container_layout.addWidget(btn)
        container_layout.addWidget(slider, 1)
        container_layout.addWidget(lbl)
        layout.addWidget(container)
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
