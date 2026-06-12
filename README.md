# Health Agent Bridge

Puente local para llevar datos de smartwatch/telefono hacia workspaces de agentes
Hermes/OpenClaw sin exponer biometria sensible a servicios externos.

El MVP parte desde payloads JSON simulados o exportados. Para iPhone + Xiaomi
Smart Band, la ruta recomendada es:

```mermaid
flowchart LR
    Band["Xiaomi Smart Band"] --> MiFitness["Mi Fitness"]
    MiFitness --> AppleHealth["Apple Health"]
    AppleHealth --> Export["Health export XML/JSON"]
    Export --> Api["FastAPI local"]
    Api --> Db["SQLite"]
    Db --> Summary["Daily summary service"]
    Summary --> Workspace["agent-workspace/context"]
    Workspace --> Agents["Hermes / OpenClaw"]
```

## MVP

- `POST /health/import`: importa metricas diarias, sueno, frecuencia cardiaca,
  actividad y notas.
- `GET /health/summary/today`: genera resumen del dia y lo escribe para agentes.
- SQLite local, sin servicios externos.
- Autenticacion simple por API key local.
- Salida Markdown/JSON en `agent-workspace/context`.

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\uvicorn health_agent_bridge.main:app --reload --app-dir src
```

Importar ejemplo:

```powershell
$headers = @{ "X-API-Key" = "change-me-local-only" }
$body = Get-Content -Raw .\examples\health-import.sample.json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/health/import `
  -Headers $headers -Body $body -ContentType "application/json"
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/health/summary/today `
  -Headers $headers
```

## Workspace Output

- `agent-workspace/context/health_today.md`
- `agent-workspace/context/health_alerts.json`
- `agent-workspace/context/reminders.json`

## Apple Health XML Import

Coloca la exportacion de Apple Health en una carpeta local ignorada por git, por
ejemplo:

```text
storage/exportar/apple_health_export/exportar.xml
```

Importar a SQLite:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python .\scripts\import_apple_health.py `
  .\storage\exportar\apple_health_export\exportar.xml `
  --user-name Mauro
```

Importar solo un rango:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python .\scripts\import_apple_health.py `
  .\storage\exportar\apple_health_export\exportar.xml `
  --from-date 2026-06-01 `
  --to-date 2026-06-12
```

## Apple Health ZIP incremental (WhatsApp workflow)

Apple Health siempre exporta todo el historial en un ZIP. El bridge no puede pedir
solo lo nuevo al iPhone, pero si puede:

- detectar si el ZIP no cambio y saltar el import
- importar solo los ultimos dias en la base (`--incremental`)
- reescribir un solapamiento de 14 dias por si Apple corrige datos viejos

Flujo recomendado:

1. Exportar en Salud (iPhone).
2. Enviarte el ZIP por WhatsApp y guardarlo en `storage/exportar.zip`.
3. Correr sync incremental y refrescar contexto para agentes.

```bash
cd /home/mauro/Dev/sync-smartwatch-xiaomi
PYTHONPATH=src .venv/bin/python scripts/sync_apple_health_export.py \
  --refresh-summary
```

Si no pasas ruta, usa el ZIP mas nuevo dentro de `storage/`.

Primera vez o reimport total:

```bash
PYTHONPATH=src .venv/bin/python scripts/sync_apple_health_export.py \
  storage/exportar.zip --full --refresh-summary
```

Estado del ultimo import: `storage/import_state.json` (ignorado por git).

### Recuperar huecos (varios dias sin enviar ZIP)

Apple siempre manda el historial completo en el ZIP. Si dejas de enviar 3 dias y
al 4.º dia mandas un export nuevo, el import incremental:

1. Toma la ultima fecha ya guardada en BD (ej. lunes).
2. Reprocesa desde `ultima_fecha - 14 dias` (solape por correcciones de Apple).
3. Hace upsert de **cada dia** presente en el XML, incluyendo mar/mie/jue del hueco.

La BD no deberia quedar con huecos de dias que Apple exporto. Tras cada import se
genera `storage/datamart_coverage.json` con fechas faltantes reales en el rango
(dias sin ningun registro en Salud, no dias sin ZIP).

Ejemplo de consulta datamart:

```sql
SELECT metric_date, steps, sleep_minutes, heart_rate_avg_bpm
FROM daily_health_rollups
WHERE user_name = 'Mauro'
  AND metric_date BETWEEN '2026-06-01' AND '2026-06-30'
ORDER BY metric_date;
```

## Automatizacion WhatsApp Web + cron

Flujo diario:

1. **18:30** cron envia recordatorio para exportar Salud en el iPhone y mandarte el ZIP
   por WhatsApp a tu chat personal (`Mauro Castro Pers (Tú)`).
2. **19:00** cron abre WhatsApp Web con sesion persistente, descarga `exportar.zip`,
   lo copia a `storage/exportar.zip`, corre import incremental y refresca el resumen
   para Fede.

### Setup una sola vez

```bash
cd /home/mauro/Dev/sync-smartwatch-xiaomi
python3 -m venv .venv
.venv/bin/pip install -r requirements-automation.txt
# En Ubuntu 26 usa Google Chrome del sistema (channel=chrome)
# .venv/bin/playwright install chromium
cp .env.example .env
# Edita .env con HEALTH_EXPORT_TELEGRAM_BOT_TOKEN si quieres recordatorio por Telegram

# Vincular WhatsApp Web (escanea QR una vez)
./scripts/run_whatsapp_health_pipeline.sh login
```

### Probar manualmente

```bash
./scripts/run_whatsapp_health_pipeline.sh reminder
./scripts/run_whatsapp_health_pipeline.sh download-sync
```

### Instalar cron

```bash
./scripts/install_health_export_cron.sh
```

Perfil Playwright guardado en `storage/whatsapp-playwright-profile/` (ignorado por git).

La tabla principal para analitica es `daily_health_rollups`, con una fila por
dia y dimensiones listas para queries:

```sql
SELECT day_name, AVG(steps), AVG(sleep_minutes)
FROM daily_health_rollups
WHERE user_name = 'Mauro'
GROUP BY day_of_week, day_name
ORDER BY day_of_week;
```

```sql
SELECT year, month, AVG(steps), AVG(heart_rate_avg_bpm)
FROM daily_health_rollups
WHERE user_name = 'Mauro'
GROUP BY year, month
ORDER BY year, month;
```

## Ubuntu Server Deployment

El servidor puede reutilizar el PostgreSQL existente si la app corre en la red
Docker `openclaw_openclaw_net` y usa el host interno `postgres-memory`.

Crear `.env.server` en el servidor:

```env
HEALTH_BRIDGE_API_KEY=change-me
HEALTH_BRIDGE_DB_BACKEND=postgres
HEALTH_BRIDGE_DATABASE_URL=postgresql://openclaw:change-me@postgres-memory:5432/health_agent_bridge
HEALTH_BRIDGE_WORKSPACE_PATH=agent-workspace
HEALTH_BRIDGE_USER_NAME=Mauro
HEALTH_BRIDGE_TIMEZONE=America/Santiago
```

Levantar API:

```bash
docker compose -f docker-compose.server.yml up -d --build
curl -s http://127.0.0.1:8012/healthz
```

## Medical Boundary

Este proyecto no diagnostica enfermedades. Solo resume tendencias de habitos y
sugiere acciones conservadoras como descanso, caminata suave, hidratacion o
consultar a un profesional si un patron preocupante se repite.
