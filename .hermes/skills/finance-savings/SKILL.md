---
name: finance-savings
description: "Use when managing fictional savings goals. Verify writes."
---

# Target tabungan fiktif

Ikuti `AGENTS.md`. Gunakan ledger fiktif yang sudah ada dan disepakati; jangan memilih path dari pengguna atau membuka database utama. Ini alokasi yang dilaporkan, bukan saldo bank. Jangan catat mutasi lagi sebagai transaksi umum atau dana darurat. Untuk simulasi tanpa penyimpanan gunakan `personal-finance-analysis`; ekspor hanya atas permintaan eksplisit lewat `finance-reporting`.

- `savings-list` dengan `{}` untuk mencari target. Gunakan UUID `id` yang tepat; tanyakan jika nama ambigu. `savings-get` memakai `id` dan opsional `monthly_contribution_rupiah` bila pengguna menyatakan setoran bulanan tetap. Estimasi adalah bulan ke depan tanpa bunga/penarikan; tenggat hanya informasi. Jangan gunakan surplus arus kas. `null` berarti belum diketahui, bukan nol. Labeli “Simulasi — data fiktif”.
- `savings-create` untuk permintaan pencatatan baru yang eksplisit: `name`, `target_rupiah` (integer positif), `idempotency_key`, opsional `due_date` (`YYYY-MM-DD`). Sampaikan UUID dan key. Pembuatan tidak mencatat saldo awal; Rp0 pun perlu dicatat eksplisit.
- `savings-preview` hanya membaca: kirim `id` + `amount_rupiah` (integer ≥0) untuk saldo awal atau koreksinya; atau `id`, `name`, `target_rupiah`, `due_date` untuk revisi target. Untuk revisi, `due_date` wajib. Kirim lagi nilai efektif untuk field target yang tidak berubah, termasuk tenggat. Pakai `null` secara eksplisit hanya bila tidak ada tenggat atau pengguna bermaksud menghapusnya. Tampilkan ledger, UUID, revisi, nilai sebelum → sesudah (termasuk saldo hasil), dan alasan. Tunggu konfirmasi eksplisit pada giliran berikutnya. Setelah disetujui, pakai persis objek `changes` hasil pratinjau ditambah `confirmed:true`, `reason`, dan `idempotency_key`; jalankan `savings-opening` atau `savings-update` sesuai jenisnya. Pada `stale_version`, baca/pratinjau ulang dan minta konfirmasi baru.
- `savings-move`: `id`, `direction` (`deposit` atau `withdrawal`), `amount_rupiah` (integer positif), `idempotency_key`, opsional `description`. Harus ada saldo awal. `insufficient_fund` berarti ditolak. Jangan tulis bila maksud, nominal, atau identitas target belum jelas.

Dari root, gunakan interpreter proyek dari skill `finance-transactions` untuk menjalankan `-B finance_cli.py --ledger NAMA OPERASI`. Nama ledger harus cocok `[a-z][a-z0-9-]{0,47}` dan operasi literal. Ikuti transport JSON stdin aman di `finance-transactions` (PTY Windows: JSON ASCII, CR/Ctrl+Z/CR, tunggu proses selesai). Jika discovery tidak tersedia, baca `.hermes/skills/finance-savings/SKILL.md` di root yang telah diverifikasi; jangan ubah konfigurasi.

Bekukan key unik per maksud dan payload sebelum menulis. Konfirmasi hanya bila exit 0, `ok:true`, operasi sesuai, serta UUID, key, jenis, revisi dan `request` yang disimpan cocok. Setelah timeout atau sesi baru, baca `savings-history` dengan `id` (gunakan daftar target bila perlu); verifikasi key dan payload tersimpan. Untuk retry teridentifikasi gunakan operasi asal dan objek `request` persis, jangan buat key baru atau menulis berdasarkan kemiripan nominal. Konflik key bukan izin membuat operasi baru. Retry mengembalikan revisi historis; baca `savings-get` untuk saldo terkini.
