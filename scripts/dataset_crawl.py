"""A slow, robots-respecting council website dataset, plus a PDF test set, through a local Firecrawl.

    python dataset_crawl.py survey     # robots.txt + one Firecrawl map per candidate → dataset/survey.json
    python dataset_crawl.py plan       # pick 24 councils, tiers 100…1000 by map size → dataset/sites.json
    python dataset_crawl.py crawl      # scrape each site's sample, then its PDFs (resumable)

Politeness, per host: robots.txt checked for every URL (ours and "*"), Crawl-delay honoured with a
5-second floor, one request at a time, and a site stops after repeated 403/429s rather than pushing on.
Different councils run in parallel because they are different hosts. Our user agent says what we are.

Output (dataset/):
  survey.json, sites.json     the candidates and the chosen plan
  robots/<slug>.txt           the robots.txt each site was crawled under
  maps/<slug>.json            Firecrawl's URL map
  pages/<slug>.jsonl          one scraped page per line: url, status, title, markdown, pdf_links, scraped_at
  errors/<slug>.jsonl         failed URLs
  pdfs/<slug>/*.pdf           PDF test files, 1–10 MB (kept out of git; pdfs.csv lists them)
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import certifi

FIRECRAWL = "http://localhost:3002/v2"
UA = "Mozilla/5.0 (compatible; council-pii-research/0.1; low-rate, respects robots.txt)"
MIN_DELAY_S = 5.0
WORKERS = 8
PDF_TARGET, PDF_PER_SITE, PDF_CHECKS_PER_SITE, PDF_MIN, PDF_MAX = 200, 15, 400, 1_000_000, 10_000_000
TIERS = list(range(100, 1001, 100))
OUT = Path(__file__).parent / "dataset"
SKIP_EXT = re.compile(r"\.(?:pdf|docx?|xlsx?|pptx?|csv|zip|jpe?g|png|gif|svg|webp|mp[34]|mov|ics|xml|rss|json|txt|odt|ods|rtf)$", re.I)
NO_PDFS = False                 # --no-pdfs: replacement runs leave the PDF count to the main run
PDF_LIKE = re.compile(r"\.pdf(?:$|[?#])|/downloads?/file/\d+|/media/\d+/download|/download/\d+", re.I)

CANDIDATES = """
cambridge.gov.uk bristol.gov.uk leeds.gov.uk manchester.gov.uk birmingham.gov.uk liverpool.gov.uk sheffield.gov.uk
nottinghamcity.gov.uk leicester.gov.uk york.gov.uk oxford.gov.uk brighton-hove.gov.uk norwich.gov.uk exeter.gov.uk
plymouth.gov.uk southampton.gov.uk portsmouth.gov.uk bathnes.gov.uk cheltenham.gov.uk gloucester.gov.uk hull.gov.uk
newcastle.gov.uk sunderland.gov.uk bradford.gov.uk wakefield.gov.uk derby.gov.uk coventry.gov.uk wolverhampton.gov.uk
stoke.gov.uk lincoln.gov.uk peterborough.gov.uk milton-keynes.gov.uk reading.gov.uk swindon.gov.uk salford.gov.uk
stockport.gov.uk trafford.gov.uk wigan.gov.uk bolton.gov.uk camden.gov.uk hackney.gov.uk islington.gov.uk
lambeth.gov.uk southwark.gov.uk westminster.gov.uk edinburgh.gov.uk glasgow.gov.uk cardiff.gov.uk cornwall.gov.uk
devon.gov.uk kent.gov.uk norfolk.gov.uk suffolk.gov.uk essex.gov.uk northyorks.gov.uk
""".split()

# Verified TLS against certifi's CA bundle: this machine's Windows store fails some valid UK council chains.
TLS = ssl.create_default_context(cafile=certifi.where())
_print = threading.Lock()


def say(*a) -> None:
    with _print:
        print(*a, flush=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def post(path: str, body: dict, timeout: int = 180) -> dict:
    """POST to the local Firecrawl."""
    req = urllib.request.Request(f"{FIRECRAWL}/{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:                      # Firecrawl wraps the site's failure; keep its words
        try:
            detail = json.loads(e.read()).get("error", "")
        except Exception:
            detail = ""
        raise RuntimeError(f"firecrawl {e.code}: {detail}"[:300]) from None


class Robots:
    """robots.txt per host, fetched once, checked for our agent and for '*'."""

    def __init__(self):
        self._by_host: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def fetch(self, host: str) -> tuple[urllib.robotparser.RobotFileParser | None, str]:
        """(parser, raw text); parser is None when robots.txt can't be read safely (we then skip the host)."""
        req = urllib.request.Request(f"https://{host}/robots.txt", headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20, context=TLS) as r:
                text = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:                                    # no robots.txt: crawling is permitted
                text = ""
            else:
                return None, f"HTTP {e.code}"
        except Exception as e:                                   # TLS errors, timeouts: don't guess
            return None, str(e)[:120]
        if "<html" in text[:500].lower():                        # a WAF page served as robots.txt
            return None, "robots.txt is an HTML page"
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        return rp, text

    def get(self, host: str) -> urllib.robotparser.RobotFileParser | None:
        with self._lock:
            if host not in self._by_host:
                self._by_host[host] = self.fetch(host)[0]
            return self._by_host[host]

    def allowed(self, url: str) -> bool:
        rp = self.get(urllib.parse.urlsplit(url).hostname or "")
        return bool(rp) and rp.can_fetch(UA, url) and rp.can_fetch("*", url)

    def delay(self, host: str) -> float:
        rp = self.get(host)
        cd = max([float(rp.crawl_delay(a) or 0) for a in (UA, "*")]) if rp else 0
        return max(MIN_DELAY_S, cd)


