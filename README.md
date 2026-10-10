# Solana Wallet Radar

Dashboard lokal untuk meneliti ide **wallet-cohort tracking**: mulai dari token historis, cari pembeli DEX paling awal, pilih cohort yang masih aktif dan tidak bot-like, lalu prioritaskan token yang dibeli bersama oleh beberapa wallet. Aplikasi ini secara sengaja adalah **research + alert + paper tracking**, bukan bot trading.

> **Peringatan:** Ini bukan nasihat investasi, prediksi harga, atau strategi yang terbukti menguntungkan. Meme token dapat kehilangan seluruh nilai. Hindari survivorship bias: token pemenang masa lalu tidak membuktikan bahwa pembeli awalnya memiliki keunggulan berulang.

## Yang sudah dibuat

- Input satu **mint Solana** sebagai token historis/seed.
- Ambil dan urutkan pembeli **DEX buy** unik pertama (bukan sekadar top holder).
- Seleksi aktivitas swap dalam 30 hari.
- Heuristik bot yang transparan: kepadatan event, median jeda, dan burst; bukan label identitas pasti.
- Kumpulkan pembelian terbaru dari cohort manusia lalu hitung konvergensi wallet/cluster.
- Hard gate: jumlah wallet/cluster, likuiditas minimum, dan pair pasar harus tersedia.
- Skor 0–100 yang dapat dilihat breakdown-nya; skor hanya prioritas audit manual.
- Simpan kandidat lolos sebagai **paper signal**; tanpa wallet signing, seed phrase, atau private key.
- Alert Telegram **hanya untuk signal live baru** di atas ambang skor. Data demo tidak pernah mengirim alert.
- Re-scan watchlist live opsional melalui API atau scheduler yang default-nya mati.
- Mode demo deterministik dan jelas ditandai agar UI bisa diuji tanpa API key.

## Struktur

```text
solana-wallet-radar/
├── app/
│   ├── main.py                 # FastAPI, persistence, paper signals, alert/scheduler
│   ├── services/
│   │   ├── analyzer.py         # pipeline cohort
│   │   ├── providers.py        # adapter Helius / Birdeye / DEX Screener
│   │   ├── scoring.py          # bot and signal heuristics
│   │   └── demo.py             # data sintetis, bukan data pasar
│   └── static/                 # dashboard Bahasa Indonesia, tanpa CDN
├── tests/test_demo_flow.py
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Jalankan lokal dengan Docker

1. Masuk ke direktori proyek.

   ```bash
   cd solana-wallet-radar
   cp .env.example .env
   ```

2. Jalankan dalam mode demo terlebih dahulu:

   ```bash
   docker compose up --build
   ```

3. Buka [http://localhost:8000](http://localhost:8000). Klik **Gunakan mint contoh**, kemudian **Jalankan analisis**.

Database SQLite akan tersimpan sebagai `data/radar.db` pada komputer Anda. Untuk menghentikan container, gunakan `docker compose down`.

### Menjalankan tanpa Docker

Memerlukan Python 3.12+.

```bash
cd solana-wallet-radar
python -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Konfigurasi mode live

Setelah dashboard demo tervalidasi, ubah `.env`:

```dotenv
APP_DEMO_MODE=false
HELIUS_API_KEY=...
BIRDEYE_API_KEY=...

# Optional, untuk alert yang hanya memberi sinyal review manual
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
ALERT_SCORE_THRESHOLD=80

# Tetap 0 sampai quota dan biaya API sudah dipahami.
AUTO_SCAN_INTERVAL_MINUTES=0
```

Kemudian restart `docker compose up --build`. Pilih **Live API** dari dropdown dashboard dan masukkan mint seed yang benar.

**Jangan pernah** menaruh private key, seed phrase, secret wallet, atau API key pada frontend/JavaScript. `.env` sudah masuk `.gitignore`.

## Peta sumber data

