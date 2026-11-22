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

Analisis menghitung arus kas sebelum alokasi tabungan, saving rate dari tabungan bersih yang benar-benar terjadi dalam simulasi, dan rasio pengeluaran terhadap pemasukan bersih. Dana darurat dinilai terhadap pengeluaran esensial bulanan. Estimasi target memakai saldo yang khusus dialokasikan dan setoran rutin yang realistis. Prototipe ini tidak memiliki penyimpanan transaksi sendiri; hal ini bukan jaminan layanan Hermes atau penyedia model tidak mencatat percakapan. Jangan memasukkan data asli.

## Desain berikutnya — belum diimplementasikan

| Lapisan | Rancangan dan syarat verifikasi |
| --- | --- |
| Pencatatan percakapan | Pisahkan kandidat transaksi dari tindakan simpan. Validasi nominal, periode, dan kategori; minta klarifikasi bila ambigu. Konfirmasi keberhasilan hanya setelah hasil simpan diverifikasi. |
| SQLite lokal | Sumber data utama yang direncanakan. Uji duplikasi, konsistensi total, dan kegagalan simpan dengan data fiktif sebelum aktivasi. File database dan berkas pendampingnya tidak masuk Git. |
| Laporan Excel | Satu laporan, dibuat atau diperbarui hanya atas permintaan eksplisit. Perlakukan workbook sebagai keluaran turunan, bukan sumber data kedua. Verifikasi isi dan rumus terhadap sumber sebelum menyatakan berhasil. |
| Penjadwalan | Rencana untuk tinjauan mingguan, evaluasi triwulanan dana darurat, dan pemulihan tinjauan yang terlewat ketika perangkat mati. Definisikan cara mencegah eksekusi ganda sebelum diaktifkan. |

Urutan pengembangan yang disarankan: evaluasi perilaku agen → uji lapisan penyimpanan dengan data fiktif → verifikasi ekspor → evaluasi penjadwalan. Rancangan ini bukan izin untuk membuat database, integrasi, atau otomasi. Tidak ada tindakan perbankan atau investasi di dalam cakupan proyek.
