"""
LEGACY — Scraper recuperado (no borrar).

Origen:
- `flores.py` = copia exacta de siochat-main/flores.py (historial Cursor)
- `flores_FLORES_backup.py` = versión en Documents/FLORES/siochat
- `ccb_scraper.py` = patrón de scraper por sitio (CCB)

Esta lógica (Playwright, human_delay, goto_with_retry, scroll, extract)
es la base con la que construiremos los scrapers de portales de empleo
en `infrastructure/scraping/portals/`.

NO ejecutar flores.py tal cual dentro de Bolsa de Empleo (es prospección Maps + WhatsApp).
Reutilizar patrones vía `browser/` y nuevos adapters en `portals/`.
"""
