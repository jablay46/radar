# Solana Wallet Radar

> **Local-first on-chain research dashboard untuk wallet-cohort tracking di Solana.**
> Aplikasi ini membantu meneliti pembeli DEX awal dari token historis, menyaring wallet yang masih aktif dan tidak bot-like, lalu memprioritaskan token yang dibeli bersama oleh cohort tersebut.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Solana](https://img.shields.io/badge/Chain-Solana-9945FF?logo=solana&logoColor=white)](https://solana.com/)

> [!WARNING]
> Ini adalah alat **riset, alert, dan paper tracking**—bukan bot trading, bukan nasihat investasi, dan bukan mesin pencari token “100×”. Token meme dapat kehilangan seluruh nilai. Jangan memasukkan private key, seed phrase, atau secret wallet ke aplikasi ini.

---

## Daftar isi

- [Apa yang dilakukan aplikasi](#apa-yang-dilakukan-aplikasi)
- [Batasan penting](#batasan-penting)
- [Arsitektur dan sumber data](#arsitektur-dan-sumber-data)
- [Prasyarat](#prasyarat)
- [Instalasi cepat dengan Docker](#instalasi-cepat-dengan-docker)
- [Instalasi tanpa Docker](#instalasi-tanpa-docker)
- [Konfigurasi](#konfigurasi)
- [Cara menggunakan dashboard](#cara-menggunakan-dashboard)
- [Contoh brief / prompt riset](#contoh-brief--prompt-riset)
- [API lokal](#api-lokal)
- [Menjalankan test](#menjalankan-test)
- [Troubleshooting](#troubleshooting)
- [Keamanan dan praktik GitHub](#keamanan-dan-praktik-github)
- [Roadmap](#roadmap)

---

## Apa yang dilakukan aplikasi

### Pipeline riset

```text
Mint token historis
       ↓
Urutkan trade DEX bertanda BUY → ambil 20 wallet unik paling awal
       ↓
Periksa apakah wallet masih melakukan swap dalam 30 hari
       ↓
Beri bot-likelihood score dan keluarkan wallet bot-like dari cohort sinyal
       ↓
Kelompokkan token yang dibeli cohort aktif
       ↓
Deduplicasi cluster pendanaan bila data cluster tersedia
       ↓
Terapkan hard gate + skor riset
       ↓
Simpan kandidat yang lolos sebagai paper signal dan, bila diaktifkan, kirim alert Telegram
```

### Fitur saat ini

- Input satu **mint address Solana** sebagai *seed token* historis.
- Mengidentifikasi **20 pembeli DEX unik paling awal** dari event `buy`, bukan sekadar top holder.
- Menentukan apakah wallet masih aktif dalam periode `SCAN_LOOKBACK_DAYS` (default: 30 hari).
- Heuristik **bot likelihood** dari jumlah event, median jeda transaksi, dan burst aktivitas.
- Mengumpulkan pembelian token terbaru dari cohort manusia dan mencari **konvergensi**.
- Menghitung jumlah wallet/cluster independen bila metadata cluster tersedia.
- Hard gate untuk konsensus, likuiditas minimum, dan ketersediaan pair pasar.
- Skor riset 0–100 dengan breakdown dan caveat yang ditampilkan di UI.
- Paper tracking; aplikasi **tidak** menyimpan atau memakai private key.
- Alert Telegram opsional untuk paper signal **live** baru yang memenuhi ambang skor.
- Mode demo sintetis deterministik sehingga UI dan logika dapat diuji tanpa API key.
- Re-scan watchlist live secara manual melalui API atau terjadwal secara opsional.

### Yang **tidak** dilakukan aplikasi

- Tidak mengeksekusi pembelian/penjualan token.
- Tidak menjadi wallet, tidak meminta seed phrase, dan tidak menandatangani transaksi.
- Tidak mengklaim bahwa suatu wallet adalah “smart money”.
- Tidak menjamin bahwa wallet yang membeli token masih memegangnya setelah wallet memindahkan aset ke CEX, bridge, atau alamat lain.
- Belum melakukan audit contract lengkap, analisis LP lock, maupun graph funding otomatis.

---

## Batasan penting

1. **Survivorship bias:** memilih token lama yang sudah terbukti sukses tidak membuktikan pembeli awalnya memiliki edge yang berulang.
2. **Trade ≠ transfer:** logika awal hanya sebaik data provider dalam membedakan swap DEX, transfer, airdrop, LP, dan deployer flow.
3. **Bot score adalah heuristik:** skor tinggi berarti pola perlu dicurigai, bukan bukti identitas bot.
4. **Independensi wallet belum otomatis:** pada mode live, wallet dapat terlihat berbeda tetapi ternyata didanai satu sumber. UI akan menandai independensi yang belum diverifikasi.
5. **Likuiditas bukan jaminan:** angka liquidity/volume tidak menggantikan pemeriksaan slippage, authority, token distribution, creator exposure, atau risiko kontrak.
6. **Skor bukan rekomendasi beli:** skor hanya mengurutkan prioritas untuk audit manual dan paper tracking.

Sebelum memakai sistem dengan data live, lakukan backtest *out-of-sample*, ukur slippage/fees, dan dokumentasikan aturan entry serta exit paper trading.

---

## Arsitektur dan sumber data

| Lapisan | Teknologi | Peran |
|---|---|---|
| Backend | FastAPI + Python 3.12 | API, pipeline analisis, scheduler, penyimpanan lokal |
| Frontend | HTML/CSS/JavaScript vanilla | Dashboard Bahasa Indonesia tanpa CDN atau framework frontend eksternal |
| Database | SQLite via SQLAlchemy | Riwayat analisis dan paper signals pada `data/radar.db` |
| Container | Docker + Docker Compose | Cara menjalankan yang disarankan |
| Market data | [DEX Screener API](https://docs.dexscreener.com/api/reference) | Harga, pair, likuiditas, volume, market-cap proxy |
| Token trades | [Birdeye Data API](https://docs.birdeye.so/docs/birdeye-ai) | Event trade token untuk menemukan pembeli DEX awal |
| Wallet history | [Helius](https://docs.helius.dev/solana-apis/enhanced-transactions-api/parsed-transaction-history) | Riwayat transaksi wallet yang sudah diparse dan aktivitas swap |
| Notifikasi | Telegram Bot API | Alert server-side opsional |
| Validasi/backtest lanjutan | [Dune](https://docs.dune.com/api-reference/apis/quickstart-analyze) | Direkomendasikan untuk SQL, label, dan backtest; belum dipanggil otomatis oleh MVP |

> [!NOTE]
> DEX Screener dipakai langsung untuk data pasar. Mode **live** membutuhkan **dua** key: Birdeye untuk trade awal dan Helius untuk aktivitas wallet. Provider dapat mengubah skema respons/fitur berdasarkan paket; normalizer terpusat di `app/services/providers.py` agar dapat disesuaikan.

### Struktur proyek

```text
radar/
├── app/
│   ├── main.py                 # FastAPI, persistence, paper signals, alert, scheduler
│   ├── config.py               # Konfigurasi dari .env
│   ├── database.py             # SQLAlchemy dan SQLite
│   ├── models.py               # Tabel analyses dan paper_signals
│   ├── static/                 # Dashboard tanpa CDN
│   └── services/
│       ├── analyzer.py         # Pipeline wallet cohort
│       ├── scoring.py          # Bot heuristic, hard gate, dan scoring
│       ├── providers.py        # Adapter Helius, Birdeye, DEX Screener
│       ├── notify.py           # Telegram server-side
│       └── demo.py             # Dataset sintetis untuk mode demo
├── data/                       # Runtime SQLite; database tidak boleh di-commit
├── tests/test_demo_flow.py     # Test logika demo
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## Prasyarat

Pilih salah satu metode instalasi:

### Opsi A — Docker (direkomendasikan)

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) atau Docker Engine + Docker Compose v2.
- Port lokal `8000` belum dipakai aplikasi lain.
- Git (opsional, tetapi direkomendasikan untuk clone repository).

Verifikasi:

```bash
docker --version
docker compose version
```

### Opsi B — Python langsung

- Python **3.12 atau lebih baru**.
- `pip` dan kemampuan membuat virtual environment.

Verifikasi:

```bash
python --version
# atau pada sebagian sistem Linux/macOS
python3 --version
```

---

## Instalasi cepat dengan Docker

### 1. Clone repository

```bash
git clone https://github.com/jablay46/radar.git
cd radar
```

Jika Anda sudah mengunduh ZIP, ekstrak lalu masuk ke folder `radar` hasil ekstraksi.

### 2. Buat file konfigurasi lokal

Linux/macOS/Git Bash:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

> File `.env` berisi konfigurasi lokal dan sudah ada di `.gitignore`. Jangan commit file ini.

### 3. Jalankan mode demo

```bash
docker compose up --build
```

Buka **http://localhost:8000** di browser.

Untuk menjalankan di background:

```bash
docker compose up --build -d
```

Lihat log:

```bash
docker compose logs -f
```

Hentikan container:

```bash
docker compose down
```

### 4. Uji dashboard

1. Klik **Gunakan mint contoh**.
2. Pastikan dropdown memilih **Demo aman (data sintetis)**.
3. Klik **Jalankan analisis**.
4. Dashboard akan memperlihatkan pembeli awal, filter bot, kandidat `MANGO` yang lolos hard gate, serta contoh kandidat yang ditolak karena cluster pendanaan.

Mode demo tidak memanggil blockchain, tidak membutuhkan API key, dan tidak mengirim Telegram alert.

---

## Instalasi tanpa Docker

### Linux/macOS

```bash
git clone https://github.com/jablay46/radar.git
cd radar

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Windows PowerShell

```powershell
git clone https://github.com/jablay46/radar.git
cd radar

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Jika PowerShell menolak aktivasi script, jalankan sekali pada terminal tersebut:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Buka **http://localhost:8000** setelah server menampilkan `Uvicorn running`.

---

## Konfigurasi

Mulai dari `.env.example`, lalu hanya ubah yang diperlukan.

| Variabel | Default | Kegunaan |
|---|---:|---|
| `APP_NAME` | `Solana Wallet Radar` | Nama yang tampil di health check |
| `APP_DEMO_MODE` | `true` | Mode default UI; gunakan `false` setelah key live siap |
| `DATABASE_URL` | `sqlite:///./data/radar.db` | Lokasi database SQLite lokal |
| `HELIUS_API_KEY` | kosong | Wajib untuk histori/aktivitas wallet live |
| `BIRDEYE_API_KEY` | kosong | Wajib untuk menemukan trade/pembeli awal live |
| `TELEGRAM_BOT_TOKEN` | kosong | Opsional untuk alert Telegram |
| `TELEGRAM_CHAT_ID` | kosong | Chat/grup tujuan alert Telegram |
| `ALERT_SCORE_THRESHOLD` | `80` | Skor minimum signal live untuk alert |
| `AUTO_SCAN_INTERVAL_MINUTES` | `0` | `0` mematikan scheduler; gunakan `15` atau lebih setelah quota dipahami |
| `SCAN_LOOKBACK_DAYS` | `30` | Jendela aktivitas wallet terbaru |
| `MIN_CONSENSUS_WALLETS` | `3` | Jumlah minimum wallet/cluster untuk hard gate |
| `MIN_LIQUIDITY_USD` | `25000` | Likuiditas minimum pair untuk hard gate |

### Mengaktifkan mode live

Isi `.env` sebagai berikut:

```dotenv
APP_DEMO_MODE=false
HELIUS_API_KEY=isi_key_helius_anda
BIRDEYE_API_KEY=isi_key_birdeye_anda

# Biarkan kosong jika belum membutuhkan alert
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Scheduler tetap mati sampai Anda memahami kuota dan biaya API.
AUTO_SCAN_INTERVAL_MINUTES=0
```

Restart aplikasi setelah mengubah `.env`:

```bash
docker compose down
docker compose up --build
```

Pada dashboard, pilih **Live API (Helius + Birdeye)**. Jika opsi live menyatakan belum siap, periksa bahwa kedua key benar-benar terbaca container:

```bash
docker compose exec wallet-radar env | grep -E 'HELIUS|BIRDEYE'
```

Perintah di atas hanya memeriksa ada/tidaknya variabel. Jangan membagikan output yang berisi nilai key.

### Mengaktifkan alert Telegram

1. Buat bot melalui [@BotFather](https://t.me/BotFather), lalu salin token bot.
2. Kirim pesan `/start` kepada bot tersebut, atau tambahkan bot ke grup tujuan dan kirim satu pesan.
3. Dapatkan `chat_id` dari Telegram Bot API menggunakan token Anda. Jangan masukkan token ke commit, screenshot, atau issue publik.
4. Isi `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` di `.env`.
5. Restart aplikasi.

Alert dikirim **hanya** ketika signal live baru dibuat, signal itu lolos hard gate, dan skornya memenuhi `ALERT_SCORE_THRESHOLD`. Pesan selalu menyatakan bahwa kandidat membutuhkan review manual.

### Scheduler live: aktifkan terakhir

Jika Anda sudah memverifikasi output API, mengerti rate limit, dan mengetahui biaya provider, aktifkan misalnya:

```dotenv
AUTO_SCAN_INTERVAL_MINUTES=15
```

Scheduler hanya melakukan re-scan pada seed mint mode live yang sebelumnya telah Anda simpan melalui dashboard. Ia tidak mengeksekusi transaksi. Mulai dengan interval yang lambat dan pantau log serta pemakaian API.

---

## Cara menggunakan dashboard

### 1. Pilih seed token historis

Masukkan **mint address Solana**, bukan symbol atau URL. Seed ideal adalah token lama yang Anda pilih dengan alasan yang terdokumentasi, misalnya pernah memiliki volume/liquidity memadai dan periode perdagangan yang cukup untuk dianalisis.

**Jangan memakai hanya satu pemenang terkenal** sebagai dasar kesimpulan. Siapkan beberapa seed positif dan pembanding yang gagal untuk backtest.

### 2. Pilih sumber data

- **Demo aman:** hanya menggunakan data sintetis dan aman untuk mempelajari alur.
- **Live API:** membutuhkan Helius + Birdeye. Hasil tergantung cakupan paket/provider dan harus diaudit pada Solscan/explorer.

### 3. Baca panel “20 pembeli DEX unik pertama”

Tabel ini menunjukkan urutan buyer, estimasi nilai buy awal bila ada, aktivitas 30 hari, dan bot-likelihood score.

- `Aktif`: ada aktivitas swap dalam jendela pengamatan.
- `Human-like`: heuristic tidak melihat pola bot kuat.
- `Review`: pola tidak jelas; jangan otomatis diperlakukan sebagai manusia.
- `Likely bot`: dikeluarkan dari penghitungan konvergensi.
- `Dormant`: buyer awal tidak melakukan swap terbaru; tetap terlihat sebagai bukti, tetapi tidak digunakan untuk sinyal.

### 4. Periksa cohort yang dapat dipantau

Cohort adalah wallet aktif yang bukan `likely bot`. `Q` di UI adalah **quality proxy konservatif**, bukan peringkat profitabilitas atau label smart money.

### 5. Tinjau kandidat konvergensi

Setiap kartu kandidat menampilkan:

- jumlah wallet/cluster independen;
- liquidity pair terdalam;
- skor riset dan breakdown;
- hard gate yang lolos/gagal;
- caveat mengenai data keamanan dan independensi.

Kandidat yang gagal hard gate **tidak** boleh diperlakukan sebagai paper signal. Kandidat yang lolos tetap harus diperiksa secara manual: authority/mint, holder concentration, LP, deployer, volume organik, slippage, dan transaksi sumber.

### 6. Gunakan paper tracking

Kandidat lolos disimpan sebagai posisi hipotetis dalam database lokal. Tombol **Perbarui paper tracking** mengambil harga terbaru dari DEX Screener bila pair dapat ditemukan. Ini bukan PnL aktual dan belum memasukkan fee, slippage, tax, maupun gagal eksekusi.

### 7. Audit di explorer

Untuk mode live, gunakan tautan wallet/tx di UI dan verifikasi sendiri melalui explorer seperti Solscan. Jangan mengambil keputusan hanya dari agregasi aplikasi.

---

## Contoh brief / prompt riset

> Aplikasi ini **tidak memiliki chat box** dan tidak memproses prompt bahasa alami. Input aplikasi adalah mint address serta mode data. Bagian berikut adalah template brief yang dapat dipakai untuk mendokumentasikan riset, memberi tugas kepada analis, atau meminta bantuan AI secara terpisah.

### Template 1 — Analisis seed token

```text
Analisis token seed Solana berikut sebagai riset wallet cohort.
Mint: <MINT_ADDRESS>
Mode: live
Jendela aktivitas: 30 hari
Tujuan: identifikasi 20 pembeli DEX awal, keluarkan wallet bot-like,
dan jelaskan token mana yang dibeli oleh minimal 3 wallet/cluster independen.

Output yang saya perlukan:
1. Daftar wallet cohort beserta alasan aktif/bot-like.
2. Kandidat yang lolos dan gagal hard gate.
3. Caveat tentang cluster pendanaan, holder concentration, authority, dan likuiditas.
4. Tidak ada rekomendasi beli dan tidak ada instruksi auto-trade.
```

### Template 2 — Review kandidat yang lolos paper gate

```text
Tinjau kandidat berikut sebelum dimasukkan ke paper tracking.
Token: <MINT_ADDRESS>
Skor radar: <SCORE>
Konvergensi: <N> wallet/cluster

Periksa secara manual:
- Pair DEX dan likuiditas aktual
- Distribusi holder dan creator/deployer exposure
- Mint/freeze authority serta risiko token
- Riwayat transaksi tiga wallet sumber
- Kemungkinan wallet tersebut berada dalam funding cluster yang sama
- Risiko slippage, volume palsu, dan exit liquidity

Simpulkan hanya sebagai daftar risiko dan langkah verifikasi, bukan rekomendasi transaksi.
```

### Template 3 — Backtest yang disiplin

```text
Rancang backtest out-of-sample untuk strategi wallet-cohort Solana.
Gunakan periode training dan test yang terpisah.
Bandingkan seed token pemenang dengan token gagal.
Masukkan delay data, fee, slippage, liquidity filter, dan survival bias.
Laporkan hit rate, median return, maximum drawdown, false-positive rate,
dan berapa sinyal yang berasal dari wallet/funding cluster yang sama.
Jangan menyimpulkan strategi layak dipakai tanpa data pembanding yang memadai.
```

---

## API lokal

Aplikasi juga dapat diakses melalui HTTP API pada `http://localhost:8000`.

### Health check

```bash
curl http://localhost:8000/api/health
```

### Lihat konfigurasi yang aman untuk frontend

Respons ini tidak mengembalikan API key.

```bash
curl http://localhost:8000/api/config
```

### Analisis demo

```bash
curl -X POST http://localhost:8000/api/analyses \
  -H 'Content-Type: application/json' \
  -d '{
    "mint": "So11111111111111111111111111111111111111112",
    "mode": "demo",
    "note": "smoke test lokal"
  }'
```

### Analisis live

Ganti mint di bawah dengan mint yang valid. Pastikan `HELIUS_API_KEY` dan `BIRDEYE_API_KEY` sudah ada di environment server.

```bash
curl -X POST http://localhost:8000/api/analyses \
  -H 'Content-Type: application/json' \
  -d '{
    "mint": "GANTI_DENGAN_MINT_SOLANA_VALID",
    "mode": "live",
    "note": "review manual"
  }'
```

### Endpoint yang tersedia

| Method | Endpoint | Fungsi |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Status mode live, Telegram, dan threshold tanpa secret |
| `POST` | `/api/analyses` | Menjalankan analisis demo/live |
| `GET` | `/api/analyses` | Riwayat analisis lokal terbaru |
| `GET` | `/api/analyses/{analysis_id}` | Detail satu hasil analisis |
| `GET` | `/api/paper-signals` | Daftar paper signal lokal |
| `POST` | `/api/paper-signals/refresh` | Memperbarui harga paper signal dari DEX Screener |
| `POST` | `/api/scans/run` | Re-scan semua seed live yang sudah tersimpan |

Contoh refresh paper signal:

```bash
curl -X POST http://localhost:8000/api/paper-signals/refresh \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

## Menjalankan test

Dengan virtual environment aktif:

```bash
python -m unittest discover -s tests -v
```

Test demo saat ini memverifikasi bahwa:

- 20 pembeli awal ditemukan;
- tiga wallet bot-like dikeluarkan;
- `MANGO` lolos karena memiliki tiga wallet/cluster independen;
- `BREAD` ditolak karena tiga wallet mentahnya hanya mewakili dua funding cluster.

Untuk test yang lebih kuat sebelum produksi, tambahkan fixture respons provider live, unit test normalizer Birdeye/Helius, test error/rate-limit, serta test integrasi API.

---

## Troubleshooting

| Gejala | Penyebab yang mungkin | Perbaikan |
|---|---|---|
| `docker: command not found` | Docker belum terpasang atau belum masuk PATH | Pasang Docker Desktop/Engine, restart terminal, lalu ulangi `docker compose version`. |
| Port 8000 sudah dipakai | Aplikasi lain memakai port tersebut | Hentikan aplikasi lain atau ubah compose menjadi `"8080:8000"`, lalu buka `http://localhost:8080`. |
| Dashboard tidak membuka | Container gagal start | Jalankan `docker compose logs -f` dan pastikan file `.env` ada. |
| Live mode “belum siap” | Salah satu API key kosong/tidak terbaca | Isi `HELIUS_API_KEY` dan `BIRDEYE_API_KEY`, lalu restart container. |
| Live mode mengembalikan 422/502 | Mint salah, paket API tidak mencakup endpoint, rate limit, atau skema respons berubah | Periksa log backend dan normalizer pada `app/services/providers.py`; uji respons provider terlebih dahulu. |
| Tidak ada signal | Ini hasil yang valid, atau cohort tidak membeli token yang sama | Jangan menurunkan hard gate hanya untuk memaksa kandidat. Periksa seed dan jendela pengamatan. |
| Banyak wallet dianggap bot | Heuristik terlalu ketat untuk tipe wallet tersebut | Audit event sumber terlebih dahulu; kalibrasikan `bot_assessment()` melalui backtest, jangan asal mengurangi threshold. |
| Paper return tidak berubah | Pair token tidak ditemukan di DEX Screener atau harga belum tersedia | Periksa token/pair di DEX Screener dan ingat bahwa demo tidak mempunyai pair live. |
| Telegram tidak mengirim | Token/chat ID salah, bot belum dimulai, atau signal tidak memenuhi threshold | Uji konfigurasi Telegram, pastikan signal live baru dan skor ≥ `ALERT_SCORE_THRESHOLD`. |

---

## Keamanan dan praktik GitHub

### Jangan commit rahasia

Pastikan `.env` tetap diabaikan Git:

```bash
git status --ignored
```

Jika secret pernah terlanjur di-push, **rotasi/revoke key segera**. Menghapus file pada commit terbaru tidak menghapus key dari riwayat Git.

### Jangan commit database runtime

`data/radar.db` adalah database lokal runtime dan dapat berisi riwayat riset. File ini harus tetap lokal. Jika sudah telanjur ter-track Git, hapus dari index lalu commit perubahan:

```bash
git rm --cached data/radar.db
git rm --cached data/radar.db-shm data/radar.db-wal 2>/dev/null || true
mkdir -p data
touch data/.gitkeep
git add .gitignore data/.gitkeep
git commit -m "chore: stop tracking local SQLite database"
git push
```

File database tetap ada di komputer lokal bila diperlukan, tetapi tidak akan masuk commit berikutnya. Bila database pernah berisi data sensitif, bersihkan juga dari riwayat Git sebelum repository dibuka untuk publik.

### Backup lokal

Sebelum mengubah konfigurasi atau menghapus container, backup database bila Anda ingin menyimpan paper signals:

```bash
cp data/radar.db data/radar.backup.db
```

### Checklist sebelum deploy publik

- [ ] `.env` tidak pernah masuk repository.
- [ ] `data/radar.db` tidak di-track.
- [ ] API key dibatasi quota/IP bila provider mendukungnya.
- [ ] Telegram bot hanya ada di chat/grup yang benar.
- [ ] `AUTO_SCAN_INTERVAL_MINUTES=0` sampai quota dan normalizer live tervalidasi.
- [ ] Ada fixture dan test untuk respons provider live.
- [ ] Ada rate limiting, autentikasi, HTTPS, dan backup database sebelum mengekspos dashboard ke internet.

---

## Roadmap

Prioritas yang disarankan sebelum fitur trading apa pun:

1. **Fixture provider live + test normalizer** agar field wallet, side, timestamp, dan output mint tidak salah dibaca.
2. **Backtest out-of-sample** untuk mengukur false-positive rate, hit rate, drawdown, slippage, dan survival bias.
3. **Funding graph / address labels** untuk menilai independensi wallet secara lebih baik.
4. **Risk enrichment**: holder concentration, authority, LP/lock, creator exposure, dan pemeriksaan keamanan token dari provider yang sesuai.
5. **Aturan paper exit** dan pencatatan biaya/slippage agar metrik paper lebih realistis.
6. **PostgreSQL + worker queue** bila jumlah seed/wallet bertambah.
7. **Authentication dan observability** sebelum deployment yang dapat diakses publik.

Auto-execution tidak direkomendasikan sebagai langkah berikutnya sebelum seluruh tahapan validasi tersebut selesai.

---

## Kontribusi

1. Fork repository dan buat branch baru.
2. Jalankan mode demo dan seluruh test sebelum membuka pull request.
3. Jangan menyertakan `.env`, database SQLite, API key, ataupun data pribadi.
4. Untuk perubahan provider, sertakan contoh respons yang sudah disamarkan sebagai fixture test.
5. Jelaskan asumsi data dan dampak terhadap scoring di pull request.

---

## Lisensi

Repository ini belum menyertakan file lisensi. Tambahkan `LICENSE` yang sesuai sebelum menerima kontribusi eksternal atau menyatakan ketentuan penggunaan.