ROBOTS = Robots()


# ---------------------------------------------------------------------------------------------- survey

def survey_one(domain: str) -> dict:
    host = f"www.{domain}"
    rp, text = ROBOTS.fetch(host)
    rec = {"slug": domain.split(".")[0], "domain": domain, "host": host, "base": f"https://{host}"}
    if rp is None:
        return {**rec, "ok": False, "why": f"robots.txt: {text}"}
    ROBOTS._by_host[host] = rp
    (OUT / "robots").mkdir(parents=True, exist_ok=True)
    (OUT / "robots" / f"{rec['slug']}.txt").write_text(text, encoding="utf-8")
    if not ROBOTS.allowed(rec["base"] + "/"):
        return {**rec, "ok": False, "why": "robots.txt disallows the home page"}
    try:
        m = post("map", {"url": rec["base"], "limit": 20000, "includeSubdomains": False, "sitemap": "include"}, 300)
    except Exception as e:
        return {**rec, "ok": False, "why": f"map failed: {str(e)[:100]}"}
    links = [x["url"] if isinstance(x, dict) else x for x in m.get("links", [])]
    (OUT / "maps").mkdir(parents=True, exist_ok=True)
    (OUT / "maps" / f"{rec['slug']}.json").write_text(json.dumps(links), encoding="utf-8")
    same = [u for u in links if urllib.parse.urlsplit(u).hostname == host]
    html = [u for u in same if not SKIP_EXT.search(urllib.parse.urlsplit(u).path) and ROBOTS.allowed(u)]
    pdfs = [u for u in links if PDF_LIKE.search(u)]
    return {**rec, "ok": True, "mapped": len(links), "html_allowed": len(html), "pdf_links_in_map": len(pdfs),
            "crawl_delay": ROBOTS.delay(host), "surveyed_at": now()}


