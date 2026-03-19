#!/usr/bin/env python3
"""Prank Builder v4 - Windows 11 style PyQt6 utility for building safe media prank executables."""

from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QIcon, QMovie, QPainter, QPainterPath, QPixmap, QRegion
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QSizeGrip,
    QSpinBox,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_TITLE = "Prank Builder v4"
PROJECT_VERSION = 4
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
SOUND_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
ICON_EXTENSIONS = {".ico"}
MODE_OPTIONS = ["Normal", "Light", "Intensive"]


def set_topmost(window: QWidget, enabled: bool) -> None:
    """Toggle always-on-top behavior using Qt flags without blocking OS controls."""
    was_visible = window.isVisible()
    flags = window.windowFlags()
    if enabled:
        flags |= Qt.WindowType.WindowStaysOnTopHint
    else:
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
    window.setWindowFlags(flags)
    if was_visible:
        window.show()


def handle_drag_drop(file_path: str, window: "MainWindow") -> tuple[bool, str]:
    """Route a dropped file to the correct field based on extension."""
    suffix = Path(file_path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        window.image_path = file_path
        window.image_field.setText(file_path)
        return True, "Loaded image/GIF"
    if suffix in SOUND_EXTENSIONS:
        window.sound_path = file_path
        window.sound_field.setText(file_path)
        return True, "Loaded audio"
    if suffix in ICON_EXTENSIONS:
        window.icon_path = file_path
        window.icon_field.setText(file_path)
        return True, "Loaded icon"
    return False, "Unsupported file type"


def enable_windows_backdrop(widget: QWidget) -> None:
    """Best-effort Windows blur/Mica backdrop. Falls back silently on unsupported platforms."""
    if sys.platform != "win32":
        return
    hwnd = int(widget.winId())
    try:
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        backdrop_type = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(  # type: ignore[attr-defined]
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop_type),
            ctypes.sizeof(backdrop_type),
        )
    except Exception:
        return


class RoundedPanel(QFrame):
    """Rounded translucent panel with clipped corners to avoid square resize artifacts."""

    def __init__(
        self,
        radius: int = 16,
        fill: QColor | None = None,
        border: QColor | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.radius = radius
        self.fill = fill or QColor(255, 255, 255, 232)
        self.border = border or QColor(220, 220, 220, 220)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect().adjusted(0, 0, -1, -1)), self.radius, self.radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        rect = QRectF(self.rect().adjusted(0, 0, -1, -1))
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.fillPath(path, self.fill)
        painter.setPen(self.border)
        painter.drawPath(path)
        super().paintEvent(event)


class TitleBar(QFrame):
    """Custom title bar for frameless builder window."""

    def __init__(self, window: QMainWindow, title: str) -> None:
        super().__init__(window)
        self.window = window
        self._drag_offset = QPoint()
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 10, 10)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleBarLabel")

        self.min_button = QPushButton("—")
        self.min_button.setObjectName("titleButton")
        self.min_button.setFixedSize(36, 30)
        self.min_button.clicked.connect(self.window.showMinimized)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(36, 30)
        self.close_button.clicked.connect(self.window.close)

        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.min_button)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        super().mouseMoveEvent(event)


