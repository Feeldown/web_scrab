# Deploy Guide

## 1) Backend (Railway)

Deploy from `backend/` directory with these files:
- `backend/main.py`
- `backend/search_engine.py`
- `backend/cleaned_medicine.json`
- `backend/requirements.txt`
- `backend/Procfile`
- `backend/nixpacks.toml`

### Railway settings
- Root directory: `backend`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment variable:
  - `ALLOWED_ORIGINS=https://<your-vercel-domain>`

If Railway root directory is set wrong, this repo also includes a root `Dockerfile`
that builds and runs `backend/` directly.

After deploy, copy backend URL like:
- `https://your-backend.up.railway.app`

Health check:
- `GET /`

## 2) Frontend (Vercel)

Deploy `frontend/` as a static site.

Important:
- Root directory: `frontend`
- Ensure `frontend/index.html` is included.
- `frontend/vercel.json` is already configured for SPA-style rewrite.

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
