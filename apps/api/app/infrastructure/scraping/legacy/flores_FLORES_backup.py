"""
Herramienta de Prospección SIO - Google Maps Lead Scraper
Extrae negocios SIN sitio web desde Google Maps para prospección vía WhatsApp.
"""

import os
import sys
import signal
import re
import time
import random
import fcntl
import math
import json
import logging
from datetime import datetime, timezone, timedelta
from collections import Counter
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from PIL import Image
import requests

from core.config import (
    KEYWORDS, ZONES, MIN_REVIEWS, COUNTRY_PREFIX, MAX_SCROLLS,
    BASE_DIR, OUTPUT_FILE, QUERIES_DONE, KEYWORD_STATS, AUTOSAVE_EVERY, PARALLEL_TABS, WEB_SKIP_LIMIT,
    CATEGORIAS_EXCLUIDAS, MAX_CARDS,
    TEMPLATE_FILE, MOCKUP_DIR, WA_MESSAGE,
    META_PHONE_ID, META_ACCESS_TOKEN, META_TEMPLATE_NAME,
    META_TEMPLATE_LANG, META_API_VERSION, META_SEND_DELAY_MIN,
    META_SEND_DELAY_MAX, DAILY_SEND_LIMIT, SEND_WAVES,
    SKIP_FIRST_LEADS, send_is_paused, scraper_is_paused,
)
from core.alertas import send_alert, alerta_on_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("SIO-Scraper")

# Zona horaria Colombia (UTC-5)
TZ_COL = timezone(timedelta(hours=-5))

def now_colombia() -> datetime:
    """Retorna la hora actual en zona horaria de Colombia (UTC-5)."""
    return datetime.now(TZ_COL)


# ──────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES
# ──────────────────────────────────────────────────────────────────────

def human_delay(min_s: float = 1.0, max_s: float = 3.5):
    """Pausa aleatoria para simular comportamiento humano."""
    time.sleep(random.uniform(min_s, max_s))


def load_done_queries():
    """Carga el set de queries ya intentadas desde archivo."""
    done = set()
    if os.path.exists(QUERIES_DONE):
        with open(QUERIES_DONE, "r", encoding="utf-8") as f:
            for line in f:
                q = line.strip()
                if q:
                    done.add(q.lower())
    return done


def mark_query_done(query: str):
    """Agrega una query al archivo de queries completadas."""
    with open(QUERIES_DONE, "a", encoding="utf-8") as f:
        f.write(query + "\n")


# ── Thompson Sampling para selección inteligente de keywords ───────────

HIGH_VALUE_KEYWORD_PRIORS = {
    # Nichos con mayor capacidad de pago y mayor valor por cliente.
    "Abogados": [28, 2],
    "Consultoría empresarial": [26, 2],
    "Revisoría fiscal": [25, 2],
    "Asesoría financiera": [24, 2],
    "Contadores": [23, 2],
    "Aseguradoras": [22, 2],
    "Corredores de seguros": [22, 2],
    "Inmobiliarias": [21, 2],
    "Constructoras": [21, 2],
    "Arquitectos": [20, 2],
    "Gestores de propiedad horizontal": [19, 2],
    "Notarías": [18, 2],
    "Seguridad privada": [18, 2],
    "Logística": [17, 2],
    "Hotel": [17, 2],
    "Instalación de Paneles Solares": [17, 2],
    "Cámaras de seguridad": [17, 2],
    "Cirugía Plástica": [16, 2],
    "Medicina estética": [16, 2],
    "Clínica de fertilidad": [16, 2],
    "Implantes dentales": [15, 2],
    "Clínicas odontológicas": [15, 2],
    "Ortodoncia y Diseño de Sonrisa": [15, 2],
    "Colegios privados": [14, 2],
    "Cardiólogos": [14, 2],
    "Oftalmólogos": [14, 2],
    "Urólogos": [14, 2],
}

HIGH_VALUE_KEYWORD_MULTIPLIER = {
    "Abogados": 3.20,
    "Consultoría empresarial": 3.00,
    "Revisoría fiscal": 2.90,
    "Asesoría financiera": 2.80,
    "Contadores": 2.70,
    "Aseguradoras": 2.60,
    "Corredores de seguros": 2.60,
    "Inmobiliarias": 2.45,
    "Constructoras": 2.40,
    "Arquitectos": 2.35,
    "Gestores de propiedad horizontal": 2.25,
    "Notarías": 2.20,
    "Seguridad privada": 2.15,
    "Logística": 2.05,
    "Hotel": 2.00,
    "Instalación de Paneles Solares": 2.00,
    "Cámaras de seguridad": 2.00,
    "Cirugía Plástica": 1.90,
    "Medicina estética": 1.90,
    "Clínica de fertilidad": 1.85,
    "Implantes dentales": 1.80,
    "Clínicas odontológicas": 1.75,
    "Ortodoncia y Diseño de Sonrisa": 1.75,
    "Colegios privados": 1.65,
    "Cardiólogos": 1.60,
    "Oftalmólogos": 1.60,
    "Urólogos": 1.60,
}

PREMIUM_BATCH_SHARE = 0.70

# ── Prioridad de envío por keyword (mayor = más urgente) ───────────────
# El sistema ordena leads_to_send por esta puntuación antes de cada oleada,
# así los nichos premium salen primero sin importar su posición en el Excel.
KEYWORD_SEND_PRIORITY = {
    # ── Tier 1: alta capacidad de pago, entienden el valor digital ──
    "Abogados": 100,
    "Cooperativas de ahorro y crédito": 98,
    "Fondos de empleados": 97,
    "Cajas de compensación familiar": 96,
    "Consultoría empresarial": 95,
    "Revisoría fiscal": 94,
    "Asesoría financiera": 93,
    "Contadores": 92,
    "Aseguradoras": 91,
    "Corredores de seguros": 90,
    "Arquitectos": 89,
    "Ingenieros estructurales": 88,
    "Agencias de publicidad": 87,
    "Productoras de video y fotografía": 86,
    "Empresas de outsourcing": 85,
    "Agencias de empleo y headhunting": 84,
    "Empresas de transporte de carga": 83,
    "Distribuidoras mayoristas": 82,
    "Proveedores de equipos médicos": 81,
    "Clínicas de salud ocupacional": 80,
    # ── Tier 2: construcción e inmobiliaria ──
    "Constructoras": 78,
    "Inmobiliarias": 77,
    "Gestores de propiedad horizontal": 76,
    "Notarías": 75,
    "Seguridad privada": 74,
    "Instalación de Paneles Solares": 73,
    "Cámaras de seguridad": 72,
    "Domótica": 71,
    "Diseñadores de interiores": 70,
    # ── Tier 3: salud especializada ──
    "Cirugía Plástica": 68,
    "Medicina estética": 67,
    "Clínica de fertilidad": 66,
    "Cirugía oftalmológica láser": 65,
    "Implantes dentales": 64,
    "Ortodoncia y Diseño de Sonrisa": 63,
    "Clínicas odontológicas": 62,
    "Cardiólogos": 61,
    "Dermatología": 60,
    "Oftalmólogos": 59,
    "Urólogos": 58,
    "Psiquiatras": 57,
    "Laboratorios clínicos": 56,
    # ── Tier 4: educación privada y automotriz premium ──
    "Colegios privados": 54,
    "Centro de idiomas": 53,
    "Concesionario de autos": 52,
    "Centros de diagnóstico automotriz": 51,
    "Taller de latonería y pintura": 50,
    "Hotel": 49,
    "Agencia de viajes": 48,
    "Logística": 47,
    # ── Tier 5: comercio con margen ──
    "Ópticas": 44,
    "Joyería y relojería": 43,
    "Mueblería": 42,
    "Tienda de tecnología": 41,
    # ── Default implícito para todo lo demás: 0 ──
}


def _lead_priority(lead: dict) -> int:
    """Puntuación de prioridad de un lead según su keyword. Usado para ordenar
    tanto la generación de mockups como el envío — premium siempre primero."""
    busqueda = lead.get("Búsqueda", "") or ""
    for keyword, score in KEYWORD_SEND_PRIORITY.items():
        if keyword.lower() in busqueda.lower():
            return score
    return 0


def apply_keyword_prior(stats: dict, keyword: str):
    """Garantiza un prior fuerte para nichos premium sin borrar aprendizaje previo."""
    prior = HIGH_VALUE_KEYWORD_PRIORS.get(keyword, [1, 1])
    current = stats.get(keyword, [1, 1])
    stats[keyword] = [max(current[0], prior[0]), max(current[1], prior[1])]

