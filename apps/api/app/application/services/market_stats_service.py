"""Métricas de mercado laboral para administrativos.

Fuente: demanda observada en portales (título + descripción de vacantes reales).
- Skills más/menos pedidas
- Títulos y empresas que más publican
- Bandas salariales (cuando el portal las muestra)
- Seniority (junior / practicante / senior)
- Competencia: postulantes SOLO cuando el portal lo publica (LinkedIn a veces);
  Computrabajo/Elempleo casi nunca lo dan sin cuenta empresa.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from app.domain.schemas.api import (
    MarketCompetitionStat,
    MarketDistributionItem,
    MarketSampleOffer,
    MarketSkillStat,
    MarketStatsResponse,
    MarketTitleStat,
)
from app.infrastructure.persistence.offer_archive import archive_count, load_archived

TZ_CO = timezone(timedelta(hours=-5))

SKILL_PATTERNS: List[Tuple[str, str]] = [
    ("Python", r"\bpython\b"),
    ("Java", r"\bjava\b(?!script)"),
    ("JavaScript", r"\bjavascript\b"),
    ("TypeScript", r"\btypescript\b"),
    ("SQL", r"\bsql\b|postgres|mysql|sql server"),
    ("NoSQL / MongoDB", r"mongo|nosql"),
    ("React", r"\breact\b"),
    ("Angular", r"\bangular\b"),
    ("Node.js", r"\bnode\.?js\b|\bnodejs\b"),
    ("Spring", r"\bspring\b"),
    (".NET / C#", r"\.net\b|\bc#\b"),
    ("PHP", r"\bphp\b"),
    ("APIs / REST", r"\bapi\b|\brest\b|microservicio"),
    ("Docker / K8s", r"docker|kubernetes"),
    ("Cloud (AWS/Azure/GCP)", r"\baws\b|azure|google cloud|\bgcp\b"),
    ("Linux", r"\blinux\b"),
    ("Git", r"\bgit\b|github|gitlab"),
    ("QA / Testing", r"\bqa\b|testing|pruebas de software|selenium|playwright"),
    ("Análisis de datos", r"an[aá]lisis de datos|data analyst|\betl\b|big data"),
    ("Power BI", r"power bi"),
    ("Excel", r"\bexcel\b"),
    ("Machine Learning / IA", r"machine learning|inteligencia artificial|\bml\b|deep learning"),
    ("Ciberseguridad", r"cibersegur|seguridad inform[aá]tica"),
    ("Scrum / Ágil", r"scrum|\b[aá]gil(es)?\b|kanban"),
    ("Inglés", r"ingl[eé]s|english"),
    ("AutoCAD", r"autocad"),
    ("Revit / BIM", r"revit|\bbim\b"),
    ("Diseño estructural", r"dise[nñ]o estructural|cimentac|planos estructurales"),
    ("Interventoría / Obra", r"interventor[ií]a|residente de obra|ayudante de obra"),
    ("SIG / ArcGIS", r"arcgis|\bsig\b|qgis"),
    ("Gestión ambiental", r"ambiental|sostenibil"),
    ("Laboratorio / Química", r"laboratorio|fisicoqu[ií]m|qu[ií]mic"),
    ("SAP / ERP", r"\bsap\b|\berp\b"),
    ("Logística / Producción", r"log[ií]stica|producci[oó]n|cadena de suministro"),
    ("SST / Calidad", r"\bsst\b|iso 9001|gesti[oó]n de calidad"),
    ("Docencia / Pedagogía", r"docen|pedagog"),
    ("Servicio al cliente", r"servicio al cliente|atenci[oó]n al cliente"),
    ("Practicante / Pasante", r"practicante|pasante|pr[aá]ctica profesional"),
]

_COMPILED = [(label, re.compile(pat)) for label, pat in SKILL_PATTERNS]

PROGRAM_LABELS: Dict[str, str] = {
    "ingenieria-civil": "Ing. Civil",
    "ingenieria-de-sistemas": "Ing. de Sistemas",
    "ingenieria-electronica": "Ing. Electrónica",
    "ingenieria-forestal": "Ing. Forestal",
    "ingenieria-quimica": "Ing. Química",
    "licenciatura-en-artes": "Lic. en Artes",
}

SENIORITY_PATTERNS: List[Tuple[str, str]] = [
    ("Practicante / Junior", r"practicante|pasante|junior|\bjr\b|trainee|semillero"),
    ("Semi-senior", r"semi[-\s]?senior|\bssr\b"),
    ("Senior / Lead", r"\bsenior\b|\bsr\b|\blead\b|l[ií]der t[eé]cnico"),
]


def _blob(row: Dict) -> str:
    return f"{row.get('title', '')} {row.get('description', '')}".lower()


def _skills_in(text: str) -> List[str]:
    return [label for label, rx in _COMPILED if rx.search(text)]


def _count_skills(rows: List[Dict]) -> Counter:
    counter: Counter = Counter()
    for row in rows:
        for skill in set(_skills_in(_blob(row))):
            counter[skill] += 1
    return counter


def _distribution(
    rows: List[Dict],
    field: str,
    labels: Dict[str, str] | None = None,
) -> List[MarketDistributionItem]:
    counter: Counter = Counter()
    total = len(rows)
    for row in rows:
        value = (row.get(field) or "").strip().lower() or "sin dato"
        counter[value] += 1
    items = []
    for value, count in counter.most_common(8):
        label = (labels or {}).get(value, value.title())
        pct = round(count * 100 / total) if total else 0
        items.append(MarketDistributionItem(label=label, count=count, percent=pct))
    return items


def _program_distribution(rows: List[Dict]) -> List[MarketDistributionItem]:
    counter: Counter = Counter()
    total = len(rows)
    for row in rows:
        tags = row.get("program_tags") or []
        slug = next((t for t in tags if t in PROGRAM_LABELS), None)
        counter[slug or "otros"] += 1
    items = []
    for slug, count in counter.most_common(8):
        label = PROGRAM_LABELS.get(slug, "Otros / general")
        pct = round(count * 100 / total) if total else 0
        items.append(MarketDistributionItem(label=label, count=count, percent=pct))
    return items


def _seniority(rows: List[Dict]) -> List[MarketDistributionItem]:
    counter: Counter = Counter()
    total = len(rows)
    for row in rows:
        text = _blob(row)
        hit = "Sin nivel claro"
        for label, pat in SENIORITY_PATTERNS:
            if re.search(pat, text):
                hit = label
                break
        counter[hit] += 1
    items = []
    for label, count in counter.most_common():
        pct = round(count * 100 / total) if total else 0
        items.append(MarketDistributionItem(label=label, count=count, percent=pct))
    return items


def _parse_salary(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    # "$ 3.500.000,00" / "$3500000"
    digits = re.findall(r"\d+", raw.replace(".", "").replace(",", ""))
    if not digits:
        return None
    # Take largest number in string (usually the salary)
    nums = [int(d) for d in digits if len(d) >= 5]
    if not nums:
        return None
    n = max(nums)
    if n < 500_000 or n > 50_000_000:
        return None
    return n


def _salary_bands(rows: List[Dict]) -> List[MarketDistributionItem]:
    bands = [
        ("< $2M", 0, 2_000_000),
        ("$2M – $3.5M", 2_000_000, 3_500_000),
        ("$3.5M – $5M", 3_500_000, 5_000_000),
        ("$5M – $8M", 5_000_000, 8_000_000),
        ("> $8M", 8_000_000, 10**12),
    ]
    counter: Counter = Counter()
    with_salary = 0
    for row in rows:
        n = _parse_salary(row.get("salary"))
        if n is None:
            continue
        with_salary += 1
        for label, lo, hi in bands:
            if lo <= n < hi:
                counter[label] += 1
                break
    if not with_salary:
        return []
    order = [b[0] for b in bands]
    items = []
    for label in order:
        count = counter.get(label, 0)
        if not count:
            continue
        items.append(
            MarketDistributionItem(
                label=label,
                count=count,
                percent=round(count * 100 / with_salary),
            )
        )
    return items


def _top_titles(rows: List[Dict], n: int = 12) -> List[MarketTitleStat]:
    counter: Counter = Counter()
    for row in rows:
        title = re.sub(r"\s+", " ", (row.get("title") or "").strip())
        if len(title) < 4:
            continue
        # Normaliza casing ligero
        key = title[:80]
        counter[key] += 1
    total = len(rows)
    return [
        MarketTitleStat(
            title=t,
            count=c,
            percent=round(c * 100 / total) if total else 0,
        )
        for t, c in counter.most_common(n)
    ]


def _top_companies(rows: List[Dict], n: int = 10) -> List[MarketDistributionItem]:
    counter: Counter = Counter()
    for row in rows:
        co = (row.get("company") or "").strip()
        if not co or "confidencial" in co.lower():
            continue
        counter[co] += 1
    total = sum(counter.values()) or 1
    return [
        MarketDistributionItem(label=c, count=n, percent=round(n * 100 / total))
        for c, n in counter.most_common(n)
    ]


def _samples_for_skill(rows: List[Dict], skill: str, limit: int = 3) -> List[MarketSampleOffer]:
    rx = next((r for lab, r in _COMPILED if lab == skill), None)
    if not rx:
        return []
    out: List[MarketSampleOffer] = []
    for row in rows:
        if not rx.search(_blob(row)):
            continue
        out.append(
            MarketSampleOffer(
                title=row.get("title") or "",
                company=row.get("company") or "",
                source=row.get("source") or "",
                salary=row.get("salary"),
                applicants=row.get("applicants"),
                url=row.get("url"),
            )
        )
        if len(out) >= limit:
            break
    return out


def _competition(rows: List[Dict]) -> MarketCompetitionStat:
    with_app = [r for r in rows if isinstance(r.get("applicants"), int) and r["applicants"] > 0]
    if not with_app:
        return MarketCompetitionStat(
            offers_with_applicants=0,
            offers_total=len(rows),
            coverage_percent=0,
            avg_applicants=None,
            median_applicants=None,
            max_applicants=None,
            note=(
                "Los portales NO publican cuántos aplicaron de forma abierta "
                "(Computrabajo/Elempleo requieren cuenta empresa; LinkedIn guest "
                "a veces muestra el dato). Usa 'vacantes abiertas por skill' como "
                "señal de demanda real del mercado."
            ),
        )
    vals = sorted(int(r["applicants"]) for r in with_app)
    mid = vals[len(vals) // 2]
    avg = round(sum(vals) / len(vals), 1)
    return MarketCompetitionStat(
        offers_with_applicants=len(with_app),
        offers_total=len(rows),
        coverage_percent=round(len(with_app) * 100 / len(rows)) if rows else 0,
        avg_applicants=avg,
        median_applicants=mid,
        max_applicants=max(vals),
        note=(
            f"Dato de postulantes disponible en {len(with_app)}/{len(rows)} vacantes "
            f"(casi siempre LinkedIn). El resto de portales no lo publica."
        ),
    )


def _build_insight(
    top: List[MarketSkillStat],
    rising: List[str],
    low: List[MarketSkillStat],
    total: int,
    days: int,
    salary_pct: int,
    competition: MarketCompetitionStat,
) -> str:
    if not total:
        return (
            "Aún no hay histórico. Pulsa «Actualizar datos del mercado» para traer "
            "vacantes reales de los últimos 7 días desde Computrabajo, Elempleo y LinkedIn."
        )
    names = ", ".join(s.skill for s in top[:5]) or "varias áreas"
    parts = [
        f"Se analizaron {total} vacantes reales en {days} días. "
        f"Las skills más pedidas: {names}."
    ]
    if rising:
        parts.append(f"En crecimiento: {', '.join(rising[:3])}.")
    if low:
        parts.append(
            f"Poco pedidas en esta muestra: {', '.join(s.skill for s in low[:3])} "
            f"(útil para no saturar cursos sin demanda)."
        )
    parts.append(f"El {salary_pct}% de las vacantes publica salario.")
    if competition.offers_with_applicants:
        parts.append(
            f"Postulantes públicos (muestra {competition.offers_with_applicants}): "
            f"promedio {competition.avg_applicants}, máx {competition.max_applicants}."
        )
    else:
        parts.append(
            "Postulantes por vacante: no disponibles públicamente en la mayoría de portales; "
            "la señal útil es cuántas vacantes piden cada skill."
        )
    parts.append(
        "Sugerencia: contrastar el top de skills con el pensum y priorizar cursos cortos "
        "donde haya brecha."
    )
    return " ".join(parts)


def _age_days(row: Dict) -> float:
    when = row.get("_when")
    if when is None:
        return 9999
    return (datetime.now(TZ_CO) - when).total_seconds() / 86400


class MarketStatsService:
    def market(self, days: int = 30) -> MarketStatsResponse:
        rows = load_archived(days=days * 2)
        now_rows = [r for r in rows if _age_days(r) < days]
        prev_rows = [r for r in rows if days <= _age_days(r) < days * 2]

        current = _count_skills(now_rows)
        previous = _count_skills(prev_rows)
        total = len(now_rows)

        skills: List[MarketSkillStat] = []
        for skill, count in current.most_common(20):
            prev = previous.get(skill, 0)
            if prev == 0:
                trend = "nueva" if count >= 2 else "estable"
            elif count > prev:
                trend = "sube"
            elif count < prev:
                trend = "baja"
            else:
                trend = "estable"
            skills.append(
                MarketSkillStat(
                    skill=skill,
                    count=count,
                    percent=round(count * 100 / total) if total else 0,
                    previous_count=prev,
                    trend=trend,
                    samples=_samples_for_skill(now_rows, skill, 3),
                )
            )

        # Menos pedidas = skills del catálogo con 0 o pocas menciones (contexto formativo)
        low_skills: List[MarketSkillStat] = []
        for skill, _pat in SKILL_PATTERNS:
            c = current.get(skill, 0)
            if c == 0:
                low_skills.append(
                    MarketSkillStat(
                        skill=skill,
                        count=0,
                        percent=0,
                        previous_count=previous.get(skill, 0),
                        trend="estable",
                        samples=[],
                    )
                )
            if len(low_skills) >= 8:
                break

        rising = [s.skill for s in skills if s.trend in ("sube", "nueva")]
        with_salary = sum(1 for r in now_rows if (r.get("salary") or "").strip())
        salary_pct = round(with_salary * 100 / total) if total else 0
        competition = _competition(now_rows)

        return MarketStatsResponse(
            days=days,
            total_offers=total,
            archive_total=archive_count(),
            top_skills=skills,
            low_demand_skills=low_skills,
            top_titles=_top_titles(now_rows),
            top_companies=_top_companies(now_rows),
            by_modality=_distribution(
                now_rows,
                "modality",
                {"hibrido": "Híbrido", "presencial": "Presencial", "remoto": "Remoto"},
            ),
            by_source=_distribution(
                now_rows,
                "source",
                {
                    "computrabajo": "Computrabajo",
                    "elempleo": "Elempleo",
                    "linkedin": "LinkedIn",
                    "empresa": "Empresa aliada",
                },
            ),
            by_program=_program_distribution(now_rows),
            by_city=_distribution(now_rows, "city"),
            by_seniority=_seniority(now_rows),
            salary_bands=_salary_bands(now_rows),
            salary_disclosed_percent=salary_pct,
            competition=competition,
            insight=_build_insight(
                skills, rising, low_skills, total, days, salary_pct, competition
            ),
            applicants_disclaimer=(
                "«Cuántos aplicaron» NO es público en Computrabajo ni Elempleo "
                "(solo lo ve la empresa). LinkedIn a veces lo muestra: lo capturamos "
                "cuando aparece. La métrica confiable de mercado es la demanda "
                "(cuántas vacantes piden cada skill)."
            ),
        )
