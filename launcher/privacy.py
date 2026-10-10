"""What Legacy Player sends over the network, each piece on its own switch, in plain words.

Legacy Player collects nothing: there is no analytics, no tracking, no account and nothing is sold or shared. The only
traffic that leaves this computer is a feature the player switched on, and each feature below says exactly where it
goes and what it carries. The doctor's check-up lists them, and anything that is on without the player having said
yes to it (an old settings file, a default from an earlier version, someone else editing the file) is flagged until
the player either keeps it or turns it off.

A confirmation is tied to the exact setting values it was given for, so changing the friends service address or the
report address asks again."""
from __future__ import annotations

NEVER = ("Never sent by any of these: your Windows user name or computer name, your files or folder names, a list of "
         "your games, your IP address (except where a feature above says so), or anything for advertising or tracking. "
         "Legacy Player has no analytics and does not collect data.")


def items(settings: dict, data: dict) -> list[dict]:
    """Every feature that can talk to something outside this computer. `on` is whether it can do so right now;
    `signature` is what a confirmation is tied to."""
    s = settings
    friends_addr = str(s.get("friends_server") or "").strip()
    report_mode = s.get("error_reports", "off")
    report_addr = str(s.get("report_url") or "").strip()
    remote_server = str(s.get("server_host") or "127.0.0.1") != "127.0.0.1"
    out = [
        {"id": "downloads", "title": "Internet downloads", "setting": "allow_internet", "on": bool(s.get("allow_internet")),
         "signature": "on" if s.get("allow_internet") else "",
         "what": "Lets you fetch emulators, RetroArch cores, box art and Legacy Player updates. Each one still waits for you to press its button.",
         "contacts": ["api.github.com and GitHub's file hosts (emulators, updates)", "buildbot.libretro.com (RetroArch and its cores)",
                      "thumbnails.libretro.com (box art)"],
         "sends": "Which file it wants. For box art, the game's name and console, so the picture library can find it.",
         "off_means": "Nothing is ever downloaded; you install emulators yourself and pick pictures by hand."},
        {"id": "game_info", "title": "Look up game details", "setting": "allow_game_info", "on": bool(s.get("allow_game_info")),
         "signature": "on" if s.get("allow_game_info") else "",
         "what": "On a game's card, 'Look it up online' fills in the description, release date, makers and player count.",
         "contacts": ["en.wikipedia.org", "www.wikidata.org"],
         "sends": "That one game's name and its console, only when you press the button for that game. The answer is kept on this computer.",
         "off_means": "Game cards show what the file name and your library say, and anything you type yourself."},
        {"id": "friends", "title": "Friends service", "setting": "friends_server", "on": bool(friends_addr), "signature": friends_addr,
         "what": "Friend codes, who is online, one-click invites into a room and short messages, through a separate service you chose.",
         "contacts": [friends_addr or "(no address set)"],
         "sends": "The name you show other players, your friend code and friends list, whether the app is open, the game you are playing or "
                  "hosting" + (", your room's invite and server code (to friends only)" if s.get("friends_share_room", True) else "")
                  + ", the messages you write, and any report you make (to the people who run that service). Never your address.",
         "off_means": "No Friends page; you share server and invite codes yourself, as before."},
        {"id": "reports", "title": "Problem reports sent automatically", "setting": "error_reports", "on": report_mode == "auto",
         "signature": f"{report_mode}|{report_addr}" if report_mode == "auto" else "",
         "what": "When something breaks, a cleaned-up report goes to the people who make Legacy Player without asking each time.",
         "contacts": [report_addr or "the address built into this copy (if any)"],
         "sends": "The error, the app and Windows version, the names of your last few actions. Names, addresses, paths and codes are removed first.",
         "off_means": "Reports are only sent when you approve each one, or when you write one yourself (Home > See an issue or a problem?)."},
        {"id": "direct", "title": "Direct connections in matches", "setting": "allow_direct_connections", "on": bool(s.get("allow_direct_connections")),
         "signature": "on" if s.get("allow_direct_connections") else "",
         "what": "Matches try to connect computer to computer before using the server relay (faster; Dolphin needs it).",
         "contacts": ["the other players in your room"],
         "sends": "Your IP address, to the players you are playing with. Game traffic goes straight between you.",
         "off_means": "Matches always go through the server relay, so nobody learns your address. Dolphin online play cannot start."},
        {"id": "private_link", "title": "Tailscale private link for Dolphin", "setting": "use_private_link", "on": bool(s.get("use_private_link")),
         "signature": "on" if s.get("use_private_link") else "",
         "what": "Plays Dolphin matches over Tailscale when everyone has it.",
         "contacts": ["the other players in your room, through Tailscale"],
         "sends": "Your Tailscale address (not your home address) to the players in your room.",
         "off_means": "Dolphin uses its normal connection."},
        {"id": "network_test", "title": "Network test when the app opens", "setting": "auto_network_test", "on": bool(s.get("auto_network_test", True)),
         "signature": "on" if s.get("auto_network_test", True) else "", "quiet": True,
         "what": "Checks whether this computer should host or join, so Server Info already knows.",
         "contacts": ["this computer", "the multiplayer server you chose" + (" (a friend's)" if remote_server else " (your own, on this computer)")],
         "sends": "Small timing messages to that server. Nothing about you.",
         "off_means": "The test runs only when you press Test my network."},
    ]
    seen = data.get("privacy_ok") or {}
    for it in out:
        it["confirmed"] = bool(it["on"]) and seen.get(it["id"]) == it["signature"]
        it["needs_look"] = bool(it["on"]) and not it["confirmed"] and not it.get("quiet")
    return out


def confirm(data: dict, item_id: str, settings: dict) -> bool:
    for it in items(settings, data):
        if it["id"] == item_id and it["on"]:
            data.setdefault("privacy_ok", {})[item_id] = it["signature"]
            return True
    return False


OFF_VALUES = {"allow_internet": False, "allow_game_info": False, "friends_server": "", "error_reports": "ask",
              "allow_direct_connections": False, "use_private_link": False, "auto_network_test": False}
