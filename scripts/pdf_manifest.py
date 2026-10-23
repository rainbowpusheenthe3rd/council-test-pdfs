"""Describe each downloaded test PDF → dataset/pdfs.csv (committed; the PDFs themselves are not).

Columns: file, site, url, bytes, sha256, pages, pdf_version, encrypted, text_layer (chars of text on the first
three pages: near 0 means scanned, the OCR case for docling), images_first5 (embedded images on the first
five pages: Pillow work), producer, opens (pypdf could parse it), error.

    python pdf_manifest.py
    python pdf_manifest.py --fetch     # re-download from pdfs.csv and check sha256 (rebuild on another machine)
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from pypdf import PdfReader

from dataset_crawl import TLS, UA

D = Path(__file__).parent / "dataset"
PDFS, CSV = D / "pdfs", D / "pdfs.csv"
COLS = ["file", "site", "url", "bytes", "sha256", "pages", "pdf_version", "encrypted", "text_layer",
        "images_first5", "producer", "opens", "error"]


def describe(path: Path) -> dict:
    """What a parser test cares about in one PDF."""
    out = {"pages": "", "pdf_version": "", "encrypted": "", "text_layer": "", "images_first5": "",
           "producer": "", "opens": False, "error": ""}
    try:
        r = PdfReader(str(path))
        out["encrypted"] = r.is_encrypted
        if r.is_encrypted:
            r.decrypt("")                                    # most "encrypted" council PDFs have an empty user password
        out["pages"] = len(r.pages)
        out["pdf_version"] = r.pdf_header.replace("%PDF-", "")
        out["producer"] = str((r.metadata or {}).get("/Producer", ""))[:60]
        out["text_layer"] = sum(len((p.extract_text() or "").strip()) for p in r.pages[:3])
        out["images_first5"] = sum(len(p.images) for p in r.pages[:5])
        out["opens"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:120]
    return out


def build(pdfs: Path = PDFS, out: Path = CSV) -> None:
    rows = []
    for ln in (pdfs / "downloads.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(ln)
        p = pdfs / d["file"]
        if p.exists():
            rows.append({"file": d["file"], "site": d["site"], "url": d["url"], "bytes": d["bytes"],
                         "sha256": d["sha256"], **describe(p)})
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)
    scanned = sum(1 for r in rows if r["opens"] and int(r["text_layer"] or 0) < 50)
    print(f"{out.name}: {len(rows)} PDFs, {sum(r['bytes'] for r in rows) / 1e6:.0f} MB; {sum(not r['opens'] for r in rows)} "
          f"fail to open, {sum(r['encrypted'] is True for r in rows)} encrypted, {scanned} with little or no text layer")


def fetch() -> None:
    """Rebuild the PDF set elsewhere from pdfs.csv, slowly, checking each hash."""
    import time
    for r in csv.DictReader(CSV.open(encoding="utf-8")):
        p = PDFS / r["file"]
        if p.exists():
            continue
        req = urllib.request.Request(r["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60, context=TLS) as resp:
            buf = resp.read()
        ok = hashlib.sha256(buf).hexdigest() == r["sha256"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(buf)
        print(("ok      " if ok else "CHANGED ") + r["file"])
        time.sleep(5)


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    else:
        build()
        if (D / "pdfs_small" / "downloads.jsonl").exists():
            build(D / "pdfs_small", D / "pdfs_small.csv")
