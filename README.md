# Arquitectura — Bolsa de Empleo UD / RutaUD

Documento maestro de arquitectura, estado del MVP, flujos, convenciones y roadmap a producción / multi-universidad.

| Campo | Valor |
|-------|--------|
| Producto | **Bolsa de Empleo UD** (marca estudiante: **RutaUD**) |
| Institución piloto | Universidad Distrital Francisco José de Caldas |
| Alcance MVP | Ingeniería de Sistemas · Bogotá · ofertas ≤ 24 h |
| Stack | FastAPI (API) · Angular 21 + SSR (web) · DeepSeek (HV) |
| Estilo | **Capas + MVC** |
| Versión API | `0.3.x` (`apps/api/app/main.py`) |

> Nombre de producto: **nunca** scrapperfacebook / siochat. Esos son legado técnico, no la marca.

---

## 1. Propósito del sistema

RutaUD no compite con Google Empleos ni LinkedIn por volumen. El diferencial institucional es:

1. **Radar ≤ 24 h** — ofertas frescas de portales reales (Computrabajo, Elempleo, LinkedIn guest), no listados viejos.
2. **HV ATS adaptada sin inventar** — DeepSeek reordena/enfatiza solo skills y experiencia del perfil del estudiante.
3. **Ojo (afinidad / brechas)** — match honesto (incluye mismatch de carrera); no bloquea “Preparar CV”.
4. **Métricas de mercado** — panel admin para coordinación (demanda de skills desde vacantes, no “postulaciones inventadas”).
5. **Publicación empresa** — canal directo además del scraping.

---

## 2. Vista de alto nivel

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Estudiantes / Coordinación / Empresas                                   │
│  Browser → Angular 21 SSR (:4200) · proxy /api → FastAPI (:8000)         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ HTTP JSON
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  API FastAPI — capas + MVC                                               │
│  Presentation → Application → Domain                                     │
│                         ↓                                                │
│              Infrastructure (AI · Scrapers · Persistence)                │
└───────┬───────────────────┬──────────────────────┬───────────────────────┘
        │                   │                      │
        ▼                   ▼                      ▼
   DeepSeek API      Portales empleo          Memoria (MVP)
   (adaptar HV)      + cola anti-stampede     + JSONL archive
                                              → Postgres (roadmap)
```

### Monorepo

```
bolsa-empleo-ud/
├── apps/
│   ├── api/                 # Backend FastAPI
│   └── web/                 # Frontend Angular 21 + SSR
├── data/
│   ├── seeds/               # Config MVP (tenant, programa, ciudad)
│   ├── archive/             # offers_archive.jsonl (histórico métricas)
│   └── cache/               # empleos_de_hoy, etc.
├── docs/
│   ├── architecture/        # ESTE documento
│   └── propuesta/           # Mockups / pitch visual
├── infra/                   # Docker / nginx (stubs → producción)
├── scripts/                 # Utilidades ops
├── rules/                   # Cursor rules del producto
└── .env.example
```

---

## 3. Arquitectura de capas + MVC (API)

### 3.1 Diagrama de dependencias

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
│  Entidades y DTOs — sin FastAPI/IO      │
└──────────────────┬──────────────────────┘
                   ▼
┌─────────────────────────────────────────┐
│  INFRASTRUCTURE                         │  app/infrastructure/
│  DeepSeek · Persistence · Scrapers      │
└─────────────────────────────────────────┘

CORE (config, openapi) — transversal, sin lógica de negocio
```

### 3.2 Piezas MVC

| Pieza MVC | Dónde | Rol |
|-----------|--------|-----|
| **Model** | `domain/models/` | Entidades (`Offer`, `StudentProfile`) |
| **View** (API) | `domain/schemas/` | Request/Response JSON (Pydantic) |
| **Controller** | `presentation/controllers/` | Rutas FastAPI, validación HTTP |
| **Vista web** | `apps/web/` | Angular (HTML/CSS); mockups en `docs/propuesta/` |

### 3.3 Regla de oro al agregar código

