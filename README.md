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
