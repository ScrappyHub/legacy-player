"""A small, plain word filter for names and messages.

It is used in two places, each with its own switch:
  * Legacy Player hides filtered words in what a player sees (Settings > Friends > Filter bad language; on by default).
  * The friends service can refuse messages and names that contain them (the moderator console; off by default).

It matches whole words after undoing the usual disguises (l33t letters, s.p.a.c.e.d letters, repeated letters), so
"shit" and "$h1iiit" are caught but "Scunthorpe" or "class" are not. The built-in list is short and covers common
profanity; moderators add their own words (including slurs) in the console, and a player can add words in Settings.
It is a helper, not a guarantee: reporting and blocking are the real tools.
"""
from __future__ import annotations

import re

BASE_WORDS = frozenset({
    "fuck", "fucker", "fucking", "fucked", "motherfucker", "shit", "shitty", "bullshit", "bitch", "bitches", "bastard",
    "cunt", "dick", "dickhead", "cock", "pussy", "asshole", "arsehole", "twat", "wanker", "prick", "slut", "whore",
    "piss", "pissed", "douche", "douchebag", "jackass", "dumbass", "retard", "retarded", "kys",
})
_LEET = str.maketrans({"0": "o", "1": "i", "!": "i", "|": "i", "3": "e", "4": "a", "@": "a", "5": "s", "$": "s", "7": "t", "+": "t", "8": "b", "9": "g"})
_TOKEN = re.compile(r"[\w@$!|+]+(?:[\s.\-_*]{1}[\w@$!|+])*", re.UNICODE)


def _norm(word: str) -> str:
    w = word.lower().translate(_LEET)
    w = re.sub(r"[^a-z]", "", w)
    return re.sub(r"(.)\1{2,}", r"\1", w)          # "shiiiit" -> "shit"


def _variants(word: str) -> set[str]:
    w = _norm(word)
    out = {w, re.sub(r"(.)\1+", r"\1", w)}          # also with every double letter folded ("asshole" -> "ashole")
    return {v for v in out if v}


def _wordset(extra) -> set[str]:
    words = set()
    for w in list(BASE_WORDS) + [str(x) for x in (extra or [])]:
        words |= _variants(w)
    return words


def _spans(text: str):
    """Pieces of text that could be one word, including s.p.a.c.e.d or s p a c e d letters."""
    for m in re.finditer(r"[^\s]+", text):
        yield m.start(), m.end(), m.group(0)
    # single letters separated by spaces or dots: "f u c k", "s.h.i.t"
    for m in re.finditer(r"(?<![\w])(?:[\w@$!|+][\s.\-_*]){2,}[\w@$!|+](?![\w])", text):
        yield m.start(), m.end(), m.group(0)


def _bad(piece: str, words: set[str]) -> bool:
    core = re.sub(r"^[^\w@$!|+]+|[^\w@$!|+]+$", "", piece)
    if not core:
        return False
    trimmed = re.sub(r"[!?.,;:]+$", "", core)             # "ASSHOLE!" is the word plus punctuation, not a leet "i"
    return bool((_variants(core) | _variants(trimmed or core)) & words)


def find(text: str, extra=None) -> list[str]:
    """The words in `text` that the filter would hide."""
    words = _wordset(extra)
    return [piece for _, _, piece in _spans(str(text or "")) if _bad(piece, words)]


def has_bad(text: str, extra=None) -> bool:
    return bool(find(text, extra))


def mask(text: str, extra=None) -> str:
    """The same text with each filtered word replaced by asterisks of the same length."""
    text = str(text or "")
    words = _wordset(extra)
    hits = sorted(((a, b) for a, b, piece in _spans(text) if _bad(piece, words)), key=lambda t: (t[0], -t[1]))
    out, last = [], 0
    for a, b in hits:
        if a < last:
            continue
        core = re.match(r"^([^\w@$!|+]*)(.*?)([^\w@$!|+]*)$", text[a:b], re.S)
        lead, mid, tail = core.groups() if core else ("", text[a:b], "")
        out.append(text[last:a] + lead + "*" * len(mid) + tail)
        last = b
    out.append(text[last:])
    return "".join(out)


def clean_words(raw) -> list[str]:
    """A word list typed by a person: one per line or comma separated, letters only after normalising, at most 500."""
    items = re.split(r"[\n,]+", str(raw or "")) if not isinstance(raw, (list, tuple)) else list(raw)
    out = []
    for w in items:
        n = _norm(str(w).strip())
        if 2 <= len(n) <= 40 and n not in out:
            out.append(n)
    return out[:500]
