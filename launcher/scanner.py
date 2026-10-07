"""Read-only library scanner. It lists and stats files; it never opens, copies,
moves, hashes or modifies game files."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from .consoles import (
    AMBIGUOUS_EXTENSIONS,
    console_for_extension,
    console_for_folder_name,
)

DEFAULT_EXCLUDES = ("Emulators", "ZZZ-*", "saves", "Saves", "BIOS", "bios")
ARCHIVES = {".zip", ".7z", ".rar"}
_TAG = re.compile(r"\s*[\(\[]([^\)\]]*)[\)\]]")
_REGIONS = ("USA", "Europe", "Japan", "World", "Brazil", "Canada", "Korea", "Asia", "Australia", "Germany", "France", "Spain", "Italy")


@dataclass
class Game:
    id: str
    console: str
    title: str
    sort_title: str
    region: str
    tags: list[str]
    path: str
    root: str
    size: int
    extension: str
    is_archive: bool
    compat_id: str      # same game on two players' machines => same compat_id

    def as_dict(self) -> dict:
        return asdict(self)


def clean_title(stem: str) -> tuple[str, str, list[str]]:
    """Return (display title, region, other tags) from a No-Intro style filename."""
    stem = stem.replace("_", " ")
    tags = [t.strip() for t in _TAG.findall(stem)]
    title = _TAG.sub("", stem).strip(" -")
    match = re.match(r"^(.*), (The|A|An)$", title)
    if match:
        title = f"{match.group(2)} {match.group(1)}"
    region = ""
    others = []
    for tag in tags:
        parts = [p.strip() for p in tag.split(",")]
        if not region and any(p in _REGIONS for p in parts):
            region = ", ".join(p for p in parts if p in _REGIONS)
        else:
            others.append(tag)
    return title or stem, region, others


def _sort_title(title: str) -> str:
    lowered = title.lower()
    for article in ("the ", "a ", "an "):
        if lowered.startswith(article):
            return lowered[len(article):]
    return lowered


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


SHARED_EXTENSIONS = {".cso", ".zso", ".chd", ".iso", ".bin"}


def _classify(path: Path, root: Path):
    extension = path.suffix.lower()
    console = console_for_extension(extension)
    if console is not None:
        # A folder name wins over an extension two consoles share (.cso is PSP and PS2).
        if extension in SHARED_EXTENSIONS:
            for part in reversed(path.relative_to(root).parts[:-1]):
                by_folder = console_for_folder_name(part)
                if by_folder is not None:
                    return by_folder
        return console
    if extension in AMBIGUOUS_EXTENSIONS:
        for part in reversed(path.relative_to(root).parts[:-1]):
            console = console_for_folder_name(part)
            if console is not None:
                return console
    return None


def scan(roots: list[Path], excludes: tuple[str, ...] = DEFAULT_EXCLUDES) -> dict:
    games: dict[str, Game] = {}
    seen_compat: set[str] = set()
    skipped = {"unrecognized": 0, "duplicates": 0}
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                d for d in dirnames if not any(fnmatch.fnmatch(d, pattern) for pattern in excludes)
            )
            stems = {Path(f).stem.lower() for f in filenames if f.lower().endswith(".cue")}
            for name in sorted(filenames):
                path = Path(dirpath) / name
                extension = path.suffix.lower()
                if extension == ".bin" and path.stem.lower() in stems:
                    continue  # the .cue sheet represents this disc
                console = _classify(path, root)
                if console is None:
                    skipped["unrecognized"] += 1
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                title, region, tags = clean_title(path.stem)
                relative = path.relative_to(root).as_posix()
                game_id = hashlib.sha1(f"{root.name}/{relative}".encode()).hexdigest()[:16]
                compat = f"{console.id}:{_slug(title)}:{_slug(region)}"
                game = Game(
                    id=game_id, console=console.id, title=title, sort_title=_sort_title(title),
                    region=region, tags=tags, path=str(path), root=str(root), size=size,
                    extension=extension, is_archive=extension in ARCHIVES, compat_id=compat,
                )
                if compat in seen_compat and game_id not in games:
                    skipped["duplicates"] += 1
                seen_compat.add(compat)
                games[game_id] = game
    return {"games": list(games.values()), "skipped": skipped}