| Quieres… | Capa | Ruta |
|----------|------|------|
| Endpoint HTTP nuevo | Presentation | `presentation/controllers/` |
| Regla de negocio / caso de uso | Application | `application/services/` |
| Entidad Offer / Student | Domain | `domain/models/` |
| DTO request/response | Domain | `domain/schemas/` |
| Filtros de dominio (ej. empresas bloqueadas) | Domain | `domain/filters/` |
| DeepSeek | Infrastructure | `infrastructure/ai/` |
| Store / DB | Infrastructure | `infrastructure/persistence/` |
| Adapter de un portal | Infrastructure | `infrastructure/scraping/portals/` |
| Helpers browser / Playwright | Infrastructure | `infrastructure/scraping/browser/` |
| Legacy flores (no borrar) | Infrastructure | `infrastructure/scraping/legacy/` |
| Cola de scrapes | Infrastructure | `infrastructure/scraping/job_queue.py` |
| Config / env | Core | `core/config.py` |
| Pantalla Angular | Web | `apps/web/src/app/features/<feature>/` |

**Prohibido:** scrapers o llamadas DeepSeek dentro de controllers; HTML en la API; hardcodear ciudad/programa en services (usar `get_settings()`).

---

## 4. Mapa de módulos API (estado actual)

### 4.1 Presentation — controllers

| Router | Prefijo típico | Responsabilidad |
|--------|----------------|-----------------|
| `tenants_controller` | `/api/v1/tenants` | Tenant activo (UD) |
| `programs_controller` | `/api/v1/programs` | Programas del piloto |
| `students_controller` | `/api/v1/students` | Perfil HV servidor |
| `offers_controller` | `/api/v1/offers` | Listado, CRUD, search indexado, today, empresa |
| `scraping_controller` | `/api/v1/scraping` | `run` + estado de cola |
| `cv_controller` | `/api/v1/cv` | Adaptar HV a oferta (requiere `ai_consent` para usar DeepSeek) + cuota diaria |
| `auth_controller` | `/api/v1/auth` | Placeholder login (sin JWT real) |

Health: `GET /health` (fuera del prefijo de negocio).

Docs: `/docs` · `/redoc` · `/openapi.json`.

### 4.2 Application — services

| Service | Qué hace |
|---------|----------|
| `scrape_service` | Orquesta portales → normaliza `Offer` → guarda / purge ≤24 h |
| `indexed_search_service` | Búsqueda sobre índice local (filtro estricto de relevancia) |
| `today_jobs_service` | “Empleos de hoy” por carreras / cache diario |
| `offer_service` | CRUD ofertas, publicación empresa |
| `student_service` | Perfil estudiante |
| `cv_service` | Adaptación HV (DeepSeek + reglas no inventar / mismatch carrera) |
| `ai_quota_service` | Tope diario global y por IP de llamadas a DeepSeek |

### 4.3 Domain

| Artefacto | Contenido |
|-----------|-----------|
| `models/offer.py` | `Offer` (id, title, company, city, modality, source, url, published_at, description, salary, program_tags, applicants) |
| `models/student.py` | `StudentProfile` — **fuente de verdad** para la IA |
| `schemas/api.py` | Contratos HTTP (health, scrape response, etc.) |
| `filters/blocked_companies.py` | Exclusiones (ej. BairesDev) |

### 4.4 Infrastructure

```
infrastructure/
├── ai/
│   └── deepseek.py          # Cliente OpenAI-compatible
├── persistence/
│   ├── memory.py            # Store MVP (perfiles + ofertas) — se pierde al reiniciar
│   └── offer_archive.py     # Append JSONL → data/archive/offers_archive.jsonl
└── scraping/
    ├── base.py              # BasePortalScraper / contrato común
    ├── job_queue.py         # Cache + single-flight + semáforo + tope cola
    ├── browser/             # human_delay, retries, launch Playwright
    ├── portals/
    │   ├── computrabajo.py
    │   ├── elempleo.py
    │   └── linkedin.py
    └── legacy/
        ├── flores.py        # NO BORRAR — Playwright base recuperado
        ├── flores_FLORES_backup.py
        └── ccb_scraper.py
```

Portales en producción del MVP usan principalmente **HTTP + BeautifulSoup**. Playwright/`browser/` y `legacy/flores.py` están listos para portales que lo exijan; no se eliminan.

---

## 5. Frontend Angular (apps/web)

### 5.1 Estructura

```
apps/web/src/app/
├── layout/shell.*           # Topbar, header, nav, footer, outlet
├── core/                    # Singletons: stores, API clients, mappers, toast
│   ├── offers-store.service.ts
│   ├── offers-api.service.ts
│   ├── hv-profile.service.ts   # Perfil + localStorage
│   ├── offer-mapper.ts         # Match % / Ojo / career mismatch
│   └── hv-ats-export.ts        # PDF / texto ATS
├── features/
│   ├── home/
│   ├── hv/                  # Constructor ATS por pasos
│   ├── ofertas/             # Radar + Empleos de hoy + cards
│   ├── cv/                  # Preparar CV para una oferta
│   ├── empresa/             # Publicar vacante
│   └── privacidad/          # Aviso Ley 1581 + borrar datos
└── shared/components/       # Topbar, header, nav, toast, footer
```

