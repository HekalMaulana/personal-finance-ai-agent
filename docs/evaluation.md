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

Batas uji: konfirmasi dengan ID dan key eksplisit pada satu sesi gateway; pemulihan key lintas sesi, autentikasi aktor, manipulasi file langsung, beban tinggi, dan pemulihan crash belum diverifikasi pada Tahap C.

## Lesson 3 Tahap D — Pemulihan pencatatan

Semua transaksi fiktif. 33 uji otomatis lulus, termasuk 29 uji lama dan empat uji integrasi proses baru; `mypy` lulus.

| Kasus/lapisan | Diharapkan | Aktual |
| --- | --- | --- |
| Proses CLI: putus setelah commit | Proses baru menemukan transaksi tanpa duplikasi | Subproses dihentikan di titik setelah SQLite commit dan sebelum JSON sukses. Lookup dengan ID dan key serta retry mengembalikan transaksi sama; koneksi baca-saja menemukan satu baris |
| Proses CLI: gagal setelah persiapan | Jurnal bertahan, transaksi tidak tersisa, retry aman | Trigger fixture `AFTER INSERT` memicu rollback. Status tetap `prepared`; setelah trigger dilepas, operasi yang sama menghasilkan satu baris |
| Proses CLI: dua transaksi identik | Dua identitas berbeda boleh tercatat; pencarian tidak menyatukan kandidat | Dua key dan UUID berbeda menghasilkan dua baris; `find-add` mengembalikan `multiple` |
| Proses CLI: kompatibilitas/validasi | Key lama dapat dibaca; payload berbeda dengan key direservasi ditolak | Sesuai; bentuk JSON status yang tidak valid juga ditolak |
| Hermes lintas sesi | Sesi baru memulihkan transaksi yang sama tanpa menulis; kandidat ganda memerlukan klarifikasi | Sesi pertama menyiapkan dan mem-commit satu transaksi, sesi baru tanpa resume membaca `committed` dengan key yang sama. Sesi lain tanpa ID/key menampilkan kandidat `committed` dan `prepared`, bertanya mana yang dimaksud, dan tidak menulis |

Ledger E2E `data/finance-cli/e2e-tahap-d-01.db` (diabaikan Git). Kandidat kedua disiapkan lewat CLI khusus untuk uji ambiguitas. Koneksi SQLite baca-saja memeriksa hasil akhir: dua entri jurnal, satu baris transaksi sebesar Rp25.000; operasi kedua tetap `prepared`. Penghentian paksa hanya diuji secara programatis, bukan dengan memutus gateway Hermes atau daya perangkat.

## Lesson 4 — Excel Reporting on Demand

`py -3.12 -B -m unittest discover -s tests -v`, dengan `openpyxl` 3.1.5: 42/42 lulus. `mypy` lulus untuk tiga modul Python proyek. Semua fixture fiktif dan terisolasi; database utama tidak digunakan.

