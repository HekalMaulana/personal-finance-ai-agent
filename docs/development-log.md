# Log pengembangan

Log ini mencatat keputusan dan bukti; status Git commit tetap ditentukan oleh riwayat Git, bukan halaman ini.

## Baseline — aturan dan skill analisis

- Menetapkan `AGENTS.md` sebagai aturan proyek dan `SKILL.md` sebagai prosedur analisis yang dapat ditinjau terpisah, tanpa program atau dependensi baru.
- Membatasi masukan ke data fiktif. Membedakan analisis di percakapan dari pencatatan transaksi yang tersimpan.
- Mendefinisikan saving rate sebagai tabungan bersih aktual dalam simulasi, bukan surplus yang belum ditabung. Menjadikan pengeluaran esensial sebagai dasar cakupan dana darurat.

## 2026-11-22 — baseline dokumentasi dan verifikasi

- Saat inspeksi awal, repositori Git lokal berada di cabang `master` tanpa commit. File proyek yang ada hanya aturan agen dan skill analisis.
- Menambahkan dokumentasi arsitektur dan evaluasi, aturan commit lokal, serta `.gitignore` untuk artefak dan data lokal. Skill analisis tidak diubah.
- Eksperimen penemuan skill: `skill_view` berhasil memuat salinan proyek di sesi pengembangan, tetapi CLI mandiri dari root tidak menampilkan skill dalam daftar aktif. Catat hasil per konteks; jangan menyamakan keberhasilan satu sesi dengan penemuan otomatis di sesi lain.
- Eksperimen hitung: satu skenario bulanan fiktif diperiksa dengan alat hitung shell dan hasilnya sesuai nilai pembanding. Ini bukan uji menyeluruh terhadap respons model. Rincian ada di [evaluasi](evaluation.md).
- Keputusan: tahan commit pertama sampai persetujuan eksplisit, lalu izinkan commit lokal rutin yang telah diverifikasi. Tidak ada perubahan remote atau push otomatis.

## 2026-11-22 — evaluasi awal Financial Analysis Skill selesai

- Tiga pengujian percakapan lulus: penemuan dan pemuatan resmi skill, analisis bulanan dengan data fiktif, serta estimasi bersyarat ketika saldo awal dan setoran rutin belum diketahui.
- [Dokumen evaluasi](evaluation.md#evaluasi-awal-personal-finance-analysis--2026-11-22) mencatat hasil yang diharapkan, hasil aktual, bukti, dan keterbatasan tiap uji. Tidak ada kegagalan yang menuntut perubahan pada `SKILL.md`.
- Keamanan hanya diamati dari perilaku yang dilaporkan, belum diuji menyeluruh. Konsistensi lintas konteks dan kasus tepi tetap menjadi pekerjaan lanjutan.

## 2026-11-22 — Lesson 3: penyimpanan SQLite mandiri

- Menambahkan `finance_storage.py` dan harness `unittest` tanpa dependensi runtime baru. API memakai nominal integer, waktu Pontianak UTC+07:00, UUID, dan idempotency key unik. Tidak ada API ubah atau hapus.
- Sebelas uji lulus dengan file SQLite sementara yang terpisah dari `data/finance.db`, termasuk insert tiga transaksi fiktif, persistensi, batas hari lokal, dan retry bersamaan. Lihat [hasil evaluasi](evaluation.md#lesson-3--penyimpanan-sqlite-mandiri).
- Pada tahap ini belum ada integrasi percakapan atau akses data asli. Koreksi dengan audit trail masih berupa [rancangan](architecture.md#koreksi-append-only--lesson-3-tahap-c).

## 2026-11-22 — Lesson 3 Tahap B: CLI dan skill transaksi

- Menambahkan CLI JSON `add`, `get`, `list`, dan `summary` serta skill proyek `finance-transactions`. Storage engine tetap menangani validasi, query berparameter, penyimpanan atomik, dan idempotensi. Perubahan engine terbatas pada mode baca-saja dan inisialisasi opsional saat penambahan valid.
- Sebelas uji engine dan delapan uji integrasi CLI lulus. Uji percakapan baru memuat skill melalui mekanisme resmi, menulis dua transaksi uji, melakukan retry idempoten, dan membaca kembali melalui proses CLI baru. Verifikasi SQLite baca-saja mengonfirmasi dua baris dengan ID yang sama. Database utama tidak digunakan.
- Preload via `--skills` tidak berhasil di gateway yang diuji; discovery dari dalam sesi berhasil. PTY Windows mengirim JSON melalui stdin tanpa mengubah kebijakan persetujuan. Lihat [bukti dan batas uji](evaluation.md#lesson-3-tahap-b--cli-dan-percakapan-hermes).

## 2026-11-22 — Lesson 3 Tahap C: koreksi dan audit trail

- Menambahkan revisi append-only dengan versi, key idempoten, alasan, dan waktu koreksi. Baris asli tidak berubah; pembacaan efektif hanya mengambil revisi terakhir. Pembuatan tabel aditif diuji pada skema lama.
- Menambahkan `correct`, `history`, dan versi opsional pada `get`. Hermes menampilkan pratinjau baca-saja sebelum konfirmasi dan tidak membentuk key baru untuk retry yang belum pasti.
- Seluruh 29 uji otomatis lulus, termasuk regresi JSON ASCII untuk field Unicode maksimum. E2E dua giliran dan verifikasi SQLite terpisah mengonfirmasi tepat satu revisi Rp250.000 → Rp25.000. Lihat [bukti uji](evaluation.md#lesson-3-tahap-c--koreksi-dan-audit-trail).
