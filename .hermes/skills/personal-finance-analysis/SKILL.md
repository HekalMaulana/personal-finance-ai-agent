---
name: personal-finance-analysis
description: "Use when analyzing mock finances. Show calculations."
---

# Analisis keuangan pribadi

Gunakan prosedur ini untuk membantu pengguna memahami anggaran, arus kas, dana darurat, dan target tabungan dalam bahasa Indonesia. Ikuti `AGENTS.md`; gunakan hanya data fiktif dan beri label **Simulasi — data fiktif**. Jika pengguna menawarkan data keuangan asli, jangan akses atau gunakan data itu; minta skenario fiktif sebagai pengganti. Analisis ini tidak menyimpan transaksi, membuat laporan Excel atau database, memasang MCP atau dependensi, mengubah konfigurasi, ataupun menjalankan transaksi keuangan.

## 1. Validasi masukan

- Tetapkan periode, mata uang, dan cakupan (individu atau rumah tangga). Untuk arus kas aktual dalam simulasi, gunakan penerimaan dan pembayaran dalam periode yang sama. Jangan campur angka aktual dalam skenario dengan anggaran atau proyeksi. Untuk proyeksi bulanan, nyatakan konversi frekuensi dan pisahkan pos satu kali dari pos berulang.
- **Pemasukan:** gunakan nominal bersih yang diterima. Pisahkan pemasukan rutin dari pemasukan tidak rutin. Jangan hitung pinjaman, transfer antar rekening sendiri, atau penarikan tabungan sebagai pemasukan.
- **Pengeluaran:** periksa tanggal, nominal, kategori, duplikasi, dan pengembalian dana. Pisahkan pos esensial dan nonesensial; periksa total kategori terhadap rincian. Jangan hitung pembelian kartu kredit dan pelunasan pembelian yang sama sebagai dua pengeluaran. Nyatakan perlakuan atas keduanya dengan konsisten.
- **Tabungan:** bedakan saldo yang sudah tersedia dari setoran dan penarikan selama periode. Hitung perpindahan ke tabungan sebagai alokasi, bukan konsumsi. Jangan menghitung transfer antarkantong tabungan atau perubahan nilai aset sebagai tabungan baru. Pisahkan dana darurat dan dana untuk masing-masing target.
- **Cicilan:** periksa nominal pembayaran per periode, tanggal jatuh tempo, dan apakah tercatat juga dalam kategori lain. Pisahkan pembayaran minimum wajib dari pelunasan tambahan. Jika tersedia, pisahkan pokok, bunga, dan biaya; jangan menambahkan komponen itu lagi bila sudah tercakup dalam total cicilan.
- **Target:** periksa nominal total (termasuk biaya terkait bila diketahui), saldo khusus target, tenggat jika ada, serta kontribusi rutin yang realistis. Jangan alokasikan saldo yang sama untuk beberapa target.
- Bedakan nol yang dikonfirmasi dari data yang belum ada. Jika informasi penting hilang atau bertentangan, ajukan klarifikasi yang spesifik. Jangan mengarang angka; tampilkan perhitungan parsial yang masih valid dan tandai metrik yang belum dapat dihitung.

## 2. Hitung arus kas dan rasio

Gunakan periode dan mata uang yang sama untuk pembilang dan penyebut. Dalam rumus berikut, *aktual* berarti benar-benar terjadi dalam skenario fiktif, bukan data dunia nyata.

| Metrik | Rumus dan perlakuan |
| --- | --- |
| Arus kas bersih sebelum alokasi tabungan | Pemasukan bersih diterima − pengeluaran aktual termasuk cicilan yang dibayar. Transfer ke tabungan sendiri bukan pengeluaran. |
| Tabungan bersih aktual | Setoran aktual ke tabungan yang berasal dari dana baru − penarikan aktual dari tabungan untuk penggunaan di luar tabungan. Keluarkan transfer antarpos tabungan dan penyetoran kembali saldo lama. |
| Saving rate aktual | Tabungan bersih aktual ÷ pemasukan bersih diterima × 100%. Jangan gunakan surplus yang belum ditabung atau setoran yang baru direncanakan. Rasio dapat negatif bila penarikan melebihi setoran. |
| Rasio pengeluaran | Pengeluaran aktual termasuk cicilan ÷ pemasukan bersih diterima × 100%. Untuk rasio kategori, ganti pembilang dengan pengeluaran aktual kategori itu; pisahkan esensial, nonesensial, dan cicilan tanpa tumpang tindih. |