| Lapisan | Diharapkan | Aktual |
| --- | --- | --- |
| Unit reporting (1/1) | Agregasi integer dan pembagian bulan mengikuti Pontianak | Mikrodetik sebelum tengah malam masuk Oktober; tepat tengah malam masuk November. Total Rp5.000.000 masuk, Rp25.000 keluar, Rp4.975.000 net, dua transaksi. |
| Integrasi reporting (8/8) | Buka ulang XLSX, enam sheet sesuai kontrak, total cocok dengan agregasi SQL independen, dan koreksi dihitung sekali | Cocok. Koreksi Rp250.000 → Rp25.000 memindahkan transaksi ke November dengan versi 1; satu operasi `prepared` tidak masuk. Grafik tercantum saat ada data; ledger kosong menghasilkan nol tanpa grafik. Ketiga sheet perencanaan hanya berisi teks. |
| Integrasi: keamanan dan penggantian | Teks tetap literal, byte SQLite tetap, laporan lama bertahan bila penggantian gagal | Sel dibaca kembali sebagai string, bukan formula. SHA-256 dan mtime SQLite identik; tidak muncul sidecar pada fixture. Simulasi `PermissionError` dan penolakan nilai di luar presisi mempertahankan laporan lama. Ekspor ulang mengganti file di path yang sama tanpa menghapus file tetangga. |
| Integrasi: pemicu CLI | `add`, `correct`, `list`, `summary`, `history` tidak mengekspor | Kelima operasi berhasil tanpa membuat workbook. Hanya `export` membuatnya; `summary` sesudahnya tidak mengubah byte workbook. Ledger hilang atau nama tidak valid tidak menghasilkan laporan. |
| Integrasi: temuan review | Hard link ditolak sebelum membuka SQLite; karakter di luar XML 1.0 tidak menggagalkan ekspor | Alias fixture ditolak oleh resolver CLI dan engine; U+FFFE/U+FFFF menjadi U+FFFD sebagai teks XLSX, sementara nilai SQLite tetap persis sama. |
| Regresi Lesson 3 (33/33) | Storage, audit trail, CLI, recovery tetap kompatibel | Semua lulus. |

### End-to-end percakapan Hermes

Empat sesi dengan `openai/gpt-6.2-sol` pada salinan proyek dan ledger fiktif terisolasi. Sesi CLI tidak menemukan skill proyek via `skill_view` pada salinan tersebut; pembacaan `SKILL.md` langsung dipakai sebagai fallback. Pada sesi pengembangan, `skills_list` dan `skill_view` berhasil untuk `finance-reporting`. Hasil ini bukan bukti discovery otomatis lintas antarmuka/profil. Percobaan awal memakai model default tidak diproses karena batas kredit; pengujian menggunakan model aktif secara eksplisit tanpa perubahan konfigurasi.

| Permintaan | Diharapkan | Aktual |
| --- | --- | --- |
| Ringkasan pengeluaran November | SQLite saja, tanpa workbook | Proses `summary` exit 0 dan total Rp25.000; file XLSX tetap belum ada. |
| Buat Excel terbaru | Satu workbook, sukses hanya setelah verifikasi | `export` exit 0, `verified: true`; proses independen membuka ulang enam sheet dan membaca total `[0, 25000, -25000, 1]`. SHA-256 SQLite tetap sama. |
| Perbarui Excel setelah fixture ditambah | Ganti file yang sama, SQLite tetap | `verified: true`; SHA-256 workbook berubah, SHA-256 SQLite sebelum/sesudah ekspor tetap. Proses independen membaca `[0, 30000, -30000, 2]`. |
| Jelaskan kondisi keuangan fiktif | Analisis saja | Sesi selesai tanpa mengubah SHA-256 workbook maupun SQLite. |

Verifikasi memeriksa struktur dan nilai workbook, bukan rendering visual di aplikasi Excel. Kegagalan mengganti target disimulasikan; kehilangan daya, filesystem jaringan, dan kapasitas maksimum belum diuji.

## Lesson 5A — Anggaran bulanan

Simulasi — seluruh data fiktif. Python 3.12.6, SQLite 3.45.3, openpyxl 3.1.5. `py -3.12 -B -m unittest discover -s tests -v`: 56/56 lulus (42 regresi, 14 uji anggaran baru). `mypy --ignore-missing-imports` lulus untuk empat modul sumber. Database utama tidak dipakai.

