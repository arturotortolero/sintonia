#!/usr/bin/env python3
"""Refresca data.json con las listas de Cocina, Noche, Dibujos y el resumen de RTVE."""
import json, random, re, sys, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "es", "Cookie": "SOCS=CAI"}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf8")

def walk(o, key):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(o, list):
        for x in o:
            yield from walk(x, key)

def videos(url):
    html = fetch(url)
    m = re.search(r"ytInitialData\s*=\s*", html)
    data = json.JSONDecoder().raw_decode(html[m.end():])[0]
    out = []
    for r in walk(data, "lockupViewModel"):
        vid = r.get("contentId")
        title = r["metadata"]["lockupMetadataViewModel"]["title"]["content"]
        t = re.search(r'"text": "(\d{1,2}(?::\d{2}){1,2})"', json.dumps(r, ensure_ascii=False))
        if not vid or not t:
            continue
        secs = 0
        for part in t.group(1).split(":"):
            secs = secs * 60 + int(part)
        out.append({"id": vid, "t": title, "s": secs})
    return out

def clean(t):
    t = re.sub(r"\s*\|\s*(Hey Arnold!?|Nicktoons|NickRewind|Nick)\b!?", "", t)
    return re.sub(r"\s+", " ", re.sub(r"[\U0001F300-\U0001FAFF⁉️]", "", t)).strip()

def arnold():
    url = "https://www.youtube.com/playlist?list=PLMnlzeYiwSXeCVwR2j9EDs-J63QPr06jU"
    keep = [v for v in videos(url)
            if re.search("Nicktoons|NickRewind", v["t"]) and "Jungle" not in v["t"] and v["s"] >= 45]
    random.Random(7).shuffle(keep)
    return [{**v, "t": clean(v["t"])} for v in keep]

def recap():
    url = "https://www.youtube.com/playlist?list=UULF7QZIf0dta-XPXsp9Hv4dTw"
    return [v["id"] for v in videos(url) if "en 10 minutos" in v["t"]][:3]

def podcasts():
    """Solo episodios: descarta los cortes por duración y mezcla, del más nuevo al más antiguo."""
    sources = [("escueladenada", 30), ("nachored", 10), ("elcuarticopod", 30)]
    lists = [[v for v in videos(f"https://www.youtube.com/@{h}/videos") if v["s"] >= m * 60]
             for h, m in sources]
    if not all(lists):
        raise RuntimeError("una de las fuentes de podcasts ha llegado vacía")
    out = []
    for i in range(max(map(len, lists))):
        out += [l[i] for l in lists if i < len(l)]
    return out

JOBS = {
    "03": ("items", arnold),
    "04": ("items", podcasts),
    "05": ("recap", recap),
    "07": ("items", lambda: videos("https://www.youtube.com/@joshuaweissmanrecipes/videos")),
    "09": ("items", lambda: videos("https://www.youtube.com/@yummy_yammy/videos")),
}

def main():
    old = json.loads(OUT.read_text("utf8")) if OUT.exists() else {}
    new = dict(old)
    failed = 0
    for num, (field, job) in JOBS.items():
        try:
            value = job()
        except Exception as e:
            print(f"{num}: error, conservo la lista anterior: {e}", file=sys.stderr)
            value = []
        if value:
            new[num] = {field: value}
            print(num, len(value))
        else:
            failed += 1
    OUT.write_text(json.dumps(new, ensure_ascii=False, indent=0) + "\n", "utf8")
    return 1 if failed == len(JOBS) else 0

if __name__ == "__main__":
    sys.exit(main())
