"""Zip the checked PDF test sets and publish them as release assets on a public GitHub repo.

    python publish_pdfs.py                # zips → dataset/release/, then creates the repo and the release

Each zip carries its manifest (pdfs.csv / pdfs_small.csv) and the safety report. Files are stored, not
deflated: PDFs are already compressed. The repo gets only a README; the zips are release assets (git
can't hold ~1 GB). Commits use the account's noreply address.
"""
from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path

D = Path(__file__).parent / "dataset"
REL = D / "release"
REPO = "rainbowpusheenthe3rd/council-test-pdfs"
NOREPLY = "89914787+rainbowpusheenthe3rd@users.noreply.github.com"
SETS = [("council_pdfs_1-10MB.zip", D / "pdfs", D / "pdfs.csv"),
        ("council_pdfs_100KB-1MB.zip", D / "pdfs_small", D / "pdfs_small.csv")]

README = """# Council test PDFs

Public PDFs from UK council websites, for testing PDF tooling (pypdf, docling, Pillow…). **Temporary repo.**

| Asset | Files | Sizes |
|---|---|---|
| `council_pdfs_1-10MB.zip` | {n_big} | 1–10 MB, log-normal, centred ≈4.5 MB |
| `council_pdfs_100KB-1MB.zip` | {n_small} | 100 KB–1 MB, even across 5 log bins (a sanity set) |

Download them from the [release](../../releases/latest). Each zip contains:
- `manifest.csv`: source URL, sha256, bytes, pages, PDF version, encrypted, text-layer chars (near 0 = scanned),
  images on the first 5 pages, producer, whether pypdf opens it
- `safety.csv`: the checks each file passed

**How they were collected:** robots.txt checked for every URL, one request per council at a time, at least
5 seconds apart. Sites with bot protection were not crawled.

**Checks before publishing:** Windows Defender scan; no JavaScript, Launch actions, embedded files, rich media or
submit-forms (raw markers and pypdf's structural view); no files containing three or more personal webmail
addresses (a sign of residents' details).

The documents belong to the councils that published them. Many are Open Government Licence; check the source
page before reusing one beyond testing.
"""


def zip_set(name: str, folder: Path, manifest: Path) -> int:
    pdfs = sorted(p for p in folder.glob("*/*.pdf") if not p.parent.name.startswith("_"))
    with zipfile.ZipFile(REL / name, "w", zipfile.ZIP_STORED) as z:
        for p in pdfs:
            z.write(p, f"pdfs/{p.relative_to(folder).as_posix()}")
        z.write(manifest, "manifest.csv")
        z.write(D / "pdf_safety.csv", "safety.csv")
    print(f"{name}: {len(pdfs)} PDFs, {(REL / name).stat().st_size / 1e6:.0f} MB")
    return len(pdfs)


def run(*cmd: str, cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=cwd)


def main() -> None:
    REL.mkdir(exist_ok=True)
    counts = [zip_set(*s) for s in SETS]
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "README.md").write_text(README.format(n_big=counts[0], n_small=counts[1]), encoding="utf-8")
        run("git", "init", "-q", "-b", "main", cwd=t)
        run("git", "add", "README.md", cwd=t)
        run("git", "-c", "user.name=rainbowpusheenthe3rd", "-c", f"user.email={NOREPLY}",
            "commit", "-q", "-m", "Council test PDFs: README", cwd=t)
        run("gh", "repo", "create", REPO, "--public", "--source", str(t), "--push",
            "--description", "Temporary: UK council PDFs for testing PDF tooling")
    run("gh", "release", "create", "v1", *[str(REL / s[0]) for s in SETS], "--repo", REPO,
        "--title", "Council test PDFs v1", "--notes", f"{counts[0]} PDFs of 1–10 MB and {counts[1]} of 100 KB–1 MB.")


if __name__ == "__main__":
    main()