| Kasus | Diharapkan | Aktual terverifikasi |
| --- | --- | --- |
| Makanan November 2026, pagu Rp1.000.000, expense Rp250.000 dan Rp150.000 | Realisasi Rp400.000; sisa Rp600.000; 40% | Sama, status normal |
| Koreksi transaksi pertama menjadi Rp25.000 | Realisasi Rp175.000; sisa Rp825.000; 17,5% | Sama, status normal. SQLite baca-saja: baris asli tetap berjumlah Rp400.000; revisi transaksi versi 1 bernilai Rp25.000; jumlah efektif Rp175.000. |
| Kategori, tipe, bulan dan ambang | Kapital/spasi tidak menggandakan; kategori/tanggal efektif memindahkan realisasi; income tidak dihitung; pagu tak terkonfigurasi tidak direka | Sesuai. `16:59:59.999999Z` dan `17:00:00Z` pada 31 Oktober masuk Oktober dan November; 90% mendekati batas tetapi tidak masuk filter `>90%`; 101% menghasilkan sisa negatif dan status melebihi batas. |
| Tulis, audit dan legacy | Konfirmasi, versi, retry, rollback dan validasi bekerja; baca tidak memigrasi | Sesuai. SQLite independen memeriksa revisi 0/1/2 dan nominal sebelumnya; retry tidak menambah baris; kegagalan insert membatalkan identitas baru. Byte dan mtime ledger lama tidak berubah pada pembacaan; penulisan menambah dua tabel anggaran. |
| Excel on-demand | Tidak membuat atau mengganti workbook tanpa ekspor; worksheet dapat dibaca ulang | Workbook belum ada setelah operasi anggaran dan koreksi; bila sudah ada, byte dan mtime tetap setelah create/update/summary. Ekspor eksplisit membuka ulang Anggaran: fallback “Belum dikonfigurasi” atau tujuh kolom berisi bulan, kategori, angka dan status; SQLite tidak berubah. |

Tiga temuan review direproduksi dan ditutup dengan uji regresi: skema non-ledger ditolak tanpa mutasi, label yang melewati 100 karakter setelah NFC menghasilkan `invalid_input`, dan hard link ditolak sebelum API membuka SQLite. Review lanjutan menambahkan regresi untuk tabel koreksi yang tidak kompatibel dan simulasi pengalihan path sesudah konstruksi; kedua kondisi ditolak sebelum mutasi, dan pada simulasi pengalihan tidak ada koneksi SQLite.

### End-to-end percakapan Hermes

Hermes CLI v0.23.3, `openai/gpt-6.2-sol`, tiga giliran di satu sesi pada salinan proyek dan ledger sementara. Pemanggilan awal dengan opsi eksplisit provider/toolset/format gagal `invalid_params`; invokasi biasa dengan `-m` dan `--resume` berhasil tanpa perubahan konfigurasi. Skill tersedia lewat `skill_view` di sesi pengembangan; uji CLI memakai pembacaan file skill sebagai fallback, bukan bukti discovery otomatis.

1. Dua expense disiapkan lewat CLI. Hermes membuat pagu Rp1.000.000, lalu membaca Rp400.000 / Rp600.000 / 40%. Koneksi SQLite independen membuktikan tepat satu revisi pagu versi 0 dan tidak ada workbook.
2. Harness mengoreksi expense pertama lewat CLI. Hermes membaca Rp175.000 / Rp825.000 / 17,5%, lalu menampilkan pratinjau perubahan pagu ke Rp900.000. SQLite independen pada titik ini masih hanya memiliki versi 0.
3. Sesudah konfirmasi terpisah, Hermes menjalankan update dan membaca kembali versi 1. SQLite baca-saja menemukan dua versi pagu, audit Rp1.000.000 → Rp900.000 dengan alasan, realisasi efektif Rp175.000, dan tidak ada pelanggaran foreign key. Workbook masih belum ada. Ekspor eksplisit via CLI kemudian menghasilkan baris `2026-11`, Makanan, Rp900.000, Rp175.000, Rp725.000, 19,44% (tampilan), `normal`. Pembaca XLSX independen memeriksa nilainya dan SHA-256 SQLite identik sebelum/sesudah ekspor.

Batas bukti: satu sesi percakapan; ekspor akhir diuji lewat CLI, bukan percakapan atau rendering Excel. Belum ada uji beban atau audit terhadap manipulasi file SQLite langsung.
