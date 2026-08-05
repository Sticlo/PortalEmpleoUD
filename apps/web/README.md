# RutaUD — Frontend (Angular 21 + SSR)

Bolsa de Empleo Universidad Distrital. UI por **features** y **componentes compartidos**.

## Arranque

```bash
cd apps/web && npm start
# http://localhost:4200
```

## Estructura

```
src/app/
  core/                         # servicios globales (HV, toast, datos)
  shared/components/            # layout reutilizable
    topbar/
    site-header/
    main-nav/
    site-footer/
    toast-message/
  layout/shell/                 # arma topbar + header + nav + footer
  features/                     # módulos por dominio
    home/                       # hero + cómo funciona
    hv/                         # ATS steps + form + preview
    ofertas/                    # radar + offer-card
    cv/                         # resultado CV adaptado
```

Cada feature tiene `*.routes.ts` (lazy load) y `components/` propios.