def survey(only: list[str] | None = None) -> None:
    """Survey every candidate, or re-survey just `only` and merge into survey.json."""
    OUT.mkdir(exist_ok=True)
    with ThreadPoolExecutor(4) as ex:                      # one map per site; different hosts
        res = list(ex.map(survey_one, only or CANDIDATES))
    if only and (OUT / "survey.json").exists():
        old = {r["domain"]: r for r in json.loads((OUT / "survey.json").read_text())}
        old.update({r["domain"]: r for r in res})
        res = [old[d] for d in CANDIDATES if d in old]
    for r in res:
        say(f"{r['domain']:<24}", f"html={r.get('html_allowed'):>6} pdf={r.get('pdf_links_in_map'):>5} "
            f"delay={r.get('crawl_delay')}" if r["ok"] else f"SKIP {r['why']}")
    (OUT / "survey.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def plan(n: int = 24) -> None:
    """24 usable councils; tiers 100…1000 (each at least twice), the biggest tiers to the biggest maps."""
    res = [r for r in json.loads((OUT / "survey.json").read_text()) if r["ok"] and r["html_allowed"] >= 100]
    res = sorted(res, key=lambda r: r["html_allowed"], reverse=True)[:n]
    tiers = sorted(TIERS * 2 + TIERS[:n - 2 * len(TIERS)], reverse=True)
    # biggest tier to the biggest map; a site that can't fill its tier takes the largest one it can
    chosen = [{**r, "tier": min(t, r["html_allowed"] // 100 * 100)} for r, t in zip(res, tiers)]
    (OUT / "sites.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
    for c in chosen:
        say(f"{c['slug']:<18} tier {c['tier']:>5}  (allowed {c['html_allowed']})")
    say(f"{len(chosen)} sites, {sum(c['tier'] for c in chosen)} pages planned")


# ----------------------------------------------------------------------------------------------- crawl

def scrape_retry(url: str, delay: float) -> dict:
    """Scrape once; on a Firecrawl-side failure wait three delays and try once more."""
    body = {"url": url, "formats": ["markdown", "links"], "onlyMainContent": True,
            "headers": {"User-Agent": UA}, "timeout": 60000, "blockAds": True}
    try:
        return post("scrape", body)
    except RuntimeError as e:
        if not str(e).startswith("firecrawl 5"):
            raise
        time.sleep(3 * delay)
        return post("scrape", body)


class Stop(Exception):
    """The site is refusing us; stop rather than push."""


def crawl_site(site: dict, pdf_count: list[int], pdf_lock: threading.Lock) -> dict:
    slug, host, tier = site["slug"], site["host"], site["tier"]
    stopped_f = OUT / "errors" / f"{slug}.stopped"
    if stopped_f.exists():
        say(f"[{slug}] skipped: refused us earlier ({stopped_f.read_text(encoding='utf-8')[:80]})")
        return {"slug": slug, "stopped": stopped_f.read_text(encoding="utf-8")}
    delay = ROBOTS.delay(host)
    links = json.loads((OUT / "maps" / f"{slug}.json").read_text())
    pool = sorted({u.split("#")[0] for u in links if urllib.parse.urlsplit(u).hostname == host
                   and not SKIP_EXT.search(urllib.parse.urlsplit(u).path)})
    random.Random(slug).shuffle(pool)                      # a seeded random sample, not the sitemap's first N
    pages_f, err_f = OUT / "pages" / f"{slug}.jsonl", OUT / "errors" / f"{slug}.jsonl"
    pages_f.parent.mkdir(exist_ok=True)
    err_f.parent.mkdir(exist_ok=True)
    done = {json.loads(ln)["url"] for ln in pages_f.open(encoding="utf-8")} if pages_f.exists() else set()
    # only pages that are really gone stay skipped; transient failures get another go on resume
    tried = ({r["url"] for r in map(json.loads, err_f.open(encoding="utf-8")) if r.get("final")}
             if err_f.exists() else set())
    refusals, failures, ok = 0, 0, len(done)
    pdf_links: list[str] = []
    for line in pages_f.open(encoding="utf-8") if pages_f.exists() else []:
        pdf_links += json.loads(line).get("pdf_links", [])
    try:
        for url in pool:
            if ok >= tier:
                break
            if url in done or url in tried or not ROBOTS.allowed(url):
                continue
            t0 = time.monotonic()
            try:
                r = scrape_retry(url, delay)
                d = r.get("data") or {}
                meta = d.get("metadata") or {}
                status = int(meta.get("statusCode") or 0)
                if not r.get("success") or status >= 400:
                    raise RuntimeError(f"status {status or r.get('error', '?')}")
                pl = sorted({u for u in d.get("links") or [] if PDF_LIKE.search(u)})
                pdf_links += pl
                rec = {"url": url, "final_url": meta.get("sourceURL") or meta.get("url") or url, "status": status,
                       "title": meta.get("title"), "language": meta.get("language"), "scraped_at": now(),
                       "markdown": d.get("markdown") or "", "pdf_links": pl}
                with pages_f.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                ok += 1
                refusals = failures = 0
                if ok % 50 == 0:
                    say(f"[{slug}] {ok}/{tier}")
            except Exception as e:
                msg = str(e)[:300]
                final = bool(re.match(r"status 4(?:0[0-9]|10)\b", msg))   # the page itself is gone
                with err_f.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"url": url, "error": msg, "final": final, "at": now()}) + "\n")
                failures = 0 if final else failures + 1
                if failures >= 15:
                    raise Stop(f"{failures} failures in a row (last: {msg[:120]})")
                if re.search(r"\b(403|429|503)\b", msg):
                    refusals += 1
                    if refusals >= 5:
                        raise Stop(f"{refusals} refusals in a row")
                    time.sleep(60 * refusals)              # back off hard
            time.sleep(max(0.0, delay - (time.monotonic() - t0)))
    except Stop as e:
        say(f"[{slug}] stopped: {e}")
        stopped_f.write_text(f"{now()} {e}", encoding="utf-8")       # never go back to a site that refused us
        return {"slug": slug, "pages": ok, "tier": tier, "pdfs": 0, "stopped": str(e)}
    say(f"[{slug}] pages done: {ok}/{tier}")
    if NO_PDFS:
        return {"slug": slug, "pages": ok, "tier": tier, "pdfs": 0}
    got = fetch_pdfs(site, pdf_links + [u for u in links if PDF_LIKE.search(u)], pdf_count, pdf_lock)
    return {"slug": slug, "pages": ok, "tier": tier, "pdfs": got}


# ------------------------------------------------------------------------------------------------ PDFs

class SizeQuota:
    """A log-normal target over 1–10 MB: log10(size) ~ N(0.65, 0.25), centred on 4.5 MB (biased towards the larger
    end, as asked), truncated to 1–10 MB, in ten log-spaced bins whose quotas sum to PDF_TARGET. A PDF is kept
    only if its bin has room."""

    BINS = 10

    def __init__(self, total: int = PDF_TARGET, mu: float = 0.65, sd: float = 0.25):
        cdf = lambda x: 0.5 * (1 + math.erf((x - mu) / (sd * math.sqrt(2))))          # noqa: E731
        edges = [i / self.BINS for i in range(self.BINS + 1)]                     # log10(MB) from 0 to 1
        mass = [cdf(b) - cdf(a) for a, b in zip(edges, edges[1:])]
        raw = [total * m / sum(mass) for m in mass]                               # truncated to [1, 10] MB
        self.target = [int(r) for r in raw]
        for i in sorted(range(self.BINS), key=lambda i: raw[i] - int(raw[i]), reverse=True)[:total - sum(self.target)]:
            self.target[i] += 1                                                   # largest remainder
        self.filled = [0] * self.BINS
        self.shas: set[str] = set()
        self.lock = threading.Lock()

    def bin(self, size: int) -> int:
        return min(self.BINS - 1, max(0, int(math.log10(size / 1e6) * self.BINS)))

    def wants(self, size: int) -> bool:
        with self.lock:
            return PDF_MIN < size < PDF_MAX and self.filled[self.bin(size)] < self.target[self.bin(size)]

    def take(self, size: int, sha: str) -> bool:
        with self.lock:
            if sha in self.shas or not (PDF_MIN < size < PDF_MAX) or self.filled[self.bin(size)] >= self.target[self.bin(size)]:
                return False
            self.filled[self.bin(size)] += 1
            self.shas.add(sha)
            return True

    def full(self) -> bool:
        with self.lock:
            return self.filled == self.target

    def describe(self) -> str:
        return " ".join(f"{f}/{t}" for f, t in zip(self.filled, self.target))


QUOTA: SizeQuota | None = None


def fetch_pdfs(site: dict, candidates: list[str], pdf_count: list[int], pdf_lock: threading.Lock) -> int:
    """Up to PDF_PER_SITE PDFs from this site's links that fit the size quota, one request at a time per host.
    Each checked URL is logged with its size (url<TAB>bytes), so a later top-up needn't ask again."""
    slug = site["slug"]
    d = OUT / "pdfs" / slug
    d.mkdir(parents=True, exist_ok=True)
    have = len(list(d.glob("*.pdf")))
    seen_f = OUT / "pdfs" / f"{slug}.checked"
    checked = {ln.split("\t")[0] for ln in seen_f.read_text(encoding="utf-8").split("\n")} if seen_f.exists() else set()
    cands = [u for u in dict.fromkeys(candidates) if u not in checked
             and (urllib.parse.urlsplit(u).hostname or "").endswith(site["domain"])]
    random.Random(slug + "pdf").shuffle(cands)
    last: dict[str, float] = {}
    for url in cands[:PDF_CHECKS_PER_SITE]:
        if QUOTA.full() or have >= PDF_PER_SITE:
            break
        host = urllib.parse.urlsplit(url).hostname
        if not ROBOTS.allowed(url):
            continue
        time.sleep(max(0.0, ROBOTS.delay(host) - (time.monotonic() - last.get(host, 0))))
        last[host] = time.monotonic()
        size, buf = 0, b""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60, context=TLS) as r:
                size = int(r.headers.get("Content-Length") or 0)
                ctype = r.headers.get("Content-Type", "").lower()
                if ("pdf" in ctype or "octet-stream" in ctype) and (not size or QUOTA.wants(size)):
                    buf = r.read(PDF_MAX + 1)              # otherwise close after the headers
        except Exception:
            pass
        with seen_f.open("a", encoding="utf-8") as f:
            f.write(f"{url}\t{size or len(buf)}\n")
        if not buf.startswith(b"%PDF"):
            continue
        sha = hashlib.sha256(buf).hexdigest()
        if not QUOTA.take(len(buf), sha):
            continue
        name = re.sub(r"[^\w.-]+", "_", Path(urllib.parse.urlsplit(url).path).name)[:80] or "doc"
        name += "" if name.lower().endswith(".pdf") else ".pdf"
        with pdf_lock:
            pdf_count[0] += 1
        (d / f"{sha[:10]}_{name}").write_bytes(buf)
        with (OUT / "pdfs" / "downloads.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"site": slug, "url": url, "file": f"{slug}/{sha[:10]}_{name}", "bytes": len(buf),
                                "sha256": sha, "at": now()}) + "\n")
        have += 1
        say(f"[{slug}] pdf {have} ({len(buf) / 1e6:.1f} MB); total {pdf_count[0]}; bins {QUOTA.describe()}")
    return have


