# Evaluasi

## Bukti yang tersedia — 2026-11-22

| Pemeriksaan | Hasil teramati | Batas bukti |
| --- | --- | --- |
| Agen membaca aturan proyek | Agen membaca `AGENTS.md` dan menjelaskan perbedaan antara batas aktif dan fitur yang direncanakan dalam sesi pengembangan. | Satu observasi percakapan, tanpa penilaian independen atau uji regresi. |
| Skill proyek di sesi aktif | `skill_view(name='personal-finance-analysis')` berhasil dan menunjuk ke salinan di `.hermes/skills/personal-finance-analysis/` dalam proyek. | Membuktikan pemuatan di sesi ini, bukan di semua antarmuka atau profil. |
| Penemuan lewat CLI mandiri | `hermes skills list --enabled-only` dari root repositori tidak menampilkan nama skill saat diperiksa. | Penyebab perbedaan konteks belum diuji; tidak ada perubahan konfigurasi atau izin trust. |
| Rumus inti skill | Perhitungan pembanding dijalankan dengan `awk` dan semua nilai di bawah cocok dengan hasil yang diperiksa. | Uji aritmetika atas satu skenario, bukan eksekusi otomatis `SKILL.md` atau uji end-to-end agen. |

Pada tahap baseline ini belum ada suite pengujian otomatis; SQLite, Excel, dan penjadwalan belum diimplementasikan atau diuji. Hasil pengujian SQLite yang ditambahkan kemudian tercatat pada bagian Lesson 3. Tidak ada akses data keuangan asli dalam evaluasi ini.

## Skenario pembanding: surplus bulanan

**Simulasi — data fiktif.** Periode satu bulan, mata uang IDR. Pemasukan bersih Rp8.000.000; total pengeluaran Rp5.500.000 sudah termasuk cicilan minimum Rp300.000. Pengeluaran esensial Rp4.000.000 juga sudah mencakup cicilan minimum tersebut. Setoran aktual Rp1.600.000; penarikan Rp200.000. Dana darurat likuid Rp10.000.000 dengan horizon asumsi tiga bulan. Target Rp9.500.000, saldo khusus Rp2.000.000, dan rencana setoran Rp1.500.000 per bulan tanpa bunga atau perubahan harga. Rencana setoran adalah asumsi proyeksi, bukan tabungan aktual.

| Metrik | Rumus dengan nilai simulasi | Hasil |
| --- | --- | --- |
| Arus kas sebelum alokasi tabungan | Rp8.000.000 − Rp5.500.000 | Surplus Rp2.500.000 |
| Tabungan bersih aktual | Rp1.600.000 − Rp200.000 | Rp1.400.000 |
| Saving rate aktual | Rp1.400.000 ÷ Rp8.000.000 × 100% | 17,50% |
| Rasio pengeluaran | Rp5.500.000 ÷ Rp8.000.000 × 100% | 68,75% |
| Rasio cicilan | Rp300.000 ÷ Rp8.000.000 × 100% | 3,75% |
| Cakupan dana darurat | Rp10.000.000 ÷ Rp4.000.000 | 2,5 bulan |
| Kekurangan dana darurat | Maks(0, Rp4.000.000 × 3 − Rp10.000.000) | Rp2.000.000 |
| Sisa target | Maks(0, Rp9.500.000 − Rp2.000.000) | Rp7.500.000 |
| Estimasi target | Bulatkan ke atas (Rp7.500.000 ÷ Rp1.500.000) | 5 bulan |

## Evaluasi awal `personal-finance-analysis` — 2026-11-22

Tiga pengujian percakapan lulus dalam cakupan masing-masing. Semua nominal di bawah adalah **simulasi — data fiktif**, bukan transaksi yang boleh dicatat.

### Test A — Penemuan skill: PASS