def load_keyword_stats() -> dict:
    """Carga estadísticas {keyword: [alpha, beta]} para Thompson Sampling.
    alpha = leads encontrados + 1 (prior), beta = queries sin leads + 1."""
    if os.path.exists(KEYWORD_STATS):
        try:
            with open(KEYWORD_STATS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_keyword_stats(stats: dict):
    """Persiste las estadísticas de Thompson Sampling a disco."""
    try:
        with open(KEYWORD_STATS, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"No se pudo guardar keyword_stats: {e}")


def thompson_select_keyword(available_keywords: list, stats: dict) -> str:
    """Elige un keyword usando Thompson Sampling (Beta-Bernoulli).
    Prioriza keywords que históricamente producen más leads,
    pero explora periódicamente los menos conocidos."""
    best_kw = None
    best_sample = -1.0
    for kw in available_keywords:
        alpha, beta = stats.get(kw, [1, 1])
        sample = random.betavariate(alpha, beta) * HIGH_VALUE_KEYWORD_MULTIPLIER.get(kw, 1.0)
        if sample > best_sample:
            best_sample = sample
            best_kw = kw
    return best_kw


def clean_phone(raw: str) -> str:
    """Elimina espacios, paréntesis, guiones y puntos de un número telefónico."""
    cleaned = re.sub(r"[\s()\-\.\+]", "", raw)
    # Si empieza con el código de país, quitarlo para normalizar
    if cleaned.startswith("57"):
        cleaned = cleaned[2:]
    # Quedarnos solo con dígitos
    cleaned = re.sub(r"\D", "", cleaned)
    return cleaned


def build_whatsapp_link(phone_clean: str, nombre: str = "", busqueda: str = "") -> str:
    """Genera el link de WhatsApp directo con mensaje personalizado."""
    if not phone_clean:
        return ""
    from urllib.parse import quote
    msg = WA_MESSAGE.format(nombre=nombre, busqueda=busqueda)
    return f"https://wa.me/{COUNTRY_PREFIX}{phone_clean}?text={quote(msg)}"


def parse_rating_reviews(text: str):
    """
    Extrae calificación y número de reseñas de textos como:
    '4,5(120)' o '4.5 (120 reseñas)' o '4,5 estrellas 120 reseñas'
    """
    rating = None
    reviews = None

    rating_match = re.search(r"(\d[.,]\d)", text)
    if rating_match:
        rating = float(rating_match.group(1).replace(",", "."))

    reviews_match = re.search(r"\((\d[\d.]*)\)", text)
    if reviews_match:
        reviews = int(reviews_match.group(1).replace(".", ""))
    else:
        reviews_match = re.search(r"(\d[\d.]*)\s*reseña", text)
        if reviews_match:
            reviews = int(reviews_match.group(1).replace(".", ""))

    return rating, reviews


def load_existing_leads(filename: str) -> tuple[list[dict], set[str], set[str]]:
    """Carga leads existentes del Excel para modo incremental.

    seen_phones incluye también contactados_previos (WhatsApp anterior / backup)
    para que el scraper no vuelva a guardar esos números.
    """
    leads = []
    seen = set()
    seen_phones = set()
    previos: set[str] = set()

    # Bloquear números ya contactados en el sistema anterior (backup SIO)
    try:
        from core.db import get_contactados_previos_phones
        previos = get_contactados_previos_phones()
        if previos:
            seen_phones |= previos
            log.info(f"🚫 {len(previos)} teléfonos del backup previo (no se volverán a scrapear)")
    except Exception as e:
        log.warning(f"No se pudo cargar contactados_previos: {e}")

    if not os.path.exists(filename):
        return leads, seen, seen_phones
    try:
        wb = load_workbook(filename, read_only=True, data_only=True)
        try:
            ws = wb.active
            headers = [cell.value for cell in ws[1]]
            skipped_previos = 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                lead = dict(zip(headers, row))
                if lead.get("Nombre"):
                    # Filtro de calidad al recargar
                    if not _lead_es_valido(lead):
                        continue
                    name_key = lead["Nombre"].lower().strip()
                    phone = (lead.get("WhatsApp Directo") or "").replace("+", "")
                    # No cargar al Excel de trabajo leads ya contactados antes
                    if phone and phone in previos:
                        skipped_previos += 1
                        continue
                    if name_key in seen or (phone and phone in seen_phones):
                        continue
                    leads.append(lead)
                    seen.add(name_key)
                    if phone:
                        seen_phones.add(phone)
            log.info(f"📂 Cargados {len(leads)} leads existentes de {filename}")
            if skipped_previos:
                log.info(f"⏭️  Omitidos {skipped_previos} leads del Excel que ya estaban en el backup")
        finally:
            wb.close()
    except Exception as e:
        log.warning(f"No se pudo leer {filename}: {e}")
    return leads, seen, seen_phones


def goto_with_retry(page, url: str, retries: int = 2, timeout: int = 20000) -> bool:
    """Navega a una URL con reintentos y backoff."""
    for attempt in range(retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception as e:
            error_msg = str(e)[:200]  # Limitar longitud del mensaje
            if attempt < retries:
                wait = (attempt + 1) * 2
                log.warning(f"    ⟳ Reintento {attempt + 1}/{retries} en {wait}s... (Error: {error_msg})")
                time.sleep(wait)
            else:
                log.error(f"    ✗ Falló tras {retries + 1} intentos: {error_msg}")
                return False


def block_heavy_resources(route):
    """Bloquea imágenes y video (pesados) pero deja CSS/fonts para parecer navegador real."""
    if route.request.resource_type in ("image", "media"):
        route.abort()
    else:
        route.continue_()


# ──────────────────────────────────────────────────────────────────────
# MOCKUP: Genera imagen JPG de landing page personalizada
# ──────────────────────────────────────────────────────────────────────

def generate_mockup(lead: dict, browser_instance) -> str | None:
    """
    Lee template_mockup.html, reemplaza placeholders con datos del lead,
    renderiza con Playwright y guarda como JPG en mockups/.
    Recibe un browser ya lanzado (no lanza uno nuevo por lead).
    Retorna la ruta del archivo JPG o None si falla.
    """
    if not os.path.exists(TEMPLATE_FILE):
        log.warning("⚠️  template_mockup.html no encontrado, omitiendo mockup.")
        return None

    os.makedirs(MOCKUP_DIR, exist_ok=True)

    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            html = f.read()

        # Reemplazar placeholders (or "" protege contra None de celdas vacías)
        nombre = lead.get("Nombre") or "Mi Negocio"
        categoria = lead.get("Categoría") or ""
        direccion = lead.get("Dirección") or ""
        telefono = lead.get("Teléfono") or ""
        calificacion = lead.get("Calificación") or 4.5
        resenas = lead.get("Reseñas") or 0
        # Generar dominio ficticio: "Odontología Dr Diego" -> "odontologiadrdiego"
        dominio = re.sub(r'[^a-zA-Z0-9]', '', nombre.lower())[:25]
        # Dividir nombre en 2 líneas para el hero title
        words = nombre.split()
        mid = len(words) // 2 or 1
        nombre_line1 = " ".join(words[:mid])
        nombre_line2 = " ".join(words[mid:]) if len(words) > 1 else categoria
        # Inicial para el avatar del card
        inicial = nombre[0].upper() if nombre else "N"
        html = html.replace("{{INICIAL}}", inicial)
        html = html.replace("{{NOMBRE_LINE1}}", nombre_line1)
        html = html.replace("{{NOMBRE_LINE2}}", nombre_line2)
        html = html.replace("{{NOMBRE}}", nombre)
        html = html.replace("{{CATEGORIA}}", categoria)
        html = html.replace("{{CATEGORIA_LOWER}}", categoria.lower())
        html = html.replace("{{DIRECCION}}", direccion)
        html = html.replace("{{TELEFONO}}", telefono)
        html = html.replace("{{CALIFICACION}}", str(calificacion))
        html = html.replace("{{RESENAS}}", str(int(resenas)))
        html = html.replace("{{ANOS}}", str(max(5, int(resenas) // 10)))
        html = html.replace("{{DOMINIO}}", dominio)

        # Guardar HTML temporal
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', nombre)[:60]
        temp_html = os.path.join(MOCKUP_DIR, f"_temp_{safe_name}.html")
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(html)

        # Renderizar con Playwright headless (browser compartido, no se crea uno por lead)
        page = browser_instance.new_page(viewport={"width": 1280, "height": 720})
        try:
            page.goto(f"file:///{temp_html.replace(os.sep, '/')}", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)

            # Captura viewport (sin scroll) como PNG temporal
            png_path = os.path.join(MOCKUP_DIR, f"{safe_name}.png")
            page.screenshot(path=png_path, full_page=False)
        finally:
            try:
                page.close()
            except Exception:
                pass

        # Convertir a JPG
        jpg_path = os.path.join(MOCKUP_DIR, f"{safe_name}.jpg")
        img = Image.open(png_path).convert("RGB")
        img.save(jpg_path, "JPEG", quality=90)
        os.remove(png_path)

        # Limpiar HTML temporal
        try:
            os.remove(temp_html)
        except Exception:
            pass

        log.info(f"    🖼️  Mockup: {jpg_path}")
        return jpg_path

    except Exception as e:
        err_msg = str(e)
        # Errores de browser muerto: propagarlos para que el caller pueda relanzar
        if any(k in err_msg for k in ("closed", "crashed", "disconnected", "Target page")):
            raise
        log.warning(f"    ⚠️  Error generando mockup para {lead.get('Nombre', '?')}: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────
# WHATSAPP CLOUD API – ENVÍO DE MENSAJES
# ──────────────────────────────────────────────────────────────────────

# Errores de Meta que indican problema del destinatario (sí marcar send_failed)
_RECIPIENT_ERROR_CODES = {131026}  # número sin WhatsApp
# Errores de Meta que indican problema de cuenta/API (no marcar send_failed)
_API_ERROR_CODES = {1, 190, 546, 131000, 131005, 131058, 132012, 133010}


def _meta_error_code(resp) -> int:
    try:
        return int(resp.json().get("error", {}).get("code", 0))
    except Exception:
        return 0


def upload_media_to_meta(image_path: str, retries: int = 3) -> str | None:
    """
    Sube una imagen a la API de Meta y retorna el media_id.
    Reintenta en errores transitorios de Meta (500 / #131000).
    """
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_ID}/media"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    for attempt in range(1, retries + 1):
        with open(image_path, "rb") as img_file:
            files = {"file": (os.path.basename(image_path), img_file, "image/jpeg")}
            data = {"messaging_product": "whatsapp"}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=30)

        if resp.status_code == 200:
            media_id = resp.json().get("id")
            log.info(f"    📤 Imagen subida → media_id: {media_id}")
            return media_id

        code = _meta_error_code(resp)
        log.error(f"    ❌ Error subiendo imagen (intento {attempt}/{retries}): {resp.status_code} — {resp.text}")
        if attempt < retries and (resp.status_code >= 500 or code in (131000, 190)):
            time.sleep(5 * attempt)
            continue
        return None
    return None


def _phone_has_whatsapp(phone: str) -> bool:
    """
    Verifica si un número tiene WhatsApp intentando enviar un mensaje de texto
    vacío (sin cuerpo) — Meta responde 131026 si el número no está registrado
    en WhatsApp, o un error diferente si sí lo está (token inválido, etc.).
    Esto evita subir la imagen y gastar el envío en números sin WA.
    Retorna True si está registrado, False si definitivamente no tiene WA.
    En cualquier error de conectividad retorna True para no bloquear el flujo.
    """
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    # Intentar enviar un template al número — si el número no tiene WA
    # Meta responde 131026 de inmediato sin cobrar.
    # Usamos type "text" con body vacío para forzar un rechazo rápido.
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": " "},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            # Mensaje enviado — definitivamente tiene WhatsApp
            # Anotar en DB para no duplicar después
            try:
                from core.db import add_message
                add_message(phone, "out", "[pre-check]", "text", "sent")
            except Exception:
                pass
            return True
        body = resp.json().get("error", {})
        code = body.get("code", 0)
        if code == 131026:
            # Número sin WhatsApp — marcar send_failed para no reintentar
            try:
                from core.db import mark_send_failed
                mark_send_failed(phone)
            except Exception:
                pass
            return False
        # Cualquier otro error (rate limit, permisos, etc.) — dejar pasar
        return True
    except Exception:
        return True


def send_whatsapp_template(phone: str, nombre: str, busqueda: str, media_id: str | None = None,
                           categoria: str = "", _skip_guard: bool = False) -> bool:
    """
    Envía un mensaje de template de WhatsApp vía Meta Cloud API.
    - phone: número completo con código de país (ej: "573001234567")
    - nombre: nombre del negocio (parámetro {{1}} del template)
    - busqueda: categoría de búsqueda (parámetro {{2}} del template)
    - media_id: ID de la imagen subida (para el header del template)
    """
    # ── GUARD: última línea de defensa contra duplicados ──
    if not _skip_guard:
        try:
            from core.db import phone_has_chat, is_reactivo
            if is_reactivo(phone):
                log.warning(f"    🛑 BLOQUEADO: +{phone} está en reactivos/contactar después. No se envía template.")
                return False
            if phone_has_chat(phone):
                log.warning(f"    🛑 BLOQUEADO: +{phone} ya tiene chat en la DB. No se envía template.")
                return False
        except Exception:
            pass  # si falla la DB, los filtros de arriba ya validaron

    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # Construir componentes del template
    components = []

    # Header con imagen (si se subió el mockup)
    if media_id:
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": media_id}}]
        })

    # Body con parámetros dinámicos
    components.append({
        "type": "body",
        "parameters": [
            {"type": "text", "text": nombre},
            {"type": "text", "text": busqueda},
        ]
    })

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": META_TEMPLATE_NAME,
            "language": {"code": META_TEMPLATE_LANG},
            "components": components,
        }
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)

    if resp.status_code == 200:
        msg_id = resp.json().get("messages", [{}])[0].get("id", "?")
        log.info(f"    ✅ Mensaje enviado a +{phone} (id: {msg_id})")
        # Registrar en DB para visibilidad en el panel de chat
        try:
            from core.db import add_message
            preview = f"[Template] {nombre} — {busqueda}"
            add_message(phone, "out", preview, "template", "sent",
                        nombre=nombre, busqueda=busqueda, categoria=categoria)
        except Exception:
            pass
        return True
    else:
        log.error(f"    ❌ Error enviando a +{phone}: {resp.status_code} — {resp.text}")
        code = _meta_error_code(resp)
        if code in _RECIPIENT_ERROR_CODES:
            try:
                from core.db import mark_send_failed
                mark_send_failed(phone)
                log.warning(f"    🛑 +{phone} marcado como send_failed — no se reintentará")
            except Exception:
                pass
        elif code in _API_ERROR_CODES or resp.status_code >= 500:
            log.warning(f"    ⚠️ Error de API Meta (#{code}) — lead NO marcado como fallido")
        return False


def send_whatsapp_text(phone: str, text: str, image_path: str | None = None) -> bool:
    """
    Envío alternativo SIN template: primero envía la imagen, luego el texto.
    Útil si el destinatario ya te escribió en las últimas 24h (ventana de conversación abierta).
    """
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # Enviar imagen primero (si existe)
    if image_path and os.path.exists(image_path):
        media_id = upload_media_to_meta(image_path)
        if media_id:
            img_payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "image",
                "image": {"id": media_id, "caption": "Así se vería su página web 👆"}
            }
            resp = requests.post(url, headers=headers, json=img_payload, timeout=30)
            if resp.status_code != 200:
                log.warning(f"    ⚠️  Error enviando imagen a +{phone}: {resp.text}")

    # Enviar texto
    txt_payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text}
    }
    resp = requests.post(url, headers=headers, json=txt_payload, timeout=30)

    if resp.status_code == 200:
        log.info(f"    ✅ Texto enviado a +{phone}")
        return True
    else:
        log.error(f"    ❌ Error enviando texto a +{phone}: {resp.status_code} — {resp.text}")
        return False


