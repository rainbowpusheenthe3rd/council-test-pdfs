# Council test PDFs

Public PDFs from UK council websites, for testing PDF tooling (pypdf, docling, Pillow…). **Temporary repo.**

| Asset | Files | Sizes |
|---|---|---|
| `council_pdfs_1-10MB.zip` | 196 | 1–10 MB, log-normal, centred ≈4.5 MB |
| `council_pdfs_100KB-1MB.zip` | 50 | 100 KB–1 MB, even across 5 log bins (a sanity set) |

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
