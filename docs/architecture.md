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

## Pemulihan pencatatan — Lesson 3 Tahap D

Sebelumnya key baru dapat terbentuk saat konteks sesi hilang. SQLite bisa sudah commit meski respons tidak sampai; timeout bukan bukti kegagalan. Sebaliknya, dua pembelian sah dapat memiliki isi identik sehingga deduplikasi berdasarkan isi akan membuang transaksi yang sah.

Tabel aditif `add_operations` pada ledger yang sama menyimpan `operation_id` UUID, `idempotency_key` unik, `prepared_at`, dan payload pencatatan ternormalisasi. `prepare_add()` menyelesaikan commit jurnal sebelum `commit_add()` dapat menulis ledger. Pencatatan menggunakan lock `BEGIN IMMEDIATE`, payload yang disimpan, dan key yang sama. `operation_status()` membaca snapshot konsisten. Status **diturunkan** dari sumber kebenaran, bukan disimpan di flag terpisah: `prepared` = jurnal ada tanpa baris transaksi yang terlihat pada saat baca; `committed` = baris asli dengan key tersebut ada. Karena insert ledger sekaligus menentukan status, tidak ada jendela antara commit ledger dan pembaruan flag. Status tidak membuktikan respons telah diterima pengguna.

CLI JSON: `prepare-add` memakai skema `add`; `commit-add` menerima `operation_id`; `operation-status` menerima tepat satu ID operasi atau key; `find-add` memakai nominal dan dapat dipersempit dengan kategori, tipe, dan tanggal lokal. Pencarian menampilkan maksimal sepuluh kandidat berdasarkan nilai asli, termasuk operasi belum commit. Satu kecocokan bukan bukti identitas. `add` lama tetap kompatibel dan tunduk pada key yang sudah direservasi. Transaksi lama dapat ditemukan dari key tanpa UUID jurnal (`operation_id: null`). Pembacaan ledger lama tidak membuat jurnal. Gunakan `get` untuk nilai efektif setelah koreksi; status pencatatan menampilkan baris asli.

Tidak ada proses yang memutar ulang otomatis, tidak ada jurnal terpisah, dan tidak ada penanda konfirmasi terkirim. Jurnal hanya untuk pencatatan baru; koreksi masih memakai mekanisme idempotensi dan audit Tahap C. Entri `prepared` tetap tersimpan jika ditinggalkan.

## Laporan Excel atas permintaan — Lesson 4

`Hermes → finance-reporting → finance_reporting.py --ledger NAMA export → TransactionStore (mode=ro) → SQLite → reports/laporan-keuangan.xlsx`. Ekspor merupakan operasi terpisah; CLI transaksi tidak mengimpor atau menjalankan reporting. Validasi nama ledger dipakai bersama dan menolak hard link sebelum SQLite dibuka. Tidak menerima path ledger atau output dari percakapan; tidak ada tugas terjadwal.

- `list_versioned_transactions()` mengambil baris dan versi efektif bersama dalam satu snapshot SQLite. Dashboard, Transaksi, dan Bulanan diturunkan dari kumpulan baris yang sama; jurnal `prepared` tidak ikut. Data versi awal muncul sebagai versi 0. Pengelompokan memakai waktu efektif Asia/Pontianak (UTC+07:00); tanggal transaksi disimpan sebagai teks ISO 8601 agar offset dan mikrodetik tetap terlihat.
- Agregasi memakai integer Rupiah; Dashboard menampilkan arus kas, bukan saldo rekening. Workbook menyimpan hasil hitung sebagai angka, bukan formula yang perlu dihitung ulang. Kategori/deskripsi disimpan sebagai sel teks literal. Karakter yang tidak valid dalam XML diganti U+FFFD di workbook saja; ledger tidak diubah. Grafik membandingkan pemasukan dan pengeluaran untuk bulan yang berisi transaksi.
- Sejak Lesson 5A, Anggaran menampilkan pagu dan realisasi SQLite dari snapshot yang sama dengan transaksi; jika kosong, tampilkan “Belum dikonfigurasi”. Sejak Lesson 5B, Dana Darurat juga membaca snapshot yang sama. Sejak Lesson 5C, Target Tabungan membaca target efektif dari snapshot yang sama, dengan placeholder bila kosong. Workbook bukan sumber data kedua; perubahan manual tidak dibaca kembali dan akan tertimpa ekspor berikutnya.
- Engine menyimpan file sementara di direktori tujuan, membukanya ulang untuk memeriksa nama sheet, jumlah baris rincian, dan total, lalu mengganti target melalui `os.replace`. Kegagalan sebelum atau pada penggantian tidak mengganti laporan lama; hanya file sementara milik ekspor yang dibersihkan. Keberhasilan dilaporkan setelah penggantian. Ini bukan jaminan ketahanan terhadap kehilangan daya; Excel yang sedang mengunci target dapat membuat pembaruan gagal.
- Tidak ada paginasi atau ekspor *as of*. Batas sheet detail 1.048.572 transaksi (empat baris pendahulu); nilai yang tidak muat dalam 15 digit desimal numerik Excel ditolak agar tidak dibulatkan diam-diam. Hasil dari ledger yang berbeda tetap memakai satu path output yang sama.