class LogPanel(QTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setAcceptRichText(True)
        self.document().setMaximumBlockCount(600)
        self.setStyleSheet(
            """
            QTextEdit {
                background: rgba(255, 255, 255, 0.76);
                border: 1px solid rgba(148, 163, 184, 0.30);
                border-radius: 14px;
                padding: 10px;
                color: #0f172a;
                font-family: 'Consolas', 'Segoe UI';
                font-size: 12px;
            }
            """
        )

    def append_log(self, message: str, level: str = "info") -> None:
        palette = {
            "info": ("#475569", "INFO"),
            "success": ("#15803d", "OK"),
            "warning": ("#b45309", "WARN"),
            "error": ("#b91c1c", "ERROR"),
        }
        color, prefix = palette.get(level, palette["info"])
        self.append(f'<span style="color:{color}; font-weight:600;">[{prefix}]</span> {message}')
        self.ensureCursorVisible()


class DropZone(QFrame):
    fileDropped = pyqtSignal(list)

    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("dropTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("dropSubtitle")
        subtitle_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            self.fileDropped.emit([url.toLocalFile() for url in urls if url.isLocalFile()])
            event.acceptProposedAction()
        else:
            event.ignore()


class PreviewWindow(QWidget):
    def __init__(self, image_path: str, sound_path: str = "", title: str = "Preview", max_volume: bool = False) -> None:
        super().__init__()
        self.image_path = image_path
        self.sound_path = sound_path
        self.max_volume = max_volume
        self.movie: QMovie | None = None
        self.pixmap: QPixmap | None = None
        self.player: QMediaPlayer | None = None
        self.audio_output: QAudioOutput | None = None

        self.setWindowTitle(title)
        self.setMinimumSize(820, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)

        panel = RoundedPanel(radius=16, fill=QColor(255, 255, 255, 230), border=QColor(220, 220, 220, 220))
        panel.setObjectName("previewPanel")
        outer.addWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        label = QLabel("Preview Window")
        label.setObjectName("previewTitle")
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        header.addWidget(label)
        header.addStretch(1)
        header.addWidget(close_button)
        layout.addLayout(header)

        self.media_label = QLabel("Preview unavailable")
        self.media_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.media_label.setScaledContents(False)
        self.media_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.media_label.setObjectName("previewMedia")
        layout.addWidget(self.media_label, 1)

        self.setStyleSheet(
            """
            QWidget { background: transparent; font-family: 'Segoe UI'; }
            QFrame#previewPanel {
                background: rgba(255, 255, 255, 0.86);
                border: 1px solid rgba(148, 163, 184, 0.30);
                border-radius: 16px;
            }
            QLabel#previewTitle {
                color: #0f172a;
                font-size: 20px;
                font-weight: 600;
            }
            QLabel#previewMedia {
                background: rgba(241, 245, 249, 0.86);
                border: 1px solid rgba(148, 163, 184, 0.28);
                border-radius: 14px;
                color: #475569;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(148, 163, 184, 0.36);
                border-radius: 12px;
                padding: 10px 16px;
                color: #0f172a;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.96); }
            """
        )
        self.apply_shadow(panel)
        self._audio_started = False
        self.load_media()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        enable_windows_backdrop(self)
        if self.sound_path and not self._audio_started:
            self._audio_started = True
            QTimer.singleShot(100, self.play_sound)

    def apply_shadow(self, widget: QWidget) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(148, 163, 184, 70))
        widget.setGraphicsEffect(shadow)

    def load_media(self) -> None:
        suffix = Path(self.image_path).suffix.lower()
        if suffix == ".gif":
            self.movie = QMovie(self.image_path)
            self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
            self.media_label.setMovie(self.movie)
            self.movie.start()
            self.scale_movie()
            return
        pixmap = QPixmap(self.image_path)
        if pixmap.isNull():
            self.media_label.setText("Could not load media.")
            return
        self.pixmap = pixmap
        self.scale_pixmap()

    def play_sound(self) -> None:
        if not self.sound_path:
            return
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0 if self.max_volume else 0.85)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(QUrl.fromLocalFile(str(Path(self.sound_path).resolve())))
        self.player.play()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.scale_pixmap()
        self.scale_movie()

    def scale_pixmap(self) -> None:
        if not self.pixmap:
            return
        scaled = self.pixmap.scaled(
            self.media_label.size() - QSize(20, 20),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.media_label.setPixmap(scaled)

    def scale_movie(self) -> None:
        if not self.movie:
            return
        target = self.media_label.size() - QSize(20, 20)
        current = self.movie.currentPixmap().size()
        if current.isEmpty():
            current = QSize(800, 600)
        self.movie.setScaledSize(current.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.player:
            self.player.stop()
        if self.movie:
            self.movie.stop()
        super().closeEvent(event)


class BuildThread(QThread):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int)
    success = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        image_path: str,
        sound_path: str,
        icon_path: str,
        output_path: str,
        config: dict[str, object],
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.sound_path = sound_path
        self.icon_path = icon_path
        self.output_path = output_path
        self.config = config

    def emit_log(self, message: str, level: str = "info") -> None:
        self.log.emit(message, level)

    def run(self) -> None:
        temp_dir: str | None = None
        try:
            valid, message = validate_inputs(self.image_path, self.sound_path, self.icon_path)
            if not valid:
                raise ValueError(message)

            self.progress.emit(5)
            temp_dir = tempfile.mkdtemp(prefix="prank_builder_v4_")
            temp_path = Path(temp_dir)
            media_dir = temp_path / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            self.emit_log(f"Created temporary workspace: {temp_path}")

            image_copy = media_dir / Path(self.image_path).name
            shutil.copy2(self.image_path, image_copy)
            self.emit_log(f"Bundled image/GIF: {image_copy.name}")

            sound_copy: Path | None = None
            if self.sound_path:
                sound_copy = media_dir / Path(self.sound_path).name
                shutil.copy2(self.sound_path, sound_copy)
                self.emit_log(f"Bundled sound: {sound_copy.name}")

            payload_path = temp_path / "payload.py"
            payload_path.write_text(
                generate_payload(
                    image_name=image_copy.name,
                    sound_name=sound_copy.name if sound_copy else "",
                    title=str(self.config.get("window_title") or APP_TITLE),
                    mode=str(self.config.get("mode") or "Normal"),
                    topmost=bool(self.config.get("topmost")),
                    fullscreen=bool(self.config.get("fullscreen")),
                    loop_sound=bool(self.config.get("loop_sound")),
                    max_volume=bool(self.config.get("max_volume")),
                    relax_mode=bool(self.config.get("relax_mode")),
                    delay_seconds=int(self.config.get("delay_seconds") or 0),
                    window_scale=int(self.config.get("window_scale") or 70),
                    esc_exit=bool(self.config.get("esc_exit")),
                ),
                encoding="utf-8",
            )
            self.progress.emit(18)
            self.emit_log("Generated payload script.")

            result = run_pyinstaller(
                script_path=payload_path,
                image_path=image_copy,
                sound_path=sound_copy,
                icon_path=Path(self.icon_path) if self.icon_path else None,
                output_path=Path(self.output_path),
                progress_callback=self.progress.emit,
                log_callback=self.emit_log,
            )
            self.progress.emit(100)
            self.emit_log(f"Build complete: {result}", "success")
            self.success.emit(str(result))
        except Exception as exc:  # noqa: BLE001
            self.emit_log(str(exc), "error")
            self.error.emit(str(exc))
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.emit_log("Temporary workspace cleaned up.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.image_path = ""
        self.sound_path = ""
        self.icon_path = ""
        self.build_thread: BuildThread | None = None
        self.preview_window: PreviewWindow | None = None

        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1180, 820)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(self.build_stylesheet())

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)

        self.background_accent = QFrame(root)
        self.background_accent.setObjectName("backgroundAccent")
        accent_blur = QGraphicsBlurEffect(self)
        accent_blur.setBlurRadius(42)
        self.background_accent.setGraphicsEffect(accent_blur)

        self.shell = RoundedPanel(
            radius=16,
            fill=QColor(248, 248, 248, 232),
            border=QColor(220, 220, 220, 235),
        )
        self.shell.setObjectName("shell")
        root_layout.addWidget(self.shell)
        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(24, 24, 24, 24)
        shell_layout.setSpacing(20)

        shell_shadow = QGraphicsDropShadowEffect(self)
        shell_shadow.setBlurRadius(42)
        shell_shadow.setOffset(0, 16)
        shell_shadow.setColor(QColor(148, 163, 184, 90))
        self.shell.setGraphicsEffect(shell_shadow)

        self.title_bar = TitleBar(self, APP_TITLE)
        shell_layout.addWidget(self.title_bar)
        shell_layout.addWidget(self.build_header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.build_files_tab(), "Files")
        self.tabs.addTab(self.build_settings_tab(), "Settings")
        self.tabs.addTab(self.build_build_tab(), "Build")
        self.tabs.addTab(self.build_logs_tab(), "Logs")
        self.tabs.addTab(self.build_help_tab(), "Help")
        shell_layout.addWidget(self.tabs, 1)

        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        self.size_grip = QSizeGrip(self.shell)
        grip_row.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        shell_layout.addLayout(grip_row)

        self.log_panel.append_log("Ready. Add an image or GIF to begin.", "success")

    def build_stylesheet(self) -> str:
        return """
        QWidget {
            font-family: 'Segoe UI';
            color: #0f172a;
            background: transparent;
        }
        QFrame#backgroundAccent {
            background: rgba(96, 165, 250, 0.18);
            border-radius: 26px;
        }
        QFrame#shell {
            background: transparent;
            border: none;
        }
        QFrame#titleBar {
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid rgba(220, 220, 220, 0.88);
            border-radius: 14px;
        }
        QFrame#acrylicCard, QGroupBox {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(220, 220, 220, 0.92);
            border-radius: 14px;
        }
        QGroupBox {
            margin-top: 16px;
            font-size: 14px;
            font-weight: 600;
            padding-top: 12px;
        }
        QGroupBox::title {
            left: 16px;
            padding: 0 8px;
        }
        QLabel#titleLabel {
            font-size: 28px;
            font-weight: 700;
        }
        QLabel#titleBarLabel {
            font-size: 14px;
            font-weight: 600;
            color: #111827;
        }
        QLabel#subtitleLabel {
            font-size: 14px;
            color: #475569;
        }
        QLabel#helpTitle {
            font-size: 15px;
            font-weight: 700;
            color: #0f172a;
        }
        QLabel#dropTitle {
            font-size: 15px;
            font-weight: 600;
        }
        QLabel#dropSubtitle {
            color: #64748b;
        }
        QFrame#dropZone {
            background: rgba(255, 255, 255, 0.70);
            border: 1px dashed rgba(148, 163, 184, 0.85);
            border-radius: 14px;
        }
        QFrame#dropZone[dragging="true"] {
            background: rgba(219, 234, 254, 0.95);
            border: 1px dashed #3b82f6;
        }
        QTabWidget::pane {
            border: 1px solid rgba(220, 220, 220, 0.90);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.72);
            top: -1px;
        }
        QTabBar::tab {
            background: rgba(255, 255, 255, 0.68);
            border: 1px solid rgba(220, 220, 220, 0.90);
            border-bottom: none;
            padding: 10px 20px;
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            margin-right: 6px;
            color: #334155;
        }
        QTabBar::tab:selected {
            background: rgba(255, 255, 255, 0.92);
            color: #0f172a;
        }
        QLineEdit, QSpinBox, QComboBox {
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid rgba(220, 220, 220, 0.92);
            border-radius: 12px;
            padding: 10px 12px;
            min-height: 22px;
        }
        QLineEdit[readOnly="true"] {
            color: #475569;
        }
        QPushButton {
            background: rgba(255, 255, 255, 0.95);
            border: 1px solid rgba(220, 220, 220, 0.92);
            border-radius: 12px;
            padding: 10px 16px;
            color: #0f172a;
            font-weight: 600;
        }
        QPushButton:hover {
            background: rgba(255, 255, 255, 1.0);
        }
        QPushButton#primaryButton {
            background: #2563eb;
            border: 1px solid #2563eb;
            color: white;
        }
        QPushButton#primaryButton:hover {
            background: #1d4ed8;
        }
        QPushButton#titleButton, QPushButton#closeButton {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(220, 220, 220, 0.88);
            border-radius: 10px;
            font-size: 13px;
            padding: 0;
        }
        QPushButton#titleButton:hover {
            background: rgba(243, 244, 246, 1.0);
        }
        QPushButton#closeButton:hover {
            background: #ef4444;
            border-color: #ef4444;
            color: white;
        }
        QProgressBar {
            background: rgba(255, 255, 255, 0.90);
            border: 1px solid rgba(220, 220, 220, 0.92);
            border-radius: 10px;
            min-height: 18px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #2563eb;
            border-radius: 9px;
        }
        QCheckBox {
            spacing: 10px;
        }
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
        }
        QCheckBox::indicator:unchecked {
            border: 1px solid rgba(100, 116, 139, 0.80);
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.92);
        }
        QCheckBox::indicator:checked {
            border: 1px solid #2563eb;
            border-radius: 6px;
            background: #2563eb;
        }
        """

    def build_header(self) -> QWidget:
        card = QFrame()
        card.setObjectName("acrylicCard")
        self.apply_card_effect(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        title = QLabel(APP_TITLE)
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Windows 11–style prank builder for predictable media-only EXEs with safe exits, preview, and build logging."
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card

    def build_files_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        drop = DropZone(
            "Drag & Drop Files",
            "Drop an image/GIF, audio file, or icon. The app detects the file type and fills the matching field automatically.",
        )
        drop.fileDropped.connect(self.route_dropped_files)
        layout.addWidget(drop)

        files_group = QGroupBox("Media Files")
        files_layout = QGridLayout(files_group)
        files_layout.setHorizontalSpacing(12)
        files_layout.setVerticalSpacing(12)

        self.image_field = self.make_path_field("Image or GIF (required)")
        self.sound_field = self.make_path_field("Audio (optional)")
        self.icon_field = self.make_path_field("Icon (.ico, optional)")

        image_button = QPushButton("Select Image / GIF")
        image_button.clicked.connect(self.select_image)
        sound_button = QPushButton("Select Audio")
        sound_button.clicked.connect(self.select_sound)
        icon_button = QPushButton("Select Icon")
        icon_button.clicked.connect(self.select_icon)

        files_layout.addWidget(QLabel("Image / GIF"), 0, 0)
        files_layout.addWidget(self.image_field, 0, 1)
        files_layout.addWidget(image_button, 0, 2)
        files_layout.addWidget(QLabel("Audio"), 1, 0)
        files_layout.addWidget(self.sound_field, 1, 1)
        files_layout.addWidget(sound_button, 1, 2)
        files_layout.addWidget(QLabel("Icon"), 2, 0)
        files_layout.addWidget(self.icon_field, 2, 1)
        files_layout.addWidget(icon_button, 2, 2)

        layout.addWidget(files_group)
        layout.addStretch(1)
        return tab

    def build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        settings_group = QGroupBox("Payload Settings")
        form = QFormLayout(settings_group)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(16)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODE_OPTIONS)
        self.topmost_check = QCheckBox("Keep payload on top when supported")
        self.fullscreen_check = QCheckBox("Optional fullscreen in Intensive mode")
        self.loop_sound_check = QCheckBox("Loop sound if audio exists")
        self.max_volume_check = QCheckBox("Max Volume on Launch")
        self.max_volume_check.toggled.connect(self.handle_max_volume_toggle)
        self.relax_mode_check = QCheckBox("Relax Mode")
        self.esc_exit_check = QCheckBox("Enable ESC as an additional exit key")
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 60)
        self.delay_spin.setSuffix(" sec")
        self.window_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.window_size_slider.setRange(30, 100)
        self.window_size_slider.setValue(70)
        self.window_size_label = QLabel("70%")
        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(0, 0, 0, 0)
        slider_row.addWidget(self.window_size_slider, 1)
        slider_row.addWidget(self.window_size_label)
        slider_widget = QWidget()
        slider_widget.setLayout(slider_row)
        self.window_size_slider.valueChanged.connect(lambda value: self.window_size_label.setText(f"{value}%"))
        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Optional payload window title")

        form.addRow("Mode", self.mode_combo)
        form.addRow("Topmost", self.topmost_check)
        form.addRow("Window behavior", self.fullscreen_check)
        form.addRow("Sound behavior", self.loop_sound_check)
        form.addRow("Volume", self.max_volume_check)
        form.addRow("Pre-roll", self.relax_mode_check)
        form.addRow("Exit options", self.esc_exit_check)
        form.addRow("Delay before showing", self.delay_spin)
        form.addRow("Window Size", slider_widget)
        form.addRow("Payload title", self.title_field)

        safety_group = QGroupBox("Safety Summary")
        safety_layout = QVBoxLayout(safety_group)
        safety_layout.addWidget(QLabel("• INSERT exits the payload (required)."))
        safety_layout.addWidget(QLabel("• ALT+F3 exits the payload (required)."))
        safety_layout.addWidget(QLabel("• ESC remains optional and configurable."))
        safety_layout.addWidget(QLabel("• Relax Mode shows a small cat pre-roll window before the prank starts."))
        safety_layout.addWidget(QLabel("• Light mode stays centered and can respect the Topmost setting."))
        safety_layout.addWidget(QLabel("• Alt+F4 and OS-level controls are not blocked."))

        layout.addWidget(settings_group)
        layout.addWidget(safety_group)
        layout.addStretch(1)
        return tab

    def build_build_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        actions_group = QGroupBox("Project Actions")
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setSpacing(12)

        preview_button = QPushButton("Preview")
        preview_button.clicked.connect(self.open_preview)
        build_button = QPushButton("Build EXE")
        build_button.setObjectName("primaryButton")
        build_button.clicked.connect(self.start_build)
        save_project_button = QPushButton("Save Project JSON")
        save_project_button.clicked.connect(self.save_project)
        load_project_button = QPushButton("Load Project JSON")
        load_project_button.clicked.connect(self.load_project)

        self.preview_button = preview_button
        self.build_button = build_button

        actions_layout.addWidget(preview_button)
        actions_layout.addWidget(build_button)
        actions_layout.addStretch(1)
        actions_layout.addWidget(save_project_button)
        actions_layout.addWidget(load_project_button)

        status_group = QGroupBox("Build Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(12)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label = QLabel("Waiting for input.")
        self.status_label.setStyleSheet("color: #475569;")
        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.status_label)

        layout.addWidget(actions_group)
        layout.addWidget(status_group)
        layout.addStretch(1)
        return tab

    def build_logs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        self.log_panel = LogPanel()
        layout.addWidget(self.log_panel)
        return tab

    def build_help_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        help_panel = QTextEdit()
        help_panel.setReadOnly(True)
        help_panel.setStyleSheet(
            "QTextEdit { background: rgba(255, 255, 255, 0.86); border: 1px solid rgba(220, 220, 220, 0.92); border-radius: 14px; padding: 12px; }"
        )
        help_panel.setHtml(
            """
            <h2 style='margin:0 0 12px 0;'>Prank Builder Help</h2>
            <p style='margin:0 0 12px 0;'>This utility creates a media-only EXE using PyInstaller. The generated prank only shows the selected image/GIF and can optionally play audio.</p>
            <p id='modes'><span id='helpTitle'>Modes</span><br>
            <b>Normal</b>: borderless, centered, not fullscreen.<br>
            <b>Light</b>: borderless, centered, calmer presentation, can respect the Topmost checkbox.<br>
            <b>Intensive</b>: borderless, always on top, optional fullscreen, and periodic focus regain.</p>
            <p><span id='helpTitle'>Settings</span><br>
            <b>Fullscreen</b>: used by Intensive mode when enabled.<br>
            <b>Loop sound</b>: replays the selected audio until the prank exits.<br>
            <b>Max Volume on Launch</b>: forces payload audio to maximum volume after the prank window appears.<br>
            <b>Relax Mode</b>: shows a small cat pre-roll window before the main prank starts.<br>
            <b>Delay</b>: waits before showing the prank window.<br>
            <b>Window Size</b>: sets the non-fullscreen prank size from 30% to 100% of the screen.<br>
            <b>Topmost</b>: keeps the prank above other windows where the selected mode allows it.</p>
            <p><span id='helpTitle'>Build process</span><br>
            The builder validates your files, writes a temporary payload script, bundles the selected media with <code>--add-data</code>, and runs PyInstaller with <code>--onefile</code> and <code>--noconsole</code>. The EXE is never launched automatically.</p>
            <p><span id='helpTitle'>Exit controls</span><br>
            <b>INSERT</b> exits the payload.<br>
            <b>ALT+F3</b> exits the payload.<br>
            <b>ESC</b> is optional and controlled in the Settings tab.</p>
            """
        )
        layout.addWidget(help_panel)
        return tab

    def apply_card_effect(self, widget: QWidget) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(148, 163, 184, 50))
        widget.setGraphicsEffect(shadow)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.background_accent.setGeometry(40, 40, max(220, self.width() - 160), max(160, self.height() - 120))

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        enable_windows_backdrop(self)

    def make_path_field(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setReadOnly(True)
        field.setPlaceholderText(placeholder)
        return field

    def collect_config(self) -> dict[str, object]:
        return {
            "version": PROJECT_VERSION,
            "image_path": self.image_path,
            "sound_path": self.sound_path,
            "icon_path": self.icon_path,
            "mode": self.mode_combo.currentText(),
            "topmost": self.topmost_check.isChecked(),
            "fullscreen": self.fullscreen_check.isChecked(),
            "loop_sound": self.loop_sound_check.isChecked() and bool(self.sound_path),
            "max_volume": self.max_volume_check.isChecked() and bool(self.sound_path),
            "relax_mode": self.relax_mode_check.isChecked(),
            "esc_exit": self.esc_exit_check.isChecked(),
            "delay_seconds": self.delay_spin.value(),
            "window_scale": self.window_size_slider.value(),
            "window_title": self.title_field.text().strip(),
        }

    def apply_config(self, config: dict[str, object]) -> None:
        self.image_path = str(config.get("image_path") or "")
        self.sound_path = str(config.get("sound_path") or "")
        self.icon_path = str(config.get("icon_path") or "")
        self.image_field.setText(self.image_path)
        self.sound_field.setText(self.sound_path)
        self.icon_field.setText(self.icon_path)
        mode = str(config.get("mode") or MODE_OPTIONS[0])
        index = max(self.mode_combo.findText(mode), 0)
        self.mode_combo.setCurrentIndex(index)
        self.topmost_check.setChecked(bool(config.get("topmost")))
        self.fullscreen_check.setChecked(bool(config.get("fullscreen")))
        self.loop_sound_check.setChecked(bool(config.get("loop_sound")))
        self.max_volume_check.blockSignals(True)
        self.max_volume_check.setChecked(bool(config.get("max_volume")))
        self.max_volume_check.blockSignals(False)
        self.relax_mode_check.setChecked(bool(config.get("relax_mode")))
        self.esc_exit_check.setChecked(bool(config.get("esc_exit")))
        self.delay_spin.setValue(int(config.get("delay_seconds") or 0))
        self.window_size_slider.setValue(int(config.get("window_scale") or 70))
        self.title_field.setText(str(config.get("window_title") or ""))

    def log(self, message: str, level: str = "info") -> None:
        self.log_panel.append_log(message, level)

    def handle_max_volume_toggle(self, enabled: bool) -> None:
        if enabled:
            self.show_message(
                APP_TITLE,
                "Sound will be played at maximum volume. Make sure it is safe to do so.",
                "warning",
            )

    def show_message(self, title: str, text: str, level: str = "info") -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        icon_map = {
            "info": QMessageBox.Icon.Information,
            "warning": QMessageBox.Icon.Warning,
            "error": QMessageBox.Icon.Critical,
        }
        box.setIcon(icon_map.get(level, QMessageBox.Icon.Information))
        box.setStyleSheet(
            """
            QMessageBox {
                background: white;
            }
            QMessageBox QLabel {
                color: black;
                background: white;
                min-width: 320px;
            }
            QMessageBox QPushButton {
                background: #f9fafb;
                color: black;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px 14px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background: #f3f4f6;
            }
            """
        )
        box.exec()

    def route_dropped_file(self, file_path: str) -> None:
        handled, message = handle_drag_drop(file_path, self)
        if handled:
            self.log(f"{message}: {file_path}", "success")
        else:
            self.log(f"{message}: {file_path}", "warning")

    def route_dropped_files(self, file_paths: list[str]) -> None:
        paths = [path for path in file_paths if path]
        if not paths:
            self.log("No usable files were dropped.", "warning")
            return
        if len(paths) > 1:
            self.log("Multiple files detected. Processing each supported file type.", "info")
        for file_path in paths:
            self.route_dropped_file(file_path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.route_dropped_files([url.toLocalFile() for url in urls if url.isLocalFile()])
            event.acceptProposedAction()

    def select_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image or GIF",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if path:
            self.image_path = path
            self.image_field.setText(path)
            self.log(f"Selected image/GIF: {path}", "success")

    def select_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio",
            "",
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a)",
        )
        if path:
            self.sound_path = path
            self.sound_field.setText(path)
            self.log(f"Selected audio: {path}", "success")

    def select_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Icon", "", "Icon (*.ico)")
        if path:
            self.icon_path = path
            self.icon_field.setText(path)
            self.log(f"Selected icon: {path}", "success")

    def open_preview(self) -> None:
        valid, message = validate_inputs(self.image_path, self.sound_path, self.icon_path)
        if not valid:
            self.log(message, "error")
            self.show_message(APP_TITLE, message, "warning")
            return
        if self.preview_window is not None:
            self.preview_window.close()
        self.preview_window = PreviewWindow(
            image_path=self.image_path,
            sound_path=self.sound_path,
            title=self.title_field.text().strip() or "Preview",
            max_volume=self.max_volume_check.isChecked() and bool(self.sound_path),
        )
        self.preview_window.show()
        self.preview_window.raise_()
        self.log("Opened preview window.", "success")

    def start_build(self) -> None:
        valid, message = validate_inputs(self.image_path, self.sound_path, self.icon_path)
        if not valid:
            self.log(message, "error")
            self.show_message(APP_TITLE, message, "warning")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save prank executable",
            str(Path.home() / "prank_builder_v4.exe"),
            "Executable (*.exe)",
        )
        if not output_path:
            self.log("Build cancelled.", "warning")
            return
        if not output_path.lower().endswith(".exe"):
            output_path += ".exe"

        self.progress_bar.setValue(0)
        self.status_label.setText("Preparing build...")
        self.build_button.setEnabled(False)
        self.preview_button.setEnabled(False)

        self.build_thread = BuildThread(
            image_path=self.image_path,
            sound_path=self.sound_path,
            icon_path=self.icon_path,
            output_path=output_path,
            config=self.collect_config(),
        )
        self.build_thread.log.connect(self.log)
        self.build_thread.progress.connect(self.progress_bar.setValue)
        self.build_thread.progress.connect(lambda value: self.status_label.setText(f"Build progress: {value}%"))
        self.build_thread.success.connect(self.on_build_success)
        self.build_thread.error.connect(self.on_build_error)
        self.build_thread.finished.connect(self.on_build_finished)
        self.build_thread.start()
        self.log(f"Starting build: {output_path}")

    def on_build_success(self, output_path: str) -> None:
        self.status_label.setText(f"Build complete: {output_path}")
        self.log(f"Build succeeded: {output_path}", "success")
        self.show_message(APP_TITLE, f"Build completed successfully.\n\nOutput: {output_path}", "info")

    def on_build_error(self, message: str) -> None:
        self.status_label.setText("Build failed.")
        self.log(f"Build failed: {message}", "error")
        self.show_message(APP_TITLE, message, "error")

    def on_build_finished(self) -> None:
        self.build_button.setEnabled(True)
        self.preview_button.setEnabled(True)

    def save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save project",
            str(Path.home() / "prank_builder_v4.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        Path(path).write_text(json.dumps(self.collect_config(), indent=2), encoding="utf-8")
        self.log(f"Saved project configuration: {path}", "success")

    def load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load project", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Project file must contain a JSON object.")
            self.apply_config(data)
            self.log(f"Loaded project configuration: {path}", "success")
        except Exception as exc:  # noqa: BLE001
            self.log(str(exc), "error")
            self.show_message(APP_TITLE, f"Could not load project file.\n\n{exc}", "error")


