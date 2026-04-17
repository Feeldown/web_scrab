# Deploy Guide

## 1) Backend (Railway)

Deploy from repository root with these files:
- `main.py`
- `search_engine.py`
- `cleaned_medicine.json`
- `requirements.txt`
- `Procfile`
- `nixpacks.toml`

### Railway settings
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment variable:
  - `ALLOWED_ORIGINS=https://<your-vercel-domain>`

After deploy, copy backend URL like:
- `https://your-backend.up.railway.app`

Health check:
- `GET /`

## 2) Frontend (Vercel)

Deploy repository root as a static site.

Important:
- Ensure `index.html` is included.
- `vercel.json` is already configured for SPA-style rewrite.

### Set API endpoint
Open browser devtools console on your frontend and run:

```js
localStorage.setItem("medicine_api_base", "https://your-backend.up.railway.app");
location.reload();
```

Or define `window.__API_BASE__` before app script if you want hard-config per environment.

## 3) Quick test

- Frontend search: should call `POST /search`
- OCR upload: should call `POST /ocr-search`
- If blocked by CORS, verify `ALLOWED_ORIGINS` in Railway
