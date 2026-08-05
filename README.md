# Bolsa de Empleo — Universidad Distrital Francisco José de Caldas

Plataforma institucional de empleabilidad (producto: **RutaUD**).  
MVP: **Ingeniería de Sistemas** · **Bogotá** · scrapers Playwright · HV con IA.

> Producto: **Bolsa de Empleo UD**. Arquitectura: **capas + MVC**.

## Mapa rápido

| Carpeta | Qué vive ahí |
|---------|----------------|
| `apps/api/app/presentation/` | Controllers (MVC) — HTTP |
| `apps/api/app/application/` | Services — reglas de negocio |
| `apps/api/app/domain/` | Models + schemas |
| `apps/api/app/infrastructure/scraping/` | **Scraper** (legacy flores + browser + portals) |
| `apps/api/app/infrastructure/ai/` | DeepSeek |
| `apps/web/` | Frontend **Angular 21 + SSR** (RutaUD) |
| `docs/propuesta/` | Mockups |
| `docs/architecture/` | Mapa completo de capas |

## Scraper (recuperado)

La lógica de Playwright **no se eliminó**. Está en:

`apps/api/app/infrastructure/scraping/legacy/flores.py`

Helpers listos para portales de empleo: `infrastructure/scraping/browser/`.

## Arranque local

```bash
cd bolsa-empleo-ud/apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # para scrapers
uvicorn app.main:app --reload --port 8000
```

- Health: http://localhost:8000/health  
- Docs: http://localhost:8000/docs  
- Mockups: `docs/propuesta/index.html`


## Frontend (Angular 21 + SSR)

```bash
cd apps/web
npm install
npm start
```

Abre http://localhost:4200 — UI basada en `docs/propuesta`.
