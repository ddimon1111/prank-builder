# Prank Builder

Prank Builder is a single-file PyQt6 desktop application for building a predictable media-only prank executable. The generated EXE only displays an image or animated GIF and can optionally play a sound file.

## Install

```bash
pip install PyQt6 pyinstaller
```

## Run the builder

```bash
python prank_builder.py
```

## How the build works

1. Select a required image or GIF.
2. Optionally select a sound file and icon.
3. Configure fullscreen mode, sound looping, delay, and an optional window title.
4. Click **Build EXE** and choose the destination executable path.
5. The app generates a temporary payload script, copies the selected media into a temp workspace, and runs PyInstaller with `--onefile` and `--noconsole`.
6. On success, the executable is written to the chosen output directory and the temp workspace is cleaned up.

## Safety notes

- No hidden execution.
- No persistence.
- No obfuscation.
- No system modifications.
- The generated executable only shows the selected media and optionally plays sound.
