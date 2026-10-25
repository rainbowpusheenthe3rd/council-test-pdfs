"""The PDFs pypdf and docling test themselves against → dataset/reference/, with dataset/reference.csv.

  * pypdf_sample-files/  py-pdf/sample-files, the submodule pypdf's `samples` tests use (CC-BY-SA-4.0)
  * pypdf_downloads/     every file in pypdf's tests/example_files.yaml, what `download_test_pdfs()` fetches
  * docling/             the PDFs under docling's tests/data/ (MIT); latex/ is skipped, those are figure
                         assets inside LaTeX sources, not PDF test cases

These are test fixtures and some are deliberately odd (attachments, forms, broken xrefs, passwords), so the
council safety filter is not applied; Defender still scans them.

    python reference_pdfs.py
"""
from __future__ import annotations

import csv
import hashlib
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml

from dataset_crawl import TLS, UA
from pdf_manifest import describe

D = Path(__file__).parent / "dataset"
OUT, CSV = D / "reference", D / "reference.csv"
YAML = "https://raw.githubusercontent.com/py-pdf/pypdf/main/tests/example_files.yaml"
COLS = ["file", "source", "url", "bytes", "sha256", "pages", "pdf_version", "encrypted", "text_layer",
        "images_first5", "producer", "opens", "error"]


def clone(repo: str, dest: Path, sparse: str | None = None) -> None:
    cmd = ["git", "clone", "-q", "--depth", "1", f"https://github.com/{repo}.git", str(dest)]
    if sparse:
        cmd[3:3] = ["--filter=blob:none", "--sparse"]
    subprocess.run(cmd, check=True)
    if sparse:
        subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", sparse], check=True)


def copy_pdfs(src: Path, dest: Path, repo: str, skip: str | None = None) -> list[dict]:
    rows = []
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src).as_posix()
        if p.suffix.lower() != ".pdf" or ".git/" in rel or (skip and rel.startswith(skip)):
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest / rel)
        rows.append({"file": f"{dest.name}/{rel}", "source": repo,
                     "url": f"https://github.com/{repo}/blob/main/{rel}"})
    for lic in ("LICENSE", "files.json"):
        if (src / lic).exists():
            shutil.copy2(src / lic, dest / lic)
    return rows


def downloads(dest: Path) -> list[dict]:
    with urllib.request.urlopen(urllib.request.Request(YAML, headers={"User-Agent": UA}), context=TLS) as r:
        entries = yaml.safe_load(r.read())
    dest.mkdir(parents=True, exist_ok=True)
    rows, failed = [], []
    for e in entries:
        p = dest / e["local_filename"]
        if not p.exists():
            try:
                req = urllib.request.Request(e["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60, context=TLS) as r:
                    p.write_bytes(r.read())
            except Exception as ex:
                failed.append(f"{e['url']}: {ex}")
                continue
            time.sleep(1)
        rows.append({"file": f"{dest.name}/{e['local_filename']}", "source": "py-pdf/pypdf example_files.yaml",
                     "url": e["url"]})
    for f in failed:
        print("failed", f)
    print(f"pypdf downloads: {len(rows)} of {len(entries)}")
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        clone("py-pdf/sample-files", t / "sf")
        rows += copy_pdfs(t / "sf", OUT / "pypdf_sample-files", "py-pdf/sample-files")
        clone("docling-project/docling", t / "dl", sparse="tests/data")
        rows += copy_pdfs(t / "dl" / "tests" / "data", OUT / "docling", "docling-project/docling", skip="latex/")
    lic = "https://raw.githubusercontent.com/docling-project/docling/main/LICENSE"
    with urllib.request.urlopen(urllib.request.Request(lic, headers={"User-Agent": UA}), context=TLS) as r:
        (OUT / "docling" / "LICENSE").write_bytes(r.read())
    rows += downloads(OUT / "pypdf_downloads")
    for r in rows:
        p = OUT / r["file"]
        buf = p.read_bytes()
        r.update(bytes=len(buf), sha256=hashlib.sha256(buf).hexdigest(), **describe(p))
        if "docling-project" in r["source"]:
            r["url"] = r["url"].replace("/blob/main/", "/blob/main/tests/data/")
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"{CSV.name}: {len(rows)} PDFs, {sum(r['bytes'] for r in rows) / 1e6:.0f} MB, "
          f"{sum(not r['opens'] for r in rows)} pypdf can't open")


if __name__ == "__main__":
    main()
