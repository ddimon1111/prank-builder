#!/usr/bin/env python3
"""Prank Builder - professional PyQt6 utility for building predictable media prank EXEs."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QIcon, QMovie, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

APP_TITLE = "Prank Builder"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
SOUND_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
ICON_EXTENSIONS = {".ico"}


class LogPanel(QPlainTextEdit):
    """Small HTML-enabled logger using extra selections via simple appended rich text."""

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumBlockCount(500)
        self.setStyleSheet(
            """
            QPlainTextEdit {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 14px;
                padding: 12px;
                selection-background-color: #2563eb;
                font-family: Consolas, 'SFMono-Regular', monospace;
                font-size: 12px;
            }
            """
        )

    def append_colored(self, message: str, level: str = "info") -> None:
        colors = {
            "info": "#cbd5e1",
            "success": "#4ade80",
            "warning": "#fbbf24",
            "error": "#f87171",
        }
        prefix = {
            "info": "[INFO]",
            "success": "[OK]",
            "warning": "[WARN]",
            "error": "[ERROR]",
        }.get(level, "[INFO]")
        self.appendPlainText(f"{prefix} {message}")
        block = self.document().lastBlock()
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        fmt = cursor.blockCharFormat()
        fmt.setForeground(QColor(colors.get(level, colors["info"])))
        cursor.select(cursor.SelectionType.BlockUnderCursor)
        cursor.setBlockCharFormat(fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()


class FileDropFrame(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropFrame")
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
            self.file_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()
        else:
            event.ignore()


class PreviewWindow(QWidget):
    def __init__(self, image_path: str, sound_path: str | None = None, title: str = "Preview") -> None:
        super().__init__()
        self.image_path = image_path
        self.sound_path = sound_path or ""
        self.movie: QMovie | None = None
        self.player: QMediaPlayer | None = None
        self.audio_output: QAudioOutput | None = None
        self._pixmap: QPixmap | None = None

        self.setWindowTitle(title)
        self.setMinimumSize(720, 480)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(
            """
            QWidget {
                background: #020617;
                color: #e2e8f0;
            }
            QLabel {
                color: #cbd5e1;
            }
            QPushButton {
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_label = QLabel("Media Preview")
        title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(title_label)
        header.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        layout.addLayout(header)

        self.media_label = QLabel("Preview unavailable")
        self.media_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.media_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.media_label.setStyleSheet(
            "border: 1px solid #334155; border-radius: 16px; background: #0f172a;"
        )
        layout.addWidget(self.media_label, 1)

        self.load_media()
        self.play_sound()

    def load_media(self) -> None:
        suffix = Path(self.image_path).suffix.lower()
        if suffix == ".gif":
            self.movie = QMovie(self.image_path)
            self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
            self.media_label.setMovie(self.movie)
            self.movie.start()
            self.rescale_movie()
            return

        pixmap = QPixmap(self.image_path)
        if pixmap.isNull():
            self.media_label.setText("Could not load preview.")
            return
        self._pixmap = pixmap
        self.update_pixmap()

    def play_sound(self) -> None:
        if not self.sound_path:
            return
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(QUrl.fromLocalFile(str(Path(self.sound_path).resolve())))
        self.player.play()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.update_pixmap()
        self.rescale_movie()

    def update_pixmap(self) -> None:
        if not self._pixmap:
            return
        scaled = self._pixmap.scaled(
            self.media_label.size() - QSize(24, 24),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.media_label.setPixmap(scaled)

    def rescale_movie(self) -> None:
        if not self.movie:
            return
        target = self.media_label.size() - QSize(24, 24)
        self.movie.setScaledSize(self.movie.currentPixmap().size().scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
        ))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.player:
            self.player.stop()
        if self.movie:
            self.movie.stop()
        super().closeEvent(event)


class BuilderSignals(QObject):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int)
    success = pyqtSignal(str)
    failure = pyqtSignal(str)
    finished = pyqtSignal()


