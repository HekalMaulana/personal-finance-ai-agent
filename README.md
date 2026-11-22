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
| Tersedia untuk ledger fiktif | Koreksi transaksi dengan riwayat append-only dan perlindungan versi lama. Gunakan `get` dengan `include_version: true`, lalu `correct` atau `history`. |
| Tersedia, teruji lewat CLI | Ekspor Excel atas permintaan eksplisit dari ledger fiktif; lihat [pengujian Lesson 4](docs/evaluation.md#lesson-4--excel-reporting-on-demand). |
| Tersedia untuk ledger fiktif | Anggaran bulanan dan realisasi efektif dari SQLite; pembaruan memakai konfirmasi dan audit versi. Lihat [evaluasi Lesson 5A](docs/evaluation.md#lesson-5a--anggaran-bulanan). |
| Direncanakan, belum aktif | Penggunaan database utama dari percakapan, tinjauan mingguan, evaluasi dana darurat triwulanan, dan pengecekan jadwal terlewat. |

## Mencoba prototipe

1. Buka sesi Hermes dari direktori repositori. Skill ada di [`.hermes/skills/personal-finance-analysis/SKILL.md`](.hermes/skills/personal-finance-analysis/SKILL.md). Jika belum tersedia di sesi, periksa penemuan skill proyek dan status kepercayaan repositori. Sebagai alternatif, minta agen membaca `SKILL.md` langsung; pembacaan manual tidak membuktikan penemuan otomatis.
2. Gunakan skenario fiktif di [dokumen evaluasi](docs/evaluation.md). Minta agen menampilkan rumus, asumsi, pertanyaan klarifikasi, dan saran yang tidak melebihi surplus rutin.
3. Cocokkan hasil dengan nilai pembanding. Jangan masukkan data rekening, kredensial, atau transaksi asli.

### Menguji penyimpanan tanpa Hermes

Untuk suite lengkap, jalankan `py -3.12 -B -m unittest discover -s tests -v` dari root dengan `openpyxl` tersedia. Uji Lesson 3 menggunakan ledger SQLite yang terpisah dari `data/finance.db`; uji Lesson 4 menggunakan direktori sementara tersendiri. Semua fixture fiktif.

### Mencoba CLI dengan ledger fiktif

Contoh di Bash dari root repositori (jangan pakai data nyata). Gunakan nama ledger yang sama untuk baca dan tulis:

```bash
python3 -B finance_cli.py --ledger lesson3-demo add <<'FINANCE_JSON'
{"transaction_type":"expense","amount_rupiah":25000,"category":"Makanan","occurred_at":"2026-11-01T12:00:00+07:00","idempotency_key":"demo-makan-01"}
FINANCE_JSON
printf '%s\n' '{}' | python3 -B finance_cli.py --ledger lesson3-demo summary
```

Untuk `get`, kirim `{"id":"<UUID hasil add>"}`; untuk `list`, kirim `{}` atau filter `start_date`, `end_date`, dan `transaction_type`. Dalam percakapan Hermes, pastikan `finance-transactions` ditemukan melalui `skills_list()` dan dimuat melalui `skill_view()`, lalu sebutkan ledger dan data fiktif yang memang diminta untuk disimpan. Tidak perlu mengubah konfigurasi global jika preload `--skills` ditolak.

### Mengoreksi transaksi fiktif

Di ledger yang sama, gunakan `get` dengan `{"id":"<UUID>","include_version":true}`. Setelah meninjau versi dan nilai sebelum/sesudah, kirim JSON ke `correct`, misalnya `{"id":"<UUID>","expected_version":0,"changes":{"amount_rupiah":25000},"reason":"Salah input","idempotency_key":"demo-correct-01"}`. Gunakan versi dan UUID dari hasil baca, bukan nilai contoh. `history` menerima `{"id":"<UUID>"}`. Di Hermes, skill menampilkan pratinjau dan menunggu konfirmasi sebelum menulis. Lihat [hasil uji Tahap C](docs/evaluation.md#lesson-3-tahap-c--koreksi-dan-audit-trail).

### Memulihkan pencatatan setelah sesi berganti

Untuk ledger fiktif, `prepare-add` menerima JSON yang sama seperti `add` dan menyimpan ID operasi sebelum mencatat transaksi. `commit-add` menerima `{"operation_id":"<UUID>"}`. Jika hasil tidak pasti, baca `operation-status` dengan ID atau `{"idempotency_key":"<key>"}` sebelum mencoba lagi. Jika keduanya hilang, `find-add` mencari kandidat, bukan menentukan identitas. Lihat [hasil uji pemulihan](docs/evaluation.md#lesson-3-tahap-d--pemulihan-pencatatan).

### Membuat atau memperbarui laporan Excel

Dari sesi Hermes di root proyek: “Buat laporan keuangan Excel terbaru untuk ledger fiktif lesson3-demo.” Untuk membuat ulang file yang sama: “Perbarui laporan Excel saya untuk ledger fiktif lesson3-demo.” Gunakan nama ledger fiktif yang sudah ada. Pertanyaan ringkasan pengeluaran saja tidak membuat file.

CLI Windows (tidak perlu JSON stdin):

```bash
py -3.12 -B finance_reporting.py --ledger lesson3-demo export
```

Gunakan Python 3.12+ dengan `openpyxl` (`requirements-reporting.txt`). Python Windows 3.12 yang diperiksa sudah memiliki 3.1.5; `python3` bawaan Hermes yang diperiksa belum memilikinya. Siapkan dependensi hanya dengan persetujuan. Workbook `reports/laporan-keuangan.xlsx` adalah keluaran lokal yang diabaikan Git. Sheet Dashboard, Transaksi, dan Bulanan berasal dari versi transaksi efektif; Anggaran menampilkan pagu dan realisasi efektif untuk semua periode yang dikonfigurasi, atau “Belum dikonfigurasi” bila tidak ada pagu. Dana Darurat dan Target Tabungan tetap belum dikonfigurasi. Pembaruan mengganti seluruh workbook, termasuk edit manual. Tutup file di Excel jika terkunci.

Uji lengkap pada Windows: `py -3.12 -B -m unittest discover -s tests -v`.

### Mengelola anggaran bulanan fiktif

Di Hermes: “Tetapkan anggaran Makanan Rp1.000.000 untuk November 2026 pada ledger fiktif lesson3-demo.” Ledger harus sudah ada. Gunakan [skill `finance-budgets`](.hermes/skills/finance-budgets/SKILL.md) untuk membuat, membaca sisa, menyaring kategori di atas 90%, atau meninjau perubahan sebelum mengonfirmasi. Tidak ada ekspor otomatis.

CLI menggunakan `finance_cli.py --ledger NAMA OPERASI` dengan satu objek JSON di stdin:

| Operasi | Field JSON |
| --- | --- |
| `budget-create` | `period` (`YYYY-MM`), `category`, `amount_rupiah` (integer positif), `idempotency_key` |
| `budget-get`, `budget-history` | `period`, `category` |
| `budget-update` | Field create ditambah `expected_version` dari `budget-get`, `confirmed: true` setelah konfirmasi, dan `reason` |
| `budget-summary` | `period`; opsional `category` dan `above_warning` (boolean; `true` berarti **lebih dari** 90%) |

Contoh JSON ringkasan: `{"period":"2026-11","category":"Makanan"}`. Nama kategori yang hanya berbeda kapitalisasi atau spasi berulang/tepi dihitung bersama. Sisa bisa negatif; status mendekati batas mulai 90% sampai 100% inklusif, dan melebihi batas setelah 100%. Tidak ada anggaran yang dibuat otomatis untuk kategori tanpa pagu.

## Dokumentasi pengembangan

- [Arsitektur](docs/architecture.md) — alur saat ini, batas keamanan, dan rancangan fitur berikutnya.
- [Log pengembangan](docs/development-log.md) — milestone, eksperimen, dan keputusan desain.
- [Evaluasi](docs/evaluation.md) — bukti yang tersedia, batas verifikasi, dan kasus uji berikutnya.
- [Aturan agen dan kontribusi](AGENTS.md) — kebijakan analisis, peninjauan perubahan, dan commit lokal. Tidak ada push otomatis.
