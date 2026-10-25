# Council test PDFs

Public PDFs from UK council websites, collected 23 October 2026, for testing PDF tooling (pypdf, docling,
Pillow…). **This is a temporary repo.**

## Download everything

The [v3 release](../../releases/tag/v3) has 24 zips, each at most 50 MB. Each one is a self-contained zip,
not a piece of a split archive. Download them all into one folder and extract them all there:

```bash
gh release download v3 -R rainbowpusheenthe3rd/council-test-pdfs -D council-test-pdfs -p "*.zip"
cd council-test-pdfs && for z in *.zip; do unzip -oq "$z"; done
```

```powershell
gh release download v3 -R rainbowpusheenthe3rd/council-test-pdfs -D council-test-pdfs -p "*.zip"
Get-ChildItem council-test-pdfs\*.zip | ForEach-Object { Expand-Archive $_ -DestinationPath council-test-pdfs -Force }
```

The repo is public, so if `gh` isn't installed you can list the asset URLs at
`https://api.github.com/repos/rainbowpusheenthe3rd/council-test-pdfs/releases/tags/v3` and fetch each one.

Each set extracts into its own folder, so the parts merge cleanly:

| Folder | Zips | Files | Size | What |
|---|---|---|---|---|
| `council_pdfs_1-10MB/` | `council_pdfs_1-10MB_part01of19` … `part19of19` | 196 | 896 MB | Council PDFs of 1–10 MB (24 councils, log-normal sizes, median 4.2 MB) |
| `council_pdfs_100KB-1MB/` | `council_pdfs_100KB-1MB` | 50 | 20 MB | Council PDFs of 100 KB–1 MB, even across log bins (a sanity set, 36 councils) |
| `reference_pdfs_pypdf_docling/` | `reference_pdfs_pypdf_docling_part01of04` … `part04of04` | 142 | 159 MB | The files pypdf and docling test themselves against ([below](#pypdf-and-docling-reference-set)) |

Each folder holds `pdfs/<council or source>/…` plus `manifest.csv`. The council folders also have
`safety.csv`. Every part carries the full manifest, so overwriting it on extract is harmless. The CSVs are
also in this repo under [`manifests/`](manifests/) and [`scans/`](scans/). Older releases have the same files
in bigger zips: v1 as one 896 MB zip, v2 in parts of 200 MB.

---

## What's in the sets

### 1–10 MB set (196 files)

The size target was **log-normal**: log10(bytes) ~ N(mean 0.65, SD 0.25) in MB, which centres it on about
4.5 MB. Two SDs either side span 1–10 MB, and the curve is cut off at those limits. The range is split into
ten log-spaced bins with fixed quotas. A file was only kept if its bin still had room, so the shape is
designed, not left to chance.

| Bin (MB) | 1.0–1.26 | 1.26–1.58 | 1.58–2.0 | 2.0–2.5 | 2.5–3.2 | 3.2–4.0 | 4.0–5.0 | 5.0–6.3 | 6.3–7.9 | 7.9–10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Target | 2 | 5 | 10 | 17 | 25 | 32 | 35 | 32 | 25 | 17 |
| **Achieved** | 2 | 5 | 10 | 17 | 25 | 31 | 33 | 32 | 24 | 17 |

The set is 4 short of 200 because collection stopped at a deadline after the last safety exclusions.
Achieved: geometric mean 4.07 MB, log10 SD 0.216.

| Property (from pypdf) | Count | Useful for testing |
|---|---|---|
| Little or no text layer (<50 chars on pages 1–3) | 25 | Scanned: OCR paths in docling |
| pypdf can't parse | 3 | Error handling |
| Encrypted (empty user password) | 3 | Decryption path |
| PDF version 1.3 / 1.4 / 1.5 / 1.6 / 1.7 | 4 / 27 / 26 / 60 / 79 | Parser coverage |
| Pages | median 39, max 1,778 | Large-document behaviour |

Files per council: Northumberland 30, Leeds 27, West Sussex 18, Leicester 13, Staffordshire 12, Bradford 12,
Durham 11, Cheltenham 10, Nottinghamshire 9, Lambeth 9, Swindon 9, Bath & NE Somerset 7, York 5, Oxford 5,
North Yorkshire 4, Barnsley 3, Bolton 3, Rotherham 2, Sandwell 2, and 1 each from Wolverhampton,
Buckinghamshire, Devon, Worcestershire and Lancashire.

### 100 KB–1 MB set (50 files)

Ten files in each of five log-spaced bins (100–158–251–398–631–1000 KB), with at most 4 per council, from 36
councils. Median 0.35 MB, median 9 pages. 2 have little or no text layer; all 50 open in pypdf.

### pypdf and docling reference set (142 files)

The files each project's own test suite runs against, fetched 25 October 2026 from `main`. They're in
`pdfs/<source>/…`, and [`manifests/reference.csv`](manifests/reference.csv) lists each file's upstream URL,
sha256 and the same pypdf properties as the council manifests.

| Folder | Files | Size | Source | Licence |
|---|---|---|---|---|
| `pypdf_sample-files/` | 35 | 14 MB | [py-pdf/sample-files](https://github.com/py-pdf/sample-files), the submodule pypdf's `samples`-marked tests use. Includes upstream `files.json`, which describes each file | CC-BY-SA-4.0 (`LICENSE` included) |
| `pypdf_downloads/` | 67 | 88 MB | Every entry in pypdf's [`tests/example_files.yaml`](https://github.com/py-pdf/pypdf/blob/main/tests/example_files.yaml), which is what `download_test_pdfs()` fetches. Mostly PDFs attached to pypdf issues; 12 are the PNG, TIFF and raw-stream files that pypdf's image tests compare against | Various: check each file's source URL |
| `docling/` | 40 | 57 MB | The PDFs under docling's [`tests/data/`](https://github.com/docling-project/docling/tree/main/tests/data) (`pdf/`, `pdf_password/`, `ocr/`, `odf/`). `latex/` was left out because its PDFs are figure assets inside LaTeX sources, not test inputs | MIT (`LICENSE` included) |

Of the 130 PDFs, **9 don't open in pypdf** and 4 are encrypted. Upstream broke some on purpose: truncated
files, bad xrefs and a PNG named `.pdf`. 38 have little or no text layer. These are test fixtures, so the
council active-content filter was **not** applied: some have attachments, forms or JavaScript by design.
Defender found no threats.

---

## Collection methodology

1. **Which councils.** 56 English, Scottish and Welsh council sites were candidates. A council was used only
   if its `robots.txt` could be read over verified TLS and allowed our agent and `*`. Councils were skipped
   for any of these:
   - `robots.txt` returned 403 (Manchester, Glasgow, Kent, Cardiff, Norfolk, Trafford, Sunderland,
     Brighton & Hove)
   - `robots.txt` was an HTML page served by a firewall (Southampton)
   - the home page was disallowed (Liverpool)
   - bot protection was hit during crawling (Birmingham, Wolverhampton, Coventry). Firecrawl asked to
     escalate to a stealth proxy, and we **did not**: crawling stopped and that council was never revisited.
2. **Finding PDFs.** PDF links came from three places:
   - a council's own pages, scraped through a self-hosted [Firecrawl](https://github.com/firecrawl/firecrawl)
     v2.11.0 as part of a separate page crawl
   - one Firecrawl `map` call per council, searching for document-heavy pages
   - those pages fetched directly, with their `href`s extracted
3. **Politeness.** For every URL:
   - `robots.txt` was checked, and any `Crawl-delay` honoured, with a 5-second minimum between requests to
     the same council
   - **one request per council at a time**, and no council was hit by two of our processes at once
   - the user agent was `Mozilla/5.0 (compatible; council-pii-research/0.1; low-rate, respects robots.txt)`
   - 15 failures in a row stopped a council for good
4. **Size check before download.** Each candidate URL got a single GET, and the `Content-Length` and
   `Content-Type` headers were read first. The body was downloaded only if it was a PDF and its size bin
   still had room. Files were accepted only if they start with `%PDF`, fall within the size range and aren't
   duplicates by sha256.
5. **Small set.** The 1–10 MB pass logged the size of every URL it checked. The 100 KB–1 MB set was picked
   from those logs, so no new discovery was needed, and downloaded under the same rules.

The scripts are in [`scripts/`](scripts/): `dataset_crawl.py` (shared robots, TLS, size-quota code and the page
crawl), `pdf_harvest.py`, `small_pdfs.py`, `pdf_safety.py`, `pdf_manifest.py`, `reference_pdfs.py` (the pypdf
and docling set) and `publish_pdfs.py` (`--parts` builds the 50 MB parts).

---

## Scans

Every published file passed every check below. The results for the published files are in
[`scans/safety.csv`](scans/safety.csv), and the full list of excluded files with reasons is in
[`scans/excluded.json`](scans/excluded.json).

| Check | How | Result |
|---|---|---|
| **Active content** | Raw-byte markers (`/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile`, `/RichMedia`, `/SubmitForm`), **plus** pypdf's structural view (catalogue `/Names` JavaScript and EmbeddedFiles, `/OpenAction`, page `/AA` actions), because raw markers can hide inside compressed object streams | **68 files excluded**: 59 with JavaScript (mostly Acrobat form-field format and calculation scripts), 11 with embedded files (mostly Swindon flood-map figures). By council: Leeds 23, Swindon 12, Northumberland 9, Lambeth 5, and 19 across 11 others |
| **Residents' personal data** | Text from up to 40 pages per file, searched for personal webmail addresses (gmail, hotmail, yahoo, outlook, btinternet and others). 3 or more would exclude a file, as a sign of objections or consultation responses | 0 files excluded. **No published file contains any personal webmail address** |
| **Benign actions kept** | `/OpenAction` (17 files) and `/AA` (24) without JavaScript or Launch: these set the opening view or zoom | Kept |
| **Integrity** | `%PDF` header, sha256 per file in the manifest | All pass |
| **Antivirus** | Windows Defender (`MpCmdRun -Scan -ScanType 3`) | Run 25 October 2026 on both council sets, including the excluded files, and on the reference set: **no threats found** |

Excluding files reshaped the size distribution, so after each round of exclusions the bins were topped up
and the new files checked again. It took four rounds.

---

## Licence and reuse

The documents belong to the councils that published them, and the source URL of each is in the manifest. Many
are under the Open Government Licence, but not all; check the source page before using a file for anything
beyond testing.