class Builder(QRunnable):
    def __init__(
        self,
        image_path: str,
        sound_path: str,
        icon_path: str,
        settings: dict[str, object],
        output_path: str,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.sound_path = sound_path
        self.icon_path = icon_path
        self.settings = settings
        self.output_path = output_path
        self.signals = BuilderSignals()

    def emit_log(self, message: str, level: str = "info") -> None:
        self.signals.log.emit(message, level)

    def run(self) -> None:
        temp_dir: str | None = None
        try:
            self.signals.progress.emit(5)
            self.emit_log("Validating configuration before build starts.")
            valid, error = validate_inputs(self.image_path, self.sound_path, self.icon_path)
            if not valid:
                raise ValueError(error)

            self.signals.progress.emit(10)
            temp_dir = tempfile.mkdtemp(prefix="prank_builder_")
            temp_path = Path(temp_dir)
            self.emit_log(f"Created temporary workspace: {temp_path}")

            media_dir = temp_path / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            image_target = media_dir / Path(self.image_path).name
            shutil.copy2(self.image_path, image_target)
            self.emit_log(f"Bundled image/GIF: {image_target.name}")

            sound_target = ""
            if self.sound_path:
                sound_file = media_dir / Path(self.sound_path).name
                shutil.copy2(self.sound_path, sound_file)
                sound_target = sound_file.name
                self.emit_log(f"Bundled sound: {sound_target}")

            script_path = temp_path / "payload.py"
            self.signals.progress.emit(20)
            script_path.write_text(
                generate_payload(
                    image_name=image_target.name,
                    sound_name=sound_target,
                    fullscreen=bool(self.settings["fullscreen"]),
                    loop_sound=bool(self.settings["loop_sound"]),
                    delay_seconds=int(self.settings["delay"]),
                    window_title=str(self.settings["title"] or "Prank Builder"),
                ),
                encoding="utf-8",
            )
            self.emit_log("Generated payload script dynamically.")

            self.signals.progress.emit(35)
            self.emit_log("Starting PyInstaller packaging step.")
            result_path = run_pyinstaller(
                script_path=script_path,
                image_path=image_target,
                sound_path=media_dir / sound_target if sound_target else None,
                icon_path=Path(self.icon_path) if self.icon_path else None,
                output_path=Path(self.output_path),
                log_callback=self.emit_log,
                progress_callback=self.signals.progress.emit,
            )

            self.signals.progress.emit(100)
            self.emit_log(f"Build complete: {result_path}", "success")
            self.signals.success.emit(str(result_path))
        except Exception as exc:  # noqa: BLE001 - user-facing build errors
            self.emit_log(str(exc), "error")
            self.signals.failure.emit(str(exc))
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.emit_log("Temporary workspace cleaned up.")
            self.signals.finished.emit()


def validate_inputs(image_path: str, sound_path: str, icon_path: str) -> tuple[bool, str]:
    if not image_path:
        return False, "An image or GIF is required before building."

    image_suffix = Path(image_path).suffix.lower()
    if image_suffix not in IMAGE_EXTENSIONS:
        return False, f"Unsupported image/GIF format: {image_suffix or 'missing extension'}"
    if not Path(image_path).is_file():
        return False, "Selected image/GIF file does not exist."

    if sound_path:
        sound_suffix = Path(sound_path).suffix.lower()
        if sound_suffix not in SOUND_EXTENSIONS:
            return False, f"Unsupported sound format: {sound_suffix}"
        if not Path(sound_path).is_file():
            return False, "Selected sound file does not exist."

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
    fullscreen: bool,
    loop_sound: bool,
    delay_seconds: int,
    window_title: str,
) -> str:
    encoded = {
        "image": base64.b64encode(image_name.encode("utf-8")).decode("ascii"),
        "sound": base64.b64encode(sound_name.encode("utf-8")).decode("ascii"),
        "title": base64.b64encode(window_title.encode("utf-8")).decode("ascii"),
    }
    return f'''from __future__ import annotations
import base64
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize, QUrl
from PyQt6.QtGui import QGuiApplication, QKeySequence, QMovie, QPixmap, QShortcut
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

IMAGE_NAME = base64.b64decode("{encoded["image"]}").decode("utf-8")
SOUND_NAME = base64.b64decode("{encoded["sound"]}").decode("utf-8")
WINDOW_TITLE = base64.b64decode("{encoded["title"]}").decode("utf-8")
FULLSCREEN = {fullscreen!r}
LOOP_SOUND = {loop_sound!r}
DELAY_SECONDS = {delay_seconds}


class PayloadWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setStyleSheet("background: black;")
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

        self.audio_output = None
        self.player = None
        self.movie = None
        self.pixmap = None

        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "media"
        self.image_path = base_dir / IMAGE_NAME
        self.sound_path = base_dir / SOUND_NAME if SOUND_NAME else None

        self.load_media()
        self.configure_sound()
        QShortcut(QKeySequence("Esc"), self, activated=self.close)

        self.resize(960, 640)
        geo = self.frameGeometry()
        center = QGuiApplication.primaryScreen().availableGeometry().center()
        geo.moveCenter(center)
        self.move(geo.topLeft())

    def load_media(self) -> None:
        if self.image_path.suffix.lower() == ".gif":
            self.movie = QMovie(str(self.image_path))
            self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
            self.label.setMovie(self.movie)
            self.movie.start()
            self.rescale_movie()
            return

        self.pixmap = QPixmap(str(self.image_path))
        self.render_pixmap()

    def configure_sound(self) -> None:
        if not self.sound_path:
            return
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(QUrl.fromLocalFile(str(self.sound_path.resolve())))
        if LOOP_SOUND:
            self.player.mediaStatusChanged.connect(self.restart_if_finished)
        self.player.play()

    def restart_if_finished(self, status) -> None:
        if LOOP_SOUND and self.player and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.render_pixmap()
        self.rescale_movie()

    def render_pixmap(self) -> None:
        if not self.pixmap:
            return
        scaled = self.pixmap.scaled(
            self.size() - QSize(20, 20),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.label.setPixmap(scaled)

    def rescale_movie(self) -> None:
        if not self.movie:
            return
        target = self.size() - QSize(20, 20)
        self.movie.setScaledSize(self.movie.currentPixmap().size().scaled(target, Qt.AspectRatioMode.KeepAspectRatio))


app = QApplication(sys.argv)
window = PayloadWindow()
if DELAY_SECONDS > 0:
    window.hide()
    QTimer.singleShot(DELAY_SECONDS * 1000, lambda: window.showFullScreen() if FULLSCREEN else window.show())
    if not FULLSCREEN:
        QTimer.singleShot(DELAY_SECONDS * 1000, window.raise_)
else:
    if FULLSCREEN:
        window.showFullScreen()
    else:
        window.show()
sys.exit(app.exec())
'''