## Anggaran bulanan — Lesson 5A

`Hermes → finance-budgets → finance_cli.py → BudgetStore (finance_budgets.py) → ledger SQLite yang sudah ada`. Tidak ada database anggaran terpisah, akses ke database utama, maupun operasi hapus.

- `budgets` menyimpan label tampilan kategori pertama dan identitas unik `(period, category_key)`. Spasi Unicode tepi dibuang dan rangkaian spasi digabung menjadi satu spasi ASCII; label dinormalisasi NFC, key ditambah `casefold()` dan NFC lagi. Pengelompokan transaksi memakai aturan key yang sama. Validasi input mengikuti batas teks ledger (termasuk penolakan karakter kontrol). Tidak ada pemetaan sinonim atau penghilangan aksen.
- `budget_revisions` menyimpan nominal integer positif, versi (`0` saat dibuat), nominal sebelumnya, alasan perubahan, waktu catat Pontianak, dan key idempotensi yang unik untuk seluruh operasi anggaran pada ledger itu. Versi terbesar menentukan nominal efektif. SQL berparameter dan `BEGIN IMMEDIATE` melindungi pembuatan identitas, audit, serta pemeriksaan versi dalam satu commit. Migrasi tabel bersifat aditif dan terjadi pada penulisan anggaran pertama; pembacaan `mode=ro` pada ledger lama tidak bermigrasi. API memeriksa tabel transaksi dan tabel koreksi bila ada, memeriksa ulang target ter-resolve sebelum membuka koneksi, dan menolak hard link. Ini pemeriksaan struktural untuk workspace tepercaya, bukan autentikasi database atau perlindungan terhadap perubahan filesystem secara bersamaan.
- API `create_budget`, `get_budget`, `update_budget`, `budget_history`, dan `budget_summary` tersedia melalui `BudgetStore`. CLI masing-masing `budget-create`, `budget-get`, `budget-update`, `budget-history`, dan `budget-summary`. Create bukan upsert (`budget_exists`, exit 8). Update mensyaratkan boolean `confirmed: true`, `expected_version` dari pratinjau, dan alasan; versi stale memberi exit 6. Gate CLI adalah pernyataan lokal, bukan autentikasi pengguna; keputusan percakapan ditegakkan oleh skill. Retry payload/key sama mengembalikan revisi asal, bukan selalu revisi terkini; key sama dengan payload ternormalisasi berbeda memberi exit 3.
- Realisasi memakai versi efektif transaksi `expense`, dikelompokkan berdasarkan `occurred_at` setelah konversi ke Asia/Pontianak (UTC+07:00 tetap, sama dengan ledger). Income dan kategori tanpa pagu tidak muncul sebagai realisasi anggaran. Perubahan nominal, kategori, tanggal, dan tipe langsung tercermin pada pembacaan berikutnya. Sisa = pagu − realisasi; persen = realisasi × 100 ÷ pagu. Nominal dan perbandingan ambang memakai integer: normal <90%, mendekati batas 90–100% inklusif, melebihi batas >100%. Penyaringan `above_warning` memakai >90%, bukan hasil pembulatan persen.
- Excel memakai `reporting_snapshot()` untuk detail efektif dan semua periode anggaran dalam satu transaksi baca. Persentase ditulis sebagai rasio numerik terformat; nilai ketujuh kolom Anggaran diperiksa saat membuka ulang XLSX sementara. Baca/tulis anggaran tidak memanggil ekspor.
- Belum ada paginasi, rollover, ambang per kategori, pemulihan identitas operasi jika key hilang, atau audit anti-tamper. Ringkasan memindai pengeluaran efektif saat dibaca; bukan laporan historis *as of*. Tidak ada penjadwalan dan tidak ada perubahan dependensi runtime.

