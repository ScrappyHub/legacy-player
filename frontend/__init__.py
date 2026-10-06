"""Legacy Player's own libretro frontend (proposal 0003): load emulation cores in-process.

A libretro core is a shared library with a small C API. Loading it here means the shell owns
the window, input, save states and netplay hooks for every core, which is the path to "one
program, every console". `core.py` is the loader; `window.py` is a plain-Tk viewer used to
prove it. A real display/audio layer (SDL) is the next step.
"""
