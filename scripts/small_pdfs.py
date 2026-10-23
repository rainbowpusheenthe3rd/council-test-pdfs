"""A 50-file sanity set of small PDFs (100 KB–1 MB) → dataset/pdfs_small/, from sizes the harvest already saw.

The main harvest logs every URL it checked with its Content-Length (pdfs/<site>.checked). The ones under
1 MB were skipped there; this picks 50 of them, 10 in each of five log-spaced bins (100–158–251–398–631–1000 KB),
spread across councils, and downloads them one request per host every 5 seconds (robots.txt still checked).
Run it after pdf_harvest.py has finished, so no host gets two of our requests at once.

    python small_pdfs.py
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dataset_crawl as C

LO, HI, BINS, PER_BIN = 100_000, 1_000_000, 5, 10
OUT = C.OUT / "pdfs_small"


def bin_of(size: int) -> int:
    return min(BINS - 1, int(math.log10(size / LO) / math.log10(HI / LO) * BINS))


def candidates() -> dict[str, list[tuple[str, int]]]:
    """(url, size) per host from every .checked log, sizes within range, shuffled."""
    by_host = defaultdict(list)
    for f in (C.OUT / "pdfs").glob("*.checked"):
        for ln in f.read_text(encoding="utf-8").splitlines():
            url, _, size = ln.partition("\t")
            if size.isdigit() and LO < int(size) < HI:
                by_host[urllib.parse.urlsplit(url).hostname].append((url, int(size)))
    rng = random.Random(7)
    for v in by_host.values():
        rng.shuffle(v)
    return by_host


def main() -> None:
    filled, lock, shas = [0] * BINS, __import__("threading").Lock(), set()
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "downloads.jsonl"
    for ln in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
        r = json.loads(ln)
        if not (OUT / r["file"]).exists():                    # excluded by the safety check: refill its bin
            continue
        filled[bin_of(r["bytes"])] += 1
        shas.add(r["sha256"])
    by_host = candidates()
    C.say(f"small-PDF candidates: {sum(map(len, by_host.values()))} across {len(by_host)} hosts; bins {filled}")

    def run(host: str) -> None:
        per_host = 0
        for url, size in by_host[host]:
            b = bin_of(size)
            with lock:
                if all(f >= PER_BIN for f in filled) or filled[b] >= PER_BIN:
                    if all(f >= PER_BIN for f in filled):
                        return
                    continue
            if per_host >= 4 or not C.ROBOTS.allowed(url):    # at most 4 per council, for spread
                continue
            time.sleep(C.ROBOTS.delay(host))
            try:
                req = urllib.request.Request(url, headers={"User-Agent": C.UA})
                with urllib.request.urlopen(req, timeout=60, context=C.TLS) as r:
                    buf = r.read(HI + 1)
            except Exception:
                continue
            if not buf.startswith(b"%PDF") or not LO < len(buf) < HI:
                continue
            sha = hashlib.sha256(buf).hexdigest()
            b = bin_of(len(buf))
            with lock:
                if sha in shas or filled[b] >= PER_BIN:
                    continue
                filled[b] += 1
                shas.add(sha)
            site = host.removeprefix("www.").split(".")[0]
            name = re.sub(r"[^\w.-]+", "_", Path(urllib.parse.urlsplit(url).path).name)[:80] or "doc"
            name += "" if name.lower().endswith(".pdf") else ".pdf"
            (OUT / site).mkdir(exist_ok=True)
            (OUT / site / f"{sha[:10]}_{name}").write_bytes(buf)
            with lock:
                with log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"site": site, "url": url, "file": f"{site}/{sha[:10]}_{name}",
                                        "bytes": len(buf), "sha256": sha, "at": C.now()}) + "\n")
            per_host += 1
            C.say(f"[{site}] small pdf ({len(buf) / 1e3:.0f} KB); bins {filled}")

    with ThreadPoolExecutor(len(by_host) or 1) as ex:
        list(ex.map(run, by_host))
    C.say(f"small set done: bins {filled}, total {sum(filled)}")


if __name__ == "__main__":
    main()
