#!/usr/bin/env python3
"""Genera il digest settimanale di compliance (GDPR, NIS2, AI Act...).

Uso: python fetch_digest.py [--days 7] [--date YYYY-MM-DD]
Scrive:
  data/YYYY-Www.json      dati grezzi della settimana
  docs/weeks/YYYY-Www.html pagina della settimana
  docs/index.html          indice/archivio
  data/seen.json           id già visti (evita ripetizioni tra settimane)
"""
import argparse, datetime as dt, hashlib, html, json, re, sys, time
from pathlib import Path
import feedparser, yaml

ROOT = Path(__file__).parent
DATA, DOCS = ROOT / "data", ROOT / "docs"
WEEKS = DOCS / "weeks"
UA = "Mozilla/5.0 (compliance-watch/1.0)"


def item_date(e):
    for k in ("published_parsed", "updated_parsed"):
        if getattr(e, k, None):
            return dt.datetime.fromtimestamp(time.mktime(getattr(e, k)), dt.timezone.utc)
    return None


def clean(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def match(text, kw):
    cats = []
    for cat, pats in kw.items():
        if any(re.search(p, text, re.I) for p in pats):
            cats.append(cat)
    return cats


def collect(cfg, since, seen):
    items, errors, fresh = [], [], set()
    for f in cfg["feeds"]:
        d = feedparser.parse(f["url"], agent=UA)
        if d.bozo and not d.entries:
            errors.append(f"{f['name']}: {getattr(d, 'bozo_exception', 'errore sconosciuto')}")
            continue
        for e in d.entries:
            link = getattr(e, "link", "")
            title = clean(getattr(e, "title", ""))
            if not link or not title:
                continue
            uid = hashlib.sha1(re.sub(r"\W+", "", title.lower()).encode()).hexdigest()[:16]
            if uid in seen or uid in fresh:
                continue
            when = item_date(e)
            if when and when < since:
                continue
            summary = clean(getattr(e, "summary", ""))[:300]
            cats = match(f"{title} {summary}", cfg["keywords"])
            if not cats and not f.get("all"):
                continue
            fresh.add(uid)
            items.append({
                "id": uid, "title": title, "link": link, "source": f["name"],
                "date": when.isoformat() if when else None,
                "summary": summary, "categories": cats or ["Fonte primaria"],
            })
    items.sort(key=lambda i: i["date"] or "", reverse=True)
    return items, errors, fresh


CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--card:#f5f5f7;--acc:#0b5fff;--bd:#e2e2e6}
@media(prefers-color-scheme:dark){:root{--bg:#161618;--fg:#f0f0f2;--mut:#9a9aa0;--card:#222226;--acc:#6ea0ff;--bd:#33333a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
main{max-width:820px;margin:0 auto;padding:2rem 1.2rem 4rem}
a{color:var(--acc)}h1{font-size:1.6rem;margin:.2rem 0}h2{font-size:1.1rem;margin:2rem 0 .8rem;border-bottom:1px solid var(--bd);padding-bottom:.3rem}
.mut{color:var(--mut);font-size:.9rem}.card{background:var(--card);border-radius:10px;padding:.8rem 1rem;margin:.6rem 0}
.card a{font-weight:600;text-decoration:none}.tag{display:inline-block;font-size:.75rem;border:1px solid var(--bd);border-radius:20px;padding:0 .5rem;margin-right:.3rem}
ul.arch{list-style:none;padding:0}ul.arch li{padding:.5rem 0;border-bottom:1px solid var(--bd)}
"""


def page(title, body):
    return (f"<!doctype html><html lang='it'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")


def render_week(label, start, end, items, errors, prev_next):
    h = [f"<p class='mut'><a href='../index.html'>← Archivio</a></p>",
         f"<h1>Compliance Watch · {label}</h1>",
         f"<p class='mut'>Periodo: {start:%d/%m/%Y} – {end:%d/%m/%Y} · {len(items)} novità</p>"]
    cats = {}
    for it in items:
        cats.setdefault(it["categories"][0], []).append(it)
    if not items:
        h.append("<p>Nessuna novità rilevante questa settimana.</p>")
    for cat, lst in cats.items():
        h.append(f"<h2>{html.escape(cat)}</h2>")
        for it in lst:
            d = it["date"][:10] if it["date"] else "data n/d"
            tags = "".join(f"<span class='tag'>{html.escape(c)}</span>" for c in it["categories"])
            summ = f"<div class='mut'>{html.escape(it['summary'])}</div>" if it["summary"] else ""
            h.append(f"<div class='card'><a href='{html.escape(it['link'])}' target='_blank' rel='noopener'>"
                     f"{html.escape(it['title'])}</a><div class='mut'>{html.escape(it['source'])} · {d}</div>{summ}<div>{tags}</div></div>")
    if errors:
        h.append("<h2>Fonti non raggiungibili</h2><ul>" + "".join(f"<li class='mut'>{html.escape(e)}</li>" for e in errors) + "</ul>")
    h.append("<p class='mut'>Selezione automatica per parole chiave: verifica sempre il testo della fonte primaria prima di agire.</p>")
    return page(f"Compliance Watch {label}", "".join(h))


def render_index():
    rows = []
    for f in sorted(DATA.glob("20??-W??.json"), reverse=True):
        d = json.loads(f.read_text("utf-8"))
        rows.append(f"<li><a href='weeks/{d['label']}.html'><b>{d['label']}</b></a> "
                    f"<span class='mut'>{d['start']} → {d['end']} · {len(d['items'])} novità</span></li>")
    body = ("<h1>Compliance Watch</h1><p class='mut'>Novità settimanali su GDPR, NIS2, AI Act e normativa cyber in Italia. "
            "Aggiornato ogni lunedì.</p><h2>Archivio</h2><ul class='arch'>" + "".join(rows) + "</ul>")
    (DOCS / "index.html").write_text(page("Compliance Watch", body), "utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--date", help="data di esecuzione YYYY-MM-DD (default: oggi)")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    end = dt.datetime.combine(today, dt.time(), dt.timezone.utc)
    start = end - dt.timedelta(days=a.days)
    y, w, _ = today.isocalendar()
    label = f"{y}-W{w:02d}"

    for p in (DATA, WEEKS):
        p.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load((ROOT / "feeds.yml").read_text("utf-8"))
    seen_f = DATA / "seen.json"
    seen = set(json.loads(seen_f.read_text()) if seen_f.exists() else [])

    items, errors, fresh = collect(cfg, start, seen)
    (DATA / f"{label}.json").write_text(json.dumps(
        {"label": label, "start": f"{start:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}", "items": items, "errors": errors},
        ensure_ascii=False, indent=1), "utf-8")
    seen_f.write_text(json.dumps(sorted(seen | fresh)))
    (WEEKS / f"{label}.html").write_text(render_week(label, start, end, items, errors, None), "utf-8")
    render_index()
    print(f"{label}: {len(items)} novità, {len(errors)} fonti in errore")
    for e in errors:
        print("  !", e, file=sys.stderr)


if __name__ == "__main__":
    main()
