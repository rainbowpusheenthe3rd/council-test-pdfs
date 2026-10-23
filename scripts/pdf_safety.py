"""Check every test PDF before it's shared: active content and residents' personal data → dataset/pdf_safety.csv.

A PDF is excluded (moved to <set>/_unsafe/) if it has any of:
  * JavaScript, a Launch action, embedded files or rich media: raw-byte markers, plus pypdf's view of the
    catalogue, OpenAction and page actions (raw markers can hide inside compressed object streams)
  * 3+ personal webmail addresses in its text: usually residents' details (objections, consultation responses)
Windows Defender scans the folders separately (see the README); a detection there also excludes a file.

    python pdf_safety.py
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from pypdf import PdfReader

D = Path(__file__).parent / "dataset"
SETS = [D / "pdfs", D / "pdfs_small"]
RAW = {k: re.compile(rb"/" + k.encode() + rb"\b") for k in
       ("JavaScript", "JS", "Launch", "EmbeddedFile", "RichMedia", "OpenAction", "AA", "XFA", "SubmitForm")}
BLOCK = {"JavaScript", "JS", "Launch", "EmbeddedFile", "RichMedia", "SubmitForm"}
WEBMAIL = re.compile(r"\b[\w.+-]+@(?:gmail|googlemail|hotmail|yahoo|outlook|live|btinternet|icloud|aol|sky|msn|"
                     r"virginmedia|talktalk|ntlworld|me)\.(?:com|co\.uk|net)\b", re.I)


def structural(r: PdfReader) -> set[str]:
    """Active content as pypdf sees it, whatever the compression."""
    out = set()
    root = r.trailer["/Root"]
    names = root.get("/Names")
    names = names.get_object() if names else {}
    if "/JavaScript" in names:
        out.add("JavaScript")
    if "/EmbeddedFiles" in names:
        out.add("EmbeddedFile")
    oa = root.get("/OpenAction")
    oa = oa.get_object() if oa is not None else None
    if isinstance(oa, dict) and oa.get("/S") in ("/JavaScript", "/Launch"):
        out.add(str(oa["/S"])[1:])
    for p in r.pages[:50]:
        aa = p.get("/AA")
        if aa is not None:
            for v in aa.get_object().values():
                if v.get_object().get("/S") in ("/JavaScript", "/Launch"):
                    out.add(str(v.get_object()["/S"])[1:])
    return out


def check(path: Path) -> dict:
    data = path.read_bytes()
    raw = {k for k, rx in RAW.items() if rx.search(data)}
    row = {"file": str(path.relative_to(D)), "bytes": len(data), "raw_markers": " ".join(sorted(raw)),
           "active": "", "webmail": 0, "error": "", "verdict": "ok"}
    try:
        r = PdfReader(str(path))
        if r.is_encrypted:
            r.decrypt("")
        active = structural(r)
        row["active"] = " ".join(sorted(active))
        text = " ".join((p.extract_text() or "") for p in r.pages[:40])
        row["webmail"] = len(set(m.lower() for m in WEBMAIL.findall(text)))
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:100]
        active = set()
    if (raw | active) & BLOCK:
        row["verdict"] = "excluded: active content"
    elif row["webmail"] >= 3:
        row["verdict"] = "excluded: personal emails"
    return row


def main() -> None:
    rows = []
    for s in SETS:
        for p in sorted(s.glob("*/*.pdf")):
            if p.parent.name.startswith("_"):
                continue
            row = check(p)
            rows.append(row)
            if row["verdict"] != "ok":
                dst = s / "_unsafe" / p.relative_to(s)
                dst.parent.mkdir(parents=True, exist_ok=True)
                p.replace(dst)
                print(f"{row['verdict']:<28} {row['file']}  [{row['raw_markers']}|{row['active']}|{row['webmail']}]")
    with (D / "pdf_safety.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if r["verdict"] != "ok"]
    print(f"{len(rows)} checked, {len(bad)} excluded, {sum(1 for r in rows if r['error'])} unparseable by pypdf (kept)")


if __name__ == "__main__":
    main()
