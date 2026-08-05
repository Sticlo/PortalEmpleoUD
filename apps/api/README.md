# API — Bolsa de Empleo UD

## Swagger / OpenAPI

| URL | Qué es |
|-----|--------|
| http://127.0.0.1:8000/docs | **Swagger UI** (probar endpoints) |
| http://127.0.0.1:8000/redoc | ReDoc (lectura) |
| http://127.0.0.1:8000/openapi.json | Esquema OpenAPI 3 |

La raíz `http://127.0.0.1:8000/` redirige a `/docs`.

## Arranque

```bash
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Front (proxy `/api` → `:8000`):

```bash
cd apps/web
npm start
```

## Endpoints MVP

- `POST /api/v1/scraping/run` — buscar por `query` (Computrabajo, ≤24 h)
- `GET /api/v1/offers` — listar (purga viejas)
- `GET /api/v1/offers/{id}` — detalle
- `POST /api/v1/cv/adapt` — adaptar HV
- `GET /health` — estado
