# Third-party software

Legacy Player's own code is MIT-licensed (see `LICENSE`).

- The Windows build bundles **Python** (PSF License) with its standard library, including Tcl/Tk, and **PyInstaller**'s
  bootloader (GPL-2.0 with the PyInstaller bootloader exception, which allows any licence for the built program).
- **Emulators are not bundled.** The app finds emulators you have, or downloads them from their own projects on your
  request. Each keeps its own licence (listed in `launcher/engines.py`). Engines whose licence forbids redistribution are
  never packaged or re-hosted by this project.
- **No games, BIOS files or other copyrighted game data** are included or distributed.
