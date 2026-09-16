# OWNERSHIP: public-derived
"""Source catalogue: public bi.go.id pages only.

Kinds:
- ``page``          fetch page text (profile, education, stability overview, ...)
- ``bi_rate_form``  BI-Rate date-range POST table (see parsers.bi_rate)
- ``table_page``    page whose HTML table contains a numeric series (JISDOR, SPIP)
- ``press_release`` listing of dated publication links -> metadata only, no PDFs
"""

from __future__ import annotations

from dataclasses import dataclass

KIND_PAGE = "page"
KIND_BI_RATE_FORM = "bi_rate_form"
KIND_TABLE_PAGE = "table_page"
KIND_PRESS_RELEASE = "press_release"


@dataclass(frozen=True)
class Source:
    chapter: int
    name: str
    url: str
    kind: str
    notes: str = ""
    # Per-source timeout override (seconds). Keep None unless a specific source
    # repeatedly times out; never raise the global timeout.
    timeout: float | None = None


SOURCES: tuple[Source, ...] = (
    # Chapter 1 -- Pengenalan BI
    Source(1, "Profil BI", "https://www.bi.go.id/id/tentang-bi/profil/Default.aspx", KIND_PAGE),
    Source(1, "Sejarah BI", "https://www.bi.go.id/id/tentang-bi/sejarah-bi/Default.aspx", KIND_PAGE),
    Source(1, "Organisasi BI", "https://www.bi.go.id/id/tentang-bi/profil/organisasi/Default.aspx", KIND_PAGE),
    Source(1, "UU BI", "https://www.bi.go.id/id/tentang-bi/profil/uu-bi/Default.aspx", KIND_PAGE),
    Source(1, "Transformasi BI", "https://www.bi.go.id/id/tentang-bi/transformasi/", KIND_PAGE),
    # Chapter 2 -- Inflasi + Nilai Tukar
    Source(
        2,
        "BI-Rate table",
        "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx",
        KIND_BI_RATE_FORM,
        "date-range POST via TextBoxDateStart/End + ButtonSearch",
        # Per-source override only (global stays 3s): the SharePoint DataPager
        # POSTs on this endpoint timed out twice at the 3s default during
        # multi-window pagination, so this source alone is allowed 8s.
        timeout=8.0,
    ),
    Source(2, "JISDOR", "https://www.bi.go.id/id/statistik/informasi-kurs/jisdor", KIND_TABLE_PAGE),
    Source(2, "Kurs Transaksi BI", "https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi", KIND_PAGE),
    Source(2, "Kurs Acuan Non-USD/IDR", "https://www.bi.go.id/id/statistik/informasi-kurs/kurs-acuan-non-usd-idr/", KIND_PAGE),
    Source(2, "Inflasi", "https://www.bi.go.id/id/fungsi-utama/moneter/inflasi/Default.aspx", KIND_PAGE),
    # Chapter 3 -- Kebijakan Moneter
    Source(3, "Siaran Pers", "https://www.bi.go.id/id/publikasi/ruang-media/news-release/", KIND_PRESS_RELEASE),
    Source(3, "Pidato Dewan Gubernur", "https://www.bi.go.id/id/publikasi/ruang-media/pidato-dewan-gubernur/Default.aspx", KIND_PRESS_RELEASE),
    Source(3, "Fungsi Moneter", "https://www.bi.go.id/id/fungsi-utama/moneter/Default.aspx", KIND_PAGE),
    Source(3, "Peraturan", "https://www.bi.go.id/id/publikasi/peraturan/Default.aspx", KIND_PAGE),
    # Chapter 4 -- SSK + Makroprudensial
    Source(4, "Ikhtisar SSK", "https://www.bi.go.id/id/fungsi-utama/stabilitas-sistem-keuangan/ikhtisar/", KIND_PAGE),
    Source(4, "Instrumen Makroprudensial", "https://www.bi.go.id/id/fungsi-utama/stabilitas-sistem-keuangan/instrumen-makroprudensial/default.aspx", KIND_PAGE),
    Source(4, "Laporan BI", "https://www.bi.go.id/id/publikasi/laporan/default.aspx", KIND_PRESS_RELEASE),
    Source(4, "Kajian BI", "https://www.bi.go.id/id/publikasi/kajian/Default.aspx", KIND_PRESS_RELEASE),
    # Chapter 5 -- Sistem Pembayaran
    Source(5, "Sistem Pembayaran", "https://www.bi.go.id/id/fungsi-utama/sistem-pembayaran/default.aspx", KIND_PAGE),
    Source(5, "Blueprint SPI", "https://www.bi.go.id/id/fungsi-utama/sistem-pembayaran/blueprint/default.aspx", KIND_PAGE),
    Source(5, "SP Nilai Besar", "https://www.bi.go.id/id/fungsi-utama/sistem-pembayaran/nilai-besar/", KIND_PAGE),
    Source(5, "SP Ritel", "https://www.bi.go.id/id/fungsi-utama/sistem-pembayaran/ritel/", KIND_PAGE),
    Source(5, "Statistik SPIP", "https://www.bi.go.id/id/statistik/ekonomi-keuangan/spip/Default.aspx", KIND_TABLE_PAGE),
    # Chapter 6 -- Uang Rupiah
    Source(6, "Rupiah (hub)", "https://www.bi.go.id/id/rupiah/", KIND_PAGE),
    Source(6, "Gambar Uang", "https://www.bi.go.id/id/rupiah/gambar-uang/Default.aspx", KIND_PAGE),
    Source(6, "Uang Rupiah Dicabut", "https://www.bi.go.id/id/rupiah/uang-dicabut/Default.aspx", KIND_PAGE),
    Source(6, "Pencegahan Rupiah Palsu", "https://www.bi.go.id/id/rupiah/pencegahan-rupiah-palsu/Default.aspx", KIND_PAGE),
    Source(6, "Cinta Bangga Paham Rupiah", "https://www.bi.go.id/id/rupiah/cinta-bangga-paham-rupiah/default.aspx", KIND_PAGE),
    Source(6, "Digital Rupiah", "https://www.bi.go.id/id/rupiah/digital-rupiah/default.aspx", KIND_PAGE),
    # Chapter 7 -- Wawasan Kebangsaan (general public pages only; thin by design)
    Source(7, "Edukasi BI", "https://www.bi.go.id/id/edukasi/Default.aspx", KIND_PAGE),
    Source(7, "Museum BI", "https://www.bi.go.id/id/layanan/museum-bi/default.aspx", KIND_PAGE),
    Source(7, "Informasi Publik", "https://www.bi.go.id/id/informasi-publik/Default.aspx", KIND_PAGE),
    # Chapter 8 -- Ekonomi-Multilateral
    Source(8, "Fungsi Moneter (ekonomi)", "https://www.bi.go.id/id/fungsi-utama/moneter/Default.aspx", KIND_PAGE),
    Source(8, "Pasar Keuangan", "https://www.bi.go.id/id/fungsi-utama/moneter/pasar-keuangan/default.aspx", KIND_PAGE),
    Source(8, "Kajian BI (multilateral)", "https://www.bi.go.id/id/publikasi/kajian/Default.aspx", KIND_PRESS_RELEASE),
    Source(8, "Laporan BI (multilateral)", "https://www.bi.go.id/id/publikasi/laporan/default.aspx", KIND_PRESS_RELEASE),
)


def sources_for_chapter(chapter_id: int) -> list[Source]:
    """All public sources configured for a chapter."""

    return [source for source in SOURCES if source.chapter == chapter_id]