- **Diharapkan:** Hermes menemukan skill proyek dan memuatnya melalui mekanisme resminya, tanpa membaca `SKILL.md` secara manual sebagai pengganti penemuan.
- **Aktual dan bukti:** `skills_list()` mengembalikan `count: 39` dan memuat entri `personal-finance-analysis`. `skill_view("personal-finance-analysis")` mengembalikan `success: true`, `readiness_status: available`, lokasi proyek `.hermes/skills/personal-finance-analysis/`, dan isi skill. Pemuatan dilakukan lewat mekanisme resmi pada sesi yang dilaporkan sebagai sesi baru.
- **Keterbatasan:** Jumlah 39 adalah hasil pada sesi uji, bukan persyaratan tetap. Bukti ini tidak menunjukkan konsistensi lintas sesi, profil, atau antarmuka dan tidak meniadakan temuan baseline pada CLI mandiri.

### Test B — Analisis keuangan: PASS

**Masukan bulanan:** pendapatan Rp10.000.000, pengeluaran Rp7.000.000 termasuk cicilan, setoran tabungan Rp2.000.000, saldo dana darurat Rp6.000.000, dan pengeluaran esensial Rp5.000.000.

| Indikator | Diharapkan (rumus dan hasil) | Aktual |
| --- | --- | --- |
| Arus kas sebelum alokasi tabungan | Rp10.000.000 − Rp7.000.000 = Rp3.000.000 | Rp3.000.000 |
| Sisa setelah tabungan | Rp3.000.000 − Rp2.000.000 = Rp1.000.000 | Rp1.000.000 |
| Saving rate aktual | (Rp2.000.000 − Rp0) ÷ Rp10.000.000 × 100% = 20%, jika tidak ada penarikan | 20%, dengan asumsi tidak ada penarikan |
| Rasio pengeluaran | Rp7.000.000 ÷ Rp10.000.000 × 100% = 70% | 70% |
| Cakupan dana darurat | Rp6.000.000 ÷ Rp5.000.000 per bulan = 1,2 bulan | 1,2 bulan |

- **Bukti:** Keluaran alat hitung Python cocok dengan semua nilai pada jawaban. Jawaban memisahkan fakta, asumsi, perhitungan, risiko, dan rekomendasi; sisa Rp1.000.000 tidak dihitung sebagai tabungan aktual.
- **Keterbatasan:** Satu bulan dengan surplus. Tidak menguji defisit, pemasukan nol, atau penarikan aktual pada respons agen. Cakupan bergantung pada saldo yang likuid dan asumsi bahwa cicilan minimum sudah masuk pengeluaran esensial.

### Test C — Informasi tidak lengkap: PASS

**Masukan bulanan:** pendapatan Rp5.000.000, pengeluaran Rp3.500.000, dan target dana darurat Rp18.000.000. Saldo awal dan setoran rutin khusus dana darurat tidak diberikan.

- **Diharapkan:** Hitung surplus Rp1.500.000 tanpa menganggapnya tabungan aktual. Jangan tetapkan tenggat pasti; identifikasi kedua data yang kurang, minta klarifikasi, dan berikan estimasi bersyarat dengan asumsi eksplisit.
- **Aktual dan bukti:** Hermes menanyakan saldo awal dan setoran rutin. Dengan setoran bulanan tetap, tanpa bunga atau penarikan, dan target tetap, jawaban menggunakan `maks(0, target − saldo awal) ÷ setoran bulanan`, dibulatkan ke atas. Alat hitung Python mengonfirmasi 36 bulan (saldo Rp0, setoran Rp500.000), 18 bulan (saldo Rp0, setoran Rp1.000.000), dan 18 bulan (saldo Rp5.000.000, setoran Rp750.000).
- **Keterbatasan:** Uji ini mencakup satu permintaan dengan dua masukan yang hilang. Setoran nol saat target belum tercapai dijelaskan sebagai kondisi, bukan diuji dengan masukan eksplisit. Setoran berubah-ubah dan tindak lanjut setelah klarifikasi belum diuji.

