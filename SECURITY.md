# Security

Report a vulnerability privately through GitHub: Security > "Report a vulnerability" on
https://github.com/Alpallyoop/legacy-player, rather than in a public issue. Please include the version
(see `launcher/version.py`) and the steps to reproduce.

What is protected and how: see `docs/THREAT_MODEL_v1.md`. In short, servers use encrypted connections with a pinned
certificate, rooms are joined by expiring invite codes with per-address lockouts, and problem reports are opt-in and
scrubbed. Releases list SHA-256 hashes and carry a GitHub build attestation.