# ── Lockfile para evitar envío simultáneo desde dos procesos ──
_SEND_LOCKFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", ".send.lock")

def _acquire_send_lock() -> bool:
    """Intenta crear un lockfile. Retorna True si se obtuvo el lock."""
    import json as _json
    if os.path.exists(_SEND_LOCKFILE):
        try:
            info = _json.loads(open(_SEND_LOCKFILE).read())
            pid = info.get("pid", 0)
            # Verificar si el proceso sigue vivo
            try:
                os.kill(pid, 0)
                log.error(f"🛑 Otro proceso de envío ya está corriendo (PID {pid}). Abortando.")
                return False
            except OSError:
                log.warning(f"⚠️ Lock viejo de PID {pid} (ya muerto). Tomando el lock.")
        except Exception:
            pass
    os.makedirs(os.path.dirname(_SEND_LOCKFILE), exist_ok=True)
    with open(_SEND_LOCKFILE, "w") as f:
        _json.dump({"pid": os.getpid(), "started": now_colombia().isoformat()}, f)
    return True

def _release_send_lock():
    """Elimina el lockfile."""
    try:
        os.remove(_SEND_LOCKFILE)
    except OSError:
        pass


def enviar_mensajes_leads():
    """
    Lee el Excel de leads y envía mensajes a todos vía WhatsApp Cloud API.
    Usa templates (para mensajes en frío) o texto libre (si la ventana de 24h está abierta).
    """
    if not _acquire_send_lock():
        return
    try:
        _enviar_mensajes_leads_impl()
    finally:
        _release_send_lock()

