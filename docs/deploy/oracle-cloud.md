# Despliegue gratuito en Oracle Cloud (Always Free)

Stack en producción: `docker compose` con tres contenedores.

| Servicio | Qué hace |
|----------|----------|
| `caddy` | HTTPS automático (Let's Encrypt) en 80/443. Enruta `/api/*` y `/health` a la API, el resto a la web. `/docs` no se expone. |
| `api` | FastAPI (1 worker). Lee `.env`; persiste `data/` en el host. |
| `web` | Angular SSR (Node). Solo responde al host definido en `DOMAIN`. |

## 1. Crear la máquina

1. Crea una cuenta en [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/). Pide tarjeta para verificar identidad; los recursos *Always Free* no se cobran.
2. **Compute → Instances → Create instance**:
   - Imagen: **Ubuntu 24.04**.
   - Shape: **VM.Standard.A1.Flex** (Ampere), 2 OCPU y 12 GB RAM (el límite gratuito es 4 OCPU / 24 GB).
   - Si sale *"Out of capacity"*, prueba otro *Availability Domain* o reintenta más tarde.
   - Descarga la llave SSH.
3. Anota la **IP pública** de la instancia.

## 2. Abrir puertos 80 y 443

En la consola: **Networking → Virtual Cloud Networks → (tu VCN) → Security Lists → Default** → *Add Ingress Rules*:

- Source `0.0.0.0/0`, TCP, puerto destino `80`
- Source `0.0.0.0/0`, TCP, puerto destino `443`

Las imágenes Ubuntu de Oracle traen un firewall propio; ábrelo también dentro de la máquina:

```bash
ssh -i llave.key ubuntu@IP_PUBLICA
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Dominio

- **Sin dominio propio (gratis):** usa `IP-CON-GUIONES.sslip.io`, por ejemplo `129-146-10-20.sslip.io` para la IP `129.146.10.20`. Caddy obtiene el certificado HTTPS igual.
- **Con dominio propio:** crea un registro `A` apuntando a la IP pública.

## 4. Instalar Docker y desplegar

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker

git clone https://github.com/Sticlo/PortalEmpleoUD.git
cd PortalEmpleoUD
cp .env.example .env
nano .env   # DOMAIN, DEEPSEEK_API_KEY, DEEPSEEK_DAILY_LIMIT(_PER_IP), SCRAPER_PROXY_URL

docker compose up -d --build
```

Abre `https://TU_DOMINIO`. El primer arranque tarda unos minutos (build de Angular + certificado).

## 5. Proxy de respaldo para las búsquedas (si un portal bloquea Oracle)

Computrabajo, Elempleo o LinkedIn pueden bloquear la IP de Oracle. La API lo detecta
(HTTP 403/429/503/999, página de captcha o conexión cortada) y repite la búsqueda por
`SCRAPER_PROXY_URL`; ese portal sigue saliendo por el proxy durante 30 minutos.
Sin `SCRAPER_PROXY_URL` las búsquedas bloqueadas caen al índice local y "Empleos de hoy".

Para ver si está pasando: `curl https://TU_DOMINIO/api/v1/scraping/queue` → campo `proxy.hosts_via_proxy`.

### Opción gratis: tu PC de casa vía Tailscale

Las búsquedas bloqueadas salen por tu internet residencial. Tu PC debe estar encendido; si no, la búsqueda cae al índice local.

1. Instala [Tailscale](https://tailscale.com/download) en tu PC (Windows) y en el servidor, con la misma cuenta:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up
   ```
2. En tu PC, anota su IP de Tailscale (`tailscale ip -4`, algo como `100.101.102.103`).
3. En tu PC, levanta un proxy HTTP escuchando solo en esa IP:
   ```powershell
   pip install proxy.py
   proxy --hostname 100.101.102.103 --port 8899
   ```
   La primera vez, permite el acceso en el firewall de Windows (red privada).
4. En el `.env` del servidor:
   ```
   SCRAPER_PROXY_URL=http://100.101.102.103:8899
   ```
   y `docker compose up -d api`.

Solo los dispositivos de tu cuenta de Tailscale llegan a ese proxy.

### Opción paga: proxy residencial

Cualquier proveedor de proxies residenciales con salida en Colombia sirve (se cobra por GB; las búsquedas gastan poco porque solo pasan por el proxy cuando hay bloqueo):

```
SCRAPER_PROXY_URL=http://usuario:clave@proveedor:puerto
```

## 6. Operación

| Tarea | Comando |
|-------|---------|
| Ver logs | `docker compose logs -f api` |
| Actualizar a lo último de `main` | `git pull && docker compose up -d --build` |
| Uso de IA de hoy | `curl https://TU_DOMINIO/api/v1/cv/quota` |
| Cambiar topes de IA | editar `.env` y `docker compose up -d api` |

## Límites conocidos

- **Gasto de IA:** `DEEPSEEK_DAILY_LIMIT` (global) y `DEEPSEEK_DAILY_LIMIT_PER_IP` cortan el uso de DeepSeek; al superarlos el CV se genera en modo local. Los contadores se reinician a medianoche (hora Colombia) y al reiniciar la API.
- **Datos en memoria:** perfiles y ofertas se pierden al reiniciar la API (la HV del estudiante queda en su navegador).
- **Privacidad:** la HV solo se envía a DeepSeek con la autorización expresa del estudiante (casilla en "Preparar CV"); el aviso está en `/privacidad`. Antes de publicar, revisa responsable y correo en `apps/web/src/app/core/privacy.config.ts`.
- **Endpoints abiertos:** publicar vacante (`/empresa`) no tiene login.