| Peran | Integrasi | Status di kode |
|---|---|---|
| Menemukan pool, harga, likuiditas, volume | [DEX Screener API](https://docs.dexscreener.com/api/reference) | Langsung digunakan; tidak perlu key untuk endpoint ini. |
| Mengambil trade token untuk pembeli awal | [Birdeye token trades](https://docs.birdeye.so/docs/birdeye-ai) | Digunakan pada mode live (`/defi/v3/token/txs`); perlu key/plan yang memiliki cakupan endpoint. |
| Mengonfirmasi wallet masih swap dan membaca swap | [Helius transaction history](https://docs.helius.dev/solana-apis/enhanced-transactions-api/parsed-transaction-history) | Digunakan pada mode live; perlu API key. |
| Backtest/validasi batch/label alamat | [Dune API dan SQL](https://docs.dune.com/api-reference/apis/quickstart-analyze) | Direkomendasikan sebagai tahap berikutnya; belum dipanggil otomatis agar biaya/query tidak tersembunyi. |
| Alert | Telegram Bot API | Opsional dan dipanggil server-side saja. |

Provider pihak ketiga bisa mengubah skema respons atau hak akses paket. Normalizer ada terpusat di `app/services/providers.py`; **sebelum menyalakan scheduler**, simpan contoh respons API aktual sebagai fixture dan sesuaikan pemetaan `wallet`, `side`, `timestamp`, dan mint token. Ini penting agar transfer, LP, atau output native SOL tidak salah dibaca sebagai pembelian meme token.

## Definisi pipeline

1. **Seed token:** Anda secara manual memilih mint token historis yang dapat diaudit.
2. **Pembeli awal:** Birdeye menyediakan event token trade; sistem mengurutkan timestamp, mempertahankan event `buy`, lalu mengambil 20 wallet unik pertama.
3. **Aktivitas:** Helius memberi histori transaksi wallet yang diparse. Wallet harus punya swap dalam `SCAN_LOOKBACK_DAYS` (default 30).
4. **Bot likelihood:** skor bertambah jika 80+ event, median interval ≤15/60 detik, atau burst 20 event/10 menit. `likely_bot` dikeluarkan dari sinyal, tetapi tetap ditampilkan.
5. **Konvergensi:** sistem mengelompokkan pembelian token terbaru berdasarkan mint. Pembelian satu wallet tidak ditampilkan sebagai sinyal.
6. **Independensi:** jika ada cluster pendanaan yang diketahui, satu cluster dihitung satu kali. Pada data live, independensi ditandai **belum diverifikasi** sampai Anda menambahkan sumber label/funding graph.
7. **Hard gate dan paper signal:** minimum 3 wallet/cluster, likuiditas ≥ `$25,000`, dan pair pasar tersedia. Hanya setelah itu token dibuat menjadi posisi hipotetis.

## Mengapa tidak langsung auto-buy?

- Trade on-chain terlihat publik, tetapi posisi bisa dipindahkan ke wallet lain, bridge, atau CEX; aksi jual tidak dapat diinferensikan dengan sempurna.
- Wallet yang menang sekali mungkin hanya beruntung. Metrik kualitas pada MVP adalah proxy konservatif, **bukan** klaim “smart money”.
- Likuiditas headline tidak menjamin slippage, tidak ada tax/blacklist, atau keamanan authority/mint.
- Konvergensi dari wallet yang didanai sumber yang sama bukan tiga opini independen.

Untuk tahap berikutnya, lakukan backtest *out-of-sample*, tambahkan pemeriksaan authority/holder/LP-lock dari provider keamanan yang sesuai, funding-cluster graph, aturan exit paper, dan biaya/slippage historis. Tetap pertahankan keputusan eksekusi sebagai tindakan manual yang terpisah.

## API lokal

| Endpoint | Fungsi |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/config` | Status aman untuk UI; tidak pernah mengembalikan secret |
| `POST /api/analyses` | Jalankan analisis `{ "mint": "...", "mode": "demo" | "live" }` |
| `GET /api/analyses` | Riwayat analisis lokal |
| `GET /api/paper-signals` | Paper signals terbuka |
| `POST /api/paper-signals/refresh` | Perbarui harga paper signal dari DEX Screener |
| `POST /api/scans/run` | Re-scan semua seed **live** yang sudah pernah disimpan |

## Test

```bash
python -m unittest discover -s tests -v
```

Test memverifikasi bahwa demo menemukan sinyal `MANGO` dari tiga wallet independen, tetapi menolak `BREAD` karena tiga wallet mentahnya hanya berasal dari dua cluster pendanaan.
