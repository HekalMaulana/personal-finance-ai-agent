# Arsitektur

## Implementasi saat ini

```text
Pengguna (skenario fiktif)
    ↓
Sesi Hermes Agent
    ├─ AGENTS.md: peran, aturan analisis, dan batas izin
    └─ SKILL.md: validasi, rumus, dan struktur hasil
    ↓
Klarifikasi jika data penting kurang; jika cukup, tampilkan analisis
    ↓
Jawaban percakapan: fakta simulasi, asumsi, hitungan, risiko, saran
```

| Komponen | Kontrak |
| --- | --- |
| [Aturan proyek](../AGENTS.md) | Memisahkan fakta, asumsi, perhitungan, dan rekomendasi; melarang data asli dan klaim penyimpanan tanpa bukti. |
| [Skill analisis](../.hermes/skills/personal-finance-analysis/SKILL.md) | Menyamakan periode dan mata uang, mencegah penghitungan ganda atas transfer/cicilan, dan membedakan saldo, setoran, serta proyeksi. |
| Hermes Agent | Menjalankan dialog dan, bila tersedia serta diperlukan, memakai alat hitung. Skill berisi prosedur, bukan program yang mengeksekusi transaksi. |
| Git dan dokumentasi | Menyimpan instruksi dan bukti pengembangan yang telah ditinjau, bukan data keuangan atau log sesi. |

Analisis menghitung arus kas sebelum alokasi tabungan, saving rate dari tabungan bersih yang benar-benar terjadi dalam simulasi, dan rasio pengeluaran terhadap pemasukan bersih. Dana darurat dinilai terhadap pengeluaran esensial bulanan. Estimasi target memakai saldo yang khusus dialokasikan dan setoran rutin yang realistis. Skill analisis ini tidak terhubung ke database; jalur transaksi di bawah terpisah. Ini bukan jaminan layanan Hermes atau penyedia model tidak mencatat percakapan. Jangan memasukkan data asli.

## Penyimpanan mandiri — Lesson 3

`finance_storage.py` memakai `sqlite3` dan hanya menerima data fiktif untuk penggunaan proyek ini. `TransactionStore()` membuka atau membuat database `data/finance.db` relatif terhadap root proyek, bukan direktori kerja pemanggil. Pengujian memakai path tepercaya yang terpisah, di bawah `data/.lesson3-test-*/`. Tidak ada koneksi ke Hermes, jaringan, atau proyek lain.

| Kolom `transactions` | Skema dan kontrak |
| --- | --- |
| `id` | `TEXT`, primary key non-null; UUID kanonik yang dibuat oleh modul. |
| `transaction_type` | `TEXT NOT NULL`, hanya `income` atau `expense`. |
| `amount_rupiah` | `INTEGER NOT NULL`, positif, paling banyak 2^63 − 1 per transaksi. |
| `category` | `TEXT NOT NULL`, 1–100 karakter setelah spasi tepi dipangkas. |
| `description` | `TEXT`, opsional (`NULL`) atau 1–500 karakter setelah pemangkasan. |
| `occurred_at` | `TEXT NOT NULL`, waktu transaksi ISO 8601 dengan enam digit pecahan detik dan offset `+07:00`. |
| `recorded_at` | `TEXT NOT NULL`, waktu dari jam sistem saat pencatatan, dengan format lokal yang sama. |
| `idempotency_key` | `TEXT NOT NULL UNIQUE`, 1–128 karakter, peka huruf besar/kecil, tanpa spasi tepi. |

- API: `add_transaction()` menulis satu transaksi, `get_transaction()` membaca berdasarkan UUID, `list_transactions()` memfilter tanggal dan tipe, dan `cash_flow()` menghitung pemasukan, pengeluaran, selisih, serta jumlah transaksi untuk rentang tanggal.
- Waktu masuk wajib memuat detik dan offset numerik atau `Z`. Modul memakai UTC+07:00 tetap dengan nama `Asia/Pontianak` sesuai kontrak Lesson 3, tanpa memerlukan data zona IANA di Windows. Aturan offset historis atau perubahan aturan di masa depan tidak dimodelkan. Tanggal filter `YYYY-MM-DD` adalah hari lokal inklusif dari `00:00:00.000000` hingga `23:59:59.999999`; batas boleh tidak diisi.
- Input divalidasi di Python dan nilai SQL di-bind dengan parameter. Skema menegakkan batas inti dan keunikan; indeks `(occurred_at, id)` mendukung urutan waktu. Pengecekan key dan insert berada dalam satu transaksi `BEGIN IMMEDIATE`. Payload identik setelah normalisasi (termasuk waktu yang mewakili instan yang sama) mengembalikan baris asli; konflik tidak mengubahnya. Setiap operasi menutup koneksinya. Total dihitung dengan integer Python agar tidak overflow pada batas agregat SQLite.
- Batas tahap ini: database lokal tidak dienkripsi oleh modul; API bukan batas izin terhadap pihak yang bisa menulis langsung ke file. Belum ada paginasi, kerangka migrasi berversi, backup/restore, atau pengujian crash dan beban. Daftar mengumpulkan semua baris yang cocok; total memindai baris yang cocok.

## Jalur percakapan untuk transaksi fiktif — Lesson 3 Tahap B

`Hermes → finance-transactions → finance_cli.py → TransactionStore → SQLite`. Skill memeriksa maksud pencatatan, meminta klarifikasi untuk detail ambigu, dan hanya mengonfirmasi hasil `add` jika proses CLI selesai dengan exit 0 dan data hasil cocok. Permintaan analisis biasa tidak mengikuti jalur ini.

