#!/usr/bin/env python3
"""Prueba rápida: scrape Computrabajo Bogotá últimas 24h."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(ROOT))

from app.infrastructure.scraping.portals.computrabajo import (  # noqa: E402
    ComputrabajoScraper,
    build_search_url,
)


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "desarrollador"
    print("URL:", build_search_url(query))
    scraper = ComputrabajoScraper(limit=20)
    offers = scraper.fetch_offers(city="Bogotá", max_age_hours=24, query=query)
    print(f"Ofertas: {len(offers)}")
    for o in offers[:10]:
        print(
            f"- [{o.published_at.strftime('%Y-%m-%d %H:%M')}] "
            f"{o.title} | {o.company} | {o.modality}"
        )
    out = Path(__file__).resolve().parents[1] / "data" / "last_computrabajo.json"
    out.write_text(
        json.dumps([o.model_dump(mode="json") for o in offers], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Guardado:", out)


if __name__ == "__main__":
    main()
