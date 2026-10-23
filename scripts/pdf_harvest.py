"""Fill the PDF test set quickly from councils that aren't in the page crawl, so no host is hit twice.

Per council, one request at a time with the same robots.txt rules and 5-second floor as dataset_crawl:
one Firecrawl map (searching for document-heavy pages), then those pages fetched directly and their PDF links
size-checked from the response headers against the shared log-normal quota (dataset_crawl.SizeQuota).

    python pdf_harvest.py          # the main crawl must run with --no-pdfs so the quota has one owner
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dataset_crawl as C

SITES = """
leicester.gov.uk peterborough.gov.uk newcastle.gov.uk northyorks.gov.uk devon.gov.uk cheltenham.gov.uk
surreycc.gov.uk hertfordshire.gov.uk nottinghamshire.gov.uk lancashire.gov.uk cambridgeshire.gov.uk
wiltshire.gov.uk dorsetcouncil.gov.uk somerset.gov.uk shropshire.gov.uk cheshireeast.gov.uk warwickshire.gov.uk
worcestershire.gov.uk leicestershire.gov.uk derbyshire.gov.uk staffordshire.gov.uk oxfordshire.gov.uk
buckinghamshire.gov.uk westsussex.gov.uk eastsussex.gov.uk hants.gov.uk gloucestershire.gov.uk
northumberland.gov.uk durham.gov.uk walsall.gov.uk sandwell.gov.uk dudley.gov.uk barnsley.gov.uk
rotherham.gov.uk doncaster.gov.uk calderdale.gov.uk
""".split()
PER_SITE, PAGES_PER_SITE = 20, 40
DOCS = re.compile(r"document|strateg|polic|plan|report|account|budget|publication|librar|download|annual|"
                  r"assessment|statement|evidence|consultation|guidance", re.I)
HREF = re.compile(r"""href=["']([^"'#]+)["']""", re.I)


class Pacer:
    """One request per host every delay seconds."""

    def __init__(self, delay: float):
        self.delay, self.last = delay, 0.0

    def wait(self) -> None:
        time.sleep(max(0.0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()


def get(url: str, pace: Pacer, limit: int) -> tuple[dict, bytes]:
    """Headers and up to `limit` bytes of the body (0: headers only)."""
    pace.wait()
    req = urllib.request.Request(url, headers={"User-Agent": C.UA})
    with urllib.request.urlopen(req, timeout=60, context=C.TLS) as r:
        return dict(r.headers), (r.read(limit) if limit else b"")


def harvest(domain: str) -> dict:
    slug, host = domain.split(".")[0], f"www.{domain}"
    if C.ROBOTS.get(host) is None or not C.ROBOTS.allowed(f"https://{host}/"):
        return {"site": slug, "skipped": "robots.txt unreadable or disallows"}
    pace = Pacer(C.ROBOTS.delay(host))
    d = C.OUT / "pdfs" / slug
    d.mkdir(parents=True, exist_ok=True)
    seen_f = C.OUT / "pdfs" / f"{slug}.checked"
    checked = {ln.split("\t")[0] for ln in seen_f.read_text(encoding="utf-8").split("\n")} if seen_f.exists() else set()
    scraped = C.OUT / "pages" / f"{slug}.jsonl"                 # a crawled council's pages already list PDFs
    known = sorted({u for ln in scraped.open(encoding="utf-8") for u in json.loads(ln)["pdf_links"]
                    if u not in checked}) if scraped.exists() else []
    links = []
    if len(known) < 50:
        try:
            m = C.post("map", {"url": f"https://{host}", "search": "documents strategy policy report plan",
                               "limit": 400, "includeSubdomains": False}, 240)
            links = [x["url"] if isinstance(x, dict) else x for x in m.get("links", [])]
        except Exception as e:
            C.say(f"[{slug}] map failed: {e}")
    pdfs = known + [u for u in links if C.PDF_LIKE.search(u)]
    random.Random(slug).shuffle(pdfs)
    pages = [u for u in links if not C.PDF_LIKE.search(u) and not C.SKIP_EXT.search(urllib.parse.urlsplit(u).path)
             and urllib.parse.urlsplit(u).hostname == host]
    pages = sorted(pages, key=lambda u: not DOCS.search(u))[:PAGES_PER_SITE] or [f"https://{host}/"]
    visited: set[str] = set()
    have, fails = len(list(d.glob("*.pdf"))), 0
    while (pages or pdfs) and have < PER_SITE and not C.QUOTA.full() and fails < 15:
        if not pdfs:                                            # find more PDF links on the next page
            url = pages.pop(0)
            if not C.ROBOTS.allowed(url):
                continue
            try:
                h, body = get(url, pace, 3_000_000)
                fails = 0
            except Exception:
                fails += 1
                continue
            if "html" not in h.get("Content-Type", ""):
                continue
            found = {urllib.parse.urljoin(url, x).split("#")[0] for x in HREF.findall(body.decode("utf-8", "replace"))}
            pdfs = [u for u in found if C.PDF_LIKE.search(u) and u not in checked
                    and (urllib.parse.urlsplit(u).hostname or "").endswith(domain)]
            visited.add(url)
            if len(visited) + len(pages) < PAGES_PER_SITE:          # follow document-ish links on the same site
                pages += [u for u in found if u not in visited and u not in pages and DOCS.search(u)
                          and urllib.parse.urlsplit(u).hostname == host and not C.PDF_LIKE.search(u)
                          and not C.SKIP_EXT.search(urllib.parse.urlsplit(u).path)][:20]
            continue
        url = pdfs.pop(0)
        if url in checked or not C.ROBOTS.allowed(url):
            continue
        checked.add(url)
        size, buf = 0, b""
        try:
            pace.wait()                                         # one GET: headers, then the body only if it fits
            req = urllib.request.Request(url, headers={"User-Agent": C.UA})
            with urllib.request.urlopen(req, timeout=90, context=C.TLS) as r:
                size = int(r.headers.get("Content-Length") or 0)
                ctype = r.headers.get("Content-Type", "").lower()
                if ("pdf" in ctype or "octet-stream" in ctype) and (not size or C.QUOTA.wants(size)):
                    buf = r.read(C.PDF_MAX + 1)
            fails = 0
        except Exception:
            fails += 1
        with seen_f.open("a", encoding="utf-8") as f:
            f.write(f"{url}\t{size or len(buf)}\n")
        if not buf.startswith(b"%PDF"):
            continue
        sha = hashlib.sha256(buf).hexdigest()
        if not C.QUOTA.take(len(buf), sha):
            continue
        name = re.sub(r"[^\w.-]+", "_", Path(urllib.parse.urlsplit(url).path).name)[:80] or "doc"
        name += "" if name.lower().endswith(".pdf") else ".pdf"
        (d / f"{sha[:10]}_{name}").write_bytes(buf)
        with C._print:
            with (C.OUT / "pdfs" / "downloads.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"site": slug, "url": url, "file": f"{slug}/{sha[:10]}_{name}", "bytes": len(buf),
                                    "sha256": sha, "at": C.now()}) + "\n")
        have += 1
        C.say(f"[{slug}] pdf {have} ({len(buf) / 1e6:.1f} MB); total {sum(C.QUOTA.filled)}; bins {C.QUOTA.describe()}")
    return {"site": slug, "pdfs": have}


CRAWLED = "camden.gov.uk leeds.gov.uk bradford.gov.uk bathnes.gov.uk swindon.gov.uk lambeth.gov.uk york.gov.uk bolton.gov.uk " \
          "oxford.gov.uk edinburgh.gov.uk".split()

if __name__ == "__main__":
    if "--deep" in sys.argv:                                    # second pass: dig further, add crawled councils
        PER_SITE, PAGES_PER_SITE = 30, 250
        skip = set(a.removeprefix("--skip=") for a in sys.argv if a.startswith("--skip="))
        sys.argv = [sys.argv[0]] + [d for d in SITES + CRAWLED if d.split(".")[0] not in skip]
    C.QUOTA = C.load_quota()
    C.say(f"PDF size quota (1-10 MB, log bins): {C.QUOTA.describe()}")
    with ThreadPoolExecutor(len(SITES)) as ex:                  # one thread per council, so one request per host
        res = list(ex.map(harvest, sys.argv[1:] or SITES))
    C.say(json.dumps(res))
    C.say(f"final bins: {C.QUOTA.describe()}  total {sum(C.QUOTA.filled)}")
