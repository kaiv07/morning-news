# morning-news

Kai's daily morning news dashboard, rebuilt each morning by a scheduled Claude task.

- `index.html` — latest edition
- `editions/YYYY-MM-DD.html` — the archive
- `data/history.json` — daily market numbers feeding the sparklines
- `scripts/build.py` — turns `content/<date>.json` into an edition (schema in its docstring)