Jika pemasukan nol, negatif, atau belum diketahui, tampilkan rasio terhadap pemasukan sebagai **tidak dapat dihitung** dan jelaskan sebabnya. Laporkan surplus atau defisit sesuai tanda hasil. Tampilkan angka yang dimasukkan ke rumus beserta satuannya, gunakan alat hitung yang tersedia bila perlu, dan bulatkan hasil hanya untuk tampilan.

## 3. Evaluasi dana darurat

- Hitung pengeluaran esensial bulanan: kebutuhan inti yang tetap harus dibayar saat pemasukan terganggu, termasuk pembayaran minimum cicilan. Jika cicilan tersebut sudah ada di total kebutuhan inti, jangan hitung kembali. Bila data mencakup beberapa bulan, gunakan periode representatif atau nyatakan mengapa tidak; jelaskan cara meratakan tagihan esensial berkala.
- Hitung `cakupan (bulan) = saldo dana darurat likuid yang memang dialokasikan ÷ pengeluaran esensial bulanan`. Jangan masukkan limit kredit, tabungan target lain, atau aset yang tidak siap dicairkan. Jika pengeluaran esensial nol atau belum diketahui, jangan menyatakan cakupan tak terbatas; minta klarifikasi.
- Untuk horizon yang dipilih, hitung `target dana darurat = pengeluaran esensial bulanan × bulan perlindungan` dan `kekurangan = maksimum(0, target dana darurat − saldo dana darurat yang memenuhi syarat)`. Kaitkan horizon dengan stabilitas pemasukan, tanggungan, dan risiko biaya mendadak. Jika horizon belum ditetapkan, bandingkan skenario berlabel asumsi, bukan satu target yang seolah pasti.

## 4. Estimasi waktu mencapai target

- Hitung `sisa target = maksimum(0, total target − saldo khusus target)`. Jika sisa nol berdasarkan masukan yang tersedia, target sudah tercapai dalam simulasi.
- Untuk kontribusi bulanan konstan yang positif, hitung `bulan = pembulatan ke atas(sisa target ÷ kontribusi bulanan)`. Dasar proyeksi: setoran bulanan, tanpa bunga dan tanpa kenaikan harga kecuali skenario menyatakan lain. Bila kontribusi nol atau negatif dan masih ada sisa, target tidak tercapai dengan pola tersebut; bila kontribusi belum diketahui, waktu belum dapat diestimasi.
- Jika tenggat menyisakan jumlah bulan positif, hitung `setoran bulanan yang dibutuhkan = sisa target ÷ jumlah setoran bulanan yang masih bisa dilakukan sebelum tenggat`. Bulatkan ke atas sesuai satuan mata uang agar tidak kurang. Bandingkan dengan surplus rutin setelah kewajiban dan alokasi lain, termasuk dana darurat. Jika tidak ada lagi kesempatan setoran bulanan, laporkan kekurangannya, bukan membaginya dengan nol.
- Untuk pemasukan atau kontribusi yang berubah-ubah, sajikan skenario konservatif dan dasar jika masukan mendukungnya. Nyatakan bahwa hasil adalah estimasi, bukan jaminan.

## 5. Ungkap asumsi, risiko, dan data yang belum ada

Tandai setiap asumsi yang memengaruhi hasil, misalnya kestabilan pemasukan, biaya tak rutin, perubahan harga target, bunga, atau jumlah setoran sebelum tenggat. Jelaskan risiko yang paling berpengaruh, arah dampaknya, dan masukan apa yang diperlukan untuk memperbaiki estimasi. Jangan masukkan nilai yang belum disepakati ke dalam angka aktual. Gunakan rentang atau skenario bersyarat bila masuk akal dan beri label jelas.

## 6. Sajikan hasil dan saran realistis

1. **Fakta dalam simulasi:** rangkum masukan, cakupan, periode, dan mata uang.
2. **Asumsi dan data yang belum tersedia:** pisahkan dari fakta; ajukan pertanyaan klarifikasi yang paling berpengaruh.
3. **Perhitungan:** tampilkan rumus, angka masukan, hasil dan satuan, serta interpretasi singkat. Tandai metrik yang tidak dapat dihitung.
4. **Risiko:** soroti biaya, perubahan pendapatan, atau benturan antaralokasi yang dapat mengubah hasil.
5. **Rekomendasi:** urutkan tindakan sesuai temuan. Jika defisit, utamakan kebutuhan pokok dan kewajiban sebelum menaikkan setoran. Jika ada surplus, bandingkan alokasi dana darurat dan target tanpa mengalokasikan uang yang sama dua kali. Jika tenggat tidak realistis, jelaskan pilihan seperti merevisi tenggat, nominal target, atau pos nonesensial dan tunjukkan dampaknya dengan rumus. Jangan menyatakan transaksi sudah tersimpan; jika relevan, katakan bahwa tidak ada transaksi yang disimpan.
