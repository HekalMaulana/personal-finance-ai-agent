# Personal Finance AI Assistant

Prototipe asisten keuangan pribadi berbahasa Indonesia berbasis Hermes Agent. Proyek ini menunjukkan bagaimana instruksi proyek dan skill yang dapat ditinjau di Git membantu agen menghasilkan analisis keuangan yang transparan, mengakui data yang belum tersedia, dan tetap berada dalam batas izin. **Hanya untuk simulasi dengan data fiktif.**

## Teknologi dan arsitektur

- **Hermes Agent** menjalankan percakapan dan memuat skill proyek pada sesi yang memenuhi syarat. CLI yang diperiksa dalam pengembangan: v0.23.3.
- **Markdown dan YAML frontmatter** mendefinisikan aturan proyek (`AGENTS.md`) dan prosedur analisis (`SKILL.md`).
- **Python 3.12+ dan `sqlite3`** menyediakan penyimpanan lokal mandiri tanpa dependensi eksternal. Lokasi default adalah `data/finance.db`.
- **Git** mencatat perkembangan kode, dokumentasi, dan skill. `.gitignore` membantu mengecualikan database dan artefak lokal, tetapi tidak menggantikan pemeriksaan sebelum commit.

Analisis percakapan Hermes tidak membaca atau menulis database. Penyimpanan berjalan terpisah melalui modul Python. Lihat [arsitektur](docs/architecture.md) untuk skema dan batas kedua komponen.

## Status proyek

| Status | Cakupan |
| --- | --- |
| Tersedia, evaluasi awal lulus | Tiga uji percakapan lulus: penemuan skill, analisis keuangan fiktif, dan estimasi dengan data tidak lengkap. Lihat [hasil dan batas evaluasi](docs/evaluation.md). |
| Tersedia, teruji mandiri | Penyimpanan SQLite lokal untuk data fiktif: tambah, baca, filter, total arus kas, dan retry idempoten. |
| Dalam pengembangan | Evaluasi konsistensi percakapan lintas sesi dan kasus tepi. Belum ada pengujian keamanan menyeluruh. |
| Direncanakan, belum aktif | Integrasi penyimpanan dengan percakapan, koreksi dengan audit trail, satu laporan Excel atas permintaan eksplisit, tinjauan mingguan, evaluasi dana darurat triwulanan, serta pengecekan jadwal terlewat. Perencanaan target dalam percakapan belum melacak kemajuan secara persisten. |

## Mencoba prototipe

1. Buka sesi Hermes dari direktori repositori. Skill ada di [`.hermes/skills/personal-finance-analysis/SKILL.md`](.hermes/skills/personal-finance-analysis/SKILL.md). Jika belum tersedia di sesi, periksa penemuan skill proyek dan status kepercayaan repositori. Sebagai alternatif, minta agen membaca `SKILL.md` langsung; pembacaan manual tidak membuktikan penemuan otomatis.
2. Gunakan skenario fiktif di [dokumen evaluasi](docs/evaluation.md). Minta agen menampilkan rumus, asumsi, pertanyaan klarifikasi, dan saran yang tidak melebihi surplus rutin.
3. Cocokkan hasil dengan nilai pembanding. Jangan masukkan data rekening, kredensial, atau transaksi asli.

### Menguji penyimpanan tanpa Hermes

Dari root repositori, jalankan `python -B -m unittest discover -s tests -v` (atau `python3` jika itu nama executable lokal). Harness membuat database SQLite sementara yang terpisah dari `data/finance.db`, memverifikasi baris yang benar-benar ditulis, lalu membersihkan database uji. Gunakan hanya data fiktif.

## Dokumentasi pengembangan

- [Arsitektur](docs/architecture.md) — alur saat ini, batas keamanan, dan rancangan fitur berikutnya.
- [Log pengembangan](docs/development-log.md) — milestone, eksperimen, dan keputusan desain.
- [Evaluasi](docs/evaluation.md) — bukti yang tersedia, batas verifikasi, dan kasus uji berikutnya.
- [Aturan agen dan kontribusi](AGENTS.md) — kebijakan analisis, peninjauan perubahan, dan commit lokal. Tidak ada push otomatis.