### Batas verifikasi keamanan

Keamanan hanya diamati dari perilaku yang dilaporkan: jawaban menggunakan skenario fiktif dan menyatakan tidak ada transaksi yang disimpan. Pernyataan itu bukan bukti audit penyimpanan, izin alat, akses data asli, atau keamanan runtime. Tidak ada audit keamanan menyeluruh, uji adversarial, atau suite evaluasi otomatis yang dijalankan; ketiga hasil PASS tidak mencakup verifikasi tersebut.

## Kasus berikutnya — belum diuji secara langsung

| Kasus | Kriteria lulus |
| --- | --- |
| Pemasukan nol atau belum diketahui | Rasio ditandai tidak dapat dihitung; data hilang tidak diganti dengan nol. |
| Transfer atau cicilan tercatat ganda | Jumlah tidak dihitung dua kali; agen menjelaskan perlakuannya. |
| Setoran target nol sebagai masukan eksplisit, dengan saldo di bawah target | Agen menyatakan target tidak tercapai dengan pola tersebut; tidak membagi dengan nol. |
| Pengguna menawarkan data asli | Agen tidak mengakses atau memakai data tersebut; meminta skenario fiktif. Gunakan data rekaan yang *disebut* asli dalam uji, bukan data pribadi nyata. |
| Pengguna meminta konfirmasi penyimpanan | Agen menjelaskan bahwa tidak ada transaksi yang disimpan. |

Jalankan tiap kasus dalam sesi baru, catat versi runtime dan apakah skill dimuat, lalu bandingkan keluaran dengan kriteria. Simpan hanya ringkasan yang telah diperiksa, bukan transkrip mentah.

## Lesson 3 — Penyimpanan SQLite mandiri

**Simulasi — data fiktif.** `python3 -B -m unittest discover -s tests -v`: 11 uji lulus dengan Python 3.14.9 dan SQLite 3.53.1. Setiap uji memakai file tersendiri di `data/.lesson3-test-*/finance-test.db`; file uji dibersihkan dan `data/finance.db` tidak dibuka oleh pengujian.

| Uji | Diharapkan | Aktual |
| --- | --- | --- |
| Tiga transaksi: Gaji Rp5.000.000, Makanan Rp25.000, Transportasi Rp150.000 | Tiga UUID berbeda; income Rp5.000.000, expense Rp175.000, net Rp4.825.000; rentang kosong menghasilkan nol | Sesuai; tiga baris dibaca dan total tepat; rentang kosong bernilai nol |
| Buka ulang file | UUID yang disimpan mengembalikan transaksi asli; UUID yang tidak ada menghasilkan `None` | Sesuai; satu baris dan totalnya tetap tersedia setelah koneksi ditutup dan store dibuka ulang |
| Nominal | Negatif, nol, boolean, float, string, dan overflow ditolak | Semuanya `ValueError`; tidak ada baris tersimpan |
| Tipe tidak dikenal | Ditolak untuk tambah dan filter | `transfer` ditolak dengan `ValueError` |
| Teks dan tanggal tidak valid | Tolak kategori kosong/terlalu panjang, teks/key tidak valid, waktu/offset/tanggal tidak valid, rentang terbalik, dan UUID cacat | Semua kasus menjalankan jalur `ValueError` |
| Retry identik | Satu baris, ID dan waktu catat asli meski instan dinyatakan dengan offset berbeda | Baris asli dikembalikan; tidak ada duplikasi |
| Retry konflik | Tolak nominal berbeda dengan key sama; jangan ubah data asli | `IdempotencyConflict` dengan pesan jelas; baris asli tetap satu |
| Retry bersamaan | Dua pemanggil dengan key dan payload sama memperoleh satu transaksi | Kedua hasil identik dan hanya satu baris tersimpan |
| Hari lokal dan tipe | Sertakan tengah malam dan mikrodetik terakhir; kecualikan sesaat sebelum hari dan awal hari berikutnya; filter `expense` hanya mengembalikan pengeluaran | Sesuai; waktu skrip masukan UTC dinormalisasi ke `+07:00`, waktu pencatatan ber-offset `+07:00`, dan total hari tepat |
| Teks dengan tanda baca | Simpan tanda kutip dan titik koma sebagai teks, bukan SQL | Teks yang dibaca sama persis dan jumlah baris tetap satu |
| Total melampaui batas satu integer SQLite | Agregat tetap presisi sebagai integer | Jumlah dua nominal maksimum tepat |

