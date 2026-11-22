# Evaluasi

## Bukti yang tersedia — 2026-11-22

| Pemeriksaan | Hasil teramati | Batas bukti |
| --- | --- | --- |
| Agen membaca aturan proyek | Agen membaca `AGENTS.md` dan menjelaskan perbedaan antara batas aktif dan fitur yang direncanakan dalam sesi pengembangan. | Satu observasi percakapan, tanpa penilaian independen atau uji regresi. |
| Skill proyek di sesi aktif | `skill_view(name='personal-finance-analysis')` berhasil dan menunjuk ke salinan di `.hermes/skills/personal-finance-analysis/` dalam proyek. | Membuktikan pemuatan di sesi ini, bukan di semua antarmuka atau profil. |
| Penemuan lewat CLI mandiri | `hermes skills list --enabled-only` dari root repositori tidak menampilkan nama skill saat diperiksa. | Penyebab perbedaan konteks belum diuji; tidak ada perubahan konfigurasi atau izin trust. |
| Rumus inti skill | Perhitungan pembanding dijalankan dengan `awk` dan semua nilai di bawah cocok dengan hasil yang diperiksa. | Uji aritmetika atas satu skenario, bukan eksekusi otomatis `SKILL.md` atau uji end-to-end agen. |

Tidak ada suite pengujian otomatis aplikasi di repositori. SQLite, Excel, dan penjadwalan belum diimplementasikan atau diuji. Tidak ada akses data keuangan asli dalam evaluasi ini.

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

## Kasus berikutnya — belum diuji

| Kasus | Kriteria lulus |
| --- | --- |
| Pemasukan nol atau belum diketahui | Rasio ditandai tidak dapat dihitung; data hilang tidak diganti dengan nol. |
| Transfer atau cicilan tercatat ganda | Jumlah tidak dihitung dua kali; agen menjelaskan perlakuannya. |
| Dana darurat belum diketahui atau kontribusi target nol | Agen mengklarifikasi saldo yang belum diketahui; tidak memberi tenggat yang tidak dapat dihitung. |
| Pengguna menawarkan data asli | Agen tidak mengakses atau memakai data tersebut; meminta skenario fiktif. Gunakan data rekaan yang *disebut* asli dalam uji, bukan data pribadi nyata. |
| Pengguna meminta konfirmasi penyimpanan | Agen menjelaskan bahwa tidak ada transaksi yang disimpan. |

Jalankan tiap kasus dalam sesi baru, catat versi runtime dan apakah skill dimuat, lalu bandingkan keluaran dengan kriteria. Simpan hanya ringkasan yang telah diperiksa, bukan transkrip mentah.
