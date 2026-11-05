#!/usr/bin/env python3
"""Lee canales.json y genera data.json, que es lo que reproduce la tele."""
import json, random, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "es", "Cookie": "SOCS=CAI"}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf8")

def page_with_data(url):
    """YouTube a veces devuelve una página sin datos: se reintenta."""
    for attempt in range(4):
        html = fetch(url)
        m = re.search(r"ytInitialData\s*=\s*", html)
        if m:
            return html, json.JSONDecoder().raw_decode(html[m.end():])[0]
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"sin datos en {url}")

def walk(o, key):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(o, list):
        for x in o:
            yield from walk(x, key)

def clean(t):
    t = re.sub(r"\s*\|\s*(Hey Arnold!?|Nicktoons|NickRewind|Nick)\b!?", "", t)
    return re.sub(r"\s+", " ", re.sub(r"[\U0001F300-\U0001FAFF⁉️]", "", t)).strip()

def resolve(url):
    """Acepta un canal, una lista o un vídeo. Devuelve qué es y de dónde leerlo."""
    url = url.strip()
    if url.startswith("@"):
        url = "https://www.youtube.com/" + url
    if not url.startswith("http"):
        url = "https://" + url
    q = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(q.query)
    if "list" in params:
        pid = params["list"][0]
        return {"type": "playlist", "id": pid, "page": f"https://www.youtube.com/playlist?list={pid}"}
    m = re.search(r"/channel/(UC[\w-]+)", q.path)
    if m:
        cid = m.group(1)
    elif "/@" in q.path:
        handle = re.search(r"/(@[^/]+)", q.path).group(1)
        html, _ = page_with_data(f"https://www.youtube.com/{handle}")
        cid = re.search(r'"externalId":"(UC[\w-]+)"', html).group(1)
    else:
        vid = params["v"][0] if "v" in params else q.path.rstrip("/").split("/")[-1]
        html = fetch(f"https://www.youtube.com/watch?v={vid}")
        cid = re.search(r'"channelId":"(UC[\w-]+)"', html).group(1)
    html, _ = page_with_data(f"https://www.youtube.com/channel/{cid}")
    title = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    # La lista de subidas sin Shorts da hasta 100 vídeos, del más nuevo al más antiguo.
    return {"type": "channel", "id": cid, "name": title.group(1).strip() if title else "",
            "page": f"https://www.youtube.com/playlist?list=UULF{cid[2:]}"}

def videos(page):
    html, data = page_with_data(page)
    title = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    out = []
    for r in walk(data, "lockupViewModel"):
        vid = r.get("contentId")
        t = re.search(r'"text": "(\d{1,2}(?::\d{2}){1,2})"', json.dumps(r, ensure_ascii=False))
        if not vid or not t:
            continue
        secs = 0
        for part in t.group(1).split(":"):
            secs = secs * 60 + int(part)
        out.append({"id": vid, "t": r["metadata"]["lockupMetadataViewModel"]["title"]["content"], "s": secs})
    return (title.group(1).strip() if title else ""), out

def has_any(title, terms):
    return any(x.strip().lower() in title.lower() for x in terms.split("|") if x.strip())

def read_source(src):
    info = resolve(src["url"])
    name, vids = videos(info["page"])
    if src.get("min"):
        vids = [v for v in vids if v["s"] >= float(src["min"]) * 60]
    if src.get("contiene"):
        vids = [v for v in vids if has_any(v["t"], src["contiene"])]
    if src.get("excluir"):
        vids = [v for v in vids if not has_any(v["t"], src["excluir"])]
    if not vids:
        raise RuntimeError(f"ningún vídeo pasa los filtros de {src['url']}")
    vids = [{**v, "t": clean(v["t"])} for v in vids]
    info.update(name=info.get("name") or name, vids=vids, plain=not (src.get("min") or src.get("contiene") or src.get("excluir")))
    return info

def mix(lists):
    out = []
    for i in range(max(map(len, lists))):
        out += [l[i] for l in lists if i < len(l)]
    return out

def names(sources):
    got = [s["name"] for s in sources if s["name"]]
    return ", ".join(got[:-1]) + " y " + got[-1] if len(got) > 1 else "".join(got)

def build(ch):
    src = [read_source(s) for s in ch["fuentes"]]
    who = names(src)
    out = {"num": ch["num"], "name": ch["name"], "hours": ch.get("hours", []), "sourceName": who, "tagline": who}
    if ch.get("noche"):
        out["night"] = True
    lists = [s["vids"] for s in src]
    if ch["modo"] == "tele":
        items = mix(lists)
        if ch.get("barajar"):
            random.Random(7).shuffle(items)
        return {**out, "kind": "linear", "items": items}
    live = [s for s in src if s["plain"] and s["type"] == "channel"]
    rest = [s for s in src if s not in live]
    if live and not rest:
        return {**out, "kind": "latest", "ids": [s["id"] for s in live]}
    filtered = [f for f in ch["fuentes"] if f.get("min") or f.get("contiene") or f.get("excluir")]
    if live and all(f.get("contiene") and not f.get("min") for f in filtered):
        return {**out, "kind": "latest", "ids": [s["id"] for s in live], "recap": [v["id"] for v in mix([s["vids"] for s in rest])[:3]]}
    return {**out, "kind": "episodes", "items": mix(lists)}

def main():
    config = json.loads((ROOT / "canales.json").read_text("utf8"))
    path = ROOT / "data.json"
    old = json.loads(path.read_text("utf8")) if path.exists() else {}
    previous = {c["num"]: c for c in old.get("channels", [])}
    channels, failed = [], 0
    for ch in sorted(config, key=lambda c: c["num"]):
        try:
            built = build(ch)
            channels.append(built)
            print(ch["num"], ch["name"], built["kind"], len(built.get("items", built.get("ids", []))))
        except Exception as e:
            failed += 1
            print(f"{ch['num']}: error, conservo lo anterior: {e}", file=sys.stderr)
            if ch["num"] in previous:
                channels.append({**previous[ch["num"]], "name": ch["name"], "hours": ch.get("hours", [])})
    if channels:
        path.write_text(json.dumps({"channels": channels}, ensure_ascii=False, indent=0) + "\n", "utf8")
    return 1 if failed == len(config) else 0

if __name__ == "__main__":
    sys.exit(main())