def run_pyinstaller(
    script_path: Path,
    image_path: Path,
    sound_path: Path | None,
    icon_path: Path | None,
    output_path: Path,
    log_callback,
    progress_callback,
) -> Path:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PyInstaller is not installed. Install it with: pip install pyinstaller"
        ) from exc

    output_path = output_path.resolve()
    dist_dir = output_path.parent
    spec_dir = script_path.parent / "spec"
    work_dir = script_path.parent / "build"
    dist_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

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
    ]

    if sound_path:
        command.extend(["--add-data", f"{sound_path}{data_sep}media"])
    if icon_path:
        command.extend(["--icon", str(icon_path)])

    hidden_imports = [
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtGui",
    ]
    for item in hidden_imports:
        command.extend(["--hidden-import", item])
    command.append(str(script_path))

    log_callback("Running command: " + " ".join(command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    progress_value = 40
    for line in process.stdout:
        clean = line.strip()
        if clean:
            log_callback(clean)
            progress_value = min(progress_value + 2, 92)
            progress_callback(progress_value)

    return_code = process.wait()
    built_path = dist_dir / (output_path.stem + (".exe" if os.name == "nt" else ""))
    if return_code != 0:
        raise RuntimeError(f"PyInstaller build failed with exit code {return_code}.")
    if not built_path.exists():
        fallback = dist_dir / output_path.stem
        if fallback.exists():
            return fallback
        raise RuntimeError("Build finished but the output executable could not be found.")
    return built_path


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.preview_window: PreviewWindow | None = None
        self.thread_pool = QThreadPool.globalInstance()

        self.image_path = ""
        self.sound_path = ""
        self.icon_path = ""

        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 760)
        self.setAcceptDrops(True)
        self.setStyleSheet(self.build_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(28, 28, 28, 28)
        outer_layout.setSpacing(18)

        hero = self.build_hero()
        outer_layout.addWidget(hero)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(18)
        outer_layout.addLayout(content_layout, 1)

        left_panel = QVBoxLayout()
        left_panel.setSpacing(18)
        content_layout.addLayout(left_panel, 3)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(18)
        content_layout.addLayout(right_panel, 2)

        left_panel.addWidget(self.build_file_section())
        left_panel.addWidget(self.build_settings_section())
        right_panel.addWidget(self.build_logs_section(), 1)

        self.log("Ready. Select an image or GIF to begin.", "success")

    def build_stylesheet(self) -> str:
        return """
        QMainWindow, QWidget {
            background: #020617;
            color: #e2e8f0;
            font-family: 'Segoe UI', Inter, Arial, sans-serif;
            font-size: 13px;
        }
        QGroupBox {
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 18px;
            margin-top: 14px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 16px;
            padding: 2px 8px;
            color: #f8fafc;
        }
        QLineEdit, QSpinBox {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 10px 12px;
            min-height: 22px;
        }
        QLineEdit[readOnly="true"] {
            color: #cbd5e1;
        }
        QPushButton {
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 12px;
            padding: 11px 16px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #1d4ed8;
        }
        QPushButton:disabled {
            background: #475569;
            color: #cbd5e1;
        }
        QCheckBox {
            spacing: 10px;
        }
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
        }
        QCheckBox::indicator:unchecked {
            border: 1px solid #64748b;
            border-radius: 6px;
            background: #0f172a;
        }
        QCheckBox::indicator:checked {
            border: 1px solid #2563eb;
            border-radius: 6px;
            background: #2563eb;
        }
        QProgressBar {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 10px;
            min-height: 18px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #22c55e;
            border-radius: 9px;
        }
        QFrame#dropFrame {
            background: #111827;
            border: 1px dashed #475569;
            border-radius: 16px;
        }
        QFrame#dropFrame[dragging="true"] {
            border: 1px dashed #38bdf8;
            background: #082f49;
        }
        QLabel#dropTitle {
            font-size: 15px;
            font-weight: 700;
            color: #f8fafc;
        }
        QLabel#dropSubtitle {
            color: #94a3b8;
        }
        QLabel#heroTitle {
            font-size: 28px;
            font-weight: 700;
        }
        QLabel#heroSubtitle {
            color: #94a3b8;
            font-size: 14px;
        }
        """

    def build_hero(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 22px;")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(15, 23, 42, 180))
        frame.setGraphicsEffect(shadow)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        title = QLabel(APP_TITLE)
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Create a predictable media-only prank executable that shows an image or GIF and optionally plays audio."
        )
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def build_file_section(self) -> QGroupBox:
        group = QGroupBox("File Inputs")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(14)

        drop = FileDropFrame("Drag & Drop Media", "Drop an image or GIF here to populate the required input.")
        drop.file_dropped.connect(self.handle_dropped_file)
        layout.addWidget(drop)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        layout.addLayout(grid)

        self.image_field = self.make_readonly_field("Image or GIF")
        self.sound_field = self.make_readonly_field("Sound")
        self.icon_field = self.make_readonly_field("Icon")

        image_button = QPushButton("Select Image / GIF")
        image_button.clicked.connect(self.select_image)
        sound_button = QPushButton("Select Sound (Optional)")
        sound_button.clicked.connect(self.select_sound)
        icon_button = QPushButton("Select Icon (Optional)")
        icon_button.clicked.connect(self.select_icon)

        grid.addWidget(QLabel("Required media"), 0, 0)
        grid.addWidget(self.image_field, 0, 1)
        grid.addWidget(image_button, 0, 2)

        grid.addWidget(QLabel("Optional sound"), 1, 0)
        grid.addWidget(self.sound_field, 1, 1)
        grid.addWidget(sound_button, 1, 2)

        grid.addWidget(QLabel("Optional icon"), 2, 0)
        grid.addWidget(self.icon_field, 2, 1)
        grid.addWidget(icon_button, 2, 2)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self.preview_button = QPushButton("Preview")
        self.preview_button.clicked.connect(self.preview_media)
        self.build_button = QPushButton("Build EXE")
        self.build_button.clicked.connect(self.start_build)
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.build_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return group

    def build_settings_section(self) -> QGroupBox:
        group = QGroupBox("Build Settings")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        self.fullscreen_check = QCheckBox("Fullscreen mode")
        self.loop_sound_check = QCheckBox("Loop sound")
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 60)
        self.delay_spin.setSuffix(" sec")
        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Optional window title")

        form.addRow("Display", self.fullscreen_check)
        form.addRow("Audio", self.loop_sound_check)
        form.addRow("Delay before start", self.delay_spin)
        form.addRow("Window title", self.title_field)
        layout.addLayout(form)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        return group

    def build_logs_section(self) -> QGroupBox:
        group = QGroupBox("Logs")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(14)
        self.log_panel = LogPanel()
        layout.addWidget(self.log_panel)
        return group

    def make_readonly_field(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setReadOnly(True)
        field.setPlaceholderText(placeholder)
        return field

    def log(self, message: str, level: str = "info") -> None:
        self.log_panel.append_colored(message, level)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.handle_dropped_file(urls[0].toLocalFile())
            event.acceptProposedAction()

    def handle_dropped_file(self, path: str) -> None:
        suffix = Path(path).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            self.image_path = path
            self.image_field.setText(path)
            self.log(f"Loaded image/GIF via drag and drop: {path}", "success")
        elif suffix in SOUND_EXTENSIONS:
            self.sound_path = path
            self.sound_field.setText(path)
            self.log(f"Loaded sound via drag and drop: {path}", "success")
        elif suffix in ICON_EXTENSIONS:
            self.icon_path = path
            self.icon_field.setText(path)
            self.log(f"Loaded icon via drag and drop: {path}", "success")
        else:
            self.log("Unsupported dropped file type.", "warning")

    def select_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image or GIF",
            "",
            "Images and GIFs (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if path:
            self.image_path = path
            self.image_field.setText(path)
            self.log(f"Selected image/GIF: {path}", "success")

    def select_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sound",
            "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.m4a)",
        )
        if path:
            self.sound_path = path
            self.sound_field.setText(path)
            self.log(f"Selected sound: {path}", "success")

    def select_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            "",
            "Icon Files (*.ico)",
        )
        if path:
            self.icon_path = path
            self.icon_field.setText(path)
            self.log(f"Selected icon: {path}", "success")

    def preview_media(self) -> None:
        valid, error = validate_inputs(self.image_path, self.sound_path, self.icon_path)
        if not valid:
            self.log(error, "error")
            QMessageBox.warning(self, APP_TITLE, error)
            return

        if self.preview_window is not None:
            self.preview_window.close()
        self.preview_window = PreviewWindow(
            self.image_path,
            self.sound_path,
            self.title_field.text().strip() or "Preview",
        )
        self.preview_window.show()
        self.preview_window.raise_()
        self.log("Opened preview window.", "success")

    def start_build(self) -> None:
        valid, error = validate_inputs(self.image_path, self.sound_path, self.icon_path)
        if not valid:
            self.log(error, "error")
            QMessageBox.warning(self, APP_TITLE, error)
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save prank executable",
            str(Path.home() / "prank_output.exe"),
            "Executable (*.exe)",
        )
        if not save_path:
            self.log("Build cancelled by user.", "warning")
            return
        if not save_path.lower().endswith(".exe"):
            save_path += ".exe"

        settings = {
            "fullscreen": self.fullscreen_check.isChecked(),
            "loop_sound": self.loop_sound_check.isChecked() and bool(self.sound_path),
            "delay": self.delay_spin.value(),
            "title": self.title_field.text().strip(),
        }
        self.log(f"Starting build for output: {save_path}")
        self.progress_bar.setValue(0)
        self.build_button.setEnabled(False)
        self.preview_button.setEnabled(False)

        worker = Builder(
            image_path=self.image_path,
            sound_path=self.sound_path,
            icon_path=self.icon_path,
            settings=settings,
            output_path=save_path,
        )
        worker.signals.log.connect(self.log)
        worker.signals.progress.connect(self.progress_bar.setValue)
        worker.signals.success.connect(self.on_build_success)
        worker.signals.failure.connect(self.on_build_failure)
        worker.signals.finished.connect(self.on_build_finished)
        self.thread_pool.start(worker)

    def on_build_success(self, output_path: str) -> None:
        self.log(f"Executable created successfully at: {output_path}", "success")
        QMessageBox.information(
            self,
            APP_TITLE,
            f"Build completed successfully.\n\nOutput: {output_path}",
        )

    def on_build_failure(self, message: str) -> None:
        self.log(f"Build failed: {message}", "error")
        QMessageBox.critical(self, APP_TITLE, message)

    def on_build_finished(self) -> None:
        self.build_button.setEnabled(True)
        self.preview_button.setEnabled(True)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(QIcon.fromTheme("applications-multimedia"))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
