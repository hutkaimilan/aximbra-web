# AXIMBRA Webshop Customer Service Agent

AI-powered customer support for e-commerce: handles order tracking, returns, invoices, and common product questions automatically.

## Features

- **Multi-platform:** Supports Shopify, WooCommerce, and Shoprenter webshops
- **Multilingual:** Hungarian, English, German
- **Privacy-first:** Never shares customer email; verifies purchase before revealing order details
- **Safety-checked:** Prevents hallucinated order numbers; all facts grounded in real data
- **Low-friction:** Drafts only (human approval required); no auto-send

## Deployment

### Local Testing

```bash
pip install -r requirements.txt
SHOP_KIND=demo python -m uvicorn app:app --reload
```

Test with demo order (ŐRLŐ coffee shop):
```bash
curl -X POST http://localhost:8000/api/demo/reply \
  -H "Content-Type: application/json" \
  -d '{
    "from_email": "anna.kovacs@example.com",
    "subject": "Hol a rendelésem?",
    "body": "Rendelt szám ORL-1042"
  }'
```

### Shopify Setup

1. **Admin Dashboard** → Settings → Apps and integrations → Develop apps
2. Create app, enable `read_orders` scope
3. Generate access token
4. Deploy with:
   ```bash
   SHOP_KIND=shopify \
   SHOPIFY_DOMAIN=your-store.myshopify.com \
   SHOPIFY_TOKEN=shppa_... \
   python -m uvicorn app:app
   ```

### WooCommerce Setup

1. **WordPress Admin** → WooCommerce → Settings → Advanced → REST API
2. Create key with **read** scope only
3. Deploy with:
   ```bash
   SHOP_KIND=woocommerce \
   WOO_URL=https://your-shop.com \
   WOO_KEY=ck_... \
   WOO_SECRET=cs_... \
   python -m uvicorn app:app
   ```

### Shoprenter Setup

1. **Shoprenter Admin** → Settings → API keys
2. Create key with **read** scope
3. Deploy with:
   ```bash
   SHOP_KIND=shoprenter \
   SHOPRENTER_DOMAIN=your-domain.shoprenter.hu \
   SHOPRENTER_TOKEN=token_... \
   python -m uvicorn app:app
   ```

## API

### Demo Endpoint (Public)

**POST** `/api/demo/reply`

Rate-limited: 20 per hour, 500 per day per IP.

```json
{
  "from_email": "customer@example.com",
  "subject": "Question about order #1234",
  "body": "When will my order arrive?"
}
```

Response:
```json
{
  "intent": "order_status",
  "order_number": "1234",
  "email_used": "customer@example.com",
  "found_as": "number_and_email",
  "order": {
    "number": "1234",
    "status": "shipped",
    "created": "2026-10-01",
    "items": ["Product A × 2", "Product B × 1"],
    "total": "12 500 Ft",
    "carrier": "GLS",
    "tracking_number": "GLS123456789",
    "tracking_url": "..."
  },
  "reply_hu": "Szép napot!...",
  "reply_en": "Good day!..."
}
```

### Production Endpoint (Authenticated)

**POST** `/api/reply`

Requires header: `X-Agent-Token: <AGENT_TOKEN>` (≥24 chars, keep secret).

Same request/response format as demo.

## How It Works

1. **Extraction:** Finds order number and language from email
2. **Intent detection:** Classifies request (status, return, invoice, etc.)
3. **Lookup:** Searches webshop for matching order
4. **Verification:** Checks email matches order (privacy gate)
5. **Reply drafting:** Generates response in customer's language
6. **Fact-checking:** Validates all numbers against order data

## Testing

```bash
pytest tests/
```

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `SHOP_KIND` | `demo` | `demo`, `shopify`, `woocommerce`, `shoprenter` |
| `AGENT_TOKEN` | (none) | Required for `/api/reply` |
| `DEMO_PER_HOUR` | `20` | Rate limit per IP per hour |
| `DEMO_PER_DAY_TOTAL` | `500` | Global rate limit per day |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Google Gemini model ID |
| `SHOP_NAME` | `AXIMBRA demo` | Shown in demo replies |

### Shopify-specific
- `SHOPIFY_DOMAIN`: e.g., `my-store.myshopify.com`
- `SHOPIFY_TOKEN`: API access token

### WooCommerce-specific
- `WOO_URL`: e.g., `https://my-shop.com`
- `WOO_KEY`, `WOO_SECRET`: REST API credentials

### Shoprenter-specific
- `SHOPRENTER_DOMAIN`: e.g., `my-domain.shoprenter.hu`
- `SHOPRENTER_TOKEN`: API token

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 503 Nincs beállítva AGENT_TOKEN | Missing env var | Set `AGENT_TOKEN` to ≥24 random chars |
| 503 Hiányzó webshop-beállítás | Missing shop credentials | Check `SHOP_KIND` and required env vars for that platform |
| 429 Rate limit | Too many demo requests | Wait an hour or increase `DEMO_PER_HOUR` |
| ShopError: "a webshop nem érhető el" | Network/connectivity issue | Check API endpoint reachability; restart |
| No order found | Invalid credentials or order doesn't exist | Verify API key/token; test with known order number |

## Deployment Notes

- **Railway:** Docker build is automatic from `Dockerfile`. Set env vars in dashboard.
- **No database:** Order data is fetched live from your webshop's API; no caching.
- **Error logging:** Check Railway logs for full error traces.

## License

Proprietary — AXIMBRA.