def load_quota() -> SizeQuota:
    """The quota, with PDFs already downloaded counted in."""
    """The quota, with PDFs already downloaded counted in; any that no longer fit go to pdfs/_excess/."""
    q = SizeQuota()
    f = OUT / "pdfs" / "downloads.jsonl"
    kept = []
    for ln in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        r = json.loads(ln)
        src = OUT / "pdfs" / r["file"]
        if not src.exists():
            continue
        if q.take(r["bytes"], r["sha256"]):
            kept.append(ln)
            continue
        dst = OUT / "pdfs" / "_excess" / r["file"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dst)
        say(f"over quota, moved to _excess: {r['file']} ({r['bytes'] / 1e6:.1f} MB)")
    if f.exists():
        f.write_text("".join(k + "\n" for k in kept), encoding="utf-8")
    return q


def safe_crawl(site: dict, pdf_count: list[int], pdf_lock: threading.Lock) -> dict:
    """One site's crash is logged and doesn't end the others."""
    try:
        return crawl_site(site, pdf_count, pdf_lock)
    except Exception as e:
        say(f"[{site['slug']}] crashed: {e!r}")
        return {"slug": site["slug"], "error": repr(e)}


def crawl(sites_file: str = "sites.json") -> None:
    sites = json.loads((OUT / sites_file).read_text())
    for s in sites:                                       # warm robots for each host
        ROBOTS.get(s["host"])
    global QUOTA
    QUOTA = load_quota()
    say(f"PDF size quota (1-10 MB, log bins): {QUOTA.describe()}")
    pdf_count, lock = [sum(QUOTA.filled)], threading.Lock()
    with ThreadPoolExecutor(WORKERS) as ex:               # biggest tiers first so they finish in time
        res = list(ex.map(lambda s: safe_crawl(s, pdf_count, lock), sorted(sites, key=lambda s: -s["tier"])))
    (OUT / f"crawl_summary_{Path(sites_file).stem}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    say(json.dumps(res))


if __name__ == "__main__":
    NO_PDFS = "--no-pdfs" in sys.argv
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    if sys.argv[1] == "survey":
        survey(args or None)
    elif sys.argv[1] == "crawl":
        crawl(*args)
    else:
        {"plan": plan, "crawl": crawl}[sys.argv[1]]()
