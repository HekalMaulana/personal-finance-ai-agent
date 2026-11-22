# Personal Finance AI Assistant

Prototipe asisten keuangan pribadi berbahasa Indonesia berbasis Hermes Agent. Proyek ini menunjukkan bagaimana instruksi proyek dan skill yang dapat ditinjau di Git membantu agen menghasilkan analisis keuangan yang transparan, mengakui data yang belum tersedia, dan tetap berada dalam batas izin. **Hanya untuk simulasi dengan data fiktif.**

## Teknologi dan arsitektur

- **Hermes Agent** menjalankan percakapan dan memuat skill proyek pada sesi yang memenuhi syarat. CLI yang diperiksa dalam pengembangan: v0.23.3.
- **Markdown dan YAML frontmatter** mendefinisikan aturan proyek (`AGENTS.md`) dan prosedur analisis (`SKILL.md`).
- **Python 3.12+ dan `sqlite3`** menyediakan penyimpanan lokal mandiri tanpa dependensi eksternal. Lokasi default adalah `data/finance.db`.
- **Git** mencatat perkembangan kode, dokumentasi, dan skill. `.gitignore` membantu mengecualikan database dan artefak lokal, tetapi tidak menggantikan pemeriksaan sebelum commit.

Skill `personal-finance-analysis` tetap untuk analisis tanpa pencatatan. Skill [`finance-transactions`](.hermes/skills/finance-transactions/SKILL.md) menghubungkan permintaan eksplisit ke CLI untuk ledger uji fiktif saja. Lihat [arsitektur](docs/architecture.md) untuk skema dan batas akses.

## Status proyek

| Status | Cakupan |
| --- | --- |
| Tersedia, evaluasi awal lulus | Tiga uji percakapan lulus: penemuan skill, analisis keuangan fiktif, dan estimasi dengan data tidak lengkap. Lihat [hasil dan batas evaluasi](docs/evaluation.md). |
| Tersedia, teruji mandiri | Penyimpanan SQLite lokal untuk data fiktif: tambah, baca, filter, total arus kas, dan retry idempoten. |
| Dalam pengembangan | Evaluasi konsistensi percakapan lintas sesi dan kasus tepi. Belum ada pengujian keamanan menyeluruh. |
| Teruji end-to-end untuk ledger fiktif | Hermes memuat `finance-transactions`, mencatat dua transaksi, mengulangi satu permintaan tanpa duplikasi, dan membaca ringkasan dari proses CLI baru. Lihat [bukti dan batas uji](docs/evaluation.md#lesson-3-tahap-b--cli-dan-percakapan-hermes). |
| Direncanakan, belum aktif | Koreksi dengan audit trail, penggunaan database utama dari percakapan, laporan Excel atas permintaan eksplisit, tinjauan mingguan, evaluasi dana darurat triwulanan, dan pengecekan jadwal terlewat. |

## Mencoba prototipe

1. Buka sesi Hermes dari direktori repositori. Skill ada di [`.hermes/skills/personal-finance-analysis/SKILL.md`](.hermes/skills/personal-finance-analysis/SKILL.md). Jika belum tersedia di sesi, periksa penemuan skill proyek dan status kepercayaan repositori. Sebagai alternatif, minta agen membaca `SKILL.md` langsung; pembacaan manual tidak membuktikan penemuan otomatis.
2. Gunakan skenario fiktif di [dokumen evaluasi](docs/evaluation.md). Minta agen menampilkan rumus, asumsi, pertanyaan klarifikasi, dan saran yang tidak melebihi surplus rutin.
3. Cocokkan hasil dengan nilai pembanding. Jangan masukkan data rekening, kredensial, atau transaksi asli.

### Menguji penyimpanan tanpa Hermes

Dari root repositori, jalankan `python -B -m unittest discover -s tests -v` (atau `python3` jika itu nama executable lokal). Harness membuat database SQLite sementara yang terpisah dari `data/finance.db`, memverifikasi baris yang benar-benar ditulis, lalu membersihkan database uji. Gunakan hanya data fiktif.

### Mencoba CLI dengan ledger fiktif

Contoh di Bash dari root repositori (jangan pakai data nyata). Gunakan nama ledger yang sama untuk baca dan tulis:

```bash
python3 -B finance_cli.py --ledger lesson3-demo add <<'FINANCE_JSON'
{"transaction_type":"expense","amount_rupiah":25000,"category":"Makanan","occurred_at":"2026-11-01T12:00:00+07:00","idempotency_key":"demo-makan-01"}
FINANCE_JSON
printf '%s\n' '{}' | python3 -B finance_cli.py --ledger lesson3-demo summary
```

Untuk `get`, kirim `{"id":"<UUID hasil add>"}`; untuk `list`, kirim `{}` atau filter `start_date`, `end_date`, dan `transaction_type`. Dalam percakapan Hermes, pastikan `finance-transactions` ditemukan melalui `skills_list()` dan dimuat melalui `skill_view()`, lalu sebutkan ledger dan data fiktif yang memang diminta untuk disimpan. Tidak perlu mengubah konfigurasi global jika preload `--skills` ditolak.

## Dokumentasi pengembangan

- [Arsitektur](docs/architecture.md) — alur saat ini, batas keamanan, dan rancangan fitur berikutnya.
- [Log pengembangan](docs/development-log.md) — milestone, eksperimen, dan keputusan desain.
- [Evaluasi](docs/evaluation.md) — bukti yang tersedia, batas verifikasi, dan kasus uji berikutnya.
- [Aturan agen dan kontribusi](AGENTS.md) — kebijakan analisis, peninjauan perubahan, dan commit lokal. Tidak ada push otomatis.
