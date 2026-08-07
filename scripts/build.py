#!/usr/bin/env python3
"""Build the morning-news site from a daily content JSON.

Usage: python3 scripts/build.py content/2026-08-08.json

Reads the content file, appends/replaces that date's numbers in data/history.json,
updates data/index.json, renders editions/<date>.html from template.html, and
refreshes index.html when the date is the newest edition.

Content schema (all text is treated as untrusted and HTML-escaped):
{
  "date": "2026-08-08",                       # ISO date of the edition (required)
  "headline": "…",                            # one serif line addressing Kai (required)
  "subline": "…",                             # one-sentence summary (required)
  "asof": "Pre-market · as of 6:45 AM ET · every figure links to its source below",
  "strip": [                                  # 5-7 stats
    {"label": "S&P 500", "value": "7,737", "delta": "+0.35%", "dir": "up"},
    ...                                       # dir: up | down | flat; delta must carry
  ],                                          # an explicit +/−/± sign or be "—"
  "history": {"spx": 7737.31, "y10": 4.63, "btc": 65144},   # raw numbers for sparklines
  "sections": [
    {"title": "Markets & economy", "items": [
      {"title": "≤10 words", "url": "https://…", "sentence": "one sentence, source in prose"},
      ...
    ]},
    ...
  ]
}
"""
import html
import json
import re
import sys
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPARK_SERIES = [
    ("spx", "S&P 500", lambda v: f"{v:,.0f}"),
    ("y10", "10-yr yield", lambda v: f"{v:.2f}%"),
    ("btc", "Bitcoin", lambda v: f"${v:,.0f}"),
]
SIGN_RE = re.compile(r"[+−±-]|—|—")


def esc(s):
    return html.escape(str(s), quote=True)


def die(msg):
    sys.exit(f"build.py: ERROR: {msg}")


def load_json(path, default):
    p = ROOT / path
    if p.exists():
        return json.loads(p.read_text())
    return default


def human_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    dt = _date(y, m, d)
    return f"{dt.strftime('%A')} · {dt.strftime('%B')} {d} {y}"


def build_strip(strip):
    if not 3 <= len(strip) <= 8:
        die("strip must have 3-8 stats")
    cells = []
    for s in strip:
        for k in ("label", "value", "delta", "dir"):
            if k not in s:
                die(f"strip stat missing '{k}': {s}")
        if s["dir"] not in ("up", "down", "flat"):
            die(f"strip dir must be up|down|flat: {s}")
        if not SIGN_RE.search(str(s["delta"])):
            die(f"strip delta needs an explicit sign (+/−) or —: {s}")
        cells.append(
            '      <div class="stat"><div class="label">%s</div>'
            '<div class="value">%s</div>'
            '<div class="delta %s">%s</div></div>'
            % (esc(s["label"]), esc(s["value"]), s["dir"], esc(s["delta"]))
        )
    return "\n".join(cells)


def build_sections(sections):
    if not sections:
        die("sections must not be empty")
    out = []
    for sec in sections:
        items = sec.get("items", [])
        if not items:
            continue
        li = []
        for it in items:
            title, sentence = esc(it.get("title", "")), esc(it.get("sentence", ""))
            url = str(it.get("url", ""))
            if not title or not sentence:
                die(f"item needs title and sentence: {it}")
            if url.startswith("https://"):
                head = f'<a class="item-title" href="{esc(url)}">{title}</a>'
            else:
                head = f'<span class="item-title">{title}</span>'
            li.append(
                f"        <li>\n          {head}\n"
                f'          <p class="item-body">{sentence}</p>\n        </li>'
            )
        out.append(
            "    <section>\n      <h2>%s</h2>\n      <ol class=\"items\">\n%s\n"
            "      </ol>\n    </section>" % (esc(sec.get("title", "")), "\n".join(li))
        )
    return "\n\n".join(out)


def build_sparks(history):
    """history: list of {date, spx?, y10?, btc?} sorted by date."""
    blocks = []
    for key, label, fmt in SPARK_SERIES:
        pts = [(h["date"], float(h[key])) for h in history if key in h and h[key] is not None]
        pts = pts[-30:]
        if not pts:
            continue
        latest = pts[-1][1]
        w, h_, pad = 200, 44, 4
        vals = [v for _, v in pts]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        if len(pts) == 1:
            body = (
                f'<circle cx="{w/2}" cy="{h_/2}" r="3" fill="#2E2C27"/>'
            )
        else:
            step = (w - 2 * pad) / (len(pts) - 1)
            coords = " ".join(
                f"{pad + i*step:.1f},{h_ - pad - (v - lo)/span*(h_ - 2*pad):.1f}"
                for i, (_, v) in enumerate(pts)
            )
            body = (
                f'<polyline points="{coords}" fill="none" stroke="#2E2C27" '
                f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        n = len(pts)
        note = "30 days" if n >= 30 else f"day {n} of 30"
        blocks.append(
            '      <div class="spark"><div class="spark-head">'
            f'<span class="spark-label">{esc(label)}</span>'
            f'<span class="spark-val">{esc(fmt(latest))}</span></div>'
            f'<svg viewBox="0 0 {w} {h_}" preserveAspectRatio="none" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(label)} trend">{body}</svg>'
            f'<div class="spark-note">{note}</div></div>'
        )
    return "\n".join(blocks)


def main():
    if len(sys.argv) != 2:
        die("usage: python3 scripts/build.py content/<date>.json")
    content = json.loads((ROOT / sys.argv[1]).read_text())

    for k in ("date", "headline", "subline", "asof", "strip", "sections", "history"):
        if k not in content:
            die(f"content missing required key '{k}'")
    iso = content["date"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
        die(f"bad date: {iso}")

    # --- history ---
    hist = load_json("data/history.json", [])
    entry = {"date": iso}
    for k, v in content["history"].items():
        if v is not None:
            entry[k] = float(v)
    hist = [h for h in hist if h.get("date") != iso] + [entry]
    hist.sort(key=lambda h: h["date"])

    # --- index ---
    idx = load_json("data/index.json", {"dates": []})
    dates = sorted(set(idx.get("dates", [])) | {iso})
    latest = dates[-1]

    # --- render ---
    tpl = (ROOT / "template.html").read_text()
    page = (
        tpl.replace("{{DATE_HUMAN}}", esc(human_date(iso)))
        .replace("{{DATE_ISO}}", iso)
        .replace("{{HEADLINE}}", esc(content["headline"]))
        .replace("{{SUBLINE}}", esc(content["subline"]))
        .replace("{{ASOF}}", esc(content["asof"]))
        .replace("{{STRIP_CELLS}}", build_strip(content["strip"]))
        .replace("{{SPARKS}}", build_sparks(hist))
        .replace("{{SECTIONS}}", build_sections(content["sections"]))
    )
    leftovers = re.findall(r"\{\{[A-Z_]+\}\}", page)
    if leftovers:
        die(f"unfilled placeholders: {leftovers}")

    # --- write ---
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "editions").mkdir(exist_ok=True)
    (ROOT / "data/history.json").write_text(json.dumps(hist, indent=1))
    (ROOT / "data/index.json").write_text(json.dumps({"dates": dates, "latest": latest}, indent=1))
    (ROOT / f"editions/{iso}.html").write_text(page)
    if iso == latest:
        (ROOT / "index.html").write_text(page)
    print(f"built editions/{iso}.html ({len(page):,} bytes); latest={latest}; "
          f"history={len(hist)} days; dates={len(dates)}")


if __name__ == "__main__":
    main()