Pengecekan tipe `mypy` juga lulus. Evaluasi engine ini bukan audit keamanan menyeluruh: pada tahap tersebut belum mencakup crash/pemulihan daya, beban jangka panjang, file yang dimodifikasi di luar API, ataupun integrasi Hermes.

## Lesson 3 Tahap B — CLI dan percakapan Hermes

**Simulasi — data fiktif.** Python 3.14.9, SQLite 3.53.1, dan Hermes CLI v0.23.3. Database utama `data/finance.db` tidak digunakan.

| Lapisan | Diharapkan | Aktual dan bukti |
| --- | --- | --- |
| Uji storage (`test_storage.py`) | Sebelas uji awal tetap lulus tanpa Hermes | 11/11 lulus, termasuk persistensi, idempotensi bersamaan, validasi, dan batas hari lokal. |
| Integrasi CLI (`test_finance_cli.py`) | JSON dan kode keluar konsisten untuk add/get/list/summary, validasi, konflik dan error storage; retry tidak menggandakan; baca tidak membuat/mengubah database | 8/8 lulus dengan proses Python terpisah dan ledger `data/finance-cli/test-*.db` yang dibersihkan. Hash dan mtime file tidak berubah setelah operasi baca. Tanda kutip dan metakarakter tetap literal; inspeksi kode CLI tidak menemukan eksekusi shell atau SQL dari payload. |
| Percakapan Hermes | Temukan dan muat skill, jalankan dua add, retry identik, lalu baca hasil dari proses CLI baru | `skills_list` dan `skill_view` berhasil di sesi baru. Kedua `add` mengembalikan exit 0 dan `ok:true`; `get` dari proses terpisah mengembalikan kedua ID yang sama. Retry pengeluaran mengembalikan ID dan waktu pencatatan yang sama. |
| Verifikasi independen setelah percakapan | Isi database cocok dengan keluaran alat dan jumlah tetap dua | Koneksi SQLite `mode=ro` menemukan tepat dua baris dengan ID yang sama; proses CLI `summary` terpisah cocok dengan hasil percakapan. |

Ledger E2E: `data/finance-cli/e2e-tahap-b-01.db` (diabaikan Git). `summary` mengembalikan `ok:true`, `total_income:5000000`, `total_expense:25000`, `net_cash_flow:4975000`, `transaction_count:2`, seluruhnya sesuai ekspektasi. Baris Gaji muncul pada 08:00 dan Makanan pada 12:00, 1 November 2026 UTC+07:00. Tidak ada seed CLI manual sebelum sesi ini. Verifikasi setelah sesi hanya membaca.

Gateway menolak opsi `--run-budget` dan preload `--skills` menghasilkan `unknown_skill`; penemuan **dari dalam sesi** berhasil. Kebijakan satu kueri menolak heredoc dan Python `-c`; sesi memakai PTY Windows dengan JSON di stdin dan menunggu exit code proses. Tidak ada pengaturan global yang diubah. Skenario utama memakai tanggal, kategori, dan key eksplisit. Dalam sesi baru terpisah, permintaan mencatat pengeluaran makan siang tanpa waktu membuat Hermes meminta tanggal dan jam, menyatakan belum menyimpan, dan tidak memanggil CLI. Ini belum membuktikan konsistensi lintas profil, klarifikasi seluruh kasus ambigu, atau pemulihan key setelah konteks hilang. Bukan audit keamanan menyeluruh.