def validate_inputs(image_path: str, sound_path: str, icon_path: str) -> tuple[bool, str]:
    if not image_path:
        return False, "An image or GIF is required."
    image_suffix = Path(image_path).suffix.lower()
    if image_suffix not in IMAGE_EXTENSIONS:
        return False, "Unsupported image/GIF format."
    if not Path(image_path).is_file():
        return False, "Selected image/GIF file does not exist."

    if sound_path:
        sound_suffix = Path(sound_path).suffix.lower()
        if sound_suffix not in SOUND_EXTENSIONS:
            return False, "Unsupported audio format."
        if not Path(sound_path).is_file():
            return False, "Selected audio file does not exist."

    if icon_path:
        icon_suffix = Path(icon_path).suffix.lower()
        if icon_suffix not in ICON_EXTENSIONS:
            return False, "Icon must be a .ico file."
        if not Path(icon_path).is_file():
            return False, "Selected icon file does not exist."
    return True, ""


def generate_payload(
    image_name: str,
    sound_name: str,
    title: str,
    mode: str,
    topmost: bool,
    fullscreen: bool,
    loop_sound: bool,
    max_volume: bool,
    relax_mode: bool,
    delay_seconds: int,
    window_scale: int,
    esc_exit: bool,
) -> str:
    data = {
        "image": base64.b64encode(image_name.encode("utf-8")).decode("ascii"),
        "sound": base64.b64encode(sound_name.encode("utf-8")).decode("ascii"),
        "title": base64.b64encode(title.encode("utf-8")).decode("ascii"),
        "mode": base64.b64encode(mode.encode("utf-8")).decode("ascii"),
    }
    return f'''from __future__ import annotations
import base64
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize, QUrl
from PyQt6.QtGui import QColor, QGuiApplication, QKeySequence, QMovie, QPainter, QPixmap, QShortcut
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QApplication, QLabel, QHBoxLayout, QVBoxLayout, QWidget


def set_topmost(window: QWidget, enabled: bool) -> None:
    was_visible = window.isVisible()
    flags = window.windowFlags()
    if enabled:
        flags |= Qt.WindowType.WindowStaysOnTopHint
    else:
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
    window.setWindowFlags(flags)
    if was_visible:
        window.show()


IMAGE_NAME = base64.b64decode("{data['image']}").decode("utf-8")
SOUND_NAME = base64.b64decode("{data['sound']}").decode("utf-8")
WINDOW_TITLE = base64.b64decode("{data['title']}").decode("utf-8")
MODE = base64.b64decode("{data['mode']}").decode("utf-8")
TOPMOST = {topmost!r}
FULLSCREEN = {fullscreen!r}
LOOP_SOUND = {loop_sound!r}
MAX_VOLUME = {max_volume!r}
RELAX_MODE = {relax_mode!r}
DELAY_SECONDS = {delay_seconds}
WINDOW_SCALE = {window_scale}
ESC_EXIT = {esc_exit!r}


def attach_exit_shortcuts(widget: QWidget, callback) -> None:
    shortcuts = [
        QShortcut(QKeySequence('Insert'), widget, activated=callback),
        QShortcut(QKeySequence('Alt+F3'), widget, activated=callback),
    ]
    if ESC_EXIT:
        shortcuts.append(QShortcut(QKeySequence('Esc'), widget, activated=callback))
    widget._exit_shortcuts = shortcuts


def make_cat_pixmap(index: int) -> QPixmap:
    pixmap = QPixmap(150, 110)
    colors = [QColor('#fde68a'), QColor('#fbcfe8'), QColor('#bfdbfe')]
    pixmap.fill(colors[index % len(colors)])
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor('#111827'))
    painter.setBrush(QColor(255, 255, 255, 180))
    painter.drawRoundedRect(12, 12, 126, 86, 18, 18)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, f'Cute Cat\\n#{index + 1}')
    painter.end()
    return pixmap


class RelaxWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('Relax Mode')
        self.setStyleSheet('background: #f3f3f3;')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        set_topmost(self, MODE == 'Intensive' or TOPMOST)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel('Relax Mode')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet('font-size: 18px; font-weight: 600; color: #111827;')
        subtitle = QLabel('Cute cat placeholders before the prank starts.')
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet('color: #475569;')
        cards = QHBoxLayout()
        cards.setSpacing(10)
        for index in range(3):
            card = QLabel()
            card.setPixmap(make_cat_pixmap(index))
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.setStyleSheet('background: white; border-radius: 12px; padding: 4px;')
            cards.addWidget(card)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(cards)
        self.resize(540, 260)
        self.center_window()

    def center_window(self) -> None:
        geo = self.frameGeometry()
        center = QGuiApplication.primaryScreen().availableGeometry().center()
        geo.moveCenter(center)
        self.move(geo.topLeft())


class PayloadWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setStyleSheet("background: #f3f3f3;")
        flags = Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setScaledContents(False)
        self.label.setStyleSheet("background: #f3f3f3; color: #111827;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.label)

        self.audio_output = None
        self.player = None
        self.movie = None
        self.pixmap = None
        self.focus_timer = None

        base_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'media'
        self.image_path = base_dir / IMAGE_NAME
        self.sound_path = base_dir / SOUND_NAME if SOUND_NAME else None

        self.load_media()
        self.configure_mode()

    def configure_mode(self) -> None:
        intensive = MODE == 'Intensive'
        light = MODE == 'Light'
        set_topmost(self, intensive or TOPMOST)
        if intensive:
            if FULLSCREEN:
                self.resize(QGuiApplication.primaryScreen().availableGeometry().size())
            else:
                self.apply_scaled_window_size()
                self.center_window()
            self.focus_timer = QTimer(self)
            self.focus_timer.timeout.connect(self.raise_and_focus)
            self.focus_timer.start(1500)
        else:
            self.apply_scaled_window_size()
            self.center_window()
            if light:
                self.raise_and_focus()

    def apply_scaled_window_size(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        scale = max(30, min(WINDOW_SCALE, 100)) / 100.0
        width = int(screen.width() * scale)
        height = int(screen.height() * scale)
        if MODE == 'Light' and self.pixmap and not self.pixmap.isNull():
            width = min(width, self.pixmap.width() + 48)
            height = min(height, self.pixmap.height() + 48)
        self.resize(max(420, width), max(320, height))

    def raise_and_focus(self) -> None:
        self.raise_()
        self.activateWindow()

    def center_window(self) -> None:
        geo = self.frameGeometry()
        center = QGuiApplication.primaryScreen().availableGeometry().center()
        geo.moveCenter(center)
        self.move(geo.topLeft())

    def load_media(self) -> None:
        if self.image_path.suffix.lower() == '.gif':
            self.movie = QMovie(str(self.image_path))
            self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
            self.label.setMovie(self.movie)
            self.movie.start()
            self.scale_movie()
            return
        self.pixmap = QPixmap(str(self.image_path))
        self.scale_pixmap()

    def configure_sound(self) -> None:
        if not self.sound_path:
            return
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0 if MAX_VOLUME else 0.85)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(QUrl.fromLocalFile(str(self.sound_path.resolve())))
        if LOOP_SOUND:
            self.player.mediaStatusChanged.connect(self.handle_media_status)
        self.player.play()

    def handle_media_status(self, status) -> None:
        if LOOP_SOUND and self.player and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.scale_pixmap()
        self.scale_movie()

    def scale_pixmap(self) -> None:
        if not self.pixmap:
            return
        scaled = self.pixmap.scaled(self.size() - QSize(20, 20), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.label.setPixmap(scaled)

    def scale_movie(self) -> None:
        if not self.movie:
            return
        target = self.size() - QSize(20, 20)
        current = self.movie.currentPixmap().size()
        if current.isEmpty():
            current = QSize(800, 600)
        self.movie.setScaledSize(current.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))


app = QApplication(sys.argv)
window = PayloadWindow()
relax_window = RelaxWindow() if RELAX_MODE else None

def quit_all() -> None:
    if relax_window is not None:
        relax_window.close()
    if window.player:
        window.player.stop()
    if window.movie:
        window.movie.stop()
    window.close()
    app.quit()

attach_exit_shortcuts(window, quit_all)
if relax_window is not None:
    attach_exit_shortcuts(relax_window, quit_all)

def start_audio() -> None:
    window.configure_sound()

def reveal_window() -> None:
    if MODE == 'Intensive' and FULLSCREEN:
        window.showFullScreen()
    else:
        window.show()
    if MODE == 'Intensive':
        window.raise_and_focus()
    QTimer.singleShot(100, start_audio)

if RELAX_MODE:
    window.hide()
    if relax_window is not None:
        relax_window.show()
    QTimer.singleShot(max(DELAY_SECONDS * 1000, 1200), lambda: (relax_window.close() if relax_window is not None else None, reveal_window()))
elif DELAY_SECONDS > 0:
    window.hide()
    QTimer.singleShot(DELAY_SECONDS * 1000, reveal_window)
else:
    reveal_window()
sys.exit(app.exec())
'''