def _enviar_mensajes_leads_impl():
    paused, reason = send_is_paused()
    if paused:
        log.warning(f"🛑 {reason}")
        return

    # Bloquear envío en fines de semana (sábado=5, domingo=6)
    if datetime.now().weekday() >= 5:
        log.warning("🛑 Hoy es fin de semana — no se envían mensajes para evitar baneo.")
        return

    if not META_PHONE_ID or not META_ACCESS_TOKEN:
        log.error("❌ Configura META_PHONE_ID y META_ACCESS_TOKEN antes de enviar.")
        log.error("   Puedes usar variables de entorno o editar flores.py directamente.")
        return

    all_leads, _ , _ = load_existing_leads(OUTPUT_FILE)
    if not all_leads:
        log.error("❌ No hay leads en el Excel. Ejecuta el scraper primero.")
        return

    from core.db import is_blacklisted, phone_has_chat, is_send_failed, is_reactivo

    # ── Saltar los primeros N leads (ya contactados) ──
    if SKIP_FIRST_LEADS:
        log.info(f"⏭️  Saltando los primeros {SKIP_FIRST_LEADS} leads (ya contactados)")
    leads = all_leads[SKIP_FIRST_LEADS:]

    # Filtrar: con teléfono, que NO hayan sido enviados, y número válido
    leads_to_send = []
    ya_enviados = 0
    bloqueados = 0
    telefono_invalido = 0
    ya_contactados = 0
    envio_fallido = 0
    reactivos = 0
    for lead in leads:
        nombre = lead.get("Nombre", "")
        phone = lead.get("WhatsApp Directo", "").replace("+", "")
        if not phone or not nombre:
            continue
        # Validar que el número colombiano sea móvil (3xx)
        phone_local = phone.removeprefix("57")
        if not phone_local.startswith("3"):
            telefono_invalido += 1
            continue
        if lead.get("Enviado"):
            ya_enviados += 1
            continue
        if is_blacklisted(phone):
            bloqueados += 1
            continue
        if is_reactivo(phone):
            reactivos += 1
            continue
        if phone_has_chat(phone):
            ya_contactados += 1
            continue
        if is_send_failed(phone):
            envio_fallido += 1
            continue
        leads_to_send.append(lead)

    if ya_contactados:
        log.info(f"⏭️  {ya_contactados} leads ya tienen chat en la DB, no se les envía de nuevo")
    if envio_fallido:
        log.info(f"⏭️  {envio_fallido} leads con envío fallido previo (sin WhatsApp), saltados")
    if reactivos:
        log.info(f"⏭️  {reactivos} leads en reactivos/contactar después, saltados")

    if not leads_to_send:
        if ya_enviados or bloqueados or telefono_invalido or ya_contactados or reactivos:
            log.info(f"✅ Nada que enviar. ({ya_enviados} ya enviados, {bloqueados} en lista negra, {reactivos} reactivos, {telefono_invalido} no móviles, {ya_contactados} ya contactados)")
        else:
            log.error("❌ No hay leads con teléfono para enviar.")
        return

    # ── Ordenar por prioridad ANTES de aplicar el tope diario ──
    # Esto garantiza que los leads seleccionados para enviar son los mismos
    # de mayor prioridad para los que se generaron los mockups.
    leads_to_send.sort(key=_lead_priority, reverse=True)

    # ── Aplicar tope diario ──
    hoy = datetime.now().strftime("%Y-%m-%d")
    enviados_hoy = sum(
        1 for l in all_leads
        if (l.get("Enviado") or "").startswith(hoy)
    )
    restantes_hoy = max(0, DAILY_SEND_LIMIT - enviados_hoy)
    if restantes_hoy == 0:
        log.info(f"🛑 Ya se enviaron {enviados_hoy} mensajes hoy (límite: {DAILY_SEND_LIMIT}). Vuelve mañana.")
        return
    if len(leads_to_send) > restantes_hoy:
        log.info(f"📊 Hay {len(leads_to_send)} pendientes pero el tope de hoy es {restantes_hoy} (ya enviados hoy: {enviados_hoy})")
        leads_to_send = leads_to_send[:restantes_hoy]

    # ── Filtrar solo los que tienen mockup (no enviar sin imagen) ──
    sin_mockup = 0
    leads_con_mockup = []
    for lead in leads_to_send:
        nombre = lead.get("Nombre", "")
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', nombre)[:60]
        jpg_path = os.path.join(MOCKUP_DIR, f"{safe_name}.jpg")
        if os.path.exists(jpg_path):
            leads_con_mockup.append(lead)
        else:
            sin_mockup += 1
    if sin_mockup:
        log.info(f"⏭️  {sin_mockup} leads sin mockup — no se les enviará (genera mockups primero)")
    leads_to_send = leads_con_mockup

    if not leads_to_send:
        log.info("❌ Ningún lead tiene mockup listo. Corre --mockups primero.")
        return

    top_nicho = leads_to_send[0].get("Búsqueda", "") if leads_to_send else ""
    log.info(f"🎯 Leads ordenados por prioridad de nicho. Primero: {top_nicho}")

    # Estimar tiempo total
    avg_delay = (META_SEND_DELAY_MIN + META_SEND_DELAY_MAX) / 2
    est_minutes = int((len(leads_to_send) * avg_delay) / 60)
    log.info("═══ ENVÍO MASIVO WhatsApp Cloud API ═══")
    log.info(f"  Enviar hoy: {len(leads_to_send)} mensajes (tope diario: {DAILY_SEND_LIMIT})")
    log.info(f"  Ya enviados hoy: {enviados_hoy}")
    log.info(f"  Sin mockup (no se envían): {sin_mockup}")
    log.info(f"  Template: {META_TEMPLATE_NAME} ({META_TEMPLATE_LANG})")
    log.info(f"  Delay entre mensajes: {META_SEND_DELAY_MIN}-{META_SEND_DELAY_MAX}s")
    log.info(f"  Tiempo estimado: ~{est_minutes} minutos")
    log.info("")

    enviados = 0
    fallidos = 0

    for i, lead in enumerate(leads_to_send, 1):
        nombre = lead.get("Nombre", "")
        busqueda = lead.get("Búsqueda", "")
        phone = lead.get("WhatsApp Directo", "").replace("+", "")

        # Buscar mockup correspondiente
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', nombre)[:60]
        jpg_path = os.path.join(MOCKUP_DIR, f"{safe_name}.jpg")

        log.info(f"[{i}/{len(leads_to_send)}] {nombre} — +{phone} 📷")

        # Verificar que el mockup aún existe (pudo borrarse entre filtro y envío)
        if not os.path.exists(jpg_path):
            log.warning(f"    ⚠️  Mockup no encontrado, saltando: {jpg_path}")
            fallidos += 1
            continue

        # Subir mockup a Meta
        media_id = upload_media_to_meta(jpg_path)
        if not media_id:
            log.warning(f"    ⚠️  No se pudo subir mockup — se reintentará mañana (sin marcar fallido)")
            fallidos += 1
            if i < len(leads_to_send):
                delay = random.uniform(META_SEND_DELAY_MIN, META_SEND_DELAY_MAX)
                log.info(f"    ⏳ Pausa {delay:.0f}s... (enviados: {enviados}/{len(leads_to_send)})")
                time.sleep(delay)
            continue

        # Enviar template con mockup
        ok = send_whatsapp_template(
            phone, nombre, busqueda, media_id, categoria=lead.get("Categoría", "")
        )
        if ok:
            enviados += 1
            lead["Enviado"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            safe_export(all_leads)  # guardar progreso después de cada envío exitoso
            # Borrar mockup después de enviar (no acumular basura)
            try:
                os.remove(jpg_path)
            except OSError:
                pass
        else:
            fallidos += 1

        # Pausa gradual entre mensajes
        if i < len(leads_to_send):
            delay = random.uniform(META_SEND_DELAY_MIN, META_SEND_DELAY_MAX)
            log.info(f"    ⏳ Pausa {delay:.0f}s... (enviados: {enviados}/{len(leads_to_send)})")
            time.sleep(delay)

    log.info(f"\n{'═' * 55}")
    log.info("  RESUMEN DE ENVÍO")
    log.info(f"{'═' * 55}")
    log.info(f"  Enviados: {enviados}")
    log.info(f"  Fallidos: {fallidos}")
    log.info(f"  Pendientes para mañana: {max(0, len(leads_to_send) - enviados)}")
    log.info(f"{'═' * 55}")

    # Alerta al dueño con resumen
    send_alert(
        f"📊 Envío terminado\n\n"
        f"✅ Enviados: {enviados}\n"
        f"❌ Fallidos: {fallidos}\n"
        f"⏳ Pendientes mañana: {max(0, len(leads_to_send) - enviados)}"
    )


def enviar_oleadas():
    """
    Envía mensajes de forma continua hasta completar la cuota diaria.
    Mantiene el mismo delay aleatorio entre mensajes.
    """
    if not _acquire_send_lock():
        return
    try:
        _enviar_oleadas_impl()
    finally:
        _release_send_lock()

def _enviar_oleadas_impl():
    paused, reason = send_is_paused()
    if paused:
        log.warning(f"🛑 {reason}")
        return

    if now_colombia().weekday() >= 5:
        log.warning("🛑 Hoy es fin de semana — no se envían mensajes.")
        return

    if not META_PHONE_ID or not META_ACCESS_TOKEN:
        log.error("❌ Configura META_PHONE_ID y META_ACCESS_TOKEN.")
        return

    hoy = now_colombia().strftime("%Y-%m-%d")
    total_enviados_hoy = 0
    total_fallidos = 0

    objetivo_diario = min(DAILY_SEND_LIMIT, sum(w.get('mensajes', 0) for w in SEND_WAVES))

    log.info("═══ MODO CONTINUO — Envío hasta completar ═══")
    log.info(f"  Objetivo diario: {objetivo_diario} mensajes")
    log.info(f"  Límite diario: {DAILY_SEND_LIMIT}")
    log.info("")

    leads_all, _, _ = load_existing_leads(OUTPUT_FILE)
    if not leads_all:
        log.error("❌ No hay leads en el Excel.")
        return

    from core.db import is_blacklisted as _is_bl, phone_has_chat as _has_chat, is_send_failed as _is_failed

    enviados_hoy_count = sum(
        1 for l in leads_all
        if (l.get("Enviado") or "").startswith(hoy)
    )
    restantes_global = max(0, objetivo_diario - enviados_hoy_count)

    if restantes_global == 0:
        log.info(f"🛑 Objetivo diario alcanzado ({objetivo_diario}). Terminando.")
        return

    leads_to_send = []
    for lead in leads_all[SKIP_FIRST_LEADS:]:
        nombre = lead.get("Nombre", "")
        phone = lead.get("WhatsApp Directo", "").replace("+", "")
        if not phone or not nombre:
            continue
        phone_local = phone.removeprefix("57")
        if not phone_local.startswith("3"):
            continue
        if lead.get("Enviado"):
            continue
        if _is_bl(phone):
            continue
        if _has_chat(phone):
            continue
        if _is_failed(phone):
            continue

        safe_name = re.sub(r'[\\/:*?"<>|]', '_', nombre)[:60]
        jpg_path = os.path.join(MOCKUP_DIR, f"{safe_name}.jpg")
        if not os.path.exists(jpg_path):
            continue
        leads_to_send.append(lead)

    if not leads_to_send:
        log.info("❌ No hay leads con mockup disponibles. Genera más mockups.")
        return

    batch_size = min(restantes_global, len(leads_to_send))
    batch = leads_to_send[:batch_size]

    log.info(f"  📊 Enviando {batch_size} mensajes continuos (disponibles: {len(leads_to_send)}, faltan hoy: {restantes_global})")

    for i, lead in enumerate(batch, 1):
        nombre = lead.get("Nombre", "")
        busqueda = lead.get("Búsqueda", "")
        phone = lead.get("WhatsApp Directo", "").replace("+", "")

        safe_name = re.sub(r'[\\/:*?"<>|]', '_', nombre)[:60]
        jpg_path = os.path.join(MOCKUP_DIR, f"{safe_name}.jpg")

        log.info(f"  [{i}/{batch_size}] {nombre} — +{phone} 📷")

        if not os.path.exists(jpg_path):
            log.warning(f"    ⚠️  Mockup no encontrado, saltando: {jpg_path}")
            total_fallidos += 1
            continue

        media_id = upload_media_to_meta(jpg_path)
        if not media_id:
            log.warning(f"    ⚠️  No se pudo subir mockup — se reintentará después (sin marcar fallido)")
            total_fallidos += 1
            if i < len(batch):
                delay = random.uniform(META_SEND_DELAY_MIN, META_SEND_DELAY_MAX)
                log.info(f"    ⏳ Pausa {delay:.0f}s... ({total_enviados_hoy}/{batch_size})")
                time.sleep(delay)
            continue

        ok = send_whatsapp_template(
            phone, nombre, busqueda, media_id, categoria=lead.get("Categoría", "")
        )

        if ok:
            total_enviados_hoy += 1
            lead["Enviado"] = now_colombia().strftime("%Y-%m-%d %H:%M")
            safe_export(leads_all)
            try:
                os.remove(jpg_path)
            except OSError:
                pass
        else:
            total_fallidos += 1

        if i < len(batch):
            delay = random.uniform(META_SEND_DELAY_MIN, META_SEND_DELAY_MAX)
            log.info(f"    ⏳ Pausa {delay:.0f}s... ({total_enviados_hoy}/{batch_size})")
            time.sleep(delay)

    log.info(f"  ✅ Envío continuo terminado: {total_enviados_hoy} enviados, {total_fallidos} fallidos")

    # Resumen final
    log.info(f"\n{'═' * 55}")
    log.info("  RESUMEN DEL DÍA (OLEADAS)")
    log.info(f"{'═' * 55}")
    log.info(f"  Total enviados hoy: {total_enviados_hoy}")
    log.info(f"  Total fallidos: {total_fallidos}")
    log.info(f"{'═' * 55}")

    send_alert(
        f"📊 Oleadas terminadas\n\n"
        f"✅ Enviados hoy: {total_enviados_hoy}\n"
        f"❌ Fallidos: {total_fallidos}"
    )


def limpiar_mockups_viejos(dias=7):
    """Elimina mockups huérfanos y de leads enviados hace más de X días."""
    leads, _, _ = load_existing_leads(OUTPUT_FILE)

    # Construir set de nombres que SÍ necesitan mockup (pendientes de envío)
    nombres_pendientes = set()
    if leads:
        for lead in leads:
            if lead.get("Enviado"):
                continue
            nombre = lead.get("Nombre", "")
            if nombre:
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', nombre)[:60]
                nombres_pendientes.add(f"{safe_name}.jpg")

    # Eliminar todos los mockups que no corresponden a un lead pendiente
    eliminados = 0
    if os.path.exists(MOCKUP_DIR):
        for fname in os.listdir(MOCKUP_DIR):
            if fname.endswith(".jpg") and fname not in nombres_pendientes:
                os.remove(os.path.join(MOCKUP_DIR, fname))
                eliminados += 1
    log.info(f"🗑️  Limpieza: {eliminados} mockups eliminados (ya enviados o huérfanos)")


def generate_missing_mockups(max_count=None):
    """
    Genera mockups solo para los próximos leads que se van a enviar.
    max_count: máximo de mockups a generar (default: 80, una oleada).
    """
    if max_count is None:
        max_count = 80  # una oleada — se vuelve a llamar entre ventanas para las siguientes
    leads, _, _ = load_existing_leads(OUTPUT_FILE)
    if not leads:
        log.warning("No hay leads en el Excel. Ejecuta el scraper primero.")
        return

    # ── Saltar los primeros N leads (ya contactados) ──
    if SKIP_FIRST_LEADS:
        log.info(f"⏭️  Saltando los primeros {SKIP_FIRST_LEADS} leads (ya contactados)")
    leads = leads[SKIP_FIRST_LEADS:]

    os.makedirs(MOCKUP_DIR, exist_ok=True)

    from core.db import is_blacklisted as _is_bl, phone_has_chat as _has_chat, is_send_failed as _is_failed

    # Detectar cuáles ya tienen mockup y tienen número móvil válido
    pending = []
    skipped_phone = 0
    skipped_sent = 0
    skipped_bl = 0
    skipped_chat = 0
    skipped_failed = 0
    for lead in leads:
        nombre = lead.get("Nombre", "")
        if not nombre:
            continue
        # Saltar ya enviados (marcados en Excel)
        if lead.get("Enviado"):
            skipped_sent += 1
            continue
        # Filtrar números no móviles
        phone = (lead.get("WhatsApp Directo") or "").replace("+", "")
        phone_local = phone.removeprefix("57")
        if phone and not phone_local.startswith("3"):
            skipped_phone += 1
            continue
        # Saltar blacklisted
        if phone and _is_bl(phone):
            skipped_bl += 1
            continue
        # Saltar si ya tienen conversación en DB (ya los contactamos o ellos nos escribieron)
        if phone and _has_chat(phone):
            skipped_chat += 1
            continue
        # Saltar si el envío anterior falló (número sin WhatsApp)
        if phone and _is_failed(phone):
            skipped_failed += 1
            continue
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', nombre)[:60]
        jpg_path = os.path.join(MOCKUP_DIR, f"{safe_name}.jpg")
        if not os.path.exists(jpg_path):
            pending.append(lead)
    if skipped_phone:
        log.info(f"⏭️  {skipped_phone} leads con número no móvil (no empiezan por 3), sin mockup")
    if skipped_sent:
        log.info(f"⏭️  {skipped_sent} leads ya enviados (Excel), sin regenerar mockup")
    if skipped_bl:
        log.info(f"⏭️  {skipped_bl} leads en lista negra, sin mockup")
    if skipped_chat:
        log.info(f"⏭️  {skipped_chat} leads con conversación previa en DB, sin mockup")
    if skipped_failed:
        log.info(f"⏭️  {skipped_failed} leads con envío fallido previo, sin mockup")

    if not pending:
        log.info("✅ Todos los leads ya tienen su mockup. Nada que hacer.")
        return

    # Ordenar por prioridad de nicho (igual que el envío) — premium primero
    pending.sort(key=_lead_priority, reverse=True)

    # Solo generar para el lote del día (no todos los pendientes)
    batch = pending[:max_count]
    top = batch[0].get("Búsqueda", "") if batch else ""
    log.info(f"🖼️  Generando mockups para {len(batch)} leads (de {len(pending)} pendientes, límite: {max_count}) — primero: {top}")

    _MOCKUP_BROWSER_ARGS = [
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--no-zygote",
        "--disable-extensions",
        "--disable-background-networking",
        "--mute-audio",
        "--js-flags=--max-old-space-size=192",
    ]
    RESTART_EVERY = 5  # reiniciar browser cada N mockups (servidor 2GB — agresivo)

    def _launch_mockup_browser(pw_inst):
        return pw_inst.chromium.launch(headless=True, args=_MOCKUP_BROWSER_ARGS)

    with sync_playwright() as pw:
        browser = _launch_mockup_browser(pw)
        try:
            for i, lead in enumerate(batch, 1):
                # Reiniciar browser proactivamente cada RESTART_EVERY leads
                if i > 1 and (i - 1) % RESTART_EVERY == 0:
                    log.info(f"  🔄 Reiniciando browser ({i-1}/{len(batch)})...")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    time.sleep(1)
                    browser = _launch_mockup_browser(pw)

                try:
                    result = generate_mockup(lead, browser)
                except Exception as e:
                    err_msg = str(e)
                    # Browser muerto (OOM killer u otro crash) — relanzar y reintentar
                    if "closed" in err_msg or "crashed" in err_msg or "disconnected" in err_msg:
                        log.warning(f"  ⚠️  Browser muerto en lead {i}, relanzando...")
                        try:
                            browser.close()
                        except Exception:
                            pass
                        time.sleep(2)
                        browser = _launch_mockup_browser(pw)
                        result = generate_mockup(lead, browser)
                    else:
                        result = None

                status = "OK" if result else "FALLÓ"
                log.info(f"  [{i}/{len(batch)}] {lead.get('Nombre', '?')} — {status}")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    log.info(f"✅ Mockups del día generados. Revisa la carpeta: {MOCKUP_DIR}")


# ──────────────────────────────────────────────────────────────────────
# NÚCLEO: SCROLL + EXTRACCIÓN DE TARJETAS
# ──────────────────────────────────────────────────────────────────────

def scroll_results(page, max_scrolls: int = MAX_SCROLLS):
    """Hace scroll en el panel lateral de resultados de Google Maps."""
    panel_selector = 'div[role="feed"]'
    try:
        page.wait_for_selector(panel_selector, timeout=8000)
    except PWTimeout:
        log.warning("No se encontró el panel de resultados (feed).")
        return

    previous_count = 0
    stale_rounds = 0

    for i in range(max_scrolls):
        page.evaluate(
            """(selector) => {
                const el = document.querySelector(selector);
                if (el) el.scrollTop = el.scrollHeight;
            }""",
            panel_selector,
        )
        human_delay(1.0, 2.5)

        # Detectar mensaje de "fin de resultados"
        end_text = page.query_selector('p.fontBodyMedium span:text("llegado al final")')
        if not end_text:
            end_text = page.query_selector('p.fontBodyMedium span:text("end of")')
        if end_text:
            log.info("  ✓ Se alcanzó el final de los resultados.")
            break

        current_count = page.locator('div[role="feed"] > div > div > a').count()
        if current_count == previous_count:
            stale_rounds += 1
            if stale_rounds >= 4:
                log.info("  ✓ No se cargan más resultados tras varios scrolls.")
                break
        else:
            stale_rounds = 0
        previous_count = current_count

    log.info(f"  Tarjetas visibles tras scroll: {previous_count}")


# ──────────────────────────────────────────────────────────────────────
# FLUJO PRINCIPAL DE BÚSQUEDA
# ──────────────────────────────────────────────────────────────────────

def collect_card_info(page) -> list[tuple[str, str]]:
    """Recoge (href, aria_label) de las tarjetas del feed para pre-filtrado."""
    links = page.locator('div[role="feed"] > div > div > a')
    count = links.count()
    results = []
    for i in range(count):
        try:
            href = links.nth(i).get_attribute("href", timeout=3000)
            aria = links.nth(i).get_attribute("aria-label", timeout=1000) or ""
            if href and "/maps/place/" in href:
                results.append((href, aria))
        except Exception:
            continue
    return results


def pre_filter_cards(cards: list[tuple[str, str]], seen_names: set[str]) -> list[str]:
    """Pre-filtra tarjetas por reseñas y duplicados usando info del aria-label."""
    filtered = []
    skipped_seen = 0
    skipped_reviews = 0
    top_reviews = 0

    for href, aria in cards:
        name = aria.split("·")[0].strip() if aria else ""
        if name and name.lower().strip() in seen_names:
            skipped_seen += 1
            continue

        reviews = 0
        reviews_match = re.search(r'\((\d[\d.]*)\)', aria)
        if reviews_match:
            reviews = int(reviews_match.group(1).replace(".", ""))
            if reviews < MIN_REVIEWS:
                skipped_reviews += 1
                continue
        top_reviews = max(top_reviews, reviews)

        filtered.append((reviews, href))

    if skipped_seen or skipped_reviews:
        log.info(f"  Pre-filtro: -{skipped_seen} duplicados, -{skipped_reviews} pocas reseñas → {len(filtered)} a visitar")

    # Los negocios con menos reseñas suelen ser más pequeños y tienen más probabilidad de no tener web.
    filtered.sort(key=lambda item: item[0])
    if top_reviews >= 50:
        log.info(f"  Priorizando negocios pequeños primero (reseñas bajas; máx: {top_reviews})")

    return [href for _, href in filtered]


def extract_lead_data(page) -> dict:
    """Extrae todos los datos de un negocio desde su página de detalle."""
    data = {
        "nombre": "",
        "categoria": "",
        "direccion": "",
        "telefono": "",
        "calificacion": None,
        "num_resenas": 0,
        "tiene_web": False,
        "instagram": "",
        "facebook": "",
    }

    try:
        name_el = page.query_selector("h1.DUwDvf")
        if name_el:
            data["nombre"] = name_el.inner_text().strip()
    except Exception:
        pass

    try:
        cat_el = page.query_selector('button[jsaction="pane.rating.category"]')
        if cat_el:
            data["categoria"] = cat_el.inner_text().strip()
    except Exception:
        pass

    try:
        rating_el = page.query_selector('div.F7nice')
        if rating_el:
            txt = rating_el.inner_text()
            r, n = parse_rating_reviews(txt)
            if r is not None:
                data["calificacion"] = r
            if n is not None:
                data["num_resenas"] = n
    except Exception:
        pass

    try:
        info_items = page.query_selector_all('[data-item-id]')
        for item in info_items:
            item_id = item.get_attribute("data-item-id") or ""
            aria = item.get_attribute("aria-label") or ""

            if item_id.startswith("address") or "dirección" in aria.lower() or "address" in aria.lower():
                data["direccion"] = aria.replace("Dirección: ", "").replace("Address: ", "").strip()

            if item_id.startswith("phone") or "teléfono" in aria.lower() or "phone" in aria.lower():
                data["telefono"] = aria.replace("Teléfono: ", "").replace("Phone: ", "").strip()

            # Solo contar como web si es un link real con href a un dominio externo
            if item_id.startswith("authority"):
                href = item.get_attribute("href") or ""
                # Verificar que sea un link <a> con URL real (no redes sociales)
                tag = item.evaluate("el => el.tagName.toLowerCase()")
                if tag == "a" and href:
                    href_lower = href.lower()
                    # Capturar redes sociales como dato útil
                    if "instagram.com" in href_lower:
                        data["instagram"] = href
                    elif "facebook.com" in href_lower:
                        data["facebook"] = href
                    # Ignorar redes sociales para determinar si tiene web propia
                    social_domains = [
                        "facebook.com", "instagram.com", "twitter.com", "x.com",
                        "tiktok.com", "youtube.com", "linkedin.com", "wa.me",
                        "whatsapp.com", "api.whatsapp.com",
                    ]
                    is_social = any(d in href_lower for d in social_domains)
                    if not is_social:
                        data["tiene_web"] = True
                        log.debug(f"      WEB detectada: {href[:60]}")
                else:
                    # Es un botón u otro elemento, no un link directo
                    pass
    except Exception:
        pass

    # Fallback: buscar link de sitio web por aria-label
    if not data["tiene_web"]:
        try:
            web_selectors = [
                'a[aria-label*="sitio web"]',
                'a[aria-label*="Sitio web"]',
                'a[aria-label*="website"]',
                'a[aria-label*="Website"]',
            ]
            for sel in web_selectors:
                el = page.query_selector(sel)
                if el:
                    href = el.get_attribute("href") or ""
                    social_domains = [
                        "facebook.com", "instagram.com", "twitter.com", "x.com",
                        "tiktok.com", "youtube.com", "linkedin.com", "wa.me",
                        "whatsapp.com",
                    ]
                    if href and not any(d in href.lower() for d in social_domains):
                        data["tiene_web"] = True
                        break
        except Exception:
            pass

    return data


def search_maps(context, main_page, query: str, all_leads: list[dict], seen_names: set[str], seen_phones: set[str]) -> int:
    """Busca en Google Maps con pre-filtrado y pestañas paralelas."""
    added = 0
    search_url = "https://www.google.com/maps/search/" + query.replace(" ", "+")
    log.info(f"🔍 Buscando: \"{query}\"")
    log.debug(f"    URL: {search_url}")
    if not goto_with_retry(main_page, search_url, retries=2, timeout=30000):
        log.error(f"    ⚠️  No se pudo cargar la búsqueda en Google Maps")
        return 0
    human_delay(1.0, 2.0)

    # Aceptar cookies si aparece el diálogo (varía por región)
    try:
        accept_btn = main_page.query_selector('button:text("Aceptar todo")')
        if not accept_btn:
            accept_btn = main_page.query_selector('button:text("Accept all")')
        if accept_btn:
            accept_btn.click()
            human_delay(0.5, 1.0)
    except Exception:
        pass

    scroll_results(main_page)

    # ── Fase 1: recoger info de tarjetas + pre-filtrar ──
    cards = collect_card_info(main_page)
    log.info(f"  Tarjetas encontradas: {len(cards)}")
    hrefs = pre_filter_cards(cards, seen_names)
    if len(hrefs) > MAX_CARDS:
        log.info(f"  Tarjetas tras filtro: {len(hrefs)} → recortando a {MAX_CARDS} (límite OOM)")
        hrefs = hrefs[:MAX_CARDS]
    log.info(f"  Tarjetas a visitar tras filtro: {len(hrefs)}")

    if not hrefs:
        return 0

    # ── Fase 2: visitar en lotes con múltiples pestañas ──
    num_tabs = min(PARALLEL_TABS, len(hrefs))
    tabs = []
    for _ in range(num_tabs):
        tab = context.new_page()
        tab.route("**/*", block_heavy_resources)
        tabs.append(tab)

    total = len(hrefs)
    consecutive_web = 0
    skip_web = 0
    skip_reviews = 0
    skip_phone = 0
    skip_tel_fijo = 0
    skip_categoria = 0
    visited = 0
    early_exit = False

    for batch_start in range(0, total, num_tabs):
        if early_exit:
            break
        batch = hrefs[batch_start:batch_start + num_tabs]

        # Navegar todas las pestañas del lote
        loaded = []
        for i, href in enumerate(batch):
            progress = batch_start + i + 1
            log.info(f"    [{progress}/{total}] Visitando...")
            if goto_with_retry(tabs[i], href, retries=1, timeout=15000):
                loaded.append(i)

        # Pausa breve para renderizado
        human_delay(2.0, 4.0)

        # Extraer datos de las pestañas cargadas
        for i in loaded:
            try:
                tabs[i].set_default_timeout(12000)
                data = extract_lead_data(tabs[i])
            except Exception as e:
                log.warning(f"    ⏭️ Timeout/error extrayendo tarjeta: {e}")
                visited += 1
                continue
            visited += 1

            name_short = (data['nombre'] or '?')[:35]
            if data["tiene_web"]:
                skip_web += 1
                consecutive_web += 1
                # ── Early stop adaptativo (Bayesiano) ──
                # P(sin web) = (negocios sin web + 1) / (visitados + 2)
                # Parar cuando la probabilidad de encontrar otro sin web es muy baja
                if consecutive_web >= 5:
                    p_no_web = (visited - skip_web + 1) / (visited + 2)
                    if p_no_web < 0.10 or consecutive_web >= WEB_SKIP_LIMIT:
                        log.info(f"    ⏭️  Early stop: P(sin web)={p_no_web:.0%} — {consecutive_web} consecutivos con web")
                        early_exit = True
                        break
                continue
            else:
                consecutive_web = max(0, consecutive_web - 2)  # Reducir gradualmente en vez de resetear a 0

            # ── Filtro de categoría (negocios que no necesitan web) ──
            cat_lower = (data.get("categoria") or "").lower()
            if any(excl in cat_lower for excl in CATEGORIAS_EXCLUIDAS):
                skip_categoria += 1
                continue

            if data["num_resenas"] < MIN_REVIEWS:
                skip_reviews += 1
                continue
            if not data["telefono"]:
                skip_phone += 1
                continue

            phone_clean = clean_phone(data["telefono"])

            # ── Filtro de celular colombiano (solo 3xx tienen WhatsApp) ──
            if not phone_clean.startswith("3") or len(phone_clean) != 10:
                skip_tel_fijo += 1
                continue
            wa_link = build_whatsapp_link(phone_clean, data["nombre"], query)

            lead = {
                "Nombre": data["nombre"],
                "Categoría": data["categoria"],
                "Dirección": data["direccion"],
                "Teléfono": data["telefono"],
                "Calificación": data["calificacion"],
                "Reseñas": data["num_resenas"],
                "WhatsApp Directo": f"+{COUNTRY_PREFIX}{phone_clean}" if phone_clean else "",
                "Link WhatsApp": wa_link,
                "Instagram": data.get("instagram", ""),
                "Facebook": data.get("facebook", ""),
                "Búsqueda": query,
            }
            key = lead["Nombre"].lower().strip()
            phone_key = lead["WhatsApp Directo"].replace("+", "")
            if key and key not in seen_names and (not phone_key or phone_key not in seen_phones):
                seen_names.add(key)
                if phone_key:
                    seen_phones.add(phone_key)
                all_leads.append(lead)
                added += 1
                log.info(f"    ✅ Lead #{len(all_leads)}: {lead['Nombre']} — {lead['Reseñas']} reseñas")

                # Guardar cada lead para no perderlo si Playwright se cae a mitad de búsqueda.
                safe_export(all_leads)
                log.info(f"    💾 Lead guardado ({len(all_leads)} leads)")

    # Resumen de descarte para esta búsqueda
    log.info(f"  📊 Visitados: {visited} | Con web: {skip_web} | Tel fijo: {skip_tel_fijo} | Categoría excl: {skip_categoria} | Pocas reseñas: {skip_reviews} | Sin tel: {skip_phone} | Nuevos: {added}")

    # Cerrar pestañas auxiliares
    for tab in tabs:
        try:
            tab.close()
        except Exception:
            pass

    return added


# ──────────────────────────────────────────────────────────────────────
# EXPORTAR A EXCEL
# ──────────────────────────────────────────────────────────────────────

COLUMNS = [
    "Nombre",
    "Categoría",
    "Dirección",
    "Teléfono",
    "Calificación",
    "Reseñas",
    "WhatsApp Directo",
    "Link WhatsApp",
    "Instagram",
    "Facebook",
    "Búsqueda",
    "Enviado",
]


def _lead_es_valido(lead: dict) -> bool:
    """Última línea de defensa: valida que un lead tenga celular colombiano y categoría aceptable."""
    phone = (lead.get("WhatsApp Directo") or "").replace("+", "")
    if phone:
        local = phone.removeprefix("57")
        if not local.startswith("3") or len(local) != 10:
            return False
    cat_lower = (lead.get("Categoría") or "").lower()
    if any(excl in cat_lower for excl in CATEGORIAS_EXCLUIDAS):
        return False
    return True


_EXCEL_WRITE_LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", ".excel_write.lock")


def _excel_path(filename: str) -> str:
    return filename if os.path.isabs(filename) else os.path.join(BASE_DIR, filename)


def export_to_excel(all_leads: list[dict], filename: str = OUTPUT_FILE):
    """Crea un archivo Excel formateado con todos los leads."""
    filename = _excel_path(filename)
    # Backup automático antes de sobreescribir
    if os.path.exists(filename):
        import shutil
        backup_name = f"{os.path.splitext(filename)[0]}_backup.xlsx"
        try:
            shutil.copy2(filename, backup_name)
        except Exception:
            pass

    # Filtro de seguridad antes de escribir
    leads_limpios = [l for l in all_leads if _lead_es_valido(l)]
    descartados = len(all_leads) - len(leads_limpios)
    if descartados:
        log.info(f"🛡️ Filtro de calidad: {descartados} leads descartados antes de guardar Excel")

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads SIO"

    # Encabezados
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="2E86C1", end_color="2E86C1", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    for col_idx, col_name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # Datos
    for row_idx, lead in enumerate(leads_limpios, start=2):
        for col_idx, col_name in enumerate(COLUMNS, start=1):
            value = lead.get(col_name, "")
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = thin_border

            # Hacer el link de WhatsApp clicable
            if col_name == "Link WhatsApp" and value:
                cell.hyperlink = value
                cell.font = Font(color="1155CC", underline="single")

    # Auto-ajustar anchos
    for col_idx, col_name in enumerate(COLUMNS, start=1):
        max_len = len(col_name)
        for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 4, 50)

    # Filtros automáticos
    ws.auto_filter.ref = ws.dimensions

    # Escritura atómica con lock + tmp único (evita colisión scraper + envío)
    os.makedirs(os.path.dirname(_EXCEL_WRITE_LOCK), exist_ok=True)
    with open(_EXCEL_WRITE_LOCK, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        tmp = f"{filename}.{os.getpid()}.{time.time_ns()}.tmp"
        try:
            wb.save(tmp)
            if not os.path.exists(tmp):
                raise OSError(f"No se creó el archivo temporal: {tmp}")
            os.replace(tmp, filename)
            log.info(f"📁 Archivo guardado: {filename}")
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


def safe_export(all_leads: list[dict], filename: str = OUTPUT_FILE):
    """Exporta a Excel con manejo de archivo bloqueado."""
    for attempt in range(3):
        try:
            export_to_excel(all_leads, filename)
            return
        except PermissionError:
            base, ext = os.path.splitext(_excel_path(filename))
            alt_name = f"{base}_{datetime.now().strftime('%H%M%S')}{ext}"
            log.warning(f"⚠️  '{filename}' está abierto. Guardando como '{alt_name}'")
            export_to_excel(all_leads, alt_name)
            return
        except OSError as e:
            if attempt < 2:
                log.warning(f"⚠️ Reintentando guardar Excel ({attempt + 1}/3): {e}")
                time.sleep(1)
            else:
                raise


# ──────────────────────────────────────────────────────────────────────
# RESUMEN
# ──────────────────────────────────────────────────────────────────────

def print_summary(all_leads: list[dict], initial_count: int, start_time: float):
    """Muestra resumen desglosado por keyword al finalizar."""
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    new_leads = len(all_leads) - initial_count

    log.info(f"\n{'═' * 55}")
    log.info(f"  RESUMEN DE PROSPECCIÓN")
    log.info(f"{'═' * 55}")
    log.info(f"  Tiempo total: {minutes}m {seconds}s")
    log.info(f"  Leads previos (del Excel): {initial_count}")
    log.info(f"  Leads nuevos esta sesión: {new_leads}")
    log.info(f"  Total en archivo: {len(all_leads)}")

    if all_leads:
        log.info(f"\n  Desglose por categoría de búsqueda:")
        keyword_counts = Counter()
        for lead in all_leads:
            search = lead.get("Búsqueda", "") or ""
            for kw in KEYWORDS:
                if kw.lower() in search.lower():
                    keyword_counts[kw] += 1
                    break
            else:
                keyword_counts["Otro"] += 1

        for kw, count in keyword_counts.most_common():
            log.info(f"    {kw}: {count}")

    log.info(f"{'═' * 55}")


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────

def main():
    start_time = time.time()

    # ── Modo incremental: cargar leads existentes ──
    all_leads, seen_names, seen_phones = load_existing_leads(OUTPUT_FILE)
    initial_count = len(all_leads)

    # Generar todas las combinaciones keyword + zona
    all_queries = []
    for kw in KEYWORDS:
        for zone in ZONES:
            all_queries.append(f"{kw} {zone}")

    # Agregar variantes de búsqueda con términos alternativos
    KEYWORD_VARIANTS = {
        "Cirugía Plástica": ["cirujano plástico", "cirugía estética", "clínica estética"],
        "Dermatología": ["dermatólogo", "clínica dermatológica", "centro dermatológico"],
        "Ortodoncia y Diseño de Sonrisa": ["ortodoncista", "consultorio odontológico", "odontología estética"],
        "Veterinarias": ["veterinario", "clínica veterinaria", "hospital veterinario"],
        "Abogados": ["abogado", "oficina de abogados", "consultorio jurídico"],
    }
    variant_queries = []
    for kw in KEYWORDS:
        if kw in KEYWORD_VARIANTS:
            for variant in KEYWORD_VARIANTS[kw]:
                for zone in ZONES:
                    variant_queries.append(f"{variant} {zone}")
    all_queries.extend(variant_queries)

    # Saltar búsquedas ya intentadas (queries_done.txt) o que ya tienen leads en el Excel
    done_queries = load_done_queries()  # carga queries_done.txt (todas las intentadas)
    for lead in all_leads:
        q = (lead.get("Búsqueda") or "").strip()
        if q:
            done_queries.add(q.lower())

    queries = [q for q in all_queries if q.lower() not in done_queries]
    skipped = len(all_queries) - len(queries)

    log.info(f"═══ SIO Prospección Tool ═══")
    log.info(f"Combinaciones totales: {len(all_queries)}")
    if skipped:
        log.info(f"Saltando {skipped} búsquedas ya realizadas (queries_done.txt + Excel)")
    log.info(f"Búsquedas pendientes: {len(queries)}")
    log.info(f"Filtro: sin web, ≥{MIN_REVIEWS} reseñas, con teléfono")
    if initial_count:
        log.info(f"Modo incremental: {initial_count} leads previos cargados")
    log.info("")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--lang=es-CO",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--single-process",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-component-extensions-with-background-pages",
            "--disable-extensions",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
            "--disable-renderer-backgrounding",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--mute-audio",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="es-CO",
        timezone_id="America/Bogota",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    main_page = context.new_page()
    main_page.route("**/*", block_heavy_resources)

    try:
        for q_idx, query in enumerate(queries, start=1):
            # ── Parar a las 9AM Colombia (solo entre semana) para no competir con el envío masivo ──
            _now_col = now_colombia()
            if _now_col.weekday() < 5 and 9 <= _now_col.hour < 18:
                log.info(f"⏰ Son las {_now_col.strftime('%H:%M')} Colombia (entre semana) — deteniendo scraper, comienza el envío masivo")
                break

            log.info(f"\n[{q_idx}/{len(queries)}] ──────────────────────────")
            mark_query_done(query)
            try:
                new_count = search_maps(context, main_page, query, all_leads, seen_names, seen_phones)
                log.info(f"  Leads nuevos en esta búsqueda: {new_count}")
                log.info(f"  Total acumulado (únicos): {len(all_leads)}")

            except Exception as e:
                log.error(f"  Error en búsqueda \"{query}\": {e}")

            # Pausa entre búsquedas
            if q_idx < len(queries):
                wait = random.uniform(5.0, 12.0)
                log.info(f"  ⏳ Pausa de {wait:.1f}s antes de la siguiente búsqueda...")
                time.sleep(wait)

                # Reiniciar browser cada 5 búsquedas para liberar memoria
                if q_idx % 5 == 0:
                    log.info(f"  🔄 Reiniciando browser para liberar memoria...")
                    try:
                        context.close()
                        browser.close()
                        browser = pw.chromium.launch(
                            headless=True,
                            args=[
                                "--disable-blink-features=AutomationControlled",
                                "--lang=es-CO",
                                "--disable-gpu",
                                "--disable-software-rasterizer",
                                "--disable-dev-shm-usage",
                                "--no-sandbox",
                                "--disable-setuid-sandbox",
                                "--disable-accelerated-2d-canvas",
                                "--no-first-run",
                                "--no-zygote",
                                "--single-process",
                                "--disable-background-networking",
                                "--disable-extensions",
                                "--mute-audio",
                            ],
                        )
                        context = browser.new_context(
                            viewport={"width": 1280, "height": 900},
                            locale="es-CO",
                            timezone_id="America/Bogota",
                            user_agent=(
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0.0.0 Safari/537.36"
                            ),
                        )
                        main_page = context.new_page()
                        main_page.route("**/*", block_heavy_resources)
                        log.info(f"  ✅ Browser reiniciado")
                    except Exception as e:
                        log.warning(f"  ⚠️ Error reiniciando browser: {e}")

                # Pausa larga aleatoria cada ~20 queries (simula humano)
                if q_idx % 20 == 0:
                    coffee = random.uniform(60, 180)
                    log.info(f"  ☕ Pausa anti-ban de {coffee:.0f}s...")
                    time.sleep(coffee)
    except KeyboardInterrupt:
        log.warning("\n⚠️  Interrumpido por el usuario. Exportando lo recopilado...")
    except Exception as e:
        log.error(f"Error inesperado: {e}")
    finally:
        # ── Cleanup: cerrar browser y Playwright SIEMPRE ──
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

    # ── Exportar INMEDIATAMENTE ──
    if all_leads:
        safe_export(all_leads)
        log.info(f"✅ Archivo listo: {OUTPUT_FILE}")
    else:
        log.warning("No se encontraron leads con los filtros aplicados.")

    print_summary(all_leads, initial_count, start_time)


def test_api():
    """
    Prueba rápida: verifica credenciales y envía un mensaje de texto
    al número de origen (+57 321 3632474) para confirmar que la API funciona.
    """
    if not META_PHONE_ID or not META_ACCESS_TOKEN:
        log.error("❌ Faltan META_PHONE_ID o META_ACCESS_TOKEN.")
        return

    log.info("═══ TEST API WhatsApp Cloud ═══")
    log.info(f"  Phone Number ID : {META_PHONE_ID}")
    log.info(f"  Token (inicio)  : {META_ACCESS_TOKEN[:20]}...")

    # Verificar token consultando el perfil del número
    verify_url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_ID}"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    resp = requests.get(verify_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        log.error(f"❌ Token inválido o Phone ID incorrecto: {resp.status_code} — {resp.text}")
        return
    info = resp.json()
    log.info(f"  ✅ Número verificado: {info.get('display_phone_number', '?')} — {info.get('verified_name', '?')}")

    # Enviar template hello_world al propio número de origen
    test_phone = "573213632474"  # número propio sin +
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": test_phone,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"},
        }
    }
    resp = requests.post(url, headers={**headers, "Content-Type": "application/json"},
                         json=payload, timeout=15)
    if resp.status_code == 200:
        msg_id = resp.json().get("messages", [{}])[0].get("id", "?")
        log.info(f"  ✅ Mensaje de prueba enviado a +{test_phone} (id: {msg_id})")
        log.info("  Revisa tu WhatsApp para confirmar que llegó.")
    else:
        log.error(f"  ❌ Error enviando mensaje: {resp.status_code} — {resp.text}")

    log.info("═══════════════════════════════")