## Dana darurat — Lesson 5B

`Hermes → finance-emergency → finance_cli.py → EmergencyFundStore → ledger SQLite fiktif yang sudah ada`. API: `configure`, `set_opening`, `move`, `summary`, `history`. `mode=ro` untuk baca; kedua tabel dibuat secara aditif pada penulisan sukses pertama. `BEGIN IMMEDIATE` mencakup cek key, pemeriksaan versi/saldo, dan penambahan riwayat. Parameter pengguna selalu dibind.

- `emergency_configurations`: snapshot berversi mulai dari 0 dengan kebutuhan esensial, target bulan, waktu Pontianak, alasan, key dan payload retry. Nilai belum diisi adalah NULL; jangan menyamakan total expense dengan esensial. Perubahan nilai yang sudah terisi memerlukan konfirmasi dan alasan; versi tetap wajib saat mengisi field yang kosong pada konfigurasi yang sudah ada.
- `emergency_movements`: revisi berurutan dengan UUID, jenis (`opening`, `opening_adjustment`, `deposit`, `withdrawal`), nominal, delta bertanda, saldo setelah mutasi, deskripsi/alasan, waktu catat Pontianak, key dan payload retry. Saldo awal eksplisit boleh nol. Saldo awal yang dikoreksi menambah selisih dari saldo awal efektif, mempertahankan mutasi lainnya, dan perlu konfirmasi serta revisi saldo terkini. Setoran/penarikan harus positif; segala operasi yang membuat saldo negatif ditolak. Retry mengembalikan baris asli (bukan saldo terkini); konflik key ditolak lintas operasi dana darurat. Riwayat menyertakan `request`, yaitu payload asal ternormalisasi yang dapat dikirim ulang, terpisah dari nilai efektif yang diwarisi.
- Alokasi ini tidak menambah baris `transactions`, tidak memengaruhi dashboard arus kas, anggaran pengeluaran, atau tabungan tujuan. Tidak ada bank, transfer antar-akun, rekonsiliasi, koreksi/edit mutasi setoran atau penarikan, atau penghapusan. Audit append-only via API, bukan proteksi file terhadap manipulasi langsung.
- Target = esensial × bulan; cakupan = saldo ÷ esensial; progres = saldo ÷ target × 100; kekurangan dibatasi minimum nol. Nilai tak tersedia bukan nol. ETA memakai pembulatan ke atas dari kekurangan ÷ setoran bulanan eksplisit; tanpa setoran positif ETA tidak tersedia kecuali target sudah tercapai. Proyeksi tidak menyimpan atau menjadwalkan setoran.
- Worksheet Dana Darurat menyimpan tujuh metrik dari snapshot baca bersama transaksi dan anggaran. Data parsial ditandai, nol berbeda dari sel kosong; metrik numerik diverifikasi saat XLSX sementara dibuka ulang. Workbook bukan rekonsiliasi bank dan hanya berubah saat ekspor eksplisit. Tidak ada pagination riwayat atau laporan *as of*.

## Target tabungan — Lesson 5C

`Hermes → finance-savings → finance_cli.py → SavingsStore → ledger SQLite fiktif yang sudah ada`. Tabel aditif `savings_events` menyimpan snapshot append-only dengan UUID target dan revisi berurutan, jenis, timestamp Pontianak, key unik dalam fitur, dan payload ternormalisasi untuk audit/retry. Revisi terakhir adalah keadaan efektif. Nama boleh sama; referensi selalu UUID. Baca/pratinjau menggunakan snapshot `mode=ro`; penambahan satu snapshot di bawah `BEGIN IMMEDIATE` menyatukan pemeriksaan key, revisi, dan saldo dengan audit. Retry mengembalikan revisi historis; key dengan maksud lain ditolak, termasuk lintas target.

Konfirmasi dengan revisi yang ditinjau dan alasan diperlukan untuk saldo awal dan perubahan target. Gate CLI mengikuti pola pernyataan `confirmed:true`, bukan autentikasi konfirmasi pengguna; skill menegakkan giliran pratinjau dan persetujuan. Koreksi saldo awal hanya menambah selisih; saldo tidak boleh negatif. Tidak ada edit/hapus mutasi, transfer otomatis, atau rekonsiliasi bank. Tenggat hanya informasi; ETA dibulatkan ke atas dari kekurangan dibagi setoran bulanan eksplisit yang tidak disimpan. Worksheet hanya dimutakhirkan melalui ekspor eksplisit; baris efektif dan tipe sel teks diperiksa setelah membuka kembali workbook sementara.

