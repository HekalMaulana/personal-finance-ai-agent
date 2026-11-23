---
name: finance-budgets
description: "Use for monthly budgets on fictional ledgers. Verify writes."
---

# Anggaran bulanan fiktif

Ikuti `AGENTS.md`. Gunakan hanya ledger uji fiktif yang sudah ada dan disepakati. Jangan membuka database utama, membuat ledger dari permintaan anggaran, atau memakai path dari pengguna. Untuk simulasi tanpa penyimpanan gunakan `personal-finance-analysis`. Jangan memicu Excel; hanya permintaan ekspor eksplisit mengikuti `finance-reporting`.

## Pilih operasi

- Pertanyaan sisa atau status: `budget-summary` dengan `period` (`YYYY-MM`), opsional `category`. Untuk **lebih dari** 90% gunakan `above_warning:true`. Untuk **minimal** 90%, baca ringkasan biasa dan tampilkan status mendekati/melebihi batas. `[]` tanpa filter berarti belum ada anggaran sesuai periode/kategori; bila ada filter ambang, `[]` hanya berarti tidak ada yang melewatinya. Jangan mengarang pagu. Kutip nilai SQLite dan gunakan label “Simulasi — data fiktif”.
- “Bulan ini” berarti bulan kalender pada UTC+07:00 (Asia/Pontianak); ambil waktu aktual dari alat. Jika periode tidak disebut tetapi maksud bulan berjalan jelas dalam konteks, sebut bulan tersebut secara eksplisit; jika ambigu, tanyakan. Tanyakan juga bila ledger, kategori, atau nominal integer Rupiah positif belum jelas.
- `budget-get`: kirim `period`, `category`. `budget_not_found` berarti anggaran tidak dikonfigurasi; `database_not_found` berarti ledger tidak ada. `budget-history`: field sama; daftar versi dari awal.
- Pembuatan baru yang eksplisit: `budget-create` berisi `period`, `category`, `amount_rupiah`, `idempotency_key`. Jika sudah ada (`budget_exists`), jangan menimpa; baca versi efektif dan masuk alur tinjauan. Pemilihan kategori mengabaikan kapitalisasi dan spasi tepi/berulang.
- Pembaruan: baca `budget-get`, lalu tampilkan ledger, bulan, kategori, versi, nominal lama → baru, serta alasan singkat. Tunggu konfirmasi eksplisit dalam giliran berikutnya. Setelah dikonfirmasi, pakai `budget-update` dengan field create ditambah `expected_version` persis dari pratinjau, `confirmed:true`, dan `reason`. Jangan mengubah payload yang disetujui. Pada `stale_version`, baca ulang dan minta konfirmasi baru. Tidak ada penghapusan.

## Jalankan CLI dan verifikasi

Dari root proyek, jalankan `-B finance_cli.py --ledger NAMA OPERASI` dengan interpreter proyek dari skill `finance-transactions`. Ikuti bagian “Panggil CLI tanpa interpolasi shell” di skill `finance-transactions`: nama cocok `[a-z][a-z0-9-]{0,47}`, operasi literal dari daftar di atas, satu objek JSON UTF-8 via stdin (gunakan serializer ASCII untuk PTY Windows). Tunggu exit proses yang selesai. Bila discovery tidak tersedia pada CLI mandiri, baca file skill di `.hermes/skills/finance-budgets/SKILL.md`; jangan mengubah konfigurasi atau kebijakan terminal.

Bekukan satu key unik per maksud (UUID atau referensi eksplisit) dan payload sebelum menulis. Klaim sukses hanya setelah proses selesai dengan exit 0, `ok:true`, nama operasi sesuai, serta periode, kategori, nominal, key, dan versi sesuai pada revisi yang dibaca SQLite. Untuk pembaruan, periksa juga nominal sebelumnya dan alasan. Jika hasil tidak pasti, periksa `budget-history` untuk key dan payload tersebut; retry hanya dengan payload dan key yang sama. Jangan membuat key baru jika operasi lama belum pasti. Retry dapat mengembalikan revisi historis, bukan versi terkini; gunakan `budget-get` untuk nilai saat ini.