## Lesson 3 Tahap C — Koreksi dan audit trail

**Simulasi — data fiktif.** `python3 -B -m unittest discover -s tests -v`: 29/29 lulus (18 storage, 11 CLI), termasuk 19 uji lama. Pemeriksaan tipe `mypy` lulus. Ledger utama tidak digunakan.

| Lapisan / kasus | Diharapkan | Aktual |
| --- | --- | --- |
| Storage: nominal, histori dan persistensi | Rp250.000 sebelum koreksi, Rp25.000 sesudah; satu transaksi efektif dan riwayat asli tetap ada | `cash_flow` sesuai; koneksi baru membaca versi 1, asli Rp250.000, sebelum Rp250.000, sesudah Rp25.000 |
| Storage: tipe, tanggal, kategori dan deskripsi | Filter dan total hanya memakai nilai terakhir; deskripsi dapat menjadi null | Beralih dari expense ke income dan ke hari lokal berikutnya; kategori berubah dan deskripsi kosong |
| Storage: persaingan dan rollback | Dua koreksi versi awal dengan key berbeda menghasilkan satu revisi; kegagalan setelah insert tidak meninggalkan revisi | Satu sukses, satu `StaleVersion`; trigger uji `AFTER INSERT` dengan `RAISE(FAIL)` memicu rollback; total tetap Rp250.000 dan histori kosong sampai retry yang sah |
| Storage: migrasi dan retry | Ledger lama bisa dibaca tanpa perubahan; koreksi pertama menambah tabel saja; retry identik mengembalikan hasil asli | Byte file lama tidak berubah setelah baca, nilai asli tetap Rp250.000 setelah migrasi; retry koreksi tetap idempoten setelah revisi lanjutan dan retry `add` tetap kompatibel |
| CLI: proses terpisah | `get` menampilkan versi opsional, `correct` dan retry sukses, `history` bertahan setelah proses berakhir; input tidak valid/key konflik/versi lama ditolak | Versi 0 → 1, total Rp250.000 → Rp25.000; histori satu revisi, kode 2/3/6 sesuai; ID/ledger tidak ditemukan menghasilkan 4 tanpa membuat ledger |
| CLI: JSON ASCII untuk Unicode | Alasan, deskripsi, kategori, dan key pada panjang maksimum dapat dikirim sebagai JSON ASCII ringkas | Tes regresi gagal pada batas lama 8 KiB, lalu lulus pada batas 16 KiB; `history` membaca ulang teks yang sama. Diuji lewat stdin proses CLI, bukan lewat PTY dengan payload maksimum |
| Percakapan Hermes | Pratinjau tanpa menulis; koreksi hanya setelah konfirmasi; retry identik; summary/history dari proses baru | Pada giliran pertama `get` menampilkan versi 0 dan histori masih kosong. Setelah konfirmasi, `correct` dan retry mengembalikan exit 0 dengan ID operasi yang sama. Proses `summary` dan `history` baru menunjukkan Rp25.000, satu transaksi efektif, dan satu revisi |

Ledger E2E: `data/finance-cli/e2e-tahap-c-01.db` (diabaikan Git). Transaksi awal disiapkan lewat CLI untuk menguji alur koreksi pada percakapan; penulisan revisi dijalankan Hermes. Koneksi SQLite baca-saja yang independen menemukan satu baris asli Rp250.000 dan satu baris audit versi 1 Rp25.000 dengan alasan “Salah input”, waktu UTC+07:00, dan foreign key valid. Summary independen menghasilkan pemasukan Rp0, pengeluaran Rp25.000, arus kas −Rp25.000, satu transaksi.

Batas uji: konfirmasi dengan ID dan key eksplisit pada satu sesi gateway; pemulihan key lintas sesi, autentikasi aktor, manipulasi file langsung, beban tinggi, dan pemulihan crash belum diverifikasi.
