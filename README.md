<!-- OWNERSHIP: tooling -->
# bi-scraper — PCPM/TPD Study Corpus Builder

Personal-use study corpus builder for the PCPM/TPD program. It fetches **public
Bank Indonesia pages only** (`bi.go.id`), stores raw snapshots + structured
records in SQLite (with FTS5 search), ingests my own chapter summaries from
`data/inbox/`, and exports NotebookLM-ready study packs and public-data-only
portfolio charts.

> **No-gated-scraping statement.** This tool never fetches, mirrors, or bypasses
> login-walled, paywalled, or DRM-locked content. `pejuang.berkarirbi.id` and
> BIReady Masternotes are **read-in-browser only** — they are blocked at the HTTP
> layer and are never downloaded, and no PDF-secure / login / paywall protection
> is ever bypassed. Chapter 7 (Wawasan Kebangsaan) uses general public pages only
> and is expected to be thin; that is reported honestly instead of padded.

## Install

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Python 3.10+ is required (typed codebase).

## Environment (by reference only)

Credentials are read from process environment variables via `os.getenv(...)`.
If the hub `.env` (`C:\personal\naquuuu\.env`) exists it is loaded **by
reference** at startup (`BI_SCRAPER_HUB_ENV` overrides the path); values are
never copied into this repository. `.env.example` contains empty placeholders
only. All scraping targets are public pages, so no secrets are required to run.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `BI_SCRAPER_HUB_ENV` | `C:\personal\naquuuu\.env` | Optional hub env file loaded by reference |
| `BI_SCRAPER_DATA_DIR` | `data/` | Corpus root |
| `BI_SCRAPER_DB` | `data/bi_study.db` | SQLite database |
| `BI_SCRAPER_EXPORTS_DIR` | `exports/` | Study pack / portfolio output |

## CLI (Typer)

```powershell
bi-scraper fetch --chapter all            # incremental: only docs newer than stored, end = today
bi-scraper fetch --chapter 2 --start-date 2026-01-01 --end-date 2026-09-01
bi-scraper fetch --chapter 2 --full       # explicit full refetch (ignores stored newest date)
bi-scraper enrich                         # scrape the full text behind stored links (HTML + public PDFs)
bi-scraper enrich --chapter 2 --limit 5   # bounded enrichment run
bi-scraper ingest-pdf --chapter 5 --path "<file.pdf>" --url <canonical-url>  # local PDF (server-blocked download)
bi-scraper audit-visuals                  # flag image-heavy pages for manual reading (no network)
bi-scraper ingest-inbox                   # tag data/inbox/*.md chapters 1-8 and index alongside corpus
bi-scraper index --rebuild                # rebuild the FTS5 index
bi-scraper export-notebook --chapter 2    # .md -> exports/notebook/ ; .txt -> exports/notebook_txt/ (same run)
bi-scraper export-notebook --chapter 2 --no-txt  # markdown only (rare; default is both)
bi-scraper export-portfolio --chapter 2   # public-data-only charts + my analysis
bi-scraper coverage                       # chapter vs doc count vs newest date (exit 1 on FAIL)
bi-scraper search "inflasi"               # FTS5 full-text search across public docs + my notes
```

## Chapter map & pinned syllabus versions

| # | Chapter | Syllabus pin | Primary public sources (bi.go.id) | Expected thickness |
| :-: | :--- | :--- | :--- | :--- |
| 1 | Pengenalan BI | v1.9 — 9 Sep 2026 | `tentang-bi/profil`, `sejarah-bi`, `organisasi`, `uu-bi`, `transformasi` | good |
| 2 | Inflasi + Nilai Tukar | v1.2 — 18 Jul 2026 | BI-Rate date-range table (POST), JISDOR, kurs transaksi/reference, inflasi | good |
| 3 | Kebijakan Moneter | v1.2 — 6 Jul 2026 | news-release + governor speeches listing → PDF/page **metadata only** | good |
| 4 | SSK + Makroprudensial | v1.5 — 29 Agu 2026 | `stabilitas-sistem-keuangan` overview, macroprudential instruments, reports | good |
| 5 | Sistem Pembayaran | v1.3 — 24 Agu 2026 | `fungsi-utama/sistem-pembayaran` pages, Blueprint SPI, SPIP statistics | good |
| 6 | Uang Rupiah | v1.1 — 20 Agu 2026 | `/id/rupiah/` (gambar-uang, uang-dicabut, anti-palsu, CBP, digital rupiah) | good |
| 7 | Wawasan Kebangsaan | v1.2 — 31 Agu 2026 | general public pages only (no gated/course sources) | **thin — reported honestly** |
| 8 | Ekonomi-Multilateral | v1.2 — 14 Sep 2026 | monetary economy pages, kajian/report publications | medium |

Documents dated **after** a chapter's syllabus pin are flagged
`[NEWER-THAN-SYLLABUS]` in coverage and exports (they may not be covered by the
course version yet).

**Manual reads (visual-heavy pages):** pages whose content is carried by
figures/charts/images are flagged by a conservative heuristic (≥3 *unique*
content images, or ≥1 image with <1,500 chars of text; icons/logos/social
assets are excluded, and images shared across ≥10 pages are treated as site
chrome). Flagged URLs are listed in every study pack under
`Perlu dibaca manual (konten visual)` — read those pages in the browser.
`audit-visuals` refreshes the flags from saved raw snapshots (no network).

