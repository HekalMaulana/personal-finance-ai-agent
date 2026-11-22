# Personal Finance AI Assistant

Prototipe asisten keuangan pribadi berbahasa Indonesia berbasis Hermes Agent. Proyek ini menunjukkan bagaimana instruksi proyek dan skill yang dapat ditinjau di Git membantu agen menghasilkan analisis keuangan yang transparan, mengakui data yang belum tersedia, dan tetap berada dalam batas izin. **Hanya untuk simulasi dengan data fiktif.**

## Teknologi dan arsitektur

- **Hermes Agent** menjalankan percakapan dan memuat skill proyek pada sesi yang memenuhi syarat. CLI yang diperiksa dalam pengembangan: v0.23.3.
- **Markdown dan YAML frontmatter** mendefinisikan aturan proyek (`AGENTS.md`) dan prosedur analisis (`SKILL.md`). Repositori tidak menambahkan runtime aplikasi atau dependensi analisis sendiri.
- **Git** mencatat perkembangan dokumentasi dan skill. `.gitignore` membantu mengecualikan artefak lokal, tetapi tidak menggantikan pemeriksaan sebelum commit.

Alur saat ini: **masukan fiktif → validasi dan klarifikasi → perhitungan eksplisit → rekomendasi dalam percakapan**. Tidak ada penulisan transaksi atau penyimpanan saldo oleh prototipe ini. Lihat [arsitektur](docs/architecture.md) untuk alur dan batas antar komponen.

## Status proyek

| Status | Cakupan |
| --- | --- |
| Tersedia, evaluasi awal lulus | Tiga uji percakapan lulus: penemuan skill, analisis keuangan fiktif, dan estimasi dengan data tidak lengkap. Lihat [hasil dan batas evaluasi](docs/evaluation.md). |
| Dalam pengembangan | Evaluasi konsistensi lintas sesi dan kasus tepi. Belum ada suite evaluasi otomatis atau pengujian keamanan menyeluruh. |
| Direncanakan, belum aktif | Pencatatan transaksi melalui percakapan, SQLite lokal sebagai sumber data, satu laporan Excel atas permintaan eksplisit, tinjauan mingguan, evaluasi dana darurat triwulanan, serta pengecekan jadwal terlewat. Perencanaan target saat ini hanya berupa estimasi dalam percakapan, bukan pelacakan kemajuan yang tersimpan. |

## Mencoba prototipe

1. Buka sesi Hermes dari direktori repositori. Skill ada di [`.hermes/skills/personal-finance-analysis/SKILL.md`](.hermes/skills/personal-finance-analysis/SKILL.md). Jika belum tersedia di sesi, periksa penemuan skill proyek dan status kepercayaan repositori. Sebagai alternatif, minta agen membaca `SKILL.md` langsung; pembacaan manual tidak membuktikan penemuan otomatis.
2. Gunakan skenario fiktif di [dokumen evaluasi](docs/evaluation.md). Minta agen menampilkan rumus, asumsi, pertanyaan klarifikasi, dan saran yang tidak melebihi surplus rutin.
3. Cocokkan hasil dengan nilai pembanding. Jangan masukkan data rekening, kredensial, atau transaksi asli.

## Dokumentasi pengembangan

- [Arsitektur](docs/architecture.md) — alur saat ini, batas keamanan, dan rancangan fitur berikutnya.
- [Log pengembangan](docs/development-log.md) — milestone, eksperimen, dan keputusan desain.
- [Evaluasi](docs/evaluation.md) — bukti yang tersedia, batas verifikasi, dan kasus uji berikutnya.
- [Aturan agen dan kontribusi](AGENTS.md) — kebijakan analisis, peninjauan perubahan, dan commit lokal. Tidak ada push otomatis.
