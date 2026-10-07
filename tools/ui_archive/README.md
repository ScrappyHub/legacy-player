# UI source archive (historical)

`launcher/ui/index.html` is the **source of truth** for the interface. Edit it directly.

Until October 2026 the page was produced by a small build script from the pieces in this folder
(`style.css`, `core.js`, `views*.js`, `patches4.py`, `assemble.py`, starting from `old_index.html`).
They are kept here so the history of how the page was put together is not lost, and so a future
split of the page into real modules has its pieces. Running `assemble.py` from this folder rebuilds an
`index_new.html` that matches the page as of that date; do not copy it over `launcher/ui/index.html`
without diffing, because the page has been edited since.