### 5.2 Rutas

| Ruta | Feature |
|------|---------|
| `/` | Inicio |
| `/hoja-de-vida` | Constructor HV ATS |
| `/ofertas` | Radar + Empleos de hoy |
| `/cv/:offerId` | Adaptar / ver CV vs oferta |
| `/empresa` | Publicar oferta |
| `/privacidad` | Aviso de privacidad (Ley 1581), revocar IA, borrar datos |

Lazy-load por `loadChildren` en `app.routes.ts`.

### 5.3 UX de búsqueda (decisión de producto)

1. Al buscar → **limpiar resultados previos** y mostrar spinner/radar.
2. Esperar **scrape en vivo** (cola + caché de la **misma** query).
3. Índice local **solo fallback** si portales/cola fallan (filtro estricto).
4. No pintar “basura” de otra búsqueda ni merge de resultados irrelevantes.

---

## 6. Flujos de negocio críticos

### 6.1 Búsqueda de ofertas

```
Usuario escribe query
    → OffersStore.search()
    → POST /api/v1/scraping/run
         → job_queue (cache 10 min | single-flight | semáforo ≤2 | cola ≤8)
         → ScrapeService → portals[] → Offer[]
         → purge > max_offer_age_hours (default 24)
         → archive JSONL (métricas)
    → offer-mapper (match %, Ojo, careerMismatchNote)
    → UI cards + “Preparar CV”
```

Si scrape responde 503 / error → `GET` search indexado estricto o vacío + mensaje reintentar / Empleos de hoy.

### 6.2 Empleos de hoy

Harvest / cache diario por programas cubiertos → `GET` today → cards recomendadas (siempre navegables a Preparar CV).

### 6.3 Adaptar HV (sin inventar)

```
Perfil (skills, proyectos, experiencia, estudios)  +  texto oferta
                    │
                    ▼
            cv_service + DeepSeek
                    │
                    ▼
   HV reordenada / keywords reales
   + gaps explícitos
   + score no inflado si hay mismatch de carrera
```

Regla de oro del prompt: **solo datos del perfil**. Si la oferta pide X y no está, no se inventa.

### 6.4 Métricas de mercado (admin)

```
Cada oferta guardada → append offers_archive.jsonl
MarketStatsService lee archive → skills, portales, modalidades, empresas
UI /admin/mercado (Chart.js)
POST stats/market/refresh → harvest controlado (misma cola de portales)
```

### 6.5 Publicación empresa

Formulario web → API offers (hoy **sin auth**) → entra al pool como fuente `manual` / empresa.

---

## 7. Cola de scraping (anti-stampede)

Archivo: `infrastructure/scraping/job_queue.py`.

| Mecanismo | Valor MVP | Para qué |
|-----------|-----------|----------|
| TTL caché por query+ciudad | ~10 min | 100 alumnos misma búsqueda → 1 scrape |
| Single-flight | 1 líder por key | Evita N scrapes idénticos en paralelo |
| Semáforo global | 2 jobs portal | No tumbar Computrabajo/Elempleo |
| Cola distinta máx. | 8 | Más allá → 503 amable |
| Timeout espera | ~90 s | No colgar workers eternos |

**Hoy:** in-memory / threading (un proceso).  
**Roadmap:** Redis + worker (Celery/RQ) **sin cambiar el contrato HTTP**.

Endpoint de observación: `GET /api/v1/scraping/queue`.

---

## 8. Configuración y entorno

`core/config.py` + `.env` (ver `.env.example`):

| Variable | Uso |
|----------|-----|
| `APP_NAME` / `APP_ENV` | Nombre y ambiente |
| `API_PREFIX` | Default `/api/v1` |
| `DEFAULT_TENANT_SLUG` | `universidad-distrital` |
| `DEFAULT_CITY` | `Bogotá` |
| `DEFAULT_PROGRAM_SLUG` | `ingenieria-de-sistemas` |
| `MAX_OFFER_AGE_HOURS` | `24` |
| `DEEPSEEK_*` | Key, model (`deepseek-v4-flash`), base URL |
| `CV_GENERATIONS_PER_STUDENT_MONTH` | Cuota (config; **enforcement** en roadmap) |
| `DATABASE_URL` | Declarada; **aún no cableada** a ORM |

