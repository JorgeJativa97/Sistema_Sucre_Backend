# Cabildo API — Backend Django

API REST para el sistema de recaudación y cartera vencida del Cabildo Municipal.
Construida con Django REST Framework, Oracle DB y Celery para tareas asíncronas.

---

## Tecnologías

- Python / Django REST Framework
- Oracle DB (cx_Oracle / oracledb)
- Celery + Redis (broker y backend de resultados)
- Gunicorn (servidor de producción)

---

## Estructura del proyecto

```
Cabildoapp/
├── Cabildoapp/
│   ├── settings.py          # Configuración principal (DB, Celery, ALLOWED_HOSTS)
│   ├── urls.py              # Registro de todos los endpoints
│   ├── celery.py            # Configuración de Celery
│   └── wsgi.py
└── Cabildo_api/
    ├── permissions.py       # Autenticación por API key (header x-api-key)
    ├── consultas/
    │   ├── views/
    │   │   ├── base.py                  # BaseAPIView: auth + conexión DB + manejo errores
    │   │   ├── ct_vencida.py            # Vistas de cartera vencida
    │   │   ├── bienes_inmuebles.py      # Vista de bienes inmuebles
    │   │   ├── comprobante.py           # Vista de comprobante de pago
    │   │   └── reporte_recaudacion.py   # Vistas de reporte de recaudación
    │   └── serializers/
    │       ├── ct_vencida.py            # Serializers de cartera vencida
    │       ├── bienes_inmuebles.py      # Serializer de bienes inmuebles
    │       └── reporte_recaudacion.py   # Serializer de recaudación
    └── task/
        └── tasks.py                     # Todas las tareas Celery
```

---

## Autenticación

Todos los endpoints requieren el header:

```
x-api-key: <clave>
```

Las claves válidas se configuran en `settings.py` mediante la variable de entorno `API_KEYS`.

---

## Flujo general de reportes asíncronos

Los reportes pesados (consultas Oracle que pueden tardar 30+ minutos) siguen un flujo de 3 pasos:

```
1. Cliente solicita el reporte
   GET /api/<endpoint>/?params
        │
        ▼
2. Backend lanza tarea Celery y responde inmediatamente
   HTTP 202 → { "task_id": "uuid", "status": "PENDING" }
        │
        ▼
3. Celery Worker ejecuta la consulta Oracle en segundo plano
   Guarda resultado en: /media/reportes/<nombre>.json
        │
        ▼
4. Cliente consulta el estado periódicamente (polling)
   GET /api/ct_vencida/status/<task_id>/
   → { "status": "PROCESSING", "progress": 50 }
   → { "status": "SUCCESS", ... }
        │
        ▼
5. Cliente descarga los datos cuando status = SUCCESS
   GET /api/<endpoint>/datos/?params
   → [ { ...registros... } ]
```

---

## Endpoints

### Autenticación requerida en todos: `x-api-key: <clave>`

---

### Cartera Vencida

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/ct_vencida/<year>/` | Inicia reporte general asíncrono |
| GET | `/api/ct_vencida/status/<task_id>/` | Consulta estado de cualquier tarea Celery |
| GET | `/api/ct_vencida/datos/<year>/` | Descarga datos del reporte general |
| GET | `/api/ct_vencida_impuesto/<year>/` | Inicia reporte por tipo de impuesto asíncrono |
| GET | `/api/ct_vencida_impuesto/datos/<year>/` | Descarga datos del reporte por impuesto |
| GET | `/api/ct_vencida_titulo/` | Lista de títulos/tipos de impuesto disponibles |
| GET | `/api/ct_vencida_titulo_detalle/<year>/` | Inicia reporte detalle por contribuyente asíncrono |
| GET | `/api/ct_vencida_titulo_detalle/datos/<year>/` | Descarga datos del reporte detalle |
| GET | `/api/ct_vencida_porimpuesto/<year>/` | Inicia reporte por títulos seleccionados asíncrono |
| GET | `/api/ct_vencida_porimpuesto/datos/<year>/` | Descarga datos del reporte por títulos |

**Parámetros:**
- `<year>` — año de corte (ej: `2025`)
- Para `ct_vencida_porimpuesto`: body JSON con lista de códigos de impuesto

---

### Reporte de Recaudación

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/recaudacion/` | Inicia reporte de recaudación por impuesto asíncrono |
| GET | `/api/recaudacion/datos/` | Descarga datos del reporte por impuesto |
| GET | `/api/recaudacion_rubro/` | Inicia reporte de recaudación por rubro asíncrono |
| GET | `/api/recaudacion_rubro/datos/` | Descarga datos del reporte por rubro |

**Query params requeridos:**
```
?fecha_inicio=YYYY-MM-DD&fecha_fin=YYYY-MM-DD
```

**Ejemplo flujo completo con curl:**
```bash
# 1. Iniciar reporte
curl -H "x-api-key: ClaveSecreta123" \
  "http://192.168.50.90:8000/api/recaudacion/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31"
# → {"task_id":"uuid...","status":"PENDING"}

# 2. Consultar estado
curl -H "x-api-key: ClaveSecreta123" \
  "http://192.168.50.90:8000/api/ct_vencida/status/uuid.../"
# → {"status":"SUCCESS","records":71,...}

# 3. Descargar datos
curl -H "x-api-key: ClaveSecreta123" \
  "http://192.168.50.90:8000/api/recaudacion/datos/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31"
# → [{...registros...}]
```

---

### Otros endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/bienes_inmuebles/` | Consulta de bienes inmuebles |
| GET | `/api/comprobante/<emi01codi>/` | Comprobante de pago |
| GET | `/api/comprobante/<emi01codi>/<nro_abono>/` | Comprobante de pago con abono |

---

## Tareas Celery (`Cabildo_api/task/tasks.py`)

| Nombre de tarea | Descripción | Archivo generado |
|-----------------|-------------|-----------------|
| `generar_reporte_cartera_vencida` | Cartera vencida general | `cartera_vencida_<year>.json` |
| `generar_reporte_cartera_vencida_impuesto` | Cartera vencida por impuesto | `cartera_vencida_impuesto_<year>.json` |
| `generar_reporte_cartera_vencida_titulo_detalle` | Cartera vencida detalle por contribuyente | `cartera_vencida_titulo_detalle_<year>.json` |
| `generar_reporte_cartera_vencida_porimpuesto` | Cartera vencida por títulos seleccionados | `cartera_vencida_porimpuesto_<year>_<codigos>.json` |
| `generar_reporte_recaudacion` | Recaudación agrupada por impuesto | `recaudacion_<fecha_inicio>_<fecha_fin>.json` |
| `generar_reporte_recaudacion_rubro` | Recaudación agrupada por rubro | `recaudacion_rubro_<fecha_inicio>_<fecha_fin>.json` |

Los archivos JSON se guardan en `MEDIA_ROOT/reportes/` y persisten para consultas posteriores.

---

## Estados de una tarea Celery

| Estado | Descripción |
|--------|-------------|
| `PENDING` | En cola, aún no inició |
| `PROCESSING` | Ejecutándose (incluye `progress` 0-100) |
| `SUCCESS` | Completada exitosamente |
| `FAILURE` | Falló (incluye mensaje de error) |

---

## Levantar el servidor (producción Linux)

```bash
# Activar entorno virtual
source /ruta/venv/bin/activate

# Levantar Django con Gunicorn
gunicorn Cabildoapp.wsgi:application --bind 0.0.0.0:8000

# Levantar worker Celery (en proceso separado)
celery -A Cabildoapp worker --loglevel=info
```
