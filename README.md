# payment-service-sample

Demo payment processing service for Bug Bot end-to-end investigation demo.

## Known Bug

`ZeroDivisionError` in `calculate_payment_fee()` when `amount=0`.

**File:** `main.py`
**Function:** `calculate_payment_fee(amount)`
**Bug line:** `fee = FIXED_FEE / amount`

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --port 8001
```

Requires Grafana Loki running at `http://localhost:3100`.

## Endpoints

- `GET /health` — health check
- `POST /process-payment` — process a payment (500 error when `amount=0`)

## Test the bug

```bash
curl -X POST http://localhost:8001/process-payment \
  -H "Content-Type: application/json" \
  -d '{"payment_id": "test-001", "amount": 0}'
```
