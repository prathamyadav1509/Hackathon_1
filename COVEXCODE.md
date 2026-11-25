# SwasthyaSetu — working notes

## Running the app

The app lives one level down from the workspace root: `SwasthyaSetu/`.
FastAPI serves the static frontend itself (`backend/main.py` mounts `frontend/` at `/`),
so a single process is enough — there is no separate frontend dev server.

```bat
cd SwasthyaSetu
py -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

Then open http://127.0.0.1:8010/

## Gotchas

- `python` is **not** on PATH in this environment (it hits the Microsoft Store
  alias stub and exits 9009). Use the `py` launcher, or `SwasthyaSetu\venv\Scripts\python.exe`.
- **Port 8000 is already taken** on this machine by an unrelated app that also
  answers `/api/health` (with a `database`/`ai_engine` payload). This project's
  health check returns `{"status": "ok", "message": "..."}` instead — use that to
  tell them apart, and run SwasthyaSetu on 8010.
- `.env` uses `DB_BACKEND=auto`: PostgreSQL if reachable, otherwise the SQLite
  file at `database/swasthyasetu.db`. `psycopg2-binary` is therefore optional at runtime.
- Endpoints are unprefixed except health: `/assess`, `/nearby-hospitals`,
  `/nearby-healthcare`, `/assessment-history`, `/api/health`.
- `SwasthyaSetu/venv` has `pytest` installed; the global interpreter does not.
  Tests: `cd SwasthyaSetu && venv\Scripts\python.exe -m pytest tests`.
- Shell quoting through `cmd` mangles inline JSON in `curl -d`. Use an httpx/requests
  script for POST smoke tests instead.