Seeds: `data/seeds/mvp_ud_sistemas_bogota.json`.

---

## 9. Modelo de datos (conceptual)

```
Tenant (universidad)
  └── Program (carrera / proyecto curricular)
        └── StudentProfile (HV fuente de verdad)
              └── CvAdaptation (historial generaciones — roadmap)

Offer
  ├── source: computrabajo | elempleo | linkedin | manual | empleos-de-hoy | …
  ├── published_at → purge si age > max_offer_age_hours
  └── program_tags[]

OfferArchive (JSONL append-only) → input de MarketStats
```

**MVP persistencia:** dicts en `memory.py` + JSONL archive.  
**Producción:** Postgres (mismas entidades + `tenant_id` en tablas desde el día 1).

---

## 10. Seguridad y privacidad (estado vs objetivo)

| Tema | Hoy (MVP) | Objetivo producción |
|------|-----------|---------------------|
| Auth | Placeholder `POST /auth/login` | JWT/sesión + roles estudiante / coordinación / empresa |
| Admin / empresa / scrape | Abiertos | Guards + API keys internas |
| CORS | `allow_origins=["*"]` | Orígenes explícitos del dominio UD |
| `/docs` | Público | Off o protegido en prod |
| HV | localStorage + API abierta | Cifrado en tránsito (HTTPS), authz por usuario, consentimiento IA |
| Cuota DeepSeek | Solo config | Enforce en `cv_service` |
| PII a terceros | Perfil/CV a DeepSeek | Minimizar campos; aviso legal; retención/borrado |

---

## 11. Observabilidad y calidad

| Pieza | Hoy | Objetivo |
|-------|-----|----------|
| `GET /health` | Siempre `ok` | Readiness (DB, cola Redis) |
| Logs | `logging` stdlib | Estructurados + correlación request |
| Errores | Consola | Sentry / equivalente |
| Tests | Smoke Angular mínimo | pytest API + fixtures HTML por portal + e2e crítico |
| CI | No | lint + test + build web/api en PR |

---

## 12. Deploy (roadmap infra)

```
Internet → nginx (TLS) → web SSR (:4000/4200)
                       → api uvicorn/gunicorn (:8000)
                       → postgres
                       → redis (cola scrapes)
                       → worker scrape/harvest
```

Despliegue gratuito actual: `docker-compose.yml` (Caddy + API + web) en Oracle Cloud Always Free — ver [`docs/deploy/oracle-cloud.md`](docs/deploy/oracle-cloud.md).

Arranque local actual (dev):

```bash
# API
cd apps/api && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Web
cd apps/web && npm start   # :4200 + proxy a :8000
```

---

## 13. Principios de crecimiento (no negociables)

1. **Multi-tenant** — `tenant_id` en datos desde el primer Postgres (aunque solo exista UD).
2. **Programa curricular** como dimensión (MVP: Sistemas; luego más ingenierías / facultades).
3. **Ciudad configurable** (MVP: Bogotá).
4. **Un adapter por portal** — no if/else gigante en un solo scraper.
5. **IA solo acomoda HV con datos reales** — diferenciador ético y legal.
6. **Ofertas frescas** — purge por `max_offer_age_hours`; el valor es velocidad, no archivo eterno de vacantes (el archive JSONL es para **métricas**, no para mostrar basura al estudiante).
7. **Capas intactas** — producción rellena infra; no reescribe controllers por conveniencia.

---

## 14. Roadmap por fases

### Fase 0 — MVP demo (actual)

- [x] Capas + MVC
- [x] Scrapers Computrabajo / Elempleo / LinkedIn + cola anti-stampede
- [x] Ofertas ≤ 24 h + Empleos de hoy
- [x] HV ATS (web) + adaptar con DeepSeek
- [x] Match / Ojo / mismatch carrera
- [x] Admin métricas mercado + charts
- [x] Publicación empresa (sin auth)
- [x] Archive JSONL para stats
- [x] UI institucional Angular SSR

### Fase 1 — Piloto campus (cobrable como “piloto”, no aún $ soporte full)

