# Kebijakan Privasi Noise Filter

Terakhir diperbarui: 14 November 2026 (aplikasi versi 0.9.0)

Noise Filter adalah aplikasi Windows dari SkillsHUB Electronics untuk membersihkan suara mikrofon. Kebijakan ini
menjelaskan data apa yang ditangani aplikasi, apa yang keluar dari PC Anda dan kapan, serta cara menghapusnya.
Versi bahasa Inggris ([PRIVACY.md](PRIVACY.md)) adalah versi utama.

## Ringkasnya

- Suara mikrofon Anda diproses **hanya di PC Anda**. Suara itu tidak pernah direkam ke disk atau dikirim ke
  mana pun saat Anda memakai filter.
- **Tidak ada akun, iklan, analitik, pelacakan, atau laporan crash.**
- Aplikasi memakai internet hanya untuk dua hal: **memeriksa model AI baru** (unduhan dari GitHub) dan,
  **hanya ketika Anda menekan "Kirim"**, mengunggah **sampel noise** pendek yang Anda pilih untuk dibagikan.
- Anda bisa menghapus semua sampel noise yang pernah Anda kirim dengan satu tombol:
  **Pengaturan > Model AI & sampel noise > Hapus sampel saya**.

## 1. Data yang tetap di PC Anda