**Expansion sources (2026-09-17, BI mentor guidance):** hub crawls for
`tentang-bi`, `informasi-kurs` (×2), `pasar-keuangan` (FX instruments:
spot/forward/swap/DNDF), `operasi-moneter`, `publikasi/lelang`,
`stabilitas-sistem-keuangan`, `sistem-pembayaran`, `rupiah`, and
`pengembangan-ekonomi`; plus the `fungsi-utama` hub, the glossary, and the
BSPI 2030 PDF (ch5). FX instruments live in ch2/ch3 as agreed.

## Freshness rule (binding)

1. `--end-date` defaults to **today**.
2. Default fetch mode is **incremental**: per chapter, only documents newer than
   the newest stored public document are requested. `--full` is the only way to
   refetch the whole range (default full start: `2016-01-01`).
3. Rankings in exports/search are **newest-first**.
4. Every study-pack header prints `Fetched-At` plus the per-chapter newest
   **parsed publish date**; chapters without parsed dates are labeled
   `HONEST-UNKNOWN` with their fetch-fallback count.
5. `coverage` gates on **real dates only**. Fetch-fallback timestamps (shown
   when no publish date could be parsed) are excluded from both the 60-day gate
   and the `[NEWER-THAN-SYLLABUS]` flag. Chapters whose only evidence is
   fallback report `HONEST-UNKNOWN` (not a failure); never-fetched chapters
   still **FAIL**. Chapter 7 is report-only by design. Exit code is `1` when any
   chapter is `STALE`.

## Storage

```
data/
├── inbox/                 # MY OWN chapter summaries (my-notes); never scraped
├── raw/{chapter}/         # raw HTML snapshots of public pages
└── bi_study.db            # SQLite: documents, chapters, indicators, fetch_log + FTS5
```

- `documents` — public pages/press-release metadata + my-notes, newest-first
  queries; `enrich` fills `content` with the scraped full text
- `chapters` — 8 chapters with pinned syllabus versions
- `indicators` — numeric series (BI-Rate, JISDOR) used for charts
- `documents_fts` — FTS5 index over title/content (rebuilt with `index --rebuild`)

`data/inbox/` holds **only my own writing** (no scraping): each note is tagged to
a chapter via frontmatter (`chapter: 2`) or a `ch2_` filename prefix, extracted
to text, and indexed alongside the public corpus.

## Politeness, robots.txt & ToS

- **robots.txt is respected** (`urllib.robotparser`, cached per host). Observed
  on `www.bi.go.id`: `Allow: /` with disallows on `/_layouts`, `/Style Library`,
  `/Lists`, `/Banner`, `/Menu Image` — i.e. JS/CSS/asset and list endpoints the
  scraper never requests. Only content pages under `/id/...` and `/en/...` are
  fetched.
- Minimum **2s delay + jitter** between requests, **randomized browser user
  agents**, **3s timeout**, **max 2 retries** with exponential backoff. 4xx
  responses are not retried.
- **Per-source timeout override (never global):** the BI-Rate pager endpoint
  (`bi-rate.aspx`) uses **8s** instead of the global 3s, after its SharePoint
  DataPager POSTs timed out twice at 3s during multi-window pagination. Every
  other source stays at the 3s default.
- **PDF enrichment:** `enrich` extracts text from **public** bi.go.id PDFs with
  `pypdf` using a 30s per-request timeout for PDF downloads only. Encrypted or
  protected PDFs are **skipped and reported — never decrypted or bypassed**.
  PDFs whose text yield is too low (<200 chars/page, e.g. scanned documents) are
  stored with a manual-read placeholder and flagged as visual-heavy. When the BI
  server blocks a large download, `ingest-pdf` imports a locally downloaded copy
  (full text, byte-identical raw snapshot in `data/raw/`).
- **Hub crawling:** `hub` sources follow only in-section links (path prefix) up
  to `max_depth` (2), capped at 60 pages per hub, same bi.go.id host; asset,
  query-string and already-stored links are skipped. PDFs discovered under the
  section are text-extracted like any other public PDF.
- An **allowlist** restricts fetching to `bi.go.id` hosts; the forbidden
  `pejuang.berkarirbi.id` host raises `ForbiddenSourceError`.
- Only public, non-gated pages are accessed; BI content is used for personal
  study and its ToS/attribution terms apply (source URLs are always recorded).

## OWNERSHIP tags

Every file starts with an `OWNERSHIP:` line:

| Tag | Meaning |
| :--- | :--- |
| `public-derived` | Selectors/URL maps/fixtures derived from public bi.go.id pages |
| `my-notes` | My own writing/summaries (e.g. `data/inbox/` content) |
| `tooling` | Local code/config with neither public nor personal content |

## Tests

`pytest` runs with **zero live network hits**: all HTTP goes through
`httpx.MockTransport` with trimmed HTML fixtures captured from public pages.
Fixtures intentionally reproduce the real BI-Rate SharePoint form (viewstate
fields, `TextBoxDateStart/End`, `HiddenFieldDateFrom/To`, `ButtonSearch`,
`#tableData > table.table`, commented `BI-7 Day` column) so parsing is
grounded in the real markup.

## Honest limitations

- The BI-Rate/JISDOR pagination is followed via `DataPager` `__doPostBack`
  targets and **capped** per run (default 50 pages); wide historical backfills
  may need repeated `--full` runs.
- Chapter 7 genuinely has little public-source depth; exports show a
  thin-coverage warning instead of fabricated content.
- Portfolio exports contain public data (charts/tables) and my own analysis
  only: zero course-verbatim text and zero third-party PDFs.
