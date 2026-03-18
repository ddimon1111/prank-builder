# Prank Builder v4

Prank Builder v4 is a single-file PyQt6 desktop application with a Windows 11–style light UI for building predictable media-only prank executables.

## Install

```bash
pip install PyQt6 pyinstaller
```

## Run the builder

```bash
python prank_builder.py
```

## Features

- Light Windows-style UI with rounded cards, soft shadows, and subtle acrylic-inspired transparency.
- Tab-based navigation: **Files**, **Settings**, **Build**, **Logs**, and **Help**.
- Drag and drop for image/GIF, audio, and icon files with automatic routing.
- Separate preview window for still images and animated GIFs, with optional sound playback.
- Payload mode selector: **Normal**, **Light**, and **Intensive**.
- Safe exit methods in the payload: **INSERT** and **ALT+F3**, with optional **ESC**.
- Project save/load via JSON.
- Real-time PyInstaller logs and build progress.
- Topmost control, improved drag-and-drop handling, and clearer build/error reporting.

## Build flow

1. Select an image or GIF.
2. Optionally add audio and an icon.
3. Choose the payload mode and settings.
4. Optionally save or load the project JSON.
5. Click **Build EXE** and choose an output path.
6. The app generates a temporary payload script, bundles the selected media, runs PyInstaller with `--onefile` and `--noconsole`, and cleans up temporary files.
7. The built executable is **not** run automatically.

## Safety

- No hidden execution.
- No persistence.
- No system modification.
- No blocking of Alt+F4 or OS-level shortcuts.
- The generated EXE always includes safe exit methods.