- [ ] Postgres + migraciones (Alembic) reemplazando `memory.py`
- [ ] Auth real + roles; cerrar admin/empresa/scrape
- [ ] CORS restringido; HTTPS; ocultar `/docs` en prod
- [ ] Enforce cuota CV / mes
- [ ] Aviso de tratamiento de datos + consentimiento IA
- [ ] Docker Compose (api + web + db)
- [ ] Backup diario DB + restore documentado
- [ ] Informe semanal para coordinación (export PDF/CSV)

### Fase 2 — Producción UD (soporte mensual)

- [ ] Redis + worker para cola de scrapes
- [ ] Monitoreo (Sentry, uptime, alertas scrapers rotos)
- [ ] SSO / correo institucional (si la U lo exige)
- [ ] Tests de contrato por portal (HTML fixtures)
- [ ] SLA interno: tiempo de reparación cuando un portal cambia DOM
- [ ] Ambiente staging ≠ producción

### Fase 3 — Multi-universidad (canal Distrital)

- [ ] Aislamiento tenant en queries y branding
- [ ] Onboarding config (ciudad, programas, portales activos)
- [ ] Facturación / métricas de uso por tenant
- [ ] Modelo comercial: IP operador + licencia UD + % canal (fuera del código; acta legal)

### Fuera de alcance cercano (no priorizar)

- Red social de egresados
- Chat genérico “agente” multi-paso
- 20+ portales el día 1
- Co-propiedad difusa del código sin contrato

---

## 15. Modelo comercial ↔ arquitectura (contexto)

No es código, pero condiciona decisiones técnicas:

| Rol | Responsabilidad |
|-----|-----------------|
| Operador técnico (desarrollador) | IP del producto, hosting, scrapers, IA, soporte |
| Universidad Distrital | Piloto acreditado, marca, posible **canal** a otras U |
| Otras U | Licencia de uso / suscripción; no fork del núcleo |

Implicación técnica: multi-tenant limpio + branding por tenant + métricas de uso por institución.

---

## 16. Scrapers — legado y futuro

El scraper Playwright original **no se eliminó**:

1. `legacy/flores.py` — copia recuperada
2. `legacy/flores_FLORES_backup.py` — backup
3. `legacy/ccb_scraper.py` — patrón por sitio
4. `browser/` — `human_delay`, `goto_with_retry`, `block_heavy_resources`, `launch_browser`

Flujo canónico por portal nuevo:

```
ScrapeService
  → BasePortalScraper
  → portals/<nombre>.py
       → HTTP y/o browser/ (Playwright)
       → normaliza a domain.models.Offer
  → job_queue (siempre pasar por cola en jobs de portal)
```

**Regla:** no borrar `legacy/`; no meter selectores de portal en services.

---

## 17. Criterios de “arquitectura sana” al revisar PRs

1. ¿El cambio toca solo la capa correcta?
2. ¿Hay un adapter nuevo o se ensució `scrape_service` con HTML de un portal?
3. ¿La IA puede inventar experiencia con este cambio? → rechazar.
4. ¿Se hardcodeó ciudad/programa/tenant? → usar settings / DB.
5. ¿El scrape bypasea `job_queue`? → rechazar en rutas públicas.
6. ¿Hay path de datos sin auth en un endpoint sensible? → no merge a `main` de prod.

---

## 18. Referencias rápidas

| Recurso | Ubicación |
|---------|-----------|
| Arranque local | `README.md` raíz |
| OpenAPI tags / descripción | `apps/api/app/core/openapi.py` |
| Settings | `apps/api/app/core/config.py` |
| Reglas Cursor producto | `rules/rules/bolsa-empleo-ud.mdc` |
| Mockups pitch | `docs/propuesta/` |
| Health | `GET http://localhost:8000/health` |
| Swagger | `http://localhost:8000/docs` |

---

## 19. Resumen ejecutivo

| Dimensión | Nota |
|-----------|------|
| Estructura de código (capas, portals, features) | Lista para crecer |
| Persistencia / auth / deploy | Pendiente Fase 1–2 |
| Diferencial de producto | Radar ≤24 h + HV sin inventar + métricas + Ojo |
| Escalabilidad de diseño | Sí (rellenar infra, no reescribir) |
| Escalabilidad operativa hoy | No (memoria, cola in-process, sin auth) |

**Mensaje para stakeholders técnicos:**  
*RutaUD es un MVP con arquitectura de producto (capas + adapters + tenant config), no un script desechable. Producción es completar persistencia, identidad, cola durable y operación — manteniendo las mismas fronteras de módulos.*
