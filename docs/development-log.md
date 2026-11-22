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
