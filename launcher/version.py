"""Version and where updates are announced. Checking only happens when the user presses the button."""
VERSION = "0.7.17"
REPO = "ScrappyHub/legacy-player"
# Where opt-in problem reports are sent (an https address that runs server/report_receiver.py). Empty until it is set
# up: reports then stay on the player's computer. A player can also set their own under Settings.
REPORT_URL = ""
# A shared server (a computer with a public address running `python -m server.cli start --share`) that Legacy Player falls
# back to when a player's own connection cannot be reached from outside. A server code, e.g. "LP-....". Empty until the
# maintainers host one; see docs/HOSTING_PUBLIC_SERVER.md. Players can also set their own under Settings.
PUBLIC_SERVER_CODE = ""