- CLI memerlukan `--ledger NAMA`; nama ASCII yang lolos allowlist dipetakan ke `data/finance-cli/NAMA.db`, bukan path dari payload atau `data/finance.db`. Gunakan ledger yang sama untuk seluruh operasi dalam satu skenario. Lokasi ini mengasumsikan workspace lokal tepercaya dan bukan batas isolasi terhadap pihak yang bisa memodifikasi file secara langsung.
- CLI membaca satu objek JSON UTF-8 maksimal 16 KiB dari stdin (cukup untuk field koreksi berukuran maksimum yang di-escape menjadi JSON ASCII ringkas). Operasi dan field di-allowlist; nilai diteruskan ke API Python, bukan dieksekusi sebagai perintah shell atau SQL. `get`, `list`, dan `summary` memakai koneksi SQLite `mode=ro` tanpa inisialisasi skema. Ledger yang belum ada tidak dibuat oleh operasi baca.
- Sukses: exit `0` dan `{ "ok": true, "operation": "...", "data": ... }`. Kesalahan: `{ "ok": false, "error": { "code": "...", "message": "..." } }`, dengan exit `2` input tidak valid, `3` konflik idempotensi, `4` ledger/transaksi tidak ditemukan, dan `5` kesalahan penyimpanan.
- Key dan payload ditetapkan sebelum pemanggilan pertama. Retry aman hanya jika ledger, key, dan payload tetap sama. Engine menegakkan keunikan key per ledger, tetapi skill tidak memiliki penyimpanan untuk memulihkan identitas operasi di luar konteks percakapan. Jika identitas tidak pasti, baca atau minta klarifikasi sebelum mencoba lagi.

## Koreksi append-only — Lesson 3 Tahap C

`transactions` tetap menyimpan data asli dan ID stabil (versi 0). Tabel aditif `transaction_corrections` menyimpan satu snapshot efektif per versi: `operation_id` (UUID, primary key), `transaction_id` (foreign key), pasangan unik `(transaction_id, version)`, `idempotency_key` unik untuk operasi koreksi, `request_json` yang dinormalisasi, `reason`, `corrected_at` (+07:00), serta `transaction_type`, `amount_rupiah`, `category`, `description`, dan `occurred_at`. Nilai sebelum koreksi diambil dari versi sebelumnya atau baris asli, bukan diduplikasi. Inisialisasi tulis dan koreksi pada ledger lama memakai `CREATE TABLE IF NOT EXISTS`; pembacaan ledger lama tidak melakukan migrasi. Tidak ada `ALTER`, `UPDATE`, atau `DELETE` pada jalur koreksi.

- `correct_transaction()` memvalidasi patch, alasan dan `expected_version`, kemudian mengunci penulisan dengan `BEGIN IMMEDIATE`. Retry identik mengembalikan revisi aslinya, bahkan jika versi efektif sudah lebih baru. Key sama dengan permintaan ternormalisasi berbeda menghasilkan konflik; key baru dengan versi lama menghasilkan `stale_version` (CLI exit `6`). Satu insert atomik sekaligus menyimpan audit dan menentukan versi efektif; koreksi tanpa perubahan ditolak.
- `get_versioned_transaction()` dan CLI `get` dengan `include_version: true` memberikan snapshot beserta versi untuk pratinjau. API `transaction_history()` dan CLI `history` mengembalikan data asli dan revisi berurutan, termasuk pasangan sebelum/sesudah. `get` biasa tetap mengembalikan bentuk lama, kini dengan nilai efektif. Retry `add` tetap mengembalikan hasil tambah asli, bukan hasil koreksi.
- `list` dan `cash_flow` (`summary`) memakai satu versi terakhir per ID, baru menerapkan filter. Perubahan tipe mengalihkan kelompok pemasukan/pengeluaran; perubahan waktu memindahkan transaksi ke periode efektif baru. Tidak ada baris pembalik atau penghitungan ganda. Ringkasan historis dapat berubah; pelaporan *as of* belum tersedia.
- Trade-off: snapshot menambah ruang dan biaya join dibanding mengganti baris, tetapi menjaga versi lama dan audit secara sederhana. Klien lama tetap dapat membuka skema, namun versi kode lama dan kueri langsung `transactions` tidak melihat koreksi. Audit append-only ditegakkan oleh API, bukan bukti anti-tamper terhadap akses file langsung. Identitas aktor dan otorisasi multi-pengguna belum tersedia.

## Desain berikutnya — belum diimplementasikan

| Lapisan | Rancangan dan syarat verifikasi |
| --- | --- |
| Penggunaan SQLite di luar uji fiktif | Belum aktif. Evaluasi kontrol akses, penanganan kehilangan konteks, dan perilaku penolakan sebelum memperluas cakupan. |
| Laporan Excel | Satu laporan, dibuat atau diperbarui hanya atas permintaan eksplisit. Perlakukan workbook sebagai keluaran turunan, bukan sumber data kedua. Verifikasi isi dan rumus terhadap sumber sebelum menyatakan berhasil. |
| Penjadwalan | Rencana untuk tinjauan mingguan, evaluasi triwulanan dana darurat, dan pemulihan tinjauan yang terlewat ketika perangkat mati. Definisikan cara mencegah eksekusi ganda sebelum diaktifkan. |

Urutan pengembangan yang disarankan: evaluasi perilaku agen → uji lapisan penyimpanan dengan data fiktif → verifikasi ekspor → evaluasi penjadwalan. Rancangan ini bukan izin untuk membuat database, integrasi, atau otomasi. Tidak ada tindakan perbankan atau investasi di dalam cakupan proyek.