def check_templates():
    """
    Consulta la API de Meta y muestra el estado de aprobación
    de todos los templates de la cuenta (resalta prospeccion_clientes).
    """
    if not META_PHONE_ID or not META_ACCESS_TOKEN:
        log.error("❌ Faltan META_PHONE_ID o META_ACCESS_TOKEN.")
        return

    # Obtener el WABA ID a partir del Phone Number ID
    phone_url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_ID}"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    resp = requests.get(phone_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        log.error(f"❌ No se pudo verificar el número: {resp.status_code} — {resp.text}")
        return

    waba_id = resp.json().get("whatsapp_business_account_id") or "2446942002405721"
    log.info(f"═══ ESTADO DE TEMPLATES — WABA: {waba_id} ═══")

    templates_url = f"https://graph.facebook.com/{META_API_VERSION}/{waba_id}/message_templates"
    resp = requests.get(templates_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        log.error(f"❌ Error consultando templates: {resp.status_code} — {resp.text}")
        return

    templates = resp.json().get("data", [])
    if not templates:
        log.warning("  No se encontraron templates en esta cuenta.")
        return

    STATUS_ICON = {
        "APPROVED": "✅",
        "PENDING":  "⏳",
        "REJECTED": "❌",
        "PAUSED":   "⏸️",
        "DISABLED": "🚫",
    }

    for t in templates:
        name   = t.get("name", "?")
        status = t.get("status", "?").upper()
        lang   = t.get("language", "?")
        icon   = STATUS_ICON.get(status, "❓")
        marker = " ◄ ESTE" if name == META_TEMPLATE_NAME else ""
        log.info(f"  {icon} [{status}] {name} ({lang}){marker}")

    log.info("═" * 55)

    # Buscar específicamente el template objetivo
    target = next((t for t in templates if t.get("name") == META_TEMPLATE_NAME), None)
    if target:
        status = target.get("status", "?").upper()
        if status == "APPROVED":
            log.info(f"✅ '{META_TEMPLATE_NAME}' está APROBADO. Ya puedes correr --enviar")
        elif status == "PENDING":
            log.info(f"⏳ '{META_TEMPLATE_NAME}' está PENDIENTE de aprobación. Vuelve a revisar en unos minutos.")
        else:
            log.warning(f"⚠️  '{META_TEMPLATE_NAME}' tiene estado: {status}")
    else:
        log.warning(f"⚠️  No se encontró el template '{META_TEMPLATE_NAME}' — ¿lo creaste en el panel?")


# ──────────────────────────────────────────────────────────────────────
# MODO AUTO — Scraper continuo + oleadas automáticas
# ──────────────────────────────────────────────────────────────────────

def auto_mode():
    """
    Modo automático que corre 24/7:
    - Fines de semana: scraper 24h sin parar
    - Entre semana: scraper de madrugada/mañana, mockups, oleadas de envío
    - Se repite cada día automáticamente
    """
    log.info("═══ SIO MODO AUTOMÁTICO ═══")
    log.info("  El sistema correrá de forma continua:")
    log.info("  📅 Lunes–Viernes: scraper mañana + mockups + oleadas")
    log.info("  📅 Sábado–Domingo: scraper 24h (sin envíos)")
    log.info("  Ctrl+C para detener")
    log.info("")

    _last_cleanup_day = None  # rastrear para ejecutar solo 1 vez al día
    _last_mockup_day   = None  # rastrear para generar mockups solo 1 vez al día

    while True:
        now = now_colombia()
        dia_semana = now.weekday()  # 0=lunes, 6=domingo
        hora = now.hour

        try:
            # ── Limpieza diaria a las 3 AM ──
            today = now.date()
            if hora == 3 and _last_cleanup_day != today:
                _last_cleanup_day = today
                log.info("🧹 Ejecutando limpieza diaria de archivos...")
                try:
                    import cleanup
                    cleanup.main()
                except Exception as e:
                    log.error(f"Error en limpieza: {e}")

            if dia_semana >= 5:
                # ═══ FIN DE SEMANA: scraper 24h ═══
                log.info(f"🗓️  {'Sábado' if dia_semana == 5 else 'Domingo'} — modo scraper continuo")
                _auto_scrape_cycle()
                # Pequeña pausa entre ciclos para no saturar
                pause = random.uniform(30, 60)
                log.info(f"  💤 Pausa {pause:.0f}s antes del siguiente ciclo de scraping...")
                time.sleep(pause)

            else:
                # ═══ ENTRE SEMANA: SOLO oleadas, sin scraper ═══

                if hora < 9:
                    # ── Mockups: generar solo en madrugada/mañana (una sola vez por día) ──
                    if _last_mockup_day != today:
                        _last_mockup_day = today
                        log.info(f"🎨 Generando mockups del día ({now.strftime('%H:%M')}) — generando los 240 antes de las 9AM")
                        try:
                            generate_missing_mockups(max_count=240)
                        except Exception as e:
                            log.error(f"Error generando mockups: {e}")

                    # Madrugada/mañana (00:00–08:59): esperar hasta las 9
                    mins_faltan = (9 - hora) * 60 - now.minute
                    log.info(f"🌙 Esperando primera oleada ({now.strftime('%H:%M')}) — faltan {mins_faltan} min para las 9AM")
                    time.sleep(300)  # dormir 5 min y revisar de nuevo

                elif 9 <= hora < 12:
                    # 9:00–11:59: enviar continuo hasta completar el objetivo diario
                    log.info(f"📨 Modo envío activo ({now.strftime('%H:%M')}) — enviando hasta completar")
                    try:
                        enviar_oleadas()
                    except Exception as e:
                        log.error(f"Error en envío continuo: {e}")
                        send_alert(f"❌ Error en envío continuo:\n{type(e).__name__}: {e}")
                        time.sleep(60)

                elif hora >= 12:
                    # 12:00–23:59: descanso (no scrapear entre semana)
                    log.info(f"🌙 Tarde/noche ({now.strftime('%H:%M')}) — en espera hasta mañana (sin scraper entre semana)")
                    time.sleep(300)

        except KeyboardInterrupt:
            log.info("\n⚠️  Modo automático detenido por el usuario.")
            break
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            log.error(f"Error en modo auto: {error_msg}")
            send_alert(f"❌ Error modo auto:\n{error_msg}")
            log.info("  Reintentando en 60s...")
            time.sleep(60)


def _sleep_until_hour(target_hour: int):
    """Duerme hasta la hora indicada del día actual (hora Colombia)."""
    now = now_colombia()
    target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if target <= now:
        return
    delta = (target - now).total_seconds()
    if delta > 0:
        log.info(f"  ⏰ Esperando hasta las {target_hour}:00 ({int(delta // 60)} min)")
        time.sleep(delta)


def _check_memory_ok(min_free_mb: int = 700) -> bool:
    """Retorna True si hay suficiente RAM libre para correr el scraper."""
    try:
        with open('/proc/meminfo') as f:
            lines = f.readlines()
        mem_available = 0
        for line in lines:
            if 'MemAvailable' in line:
                mem_available = int(line.split()[1]) // 1024  # KB → MB
                break
        if mem_available < min_free_mb:
            log.warning(f"⚠️  Memoria disponible: {mem_available}MB < {min_free_mb}MB mínimo — saltando ciclo de scraping")
            return False
        log.info(f"  💾 Memoria disponible: {mem_available}MB — OK")
        return True
    except Exception:
        return True  # si no se puede leer, continuar


def _auto_scrape_cycle(stop_hour: int = None):
    """
    Ejecuta UN ciclo de scraping con selección inteligente de queries.
    Usa Thompson Sampling para priorizar keywords productivos,
    delays log-normal para simular humano, y Poisson coffee breaks.
    Si stop_hour se indica, corta el ciclo al llegar esa hora (Colombia).
    """
    paused, reason = scraper_is_paused()
    if paused:
        log.warning(f"🛑 {reason}")
        return

    # Chequeo de memoria antes de iniciar
    if not _check_memory_ok(min_free_mb=700):
        time.sleep(300)  # esperar 5 minutos y dejar que el sistema libere memoria
        return

    all_leads, seen_names, seen_phones = load_existing_leads(OUTPUT_FILE)
    initial_count = len(all_leads)

    # Protección: si el Excel existe pero no se pudo cargar, NO sobreescribir
    if initial_count == 0 and os.path.exists(OUTPUT_FILE):
        log.error("⚠️  El Excel existe pero se cargaron 0 leads — posible corrupción. Abortando ciclo.")
        return

    # Variantes de keywords para multiplicar cobertura
    KEYWORD_VARIANTS = {
        "Cirugía Plástica": ["cirujano plástico", "cirugía estética", "clínica estética"],
        "Dermatología": ["dermatólogo", "clínica dermatológica", "centro dermatológico"],
        "Ortodoncia y Diseño de Sonrisa": ["ortodoncista", "odontología estética"],
        "Veterinarias": ["veterinario", "clínica veterinaria", "hospital veterinario"],
        "Abogados": ["abogado", "oficina de abogados", "bufete de abogados"],
        "Arquitectos": ["firma de arquitectos", "estudio de arquitectura", "arquitecto independiente"],
        "Consultorios odontológicos": ["dentista", "odontólogo"],
        "Restaurantes": ["restaurante bar", "trattoria", "comedor"],
        "Gimnasios": ["gimnasio CrossFit", "centro de entrenamiento"],
        "Peluquerías": ["peluquería unisex", "salón de corte"],
        "Talleres mecánicos": ["taller automotriz", "mecánico"],
        "Inmobiliarias": ["agencia inmobiliaria", "bienes raíces"],
        "Contadores": ["contador público", "firma de contabilidad", "oficina contable"],
        "Consultoría empresarial": ["consultor empresarial", "consultoría de negocios", "firma consultora"],
        "Asesoría financiera": ["asesor financiero", "planeación financiera", "consultor financiero"],
        "Revisoría fiscal": ["revisor fiscal", "firma de revisoría fiscal", "auditoría contable"],
        "Constructoras": ["empresa constructora", "constructora de vivienda"],
        "Aseguradoras": ["asesor de seguros", "agencia de seguros", "broker de seguros"],
        "Corredores de seguros": ["corredor de seguros", "broker de seguros", "intermediario de seguros"],
        "Spa": ["spa y relajación", "centro de bienestar"],
        "Psicólogos": ["psicólogo clínico", "terapia psicológica"],
        "Nutricionistas": ["nutriólogo", "consulta nutricional"],
        "Fisioterapia": ["centro de fisioterapia", "fisioterapeuta"],
        "Ópticas": ["optometría", "tienda de lentes"],
        "Laboratorios clínicos": ["laboratorio médico", "laboratorio de análisis"],
        "Carpintería": ["carpintero", "taller de carpintería"],
        "Electricistas": ["electricista certificado", "instalaciones eléctricas"],
        "Plomeros": ["plomero", "fontanería"],
        "Cerrajería": ["cerrajero 24 horas", "cerrajero"],
        "Reparación de celulares": ["arreglo de celulares", "servicio técnico celulares"],
        "Cámaras de seguridad": ["CCTV", "videovigilancia"],
        "Panadería": ["panadería artesanal", "panadería y repostería"],
        "Cafetería": ["café especialidad", "coffee shop"],
        "Autolavado": ["lavadero de carros", "car wash"],
        "Floristería": ["florería", "arreglos florales"],
        "Estudio fotográfico": ["fotógrafo profesional", "fotografía de estudio"],
    }

    # Filtrar queries ya hechas (desde archivo + desde leads)
    done_queries = load_done_queries()
    for lead in all_leads:
        q = (lead.get("Búsqueda") or "").strip()
        if q:
            done_queries.add(q.lower())

    # ── Construir mapa keyword → queries pendientes ──
    # Cada keyword base agrupa sus variantes para Thompson Sampling
    keyword_zones = {}  # {base_kw: [query_string, ...]}
    total_queries = 0
    for kw in KEYWORDS:
        variants = [kw] + KEYWORD_VARIANTS.get(kw, [])
        for v in variants:
            for zone in ZONES:
                total_queries += 1
                q = f"{v} {zone}"
                if q.lower() not in done_queries:
                    keyword_zones.setdefault(kw, []).append(q)

    # Eliminar keywords sin queries pendientes
    keyword_zones = {k: v for k, v in keyword_zones.items() if v}
    total_pending = sum(len(v) for v in keyword_zones.values())

    if total_pending == 0:
        log.info(f"🔄 CICLO COMPLETO — Todas las {total_queries} queries fueron buscadas.")
        log.info(f"  Total leads acumulados: {len(all_leads)}")
        log.info(f"  Reiniciando búsqueda (re-scrape): nuevos negocios aparecen constantemente.")
        if os.path.exists(QUERIES_DONE):
            os.remove(QUERIES_DONE)
        # Reset Thompson stats para re-explorar (mantener priors ligeros)
        kw_stats = load_keyword_stats()
        for kw in kw_stats:
            # Decay: reducir confianza para re-explorar en el nuevo ciclo
            kw_stats[kw][0] = max(1, kw_stats[kw][0] // 2)
            kw_stats[kw][1] = max(1, kw_stats[kw][1] // 2)
        save_keyword_stats(kw_stats)
        # Reconstruir keyword_zones con todas las queries
        done_queries = set()
        keyword_zones = {}
        for kw in KEYWORDS:
            variants = [kw] + KEYWORD_VARIANTS.get(kw, [])
            for v in variants:
                for zone in ZONES:
                    q = f"{v} {zone}"
                    keyword_zones.setdefault(kw, []).append(q)
        keyword_zones = {k: v for k, v in keyword_zones.items() if v}
        total_pending = sum(len(v) for v in keyword_zones.values())

    # ── Thompson Sampling: construir batch inteligente ──
    kw_stats = load_keyword_stats()
    # Inicializar stats para keywords nuevos y reforzar nichos premium.
    for kw in KEYWORDS:
        apply_keyword_prior(kw_stats, kw)

    batch_size = min(20, total_pending)  # MAX 20 queries por ciclo para evitar OOM
    premium_target = max(1, round(batch_size * PREMIUM_BATCH_SHARE)) if batch_size else 0
    batch = []  # lista de (base_keyword, query_string)
    for _ in range(batch_size):
        available = [k for k in keyword_zones if keyword_zones[k]]
        if not available:
            break
        premium_selected = sum(1 for kw, _ in batch if kw in HIGH_VALUE_KEYWORD_MULTIPLIER)
        premium_available = [k for k in available if k in HIGH_VALUE_KEYWORD_MULTIPLIER]
        selection_pool = premium_available if premium_selected < premium_target and premium_available else available
        # Thompson Sampling elige el keyword más prometedor
        base_kw = thompson_select_keyword(selection_pool, kw_stats)
        # Elegir una query aleatoria de ese keyword
        query = random.choice(keyword_zones[base_kw])
        keyword_zones[base_kw].remove(query)
        if not keyword_zones[base_kw]:
            del keyword_zones[base_kw]
        batch.append((base_kw, query))

    # Mostrar top-5 keywords seleccionados para este lote
    from collections import Counter as _Counter
    kw_counts = _Counter(kw for kw, _ in batch)
    premium_count = sum(cnt for kw, cnt in kw_counts.items() if kw in HIGH_VALUE_KEYWORD_MULTIPLIER)
    top5 = kw_counts.most_common(5)
    log.info(f"📍 Queries pendientes: {total_pending}/{total_queries} | Leads actuales: {len(all_leads)}")
    log.info(f"💎 Nichos premium este lote: {premium_count}/{len(batch)} objetivo≈{premium_target} (sin dejar de explorar otros)")
    log.info(f"🎰 Thompson Sampling — Top keywords este lote:")
    for kw, cnt in top5:
        a, b = kw_stats.get(kw, [1, 1])
        multiplier = HIGH_VALUE_KEYWORD_MULTIPLIER.get(kw, 1.0)
        premium = f", premium×{multiplier:.2f}" if multiplier > 1 else ""
        log.info(f"    {kw}: {cnt} queries (α={a}, β={b}, tasa≈{a/(a+b):.0%}{premium})")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--lang=es-CO",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--js-flags=--max-old-space-size=256",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="es-CO",
        timezone_id="America/Bogota",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    context.set_default_timeout(30000)
    context.set_default_navigation_timeout(30000)
    main_page = context.new_page()
    main_page.route("**/*", block_heavy_resources)

    new_leads_cycle = 0
    # Poisson: próximo coffee break a ~20 queries (variable)
    next_coffee = max(10, int(random.expovariate(1.0 / 20)))
    try:
        for q_idx, (base_kw, query) in enumerate(batch, 1):
            # ── Cortar si llegó la hora límite (ej. hora de oleadas) ──
            now = now_colombia()
            if stop_hour is not None and now.weekday() < 5 and stop_hour <= now.hour < 18:
                log.info(f"⏰ Son las {now.strftime('%H:%M')} — pausando scraper para siguiente fase")
                break

            log.info(f"\n  [{q_idx}/{len(batch)}] ──────────────────────────")
            new_count = 0
            mark_query_done(query)
            try:
                new_count = search_maps(context, main_page, query, all_leads, seen_names, seen_phones)
                new_leads_cycle += new_count
                if new_count > 0:
                    safe_export(all_leads)
            except Exception as e:
                log.error(f"  Error en \"{query}\": {e}")

            # ── Actualizar Thompson Sampling stats ──
            if new_count > 0:
                kw_stats[base_kw][0] += new_count  # α += leads encontrados
            else:
                kw_stats[base_kw][1] += 1           # β += fracaso
            save_keyword_stats(kw_stats)

            if q_idx < len(batch):
                # ── Delay log-normal (más humano que uniforme) ──
                # Mediana ~8s, con colas largas ocasionales (20-30s)
                wait = random.lognormvariate(math.log(8.0), 0.5)
                wait = max(3.0, min(wait, 30.0))
                time.sleep(wait)

                # ── Coffee breaks con proceso de Poisson ──
                # Intervalos impredecibles en vez de cada 20 fijo
                if q_idx >= next_coffee:
                    coffee = random.lognormvariate(math.log(90), 0.5)
                    coffee = max(30, min(coffee, 300))
                    log.info(f"  ☕ Pausa anti-ban de {coffee:.0f}s...")
                    time.sleep(coffee)
                    # Próximo break: ~20 queries después (Poisson)
                    next_coffee = q_idx + max(8, int(random.expovariate(1.0 / 20)))
    except KeyboardInterrupt:
        log.warning("\n⚠️  Ciclo interrumpido. Guardando...")
        raise
    finally:
        # Cleanup — SIEMPRE cerrar browser para liberar RAM
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

    # Guardar
    if all_leads:
        safe_export(all_leads)

    # Resumen detallado del ciclo
    done_count = 0
    if os.path.exists(QUERIES_DONE):
        try:
            with open(QUERIES_DONE, "r", encoding="utf-8") as f:
                done_count = sum(1 for line in f if line.strip())
        except Exception:
            pass
    log.info(f"  📊 RESUMEN CICLO: +{new_leads_cycle} leads nuevos | Total: {len(all_leads)} | Queries hechas: {done_count}/~45790")


def scraper_loop():
    """Scraper continuo: lotes inteligentes, queries no repetidas y reinicio limpio por ciclo."""
    paused, reason = scraper_is_paused()
    if paused:
        log.warning(f"🛑 {reason}")
        return

    log.info("🚀 Scraper continuo iniciado (queries mezcladas + anti-repetidos)")
    while True:
        paused, reason = scraper_is_paused()
        if paused:
            log.warning(f"🛑 {reason}")
            return
        now = now_colombia()
        if now.weekday() < 5 and 9 <= now.hour < 18:
            # Dormir hasta las 18:00 sin salir del proceso — evita restart loop de systemd
            target = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_sec = max(60, int((target - now).total_seconds()))
            log.info(
                f"⏰ Son las {now.strftime('%H:%M')} Colombia (entre semana) — "
                f"pausando scraper hasta las 18:00 ({wait_sec // 60} min)"
            )
            time.sleep(min(wait_sec, 1800))  # despertar cada 30 min máx. por si cambia el horario
            continue
        try:
            _auto_scrape_cycle(stop_hour=9)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log.error(f"⚠️ Ciclo de scraper falló: {type(e).__name__}: {e}")
        pause = random.uniform(20, 45)
        log.info(f"🔁 Siguiente ciclo en {pause:.0f}s...")
        time.sleep(pause)


def generate_single_mockup(phone: str):
    """
    Genera UN mockup para un teléfono específico.
    Busca datos en el Excel; si no existe, usa datos del chat DB o ficticios.
    Diseñado para ser llamado como subprocess desde el webhook.
    """
    phone = phone.replace("+", "").strip()

    # Intentar obtener datos del Excel
    leads, _, _ = load_existing_leads(OUTPUT_FILE)
    lead = None
    for l in leads:
        p = (l.get("WhatsApp Directo") or "").replace("+", "")
        if p == phone:
            lead = l
            break

    # Si no está en Excel, intentar datos del chat DB
    if not lead:
        try:
            from core.db import get_db
            with get_db() as conn:
                row = conn.execute(
                    "SELECT nombre, categoria, busqueda FROM chats WHERE phone = ?",
                    (phone,)
                ).fetchone()
                if row:
                    lead = {
                        "Nombre": row["nombre"] or "Mi Negocio",
                        "Categoría": row.get("categoria", "") or row.get("busqueda", "") or "Servicios Profesionales",
                        "Dirección": "Bogotá, Colombia",
                        "Teléfono": f"+{phone}",
                        "Calificación": 4.8,
                        "Reseñas": 50,
                    }
        except Exception:
            pass

    # Fallback total: datos ficticios
    if not lead:
        lead = {
            "Nombre": "Mi Negocio",
            "Categoría": "Servicios Profesionales",
            "Dirección": "Bogotá, Colombia",
            "Teléfono": f"+{phone}",
            "Calificación": 4.8,
            "Reseñas": 50,
        }

    nombre = lead.get("Nombre") or "Mi Negocio"
    log.info(f"🖼️  Generando mockup individual: {nombre} (+{phone})")

    with sync_playwright() as pw:
        result = generate_mockup(lead, pw)

    if result:
        log.info(f"✅ Mockup listo: {result}")
        # Imprimir la ruta al stdout para que el webhook la capture
        print(f"MOCKUP_PATH:{result}")
    else:
        log.error(f"❌ No se pudo generar mockup para +{phone}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        if "--mockups" in sys.argv:
            # Borrar todos los mockups anteriores antes de generar los del día
            if os.path.exists(MOCKUP_DIR):
                borrados = 0
                for fname in os.listdir(MOCKUP_DIR):
                    if fname.endswith(".jpg"):
                        os.remove(os.path.join(MOCKUP_DIR, fname))
                        borrados += 1
                log.info(f"🗑️  Limpieza: {borrados} mockups viejos eliminados")
            generate_missing_mockups(max_count=240)
        elif "--mockup-one" in sys.argv:
            idx = sys.argv.index("--mockup-one")
            phone = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
            if not phone:
                print("Uso: python flores.py --mockup-one 573017453703")
                sys.exit(1)
            generate_single_mockup(phone)
        elif "--enviar" in sys.argv:
            enviar_mensajes_leads()
        elif "--oleadas" in sys.argv:
            enviar_oleadas()
        elif "--auto" in sys.argv:
            auto_mode()
        elif "--scrape-loop" in sys.argv:
            scraper_loop()
        elif "--limpiar-mockups" in sys.argv:
            limpiar_mockups_viejos()
        elif "--test-api" in sys.argv:
            test_api()
        elif "--check-templates" in sys.argv:
            check_templates()
        else:
            scraper_loop()
    except Exception as e:
        task = sys.argv[1] if len(sys.argv) > 1 else "scraper"
        send_alert(f"❌ {task} falló:\n\n{type(e).__name__}: {e}")
        raise
