# Payment Gateway (FastAPI)

Fondasi platform **payment gateway** untuk usaha Anda sendiri: Anda (operator)
mendaftarkan merchant, merchant menerima pembayaran pelanggan lewat API Anda,
Anda mengambil biaya MDR, lalu dana bersih tercatat sebagai saldo merchant.

```
Pelanggan ──bayar──▶ Acquirer (bank / QRIS / e-wallet)
                         │ callback
                         ▼
Merchant ──API──▶  PAYMENT GATEWAY (aplikasi ini) ──webhook bertanda tangan──▶ Merchant
                   • pembayaran, refund, kedaluwarsa
                   • biaya MDR + ledger saldo merchant
```

## Fitur

| Area | Isi |
|---|---|
| Merchant | Onboarding oleh admin, API key (`sk_test_…`/`sk_live_…`, disimpan sebagai hash SHA-256), rotasi & nonaktifkan |
| Pembayaran | QRIS, Virtual Account (BCA, BNI, BRI, MANDIRI, PERMATA), e-wallet (OVO, DANA, GOPAY, SHOPEEPAY, LINKAJA) |
| Keandalan | Header `Idempotency-Key`, `reference_id` unik per merchant, kedaluwarsa otomatis |
| Status | `PENDING → PAID → PARTIALLY_REFUNDED/REFUNDED`, `PENDING → EXPIRED/FAILED` |
| Model bisnis | Biaya MDR per metode (`app/fees.py`), ledger saldo (`PAYMENT`, `FEE`, `REFUND`) |
| Webhook | `payment.created`, `payment.paid`, `payment.expired`, `refund.succeeded/failed`, tanda tangan HMAC-SHA256, log & retry |
| Checkout | Halaman pembayaran `GET /checkout/{payment_id}` untuk pelanggan |
| Acquirer | Adapter pluggable (`app/providers/`); saat ini `SimulatorProvider` untuk sandbox |

## Menjalankan

```bash
cd payment-gateway
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # ganti ADMIN_TOKEN
uvicorn app.main:app --reload
```

Dokumentasi API interaktif: http://localhost:8000/docs

Test: `pytest -q`

## Contoh alur

```bash
# 1. Admin mendaftarkan merchant (api_key & webhook_secret hanya tampil sekali)
curl -X POST localhost:8000/admin/merchants -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Toko Maju","email":"owner@tokomaju.id","webhook_url":"https://tokomaju.id/hook"}'

# 2. Merchant membuat pembayaran
curl -X POST localhost:8000/v1/payments -H "Authorization: Bearer sk_test_..." \
  -H "Idempotency-Key: order-123" -H "Content-Type: application/json" \
  -d '{"reference_id":"ORDER-123","amount":150000,"method":"VIRTUAL_ACCOUNT","channel":"BCA"}'

# 3. (Sandbox) simulasikan pelanggan membayar
curl -X POST localhost:8000/v1/simulate/payments/pay_xxx/pay -H "Authorization: Bearer sk_test_..."

# 4. Cek saldo, refund
curl localhost:8000/v1/balance -H "Authorization: Bearer sk_test_..."
curl -X POST localhost:8000/v1/payments/pay_xxx/refunds -H "Authorization: Bearer sk_test_..." \
  -H "Content-Type: application/json" -d '{"amount":50000,"reason":"barang rusak"}'
```

## Endpoint

**Admin** (header `X-Admin-Token`)
- `POST /admin/merchants`, `GET /admin/merchants`
- `POST /admin/merchants/{id}/api-keys` (rotasi key), `POST /admin/merchants/{id}/deactivate`
- `GET /admin/merchants/{id}/balance`
- `POST /admin/jobs/expire-payments`, `POST /admin/jobs/retry-webhooks` (jalankan via cron, mis. tiap menit)

**Merchant** (header `Authorization: Bearer sk_…`)
- `GET/PATCH /v1/me`
- `POST /v1/payments`, `GET /v1/payments?status=PAID`, `GET /v1/payments/{id}`
- `POST/GET /v1/payments/{id}/refunds`
- `GET /v1/balance`, `GET /v1/webhooks`
- `POST /v1/simulate/payments/{id}/pay` (sandbox saja; 404 saat `ENVIRONMENT=production`)

## Verifikasi webhook (sisi merchant)

Header `X-Signature: t=<unix>,v1=<hex>` dengan
`v1 = HMAC_SHA256(webhook_secret, "<t>." + raw_body)`.

```python
from app.security import verify_signature
ok = verify_signature(webhook_secret, raw_body_bytes, request.headers["X-Signature"])
```

Tolak jika tanda tangan salah atau `t` lebih dari 5 menit. Gunakan `X-Event-Id` untuk
mencegah pemrosesan ganda (webhook bisa dikirim lebih dari sekali).

## Biaya (contoh, ubah di `app/fees.py`)

| Metode | MDR |
|---|---|
| QRIS | 0,7% (maks. transaksi Rp10.000.000) |
| Virtual Account | Rp4.000 flat |
| E-wallet | 1,5% |

## Menambah acquirer sungguhan

1. Buat kelas turunan `PaymentProvider` di `app/providers/` (`create_charge`, `refund`).
2. Daftarkan dengan `register_provider(...)` dan pilih di `get_provider()`.
3. Tambahkan router callback dari acquirer yang **memverifikasi tanda tangan acquirer**,
   lalu memanggil `services.payments.mark_paid(...)`.

## Sebelum go-live: hal yang wajib (bukan sekadar kode)

Menjalankan usaha payment gateway di Indonesia adalah kegiatan yang diatur ketat:

- **Izin Bank Indonesia** sebagai *Penyelenggara Jasa Pembayaran* (PJP, PBI No. 22/23/PBI/2020),
  termasuk kategori izin yang sesuai (mis. payment gateway / acquiring). Alternatifnya, mulai
  sebagai mitra/agregator di bawah PJP berizin (mis. Midtrans, Xendit, DOKU) — jauh lebih cepat.
- **Kerja sama acquirer**: bank untuk VA, lembaga switching/ASPI untuk QRIS (standar QRIS & batas MDR),
  penerbit e-wallet.
- **KYC/KYB merchant & APU-PPT** (anti pencucian uang), pemantauan transaksi mencurigakan, lapor PPATK.
- **Keamanan**: PCI DSS bila menangani data kartu, enkripsi, audit, pentest, ISO 27001.
- **Pelindungan data** sesuai UU PDP No. 27/2022.
- **Settlement/payout** ke rekening merchant dan rekonsiliasi harian dengan acquirer
  (belum ada di kode ini).

## Batasan versi ini

- Database default SQLite; untuk produksi gunakan PostgreSQL (`DATABASE_URL=postgresql+psycopg://…`)
  dan migrasi skema dengan Alembic.
- Webhook dikirim lewat background task FastAPI + job retry; untuk skala besar pindahkan ke antrean
  (Celery/RQ/Redis) dengan backoff eksponensial.
- Belum ada: settlement/payout, rekonsiliasi, dashboard merchant, rate limiting, audit log admin.