def run_pyinstaller(
    script_path: Path,
    image_path: Path,
    sound_path: Path | None,
    icon_path: Path | None,
    output_path: Path,
    progress_callback,
    log_callback,
) -> Path:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("PyInstaller is not installed. Run: pip install pyinstaller") from exc

    output_path = output_path.resolve()
    dist_dir = output_path.parent
    work_dir = script_path.parent / "build"
    spec_dir = script_path.parent / "spec"
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    data_sep = ";" if os.name == "nt" else ":"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconsole",
        "--clean",
        "--name",
        output_path.stem,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--add-data",
        f"{image_path}{data_sep}media",
        "--hidden-import",
        "PyQt6.QtMultimedia",
        "--hidden-import",
        "PyQt6.QtGui",
    ]
    if sound_path:
        command.extend(["--add-data", f"{sound_path}{data_sep}media"])
    if icon_path:
        command.extend(["--icon", str(icon_path)])
    command.append(str(script_path))

    log_callback("Running command: " + " ".join(command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    progress = 24

    def stream(pipe, level: str) -> None:
        nonlocal progress
        if pipe is None:
            return
        for line in pipe:
            text = line.strip()
            if text:
                log_callback(text, level)
                progress = min(progress + 2, 94)
                progress_callback(progress)

    stdout_thread = threading.Thread(target=stream, args=(process.stdout, "info"), daemon=True)
    stderr_thread = threading.Thread(target=stream, args=(process.stderr, "error"), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    if return_code != 0:
        raise RuntimeError(f"PyInstaller build failed with exit code {return_code}.")

    built_path = dist_dir / (output_path.stem + (".exe" if os.name == "nt" else ""))
    if built_path.exists():
        return built_path
    fallback = dist_dir / output_path.stem
    if fallback.exists():
        return fallback
    raise RuntimeError("Build completed but the output executable was not found.")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(QIcon.fromTheme("applications-graphics"))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
