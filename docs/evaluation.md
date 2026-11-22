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

Pengecekan tipe `mypy` juga lulus. Pengujian ini bukan audit keamanan menyeluruh: belum mencakup crash/pemulihan daya, beban jangka panjang, file yang dimodifikasi di luar API, ataupun integrasi Hermes.
