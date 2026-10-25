"""Zip the checked PDF test sets and publish them as release assets on a public GitHub repo.

    python publish_pdfs.py                # zips → dataset/release/, then creates the repo and the release
    python publish_pdfs.py --parts        # every set in parts of ≤50 MB → release v3

Each zip carries its manifest (pdfs.csv / pdfs_small.csv) and the safety report. Files are stored, not
deflated: PDFs are already compressed. The repo gets only a README; the zips are release assets (git
can't hold ~1 GB). Commits use the account's noreply address.
"""
from __future__ import annotations

import shutil
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


PART_MB = 50                                                  # Explorer's zip handling chokes near 1 GB


def zip_set(name: str, folder: Path, manifest: Path, extra: tuple[Path, ...] = (D / "pdf_safety.csv",)) -> list[str]:
    """Zip a set as self-contained parts of at most PART_MB (not a split archive: each part opens on its own).
    Every part carries the full manifest. Entries sit under a folder named for the set, so every zip in the
    release can be extracted into one directory without clashes. Returns the part filenames."""
    keep = (lambda p: p.is_file() and p.name not in ("LICENSE", "files.json")) if folder.name == "reference" \
        else (lambda p: p.suffix.lower() == ".pdf")             # pypdf's tests also fetch the PNG/TIFF they compare to
    pdfs = sorted(p for p in folder.rglob("*") if keep(p)
                  and not any(s.startswith("_") for s in p.relative_to(folder).parts))
    parts, size = [[]], 0
    for p in pdfs:
        if parts[-1] and size + p.stat().st_size > PART_MB * 1e6:
            parts.append([])
            size = 0
        parts[-1].append(p)
        size += p.stat().st_size
    stem = name.removesuffix(".zip")
    names = [name] if len(parts) == 1 else [f"{stem}_part{i:02}of{len(parts):02}.zip" for i in range(1, len(parts) + 1)]
    for n, part in zip(names, parts):
        with zipfile.ZipFile(REL / n, "w", zipfile.ZIP_STORED) as z:
            for p in part:
                z.write(p, f"{stem}/pdfs/{p.relative_to(folder).as_posix()}")
            for lic in folder.rglob("LICENSE"):                 # upstream licences travel with their files
                z.write(lic, f"{stem}/pdfs/{lic.relative_to(folder).as_posix()}")
            z.write(manifest, f"{stem}/manifest.csv")
            for e in extra:
                z.write(e, f"{stem}/{e.name.replace('pdf_', '')}")
        print(f"{n}: {len(part)} PDFs, {(REL / n).stat().st_size / 1e6:.0f} MB")
    return names


def run(*cmd: str, cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=cwd)


def release_parts(tag: str = "v3") -> None:
    """Re-zip all three sets in parts and publish them as one release (the README is edited in the repo itself)."""
    shutil.rmtree(REL, ignore_errors=True)
    REL.mkdir()
    names = [n for s in SETS for n in zip_set(*s)]
    names += zip_set("reference_pdfs_pypdf_docling.zip", D / "reference", D / "reference.csv", extra=())
    run("gh", "release", "create", tag, *[str(REL / n) for n in names], "--repo", REPO, "--latest",
        "--title", f"Council test PDFs {tag}: every set in parts of ≤{PART_MB} MB",
        "--notes", f"All three sets (council 1–10 MB, council 100 KB–1 MB, pypdf/docling reference) as "
                   f"self-contained zips of at most {PART_MB} MB. Download every asset and extract them all into "
                   "one folder: each set lands in its own subfolder. See the README.")


def main() -> None:
    REL.mkdir(exist_ok=True)
    counts = [len(zip_set(*s)) for s in SETS]
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
    import sys
    release_parts() if "--parts" in sys.argv else main()
