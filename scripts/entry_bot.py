"""Turn a "Suggest an entry" issue into a site entry.

  python scripts/entry_bot.py check <event.json>   validate the issue, write a comment to comment.md
  python scripts/entry_bot.py add   <event.json>   append it to data/entries.json and save its image

The issue body is untrusted input: it is only parsed as text, never executed.
"""
import html
import io
import ipaddress
import json
import re
import socket
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "entries.json"
IMG = ROOT / "img"
UA = "Mozilla/5.0 (compatible; fast-with-ai-bot/1.0; +https://woletee.github.io/fast-with-ai/)"
FIELDS = {
    "Title": "title", "Who did it": "who", "When (year and month)": "date", "Category": "field",
    "How long it took": "big", "Compared to": "vs", "What was done": "what", "What the AI did": "ai",
    "Source link": "source", "Second source (optional)": "source2", "Caveats (optional)": "note",
}
CATEGORY = {"Science": "science", "Software": "software", "Math & games": "math", "Business": "business"}
LIMITS = {"title": 60, "who": 60, "big": 20, "vs": 60, "what": 140, "ai": 140, "note": 60}
REQUIRED = ["title", "who", "date", "field", "big", "vs", "what", "ai", "source"]


def parse(body: str) -> dict:
    out = {}
    for block in re.split(r"^### ", body or "", flags=re.M)[1:]:
        label, _, value = block.partition("\n")
        value = value.strip()
        key = FIELDS.get(label.strip())
        if key and value and value != "_No response_":
            out[key] = re.sub(r"\s+", " ", value)
    return out


def public_http_url(url: str) -> bool:
    try:
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        for info in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except Exception:
        return False


def fetch(url: str, limit: int):
    if not public_http_url(url):
        raise ValueError("not a public http(s) link")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.geturl(), r.headers.get("Content-Type", ""), r.read(limit)


def og_image(page: str, base: str):
    for tag in re.findall(r"<meta[^>]+>", page, re.I):
        if re.search(r'(property|name)\s*=\s*["\']?(og:image(:secure_url)?|twitter:image(:src)?)(["\'\s>]|$)', tag, re.I):
            m = re.search(r'content\s*=\s*(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))', tag, re.I)
            if m:
                return urllib.parse.urljoin(base, html.unescape(next(g for g in m.groups() if g)))
    return None


def validate(e: dict) -> list:
    problems = [f"**{k}** is missing" for k in REQUIRED if not e.get(k)]
    if e.get("date") and not re.fullmatch(r"(19|20)\d\d-(0[1-9]|1[0-2])", e["date"]):
        problems.append("**When** should look like `2026-07`")
    if e.get("field") and e["field"] not in CATEGORY:
        problems.append("**Category** must be one of the listed options")
    for k, n in LIMITS.items():
        if len(e.get(k, "")) > n:
            problems.append(f"**{k}** is too long ({len(e[k])} characters, max {n})")
    for k in ("source", "source2"):
        if e.get(k) and not public_http_url(e[k]):
            problems.append(f"**{k}** must be a public http(s) link")
    return problems


def source_label(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.removeprefix("www.")


def check(event: dict) -> int:
    issue = event["issue"]
    e = parse(issue.get("body", ""))
    problems = validate(e)
    reach = []
    for k in ("source", "source2"):
        if e.get(k) and public_http_url(e[k]):
            try:
                final, _, page = fetch(e[k], 1_500_000)
                img = og_image(page.decode("utf-8", "replace"), final)
                reach.append(f"- {source_label(e[k])}: reachable" + (", has a preview image" if img else ", no preview image (placeholder art will be used)"))
            except Exception as ex:
                reach.append(f"- {source_label(e[k])}: could not open it ({type(ex).__name__})")
    lines = ["Thanks for the suggestion!", ""]
    if problems:
        lines += ["Please edit the issue to fix these:", *[f"- {p}" for p in problems], ""]
    else:
        lines += ["The form looks complete. A maintainer will check the claims against the source, then add the `approved` label. The site updates automatically after that.", ""]
    if reach:
        lines += ["Source check:", *reach]
    Path("comment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def add(event: dict) -> int:
    issue = event["issue"]
    e = parse(issue.get("body", ""))
    problems = validate(e)
    if problems:
        Path("comment.md").write_text("Could not add this entry:\n" + "\n".join(f"- {p}" for p in problems) + "\n", encoding="utf-8")
        return 1
    entries = json.loads(DATA.read_text(encoding="utf-8"))
    eid = f"i{issue['number']}"
    if any(x.get("id") == eid for x in entries):
        Path("comment.md").write_text("This entry is already on the site.\n", encoding="utf-8")
        return 0
    entry = {
        "id": eid, "date": e["date"], "field": CATEGORY[e["field"]], "title": e["title"], "who": e["who"],
        "big": e["big"], "vs": e["vs"], "what": e["what"], "ai": e["ai"],
        "sources": [{"label": source_label(e[k]), "url": e[k]} for k in ("source", "source2") if e.get(k)],
        "issue": issue["html_url"],
    }
    if e.get("note"):
        entry["note"] = e["note"]
    try:
        from PIL import Image
        final, _, page = fetch(e["source"], 1_500_000)
        img_url = og_image(page.decode("utf-8", "replace"), final)
        if img_url:
            _, _, data = fetch(img_url, 8_000_000)
            im = Image.open(io.BytesIO(data)).convert("RGB")
            ratio = im.width / max(im.height, 1)
            im.thumbnail((900, 900))
            IMG.mkdir(exist_ok=True)
            im.save(IMG / f"{eid}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
            entry.update({"image": f"img/{eid}.jpg", "imageCredit": source_label(e["source"]), "imagePage": e["source"]})
            if not 1.6 <= ratio <= 2.2:
                entry["imageFit"] = "contain"
    except Exception as ex:
        print("image skipped:", type(ex).__name__, ex)
    entries.append(entry)
    DATA.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    Path("comment.md").write_text(
        "Added to the list. It will be live at https://woletee.github.io/fast-with-ai/ in a minute or two. Thanks!\n",
        encoding="utf-8")
    print("added", eid, entry["title"])
    return 0


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    event = json.loads(Path(path).read_text(encoding="utf-8"))
    sys.exit({"check": check, "add": add}[mode](event))
