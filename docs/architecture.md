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

Analisis menghitung arus kas sebelum alokasi tabungan, saving rate dari tabungan bersih yang benar-benar terjadi dalam simulasi, dan rasio pengeluaran terhadap pemasukan bersih. Dana darurat dinilai terhadap pengeluaran esensial bulanan. Estimasi target memakai saldo yang khusus dialokasikan dan setoran rutin yang realistis. Alur percakapan ini tidak terhubung ke database; hal ini bukan jaminan layanan Hermes atau penyedia model tidak mencatat percakapan. Jangan memasukkan data asli.

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
- Batas tahap ini: database lokal tidak dienkripsi oleh modul; API bukan batas izin terhadap pihak yang bisa menulis langsung ke file. Belum ada paginasi, migrasi versi skema, backup/restore, atau pengujian crash dan beban. Daftar mengumpulkan semua baris yang cocok; total memindai baris yang cocok.

### Rancangan koreksi — belum diimplementasikan

Tidak ada API ubah atau hapus. Rancang koreksi sebagai entri audit append-only yang mereferensikan UUID asli dan mencatat alasan, aktor, waktu, serta idempotency key. Simpan entri pembalik dan transaksi pengganti opsional secara atomik tanpa mengubah baris asli. Tetapkan aturan periode pelaporan agar koreksi tidak dihitung ganda. Sebelum diaktifkan, uji rollback atomik, retry, konflik, koreksi berulang, dan rekonsiliasi total serta audit trail.

## Desain berikutnya — belum diimplementasikan

| Lapisan | Rancangan dan syarat verifikasi |
| --- | --- |
| Pencatatan percakapan | Pisahkan kandidat transaksi dari tindakan simpan. Validasi nominal, periode, dan kategori; minta klarifikasi bila ambigu. Konfirmasi keberhasilan hanya setelah hasil simpan diverifikasi. |
| Penggunaan SQLite dari Hermes | Hubungkan penyimpanan yang sudah teruji mandiri hanya setelah kontrak konfirmasi, idempotency key, dan penanganan kegagalan simpan diuji dari percakapan. File database dan berkas pendampingnya tidak masuk Git. |
| Laporan Excel | Satu laporan, dibuat atau diperbarui hanya atas permintaan eksplisit. Perlakukan workbook sebagai keluaran turunan, bukan sumber data kedua. Verifikasi isi dan rumus terhadap sumber sebelum menyatakan berhasil. |
| Penjadwalan | Rencana untuk tinjauan mingguan, evaluasi triwulanan dana darurat, dan pemulihan tinjauan yang terlewat ketika perangkat mati. Definisikan cara mencegah eksekusi ganda sebelum diaktifkan. |

Urutan pengembangan yang disarankan: evaluasi perilaku agen → uji lapisan penyimpanan dengan data fiktif → verifikasi ekspor → evaluasi penjadwalan. Rancangan ini bukan izin untuk membuat database, integrasi, atau otomasi. Tidak ada tindakan perbankan atau investasi di dalam cakupan proyek.
