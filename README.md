# Local Shop AI Bot (Complete Local Starter)

Yeh project local dukaan ke liye full starter AI system deta hai jisme shop-specific bot, unique URL, owner controls, chat logs, aur offline fallback included hai.

## Key Features
- ✅ Shop create with unique slug URL (`/shop/<slug>`)
- ✅ Rule-based AI responses (Q&A, timings, products, policies)
- ✅ Owner key protected admin operations
- ✅ Update/Delete shop APIs
- ✅ Chat logs API (owner key required)
- ✅ Offline fallback (service worker + localStorage)
- ✅ **No pip dependency required** (pure Python stdlib)

## Run (Local)
```bash
python3 app.py
```
Open `http://localhost:8000`

## API
### Public
- `GET /health`
- `POST /api/shops`
- `GET /api/shops`
- `GET /api/shops/<slug>`
- `POST /api/shops/<slug>/chat`

### Owner Protected (header: `X-Owner-Key`)
- `PUT /api/shops/<slug>`
- `DELETE /api/shops/<slug>`
- `GET /api/shops/<slug>/logs`

## Sample Create Request
```bash
curl -X POST http://localhost:8000/api/shops \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sharma Kirana",
    "timings": "Mon-Sat 9AM-9PM",
    "products": ["Atta", "Rice", "Oil"],
    "rules": ["Return within 2 days with bill"],
    "qna": [{"question":"delivery","answer":"Haan, 3km tak free."}]
  }'
```

## GitHub Push (manual)
```bash
git add .
git commit -m "Complete local shop AI system"
git push origin <your-branch>
```

> Note: Is repo me sirf local commit se GitHub pe file tab dikhengi jab `git push` hoga.
