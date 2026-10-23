# Council test PDFs

Public PDFs from UK council websites, collected 23 October 2026, for testing PDF tooling (pypdf, docling,
Pillow…). **This is a temporary repo.**

| Release asset | Files | Councils | Sizes | Median |
|---|---|---|---|---|
| [`council_pdfs_1-10MB.zip`](../../releases/download/v1/council_pdfs_1-10MB.zip) | 196 | 24 | 1–10 MB, log-normal, weighted towards larger files | 4.2 MB |
| [`council_pdfs_100KB-1MB.zip`](../../releases/download/v1/council_pdfs_100KB-1MB.zip) | 50 | 36 | 100 KB–1 MB, even across log bins (a sanity set) | 0.35 MB |

Each zip contains `pdfs/<council>/<sha256-prefix>_<name>.pdf`, plus `manifest.csv` and `safety.csv`. The same
two CSVs are in this repo under [`manifests/`](manifests/) and [`scans/`](scans/).

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
crawl), `pdf_harvest.py`, `small_pdfs.py`, `pdf_safety.py`, `pdf_manifest.py` and `publish_pdfs.py`.

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
| **Antivirus** | Windows Defender (`MpCmdRun -Scan -ScanType 3`) | **Not yet run.** It was blocked by a tool permission during collection. Until it's run, treat the files like any downloaded document |

Excluding files reshaped the size distribution, so after each round of exclusions the bins were topped up
and the new files checked again. It took four rounds.

---

## Licence and reuse

The documents belong to the councils that published them, and the source URL of each is in the manifest. Many
are under the Open Government Licence, but not all; check the source page before using a file for anything
beyond testing.