| Apa | Di mana | Untuk apa |
|---|---|---|
| Pengaturan (perangkat, filter, equalizer, tema, bahasa, ukuran jendela) | `%APPDATA%\NoiseFilter\config.json` | Mengingat pilihan Anda |
| Model AI yang diunduh | `%APPDATA%\NoiseFilter\models\` | Model peredam noise yang lebih baru |
| Status berbagi sampel: ID instalasi acak, pilihan persetujuan, jumlah sampel terkirim | `%APPDATA%\NoiseFilter\contribute.json` | Agar Anda bisa menghapus sampel nanti |
| Profil "Pelajari noise ruangan saya" | Hanya di memori | Peredaman lebih baik; hilang saat aplikasi ditutup |

Aliran suara dari mikrofon melewati filter di memori, 10 ms setiap kali, lalu dikirim ke perangkat output yang
Anda pilih (misalnya VB-CABLE). Suara itu tidak disimpan.

**Kendali lokal.** Perintah `nfctl` dan server MCP untuk asisten AI berbicara dengan aplikasi melalui pipe lokal
yang hanya bisa dibuka oleh akun Windows Anda. Tidak ada yang lewat jaringan.

Menghapus instalasi aplikasi tidak menghapus `%APPDATA%\NoiseFilter`; hapus folder itu untuk membuang file-file ini.

## 2. Pemeriksaan pembaruan model AI

Sekitar 3 detik setelah aplikasi dibuka, dan saat Anda menekan "Cek update model AI", aplikasi mengunduh
file kecil (`manifest.json`) dari `raw.githubusercontent.com` (GitHub). Jika ada model yang lebih baru, file
model diunduh dari GitHub dan checksum-nya diverifikasi. **Tidak ada data tentang Anda yang diunggah.** Seperti
permintaan web lainnya, GitHub menerima alamat IP Anda dan user agent aplikasi; cara GitHub menanganinya
dijelaskan di [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).
Atur variabel lingkungan `NF_NO_UPDATE_CHECK=1` untuk mematikan pemeriksaan otomatis.

## 3. Berbagi sampel noise (opsional)

Anda bisa membantu AI menjadi lebih baik dengan membagikan rekaman **noise latar saja** (kipas, AC, lalu lintas,
keyboard...). Ini selalu pilihan Anda:

- Aplikasi menawarkan sampel setelah "Pelajari noise ruangan saya", "Rekam noise…" (10 detik dari mikrofon) atau
  "Kirim file noise…" (file yang Anda rekam sendiri). Anda bisa mendengarkannya dulu.
- Sebelum ditawarkan, rekaman diperiksa **di PC Anda**, dan bagian yang terdengar seperti suara orang atau musik
  ditolak.
- Tidak ada yang dikirim sebelum Anda mencentang kotak persetujuan dan menekan **Kirim**. Tawaran ini bisa
  dimatikan dengan "Jangan tanya lagi" atau pengaturan "Tawarkan berbagi sampel noise".

**Yang dikirim bersama setiap sampel:**

- klip audio (2-10 detik, WAV mono 48 kHz);
- jenis noise yang Anda pilih (misalnya "Kipas / AC");
- versi aplikasi dan nama sistem operasi (misalnya "windows");
- ID instalasi acak (dibuat sekali di PC Anda; mengenali instalasi, bukan Anda atau PC Anda);
- versi persetujuan (`cc0-v1`) dan apakah klip berasal dari mikrofon atau file.

Tidak ada nama, email, akun, nama perangkat, lokasi, atau file lain yang dikirim.

**Ke mana dikirim.** Sampel diterima oleh Cloudflare Worker (`noise-filter-samples.mukhamadkhoirul.workers.dev`)
dan disimpan di bucket penyimpanan Cloudflare R2 yang privat. Layanan kami tidak menyimpan alamat IP Anda.
Cloudflare, sebagai penyedia hosting, memproses data koneksi (seperti alamat IP) untuk menjalankan dan melindungi
jaringannya, sesuai [Cloudflare Privacy Policy](https://www.cloudflare.com/privacypolicy/).

**Apa yang terjadi selanjutnya.**

1. Pemeriksaan otomatis berjalan setiap hari (format, panjang, clipping, deteksi suara orang, duplikat).
2. Pengembang **mendengarkan setiap sampel** di halaman review yang dilindungi kata sandi, lalu menerima atau
   menolaknya.
3. Hanya sampel yang diterima yang dipakai untuk melatih versi baru model AI Noise Filter. Pelatihan berjalan di
   GitHub Actions; model hasilnya diterbitkan di repositori GitHub publik.
4. Sampel yang ditolak dihapus otomatis setelah 30 hari. Sampel yang diterima disimpan untuk pelatihan berikutnya
   sampai Anda menghapusnya.

**Lisensi sampel Anda.** Dengan menyetujui, Anda melepas sampel di bawah
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/deed.id) (domain publik). Saat ini kami tidak
menerbitkan sampel tersebut, tetapi CC0 mengizinkannya dibagikan, misalnya sebagai bagian dari dataset noise
terbuka. Bagikan hanya noise yang Anda rekam sendiri dan rela Anda berikan.

**Menghapus sampel Anda.** Tekan **Pengaturan > Model AI & sampel noise > Hapus sampel saya**. Semua sampel dari instalasi ini
(menunggu, diterima, atau ditolak) langsung dihapus dari penyimpanan kami. (Tombol ini muncul setelah Anda pernah mengirim sampel.) Model yang sudah dilatih dengan sampel
itu tidak bisa "melupakannya", tetapi sampelnya sendiri hilang. Tombol hapus bekerja dengan ID instalasi di
`contribute.json`, jadi tekan tombol itu **sebelum** menghapus instalasi atau menghapus file tersebut.

## 4. Anak-anak

Noise Filter tidak ditujukan untuk anak-anak dan tidak dengan sengaja mengumpulkan data pribadi siapa pun. Sampel
noise tidak boleh berisi suara orang.

## 5. Perubahan

Jika kebijakan ini berubah, versi barunya ikut di aplikasi dan diterbitkan di repositori dengan tanggal baru.
Perubahan yang mengirim jenis data baru akan meminta persetujuan Anda lagi.

## 6. Kontak

Pertanyaan atau permintaan: buka issue di
[github.com/SkillsHUB-Electronics/Noise-Filter/issues](https://github.com/SkillsHUB-Electronics/Noise-Filter/issues).
Jangan menulis data pribadi di issue publik; minta kontak privat di sana jika perlu.
