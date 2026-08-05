# Arquitectura — Bolsa de Empleo UD

## Capas + MVC

```
HTTP Request
    │
    ▼
┌─────────────────────────────────────────┐
│  PRESENTATION  (Controllers / MVC-C)    │  app/presentation/controllers/
│  HTTP in/out — sin reglas de negocio    │
└──────────────────┬──────────────────────┘
                   ▼
┌─────────────────────────────────────────┐
│  APPLICATION   (Services)               │  app/application/services/
│  Casos de uso — orquesta dominio + infra│
└──────────────────┬──────────────────────┘
                   ▼
┌─────────────────────────────────────────┐
│  DOMAIN        (Models / MVC-M)         │  app/domain/models/ + schemas/
│  Entidades y DTOs                       │
└──────────────────┬──────────────────────┘
                   ▼
┌─────────────────────────────────────────┐
│  INFRASTRUCTURE                         │  app/infrastructure/
│  DeepSeek · DB · Scrapers Playwright    │
└─────────────────────────────────────────┘
```

| Pieza MVC | Dónde |
|-----------|--------|
| **Model** | `domain/models/` |
| **View** (API) | `domain/schemas/` (JSON de respuesta/request) |
| **Controller** | `presentation/controllers/` |

La “vista” web (HTML) vive en `apps/web/` y `docs/propuesta/`.

## Dónde va cada cosa

| Quieres… | Capa | Ruta |
|----------|------|------|
| Endpoint HTTP nuevo | Presentation | `presentation/controllers/` |
| Regla de negocio | Application | `application/services/` |
| Entidad Offer/Student | Domain | `domain/models/` |
| Request/Response JSON | Domain | `domain/schemas/` |
| DeepSeek | Infrastructure | `infrastructure/ai/deepseek.py` |
| Store / DB | Infrastructure | `infrastructure/persistence/` |
| **Scraper (lógica base)** | Infrastructure | `infrastructure/scraping/` |
| Helpers Playwright (`human_delay`, retries) | Infrastructure | `infrastructure/scraping/browser/` |
| **flores.py recuperado** | Infrastructure | `infrastructure/scraping/legacy/flores.py` |
| Adapter Computrabajo/etc. | Infrastructure | `infrastructure/scraping/portals/` |
| Config / env | Core | `core/config.py` |
| Frontend Angular 21 + SSR | Web | `apps/web/` (UI desde `docs/propuesta`) |

## Scraper — no se pierde

El scraper original se **recuperó** (no está borrado):

1. `legacy/flores.py` — copia exacta de lo que había en siochat-main  
2. `legacy/flores_FLORES_backup.py` — backup en `Documents/FLORES/siochat`  
3. `legacy/ccb_scraper.py` — patrón scraper por sitio  
4. `browser/` — `human_delay`, `goto_with_retry`, `block_heavy_resources`, `launch_browser` listos para portales de empleo  

Flujo futuro por portal:

```
ScrapeService → BasePortalScraper → portals/computrabajo.py
                                  → usa browser/ (lógica de flores)
                                  → normaliza a domain.models.Offer
```

## Principios de crecimiento

1. Multi-tenant (`tenant_id`) desde el día 1  
2. Programas curriculares como dimensión (MVP: Sistemas)  
3. Ciudad configurable (MVP: Bogotá)  
4. Un adapter por portal de empleo  
5. IA solo acomoda HV con skills reales  

## Seeds MVP

`data/seeds/mvp_ud_sistemas_bogota.json`
