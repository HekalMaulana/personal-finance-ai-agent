---
name: finance-reporting
description: "Export Excel on explicit request. Use fictional ledgers."
---

# Laporan Excel atas permintaan

Ikuti `AGENTS.md`. Skill ini hanya untuk ekspor dari ledger fiktif yang sudah ada dan disepakati. Workbook adalah keluaran turunan, bukan sumber data atau saldo rekening aktual.

## Pilih jalur berdasarkan permintaan

- “Buat laporan keuangan Excel terbaru” atau “Perbarui laporan Excel saya”: ekspor hanya jika permintaan pembuatan/pembaruan jelas dan nama ledger fiktif diketahui. Keduanya memakai target yang sama: `reports/laporan-keuangan.xlsx`. Tanyakan nama ledger jika belum jelas; jangan menebak atau mengambil path dari pengguna.
- “Berapa pengeluaran bulan ini?”: gunakan `finance-transactions` dan `summary` pada ledger yang disepakati, dengan rentang hari lokal Asia/Pontianak. Tidak membuat Excel.
- “Jelaskan kondisi keuangan saya”: gunakan `personal-finance-analysis` untuk data fiktif. Jangan ekspor otomatis.
- Pencatatan, koreksi, pembacaan, riwayat, pemulihan, dan pertanyaan tentang fitur bukan izin ekspor. Jangan menjadwalkan ekspor. Jangan akses database utama, data asli, atau laporan lama untuk mencari ledger.

## Jalankan dan verifikasi

Dari root proyek pada Windows, panggil `py -3.12 -B finance_reporting.py --ledger NAMA export`. `NAMA` harus cocok `[a-z][a-z0-9-]{0,47}`; ganti hanya token itu, tanpa interpolasi teks pengguna lain. Tidak ada JSON stdin atau argumen output. Di lingkungan lain gunakan interpreter Python 3.12+ yang sudah dapat mengimpor `openpyxl`. Jika `skill_view` tidak menemukan skill pada CLI mandiri, baca `.hermes/skills/finance-reporting/SKILL.md` dari root proyek yang sudah diverifikasi; ini bukan bukti penemuan otomatis. Jangan pasang dependensi atau ubah konfigurasi; jika perintah tidak tersedia, minta interpreter yang telah disiapkan.

Konfirmasi sukses hanya jika proses selesai dengan exit 0, JSON `ok: true`, `operation: "export"`, `data.verified: true`, ledger yang sama, path persis `reports/laporan-keuangan.xlsx`, dan jumlah transaksi integer nonnegatif. CLI membuka ulang workbook sementara untuk memeriksa struktur dan total sebelum mengganti file. Keberadaan file lama saja bukan bukti keberhasilan. Pada timeout, kegagalan atau hasil tidak pasti, laporkan bahwa pembaruan belum terverifikasi; jangan mengklaim laporan lama adalah laporan baru. Laporkan path dan jumlah transaksi setelah sukses. `Anggaran` menampilkan pagu dan realisasi efektif SQLite, atau “Belum dikonfigurasi” bila kosong. `Dana Darurat` menampilkan alokasi yang dilaporkan pengguna, bukan saldo bank; nilai yang belum ditetapkan tetap kosong atau “Belum dikonfigurasi”. `Target Tabungan` tetap belum dikonfigurasi. Permintaan anggaran mengikuti `finance-budgets`, tanpa ekspor otomatis. Jangan kirim workbook ke pihak lain.