## Analisis terjadwal — Lesson 6A

`finance_analysis.py` memakai ledger fiktif bernama yang sudah ada dan validasi path CLI yang sama. Tidak ada koneksi ke database utama, model, Excel, atau gateway. Aplikasi CLI analisis menjalankan pemeriksaan catch-up setiap kali `run-due` diluncurkan; CLI pencatatan dan sesi Hermes biasa tidak memicu pekerjaan.

- `weekly` memakai tanggal Senin awal minggu sebagai ID periode. Senin pukul 09.00 Asia/Pontianak, pekerjaan mengevaluasi Senin sebelumnya 00.00 hingga Senin saat jadwal 00.00 (eksklusif). Versi efektif transaksi dipilih sebelum filter waktu; pemasukan dan pengeluaran dijumlahkan sebagai integer Rupiah, arus kas = pemasukan − pengeluaran, bukan saldo rekening. Realisasi minggu dibagi per bulan dan kategori, lalu dibandingkan dengan pagu bulanan efektif saat eksekusi; ini bukan realisasi sebulan penuh atau anggaran mingguan yang diprorata.
- `quarterly` memakai `YYYY-Qn` dari jadwal 1 Januari/April/Juli/Oktober pukul 09.00 Asia/Pontianak (UTC+07:00 tetap). Engine memakai `read_fund_summary` pada snapshot SQLite saat eksekusi; `observed_at` berbeda dari `due_at`. Saldo adalah alokasi yang dilaporkan, bukan saldo bank ataupun rekonstruksi historis. Nilai belum ditetapkan tetap `null`.
- Ledger menyimpan tabel aditif `analysis_runs`, kunci utama `(kind, period)`. `run-due` memasukkan kandidat `pending` tanpa menimpa baris, kemudian menyimpan `running` dengan nomor percobaan. `BEGIN IMMEDIATE` memagari pembacaan data, penghitungan, dan commit `completed` beserta hasil atau `failed` beserta kode kegagalan. Hasil selesai tidak dihitung ulang, termasuk setelah koreksi ledger. Engine menolak trigger pada jurnal di bawah lock yang sama. Lock writer SQLite berlaku selama penghitungan; operasi penulisan lain bisa tertunda.
- Proses terhenti melepaskan lock SQLite. Runner berikutnya memeriksa ulang status dan nomor percobaan di bawah lock; `running` dapat diteruskan dengan nomor yang sama, tanpa hasil ganda. Kerja komputasi yang belum commit bisa diulang. Jika penyimpanan status gagal, gunakan `status` sebelum mencoba lagi; baris `running` tidak membuktikan worker masih hidup. `failed` memerlukan `run-due --resume KIND PERIOD`, maksimal tiga percobaan total. Kode kegagalan tidak berisi data ledger atau pesan internal mentah.
- Jendela catch-up bergulir: empat minggu terakhir dan paling banyak satu triwulan, dari yang paling lama dalam jendela. Periode yang terlewat di luar jendela tidak dimaterialisasi. Baris lama yang sudah tercatat tetapi belum selesai dapat diperiksa di `history` atau dilanjutkan eksplisit dengan `--resume`. `check-due`, `status`, dan `history` memakai `mode=ro` dan tidak membuat tabel. Tidak ada pemicu otomatis, pengiriman hasil, atau perubahan pada tabel keuangan.

## Desain berikutnya — belum diimplementasikan

| Lapisan | Rancangan dan syarat verifikasi |
| --- | --- |
| Penggunaan SQLite di luar uji fiktif | Belum aktif. Evaluasi kontrol akses, penanganan kehilangan konteks, dan perilaku penolakan sebelum memperluas cakupan. |
| Pemicu otomasi | Engine dan catch-up sudah tersedia via CLI; cron, gateway, dan pengiriman notifikasi belum diaktifkan. |

Urutan pengembangan yang disarankan: evaluasi perilaku agen → uji lapisan penyimpanan dengan data fiktif → verifikasi ekspor → evaluasi penjadwalan. Rancangan ini bukan izin untuk membuat database, integrasi, atau otomasi. Tidak ada tindakan perbankan atau investasi di dalam cakupan proyek.
