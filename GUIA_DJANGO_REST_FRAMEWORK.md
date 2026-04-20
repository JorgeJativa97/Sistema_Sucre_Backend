yuj9o=[¨P# Guía de Django REST Framework*/
### Desde lo básico hasta nivel avanzado — basada en el proyecto Cabildo API

---

## Índice

1. [¿Qué es Django REST Framework?](#1-qué-es-django-rest-framework)
2. [Instalación y configuración](#2-instalación-y-configuración)
3. [Conceptos fundamentales de HTTP](#3-conceptos-fundamentales-de-http)
4. [Views — Las vistas](#4-views--las-vistas)
5. [Serializers — Transformar datos](#5-serializers--transformar-datos)
6. [URLs — Registrar endpoints](#6-urls--registrar-endpoints)
7. [Permissions — Control de acceso](#7-permissions--control-de-acceso)
8. [Response y códigos HTTP](#8-response-y-códigos-http)
9. [Manejo de errores](#9-manejo-de-errores)
10. [Herencia de clases — Reutilizar código](#10-herencia-de-clases--reutilizar-código)
11. [Consultas a base de datos](#11-consultas-a-base-de-datos)
12. [Tareas asíncronas con Celery](#12-tareas-asíncronas-con-celery)
13. [Logging — Registrar eventos](#13-logging--registrar-eventos)
14. [Buenas prácticas](#14-buenas-prácticas)

---

## 1. ¿Qué es Django REST Framework?

Django REST Framework (DRF) es una librería que se instala sobre Django y permite construir **APIs REST** de forma rápida y ordenada.

Una **API REST** es un servicio web que:
- Recibe peticiones HTTP (GET, POST, PUT, DELETE)
- Procesa los datos (consulta BD, ejecuta lógica)
- Devuelve respuestas en formato JSON

```
Cliente (React, Postman, curl)
        │
        │  GET /api/recaudacion/?fecha_inicio=2025-01-01
        ▼
    Django + DRF
        │
        │  Consulta Oracle DB
        │  Serializa datos
        │  Devuelve JSON
        ▼
    { "IMPUESTO": "...", "TOTAL": 1250000 }
```

---

## 2. Instalación y configuración

### Instalación

```bash
pip install djangorestframework
```

### Configuración en `settings.py`

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    # ...
    'rest_framework',   # <-- agregar esto
    'Cabildo_api',
]
```

### Configuración global de DRF (opcional)

```python
REST_FRAMEWORK = {
    # Formato de respuesta por defecto
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    # Qué hacer si no hay autenticación configurada
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    # Permisos por defecto (en este proyecto se manejan por view)
    'DEFAULT_PERMISSION_CLASSES': [],
}
```

---

## 3. Conceptos fundamentales de HTTP

Antes de continuar, es importante entender los verbos HTTP y los códigos de respuesta que usa DRF.

### Verbos HTTP

| Verbo | Uso |
|-------|-----|
| `GET` | Obtener datos (no modifica nada) |
| `POST` | Crear un recurso nuevo |
| `PUT` | Actualizar un recurso completo |
| `PATCH` | Actualizar parcialmente un recurso |
| `DELETE` | Eliminar un recurso |

> En este proyecto todos los endpoints usan `GET` porque solo consultan datos.

### Códigos de respuesta más usados

| Código | Significado | Cuándo usarlo |
|--------|-------------|---------------|
| `200 OK` | Todo salió bien | Consulta exitosa |
| `202 Accepted` | Aceptado, procesando | Tarea asíncrona iniciada |
| `400 Bad Request` | Parámetros incorrectos | Fecha inválida, falta parámetro |
| `404 Not Found` | No encontrado | Archivo JSON no existe |
| `500 Internal Server Error` | Error del servidor | Excepción no controlada |

---

## 4. Views — Las vistas

Las **views** son las funciones o clases que reciben una petición HTTP y devuelven una respuesta. Es el corazón de cada endpoint.

### 4.1 APIView — La base de todo

`APIView` es la clase base de DRF. Cada método HTTP se define como un método de la clase:

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class MiPrimeraView(APIView):

    def get(self, request):
        # Lógica para GET
        return Response({"mensaje": "Hola mundo"}, status=status.HTTP_200_OK)

    def post(self, request):
        # Lógica para POST
        datos = request.data  # body de la petición
        return Response({"recibido": datos}, status=status.HTTP_201_CREATED)
```

### 4.2 Leer parámetros de la URL

Hay dos formas de pasar parámetros:

**Query params** — van en la URL después del `?`:
```
GET /api/recaudacion/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31
```

```python
def get(self, request):
    fecha_inicio = request.query_params.get('fecha_inicio')
    fecha_fin    = request.query_params.get('fecha_fin')

    if not fecha_inicio:
        return Response(
            {"detail": "fecha_inicio es requerido"},
            status=status.HTTP_400_BAD_REQUEST
        )
```

**Path params** — van dentro de la URL:
```
GET /api/ct_vencida/2025/
```

```python
# En urls.py se define el parámetro con <int:year>
path('api/ct_vencida/<int:year>/', MiView.as_view())

# En la view llega como argumento
def get(self, request, year):
    print(year)  # 2025
```

### 4.3 Ejemplo real del proyecto

```python
# Cabildo_api/consultas/views/reporte_recaudacion.py

class RecaudacionImpuestoAPIView(BaseRecaudacionAPIView):
    """
    GET /api/recaudacion/?fecha_inicio=YYYY-MM-DD&fecha_fin=YYYY-MM-DD
    Inicia la generación asíncrona del reporte de recaudación.
    """

    def get(self, request):
        try:
            # 1. Leer y validar parámetros
            fecha_inicio, fecha_fin = self._get_fechas(request)

            # 2. Lanzar tarea Celery
            task = generar_reporte_recaudacion.delay(fecha_inicio, fecha_fin)

            # 3. Responder inmediatamente con 202
            return Response({
                'task_id': task.id,
                'status': 'PENDING',
                'message': f'Generando reporte del {fecha_inicio} al {fecha_fin}.',
            }, status=status.HTTP_202_ACCEPTED)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(e, 'RecaudacionImpuestoAPIView', request)
```

---

## 5. Serializers — Transformar datos

Un **serializer** transforma datos complejos (diccionarios, objetos de BD) en tipos Python simples que se pueden convertir a JSON, y viceversa.

### 5.1 ¿Por qué usarlos?

Sin serializer tendrías que validar y convertir datos manualmente:
```python
# Sin serializer — tedioso y propenso a errores
datos = {
    "total": str(row[0]),   # convertir Decimal a string manualmente
    "fecha": row[1].isoformat() if row[1] else None,
    # ...
}
```

Con serializer DRF hace esto automáticamente y además **valida** los tipos.

### 5.2 Tipos de campos más usados

```python
from rest_framework import serializers

class EjemploSerializer(serializers.Serializer):
    nombre    = serializers.CharField()                        # texto
    edad      = serializers.IntegerField()                     # entero
    saldo     = serializers.DecimalField(max_digits=15,        # decimal
                                         decimal_places=2)
    activo    = serializers.BooleanField()                     # true/false
    fecha     = serializers.DateField()                        # YYYY-MM-DD
    texto_opt = serializers.CharField(allow_null=True)         # puede ser null
    lista     = serializers.ListField(                         # lista de strings
                    child=serializers.CharField())
```

### 5.3 El parámetro `source`

Permite que el campo en el JSON tenga un nombre diferente al campo en los datos crudos.
Útil cuando Oracle devuelve columnas en MAYÚSCULAS pero quieres el JSON en minúsculas:

```python
# Cabildo_api/consultas/serializers/ct_vencida.py

class CtVencidaSerializer(serializers.Serializer):
    # JSON: "cedula"  ←  datos crudos: "CEDULA"
    cedula  = serializers.CharField(source='CEDULA')
    nombre  = serializers.CharField(source='NOMBRE')
    total   = serializers.DecimalField(max_digits=15,
                                       decimal_places=2,
                                       source='TOTAL')
```

### 5.4 Serializar muchos registros con `many=True`

```python
# Un solo objeto
serializer = CtVencidaSerializer(un_registro)
print(serializer.data)
# {"cedula": "1234", "nombre": "Juan", "total": "500.00"}

# Lista de objetos
serializer = CtVencidaSerializer(lista_registros, many=True)
print(serializer.data)
# [{"cedula": "1234", ...}, {"cedula": "5678", ...}]
```

### 5.5 Validación con serializers

```python
class FechaSerializer(serializers.Serializer):
    fecha_inicio = serializers.DateField()
    fecha_fin    = serializers.DateField()

    def validate(self, data):
        # Validación a nivel de objeto (accede a todos los campos)
        if data['fecha_inicio'] > data['fecha_fin']:
            raise serializers.ValidationError(
                "fecha_inicio no puede ser mayor que fecha_fin"
            )
        return data

# Uso:
serializer = FechaSerializer(data=request.query_params)
if serializer.is_valid():
    datos = serializer.validated_data
else:
    return Response(serializer.errors, status=400)
```

### 5.6 Serializer del proyecto — RecaudacionImpuestoSerializer

```python
# Cabildo_api/consultas/serializers/reporte_recaudacion.py

class RecaudacionImpuestoSerializer(serializers.Serializer):
    IMPUESTO      = serializers.CharField(allow_null=True)
    EMISIONTITULO = serializers.DecimalField(max_digits=30, decimal_places=2)
    INTERES       = serializers.DecimalField(max_digits=30, decimal_places=2)
    COACTIVA      = serializers.DecimalField(max_digits=30, decimal_places=2)
    DESCUENTO     = serializers.DecimalField(max_digits=30, decimal_places=2)
    RECARGO       = serializers.DecimalField(max_digits=30, decimal_places=2)
    IVA           = serializers.DecimalField(max_digits=30, decimal_places=2)
    NRO_TITULOS   = serializers.IntegerField()
    TOTAL         = serializers.DecimalField(max_digits=30, decimal_places=2)
```

> Los campos en MAYÚSCULAS coinciden exactamente con los nombres de columna que devuelve Oracle, por eso no se necesita `source`.

---

## 6. URLs — Registrar endpoints

### 6.1 Estructura básica

```python
# Cabildoapp/urls.py

from django.urls import path
from Cabildo_api.consultas.views.reporte_recaudacion import RecaudacionImpuestoAPIView

urlpatterns = [
    path('api/recaudacion/', RecaudacionImpuestoAPIView.as_view(), name='recaudacion_impuesto'),
]
```

> `.as_view()` convierte la clase en una función que Django puede llamar.

### 6.2 Parámetros en la URL

```python
urlpatterns = [
    # Parámetro entero
    path('api/ct_vencida/<int:year>/', CtVencidaView.as_view()),

    # Parámetro string
    path('api/status/<str:task_id>/', TaskStatusAPIView.as_view()),

    # Múltiples parámetros
    path('api/comprobante/<int:emi01codi>/<int:nro_abono>/', ComprobanteView.as_view()),
]
```

### 6.3 Tipos de parámetros disponibles

| Tipo | Ejemplo | Descripción |
|------|---------|-------------|
| `<int:name>` | `/api/reporte/2025/` | Solo números enteros |
| `<str:name>` | `/api/status/abc-123/` | Cualquier texto sin `/` |
| `<slug:name>` | `/api/item/mi-item/` | Letras, números, guiones |
| `<uuid:name>` | `/api/task/550e8400.../` | UUID estándar |

---

## 7. Permissions — Control de acceso

Las **permissions** controlan quién puede acceder a cada endpoint.

### 7.1 Cómo funciona

Antes de ejecutar el método `get()` o `post()`, DRF evalúa los `permission_classes`. Si alguno devuelve `False`, responde automáticamente con `403 Forbidden`.

```
Petición HTTP
     │
     ▼
¿Pasa los permission_classes?
     │
  No │──── 403 Forbidden
     │
  Sí │
     ▼
Ejecuta get() / post() / etc.
```

### 7.2 Permiso personalizado del proyecto

```python
# Cabildo_api/permissions.py

from rest_framework.permissions import BasePermission
from django.conf import settings

class HasAPIKey(BasePermission):
    """
    Valida que la petición incluya un header X-API-Key válido.
    """
    message = "API Key inválida o faltante"

    def has_permission(self, request, view):
        api_key = request.headers.get('X-API-Key', '')
        if not api_key:
            return False
        return api_key in settings.API_KEYS
```

**¿Cómo se usa?**

```python
class MiView(APIView):
    permission_classes = [HasAPIKey]  # se aplica a todos los métodos

    def get(self, request):
        # Solo llega aquí si el header X-API-Key es válido
        return Response({"data": "ok"})
```

**En `settings.py`:**

```python
API_KEYS = os.getenv('API_KEYS', '').split(',')
# .env: API_KEYS=ClaveSecreta123,OtraClave456
```

### 7.3 Permisos predefinidos de DRF

```python
from rest_framework.permissions import (
    AllowAny,           # Cualquiera puede acceder (sin autenticación)
    IsAuthenticated,    # Solo usuarios autenticados (sesión Django)
    IsAdminUser,        # Solo administradores
    IsAuthenticatedOrReadOnly,  # Autenticados pueden escribir, todos pueden leer
)
```

---

## 8. Response y códigos HTTP

### 8.1 La clase Response

`Response` de DRF serializa automáticamente los datos Python a JSON:

```python
from rest_framework.response import Response
from rest_framework import status

# Respuesta exitosa
return Response({"mensaje": "ok"}, status=status.HTTP_200_OK)

# Respuesta con error
return Response({"detail": "No encontrado"}, status=status.HTTP_404_NOT_FOUND)

# Lista de datos
return Response([{"id": 1}, {"id": 2}], status=status.HTTP_200_OK)
```

### 8.2 Constantes de status en DRF

```python
from rest_framework import status

# 2xx — Éxito
status.HTTP_200_OK            # 200
status.HTTP_201_CREATED       # 201
status.HTTP_202_ACCEPTED      # 202 — usado en tareas asíncronas
status.HTTP_204_NO_CONTENT    # 204

# 4xx — Error del cliente
status.HTTP_400_BAD_REQUEST   # 400
status.HTTP_401_UNAUTHORIZED  # 401
status.HTTP_403_FORBIDDEN     # 403
status.HTTP_404_NOT_FOUND     # 404

# 5xx — Error del servidor
status.HTTP_500_INTERNAL_SERVER_ERROR  # 500
```

### 8.3 Patrón de respuesta del proyecto

El proyecto usa un patrón consistente para todas las respuestas:

```python
# Éxito — tarea asíncrona iniciada
return Response({
    'task_id': task.id,
    'status': 'PENDING',
    'message': 'Generando reporte...',
}, status=status.HTTP_202_ACCEPTED)

# Error de validación
return Response(
    {"detail": "fecha_inicio es requerido"},
    status=status.HTTP_400_BAD_REQUEST
)

# Error del servidor
return Response(
    {"detail": "Error al ejecutar query", "error": str(e)},
    status=status.HTTP_500_INTERNAL_SERVER_ERROR
)
```

---

## 9. Manejo de errores

### 9.1 Try/Except básico en una view

```python
def get(self, request):
    try:
        datos = ejecutar_consulta()
        return Response(datos, status=status.HTTP_200_OK)

    except ValueError as e:
        # Error controlado (validación)
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        # Error inesperado
        return Response(
            {"detail": "Error interno", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
```

### 9.2 Manejo centralizado — patrón del proyecto

En lugar de repetir el bloque de error en cada view, el proyecto lo centraliza en `BaseAPIView`:

```python
# Cabildo_api/consultas/views/base.py

class BaseAPIView(APIView):
    permission_classes = [HasAPIKey]

    def _handle_error(self, e, view_name, request, **extra):
        """
        Registra el error en el log y retorna una respuesta 500 estandarizada.
        **extra permite pasar contexto adicional al log (ej: year=2025)
        """
        logger.error(
            f"{view_name} - Error inesperado: {str(e)}\n{traceback.format_exc()}",
            exc_info=True,
            extra={'method': 'GET', 'path': request.path, **extra}
        )
        return Response(
            {"detail": "Error al ejecutar query", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
```

**Uso en cualquier view hija:**

```python
class RecaudacionImpuestoAPIView(BaseAPIView):
    def get(self, request):
        try:
            # ... lógica
        except Exception as e:
            # Una sola línea reemplaza todo el bloque de error
            return self._handle_error(
                e, 'RecaudacionImpuestoAPIView', request,
                fecha_inicio=request.query_params.get('fecha_inicio'),
            )
```

---

## 10. Herencia de clases — Reutilizar código

### 10.1 ¿Por qué usar herencia?

Sin herencia, cada view repetiría el mismo código:

```python
# Sin herencia — código duplicado en cada view
class ViewA(APIView):
    permission_classes = [HasAPIKey]  # repetido

    def _fetch_query(self, sql, params):  # repetido
        ...

    def _handle_error(self, e, ...):  # repetido
        ...

class ViewB(APIView):
    permission_classes = [HasAPIKey]  # repetido otra vez
    # ...
```

### 10.2 Árbol de herencia del proyecto

```
APIView (DRF)
    └── BaseAPIView           ← autenticación + BD + manejo errores
            ├── TaskStatusAPIView
            └── BaseRecaudacionAPIView   ← validación de fechas
                    ├── RecaudacionImpuestoAPIView
                    ├── RecaudacionDatosAPIView
                    ├── RecaudacionRubroApiView
                    └── RecaudacionRubroDatosAPIView
```

### 10.3 Implementación paso a paso

**Nivel 1 — Base global:**

```python
class BaseAPIView(APIView):
    permission_classes = [HasAPIKey]  # aplica a todas las views hijas

    def _fetch_query(self, sql, params=None):
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            cols = [c[0] for c in cursor.description]
            rows = cursor.fetchall()
        return [
            {col: (float(val) if isinstance(val, Decimal) else val)
             for col, val in zip(cols, row)}
            for row in rows
        ]

    def _handle_error(self, e, view_name, request, **extra):
        logger.error(f"{view_name} - Error: {str(e)}", exc_info=True)
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

**Nivel 2 — Base específica de recaudación:**

```python
class BaseRecaudacionAPIView(BaseAPIView):
    # Hereda: permission_classes, _fetch_query, _handle_error

    def _get_fechas(self, request):
        """Lógica común de validación de fechas para todos los reportes de recaudación"""
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin    = request.query_params.get('fecha_fin')

        if not fecha_inicio or not fecha_fin:
            raise ValueError("Los parámetros 'fecha_inicio' y 'fecha_fin' son requeridos")

        datetime.strptime(fecha_inicio, '%Y-%m-%d')  # valida formato
        datetime.strptime(fecha_fin,    '%Y-%m-%d')

        if fecha_inicio > fecha_fin:
            raise ValueError("'fecha_inicio' no puede ser mayor que 'fecha_fin'")

        return fecha_inicio, fecha_fin
```

**Nivel 3 — View concreta:**

```python
class RecaudacionImpuestoAPIView(BaseRecaudacionAPIView):
    # Hereda TODO: permission_classes, _fetch_query, _handle_error, _get_fechas
    # Solo implementa la lógica específica de este endpoint

    def get(self, request):
        try:
            fecha_inicio, fecha_fin = self._get_fechas(request)  # heredado
            task = generar_reporte_recaudacion.delay(fecha_inicio, fecha_fin)
            return Response({'task_id': task.id, 'status': 'PENDING'}, status=202)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        except Exception as e:
            return self._handle_error(e, 'RecaudacionImpuestoAPIView', request)  # heredado
```

---

## 11. Consultas a base de datos

### 11.1 ORM vs SQL raw

Django tiene un ORM (Object Relational Mapper) que permite hacer consultas sin escribir SQL. Sin embargo, este proyecto usa **SQL raw** directamente por dos razones:
1. La base de datos es **Oracle** con funciones propias (`web_interes`, `F_PAGOABONO`, etc.)
2. Las consultas son muy complejas con `UNION ALL`, cálculos anidados y funciones PL/SQL

### 11.2 Ejecutar SQL raw con Django

```python
from django.db import connection

def ejecutar_consulta(year):
    with connection.cursor() as cursor:
        # Ejecutar la query con parámetros nombrados (Oracle usa :nombre)
        cursor.execute("""
            SELECT impuesto, SUM(total) as total
            FROM mi_tabla
            WHERE anio = :year
            GROUP BY impuesto
        """, {'year': year})

        # Obtener nombres de columnas
        cols = [c[0] for c in cursor.description]

        # Obtener todas las filas
        rows = cursor.fetchall()

    # Convertir a lista de diccionarios
    return [dict(zip(cols, row)) for row in rows]
```

### 11.3 El método `_fetch_query` del proyecto

```python
def _fetch_query(self, sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or {})
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    return [
        # Convertir Decimal a float automáticamente para serialización JSON
        {col: (float(val) if isinstance(val, Decimal) else val)
         for col, val in zip(cols, row)}
        for row in rows
    ]
```

> Oracle devuelve números como `Decimal`, que no es serializable a JSON por defecto. Por eso se convierte a `float`.

### 11.4 Parámetros en Oracle vs PostgreSQL/MySQL

```python
# Oracle — usa :nombre
cursor.execute("SELECT * FROM tabla WHERE anio = :year", {'year': 2025})

# PostgreSQL/MySQL — usa %s
cursor.execute("SELECT * FROM tabla WHERE anio = %s", [2025])
```

### 11.5 LIKE con % en Oracle (caso especial)

Cuando el SQL tiene `LIKE '%texto%'`, Python interpreta `%t` como formato de string y da error. La solución es escapar con `%%`:

```python
# Incorrecto — error: "unsupported format character"
sql = "WHERE TIPO LIKE '%NORMAL%'"

# Correcto — se escapa el % con %%
sql = "WHERE TIPO LIKE '%%NORMAL%%'"
```

### 11.6 fetchmany — Procesar en lotes

Para consultas que devuelven miles de registros, `fetchall()` puede consumir demasiada memoria. La alternativa es `fetchmany()`:

```python
# En CtVencidaSerializer.execute_query()
results = []
batch_size = 500
while True:
    batch = cursor.fetchmany(batch_size)
    if not batch:
        break
    for row in batch:
        results.append({...})
```

---

## 12. Tareas asíncronas con Celery

### 12.1 ¿Por qué usar Celery?

Las consultas Oracle del proyecto pueden tardar **30 minutos o más**. Sin Celery:

```
Cliente espera 30 minutos sin respuesta → timeout → error
```

Con Celery:

```
Cliente recibe task_id en < 1 segundo → consulta el estado cada 2s → descarga cuando termina
```

### 12.2 Componentes de Celery

```
Django (view)
    │  task.delay()       ← encola la tarea
    ▼
Redis (broker)            ← cola de mensajes
    │
    ▼
Celery Worker             ← ejecuta la tarea en segundo plano
    │
    ▼
Redis (result backend)    ← guarda el resultado
    │
    ▼
Django (status view)      ← AsyncResult consulta el estado
```

### 12.3 Definir una tarea

```python
# Cabildo_api/task/tasks.py

from celery import shared_task
import logging

logger = logging.getLogger('api')

@shared_task(bind=True, name='generar_reporte_recaudacion')
def generar_reporte_recaudacion(self, fecha_inicio, fecha_fin):
    """
    bind=True  → permite usar self.update_state() para reportar progreso
    name=      → nombre único de la tarea en Celery
    """
    try:
        # Reportar progreso — visible desde el endpoint de status
        self.update_state(state='PROCESSING', meta={
            'progress': 10,
            'status': 'Consultando datos...'
        })

        # Ejecutar la consulta larga
        with connection.cursor() as cursor:
            cursor.execute(SQL_RECAUDACION, {
                'fecha_inicio': fecha_inicio,
                'fecha_fin':    fecha_fin,
            })
            cols = [c[0] for c in cursor.description]
            rows = cursor.fetchall()

        self.update_state(state='PROCESSING', meta={'progress': 50, 'status': 'Procesando...'})

        data = [{col: val for col, val in zip(cols, row)} for row in rows]

        # Guardar resultado en archivo JSON
        filename = f'recaudacion_{fecha_inicio}_{fecha_fin}.json'
        filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', filename)
        with open(filepath, 'w') as f:
            json.dump(data, f)

        # Retornar metadata del resultado
        return {
            'status': 'SUCCESS',
            'records': len(data),
            'file': f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(f"Error en tarea: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
```

### 12.4 Lanzar una tarea desde una view

```python
# .delay() envía la tarea a la cola de Redis y retorna inmediatamente
task = generar_reporte_recaudacion.delay(fecha_inicio, fecha_fin)

# task.id es el UUID que el cliente usará para consultar el estado
print(task.id)  # "7b408735-41a5-4cae-be44-26e91ee62162"
```

### 12.5 Consultar el estado de una tarea

```python
# Cabildo_api/consultas/views/base.py

from celery.result import AsyncResult

class TaskStatusAPIView(BaseAPIView):
    def get(self, request, task_id):
        task_result = AsyncResult(task_id)
        state = task_result.state  # PENDING | PROCESSING | SUCCESS | FAILURE

        if state == 'PENDING':
            return Response({'status': state, 'message': 'En cola...'})

        elif state == 'PROCESSING':
            info = task_result.info or {}
            return Response({
                'status': state,
                'progress': info.get('progress', 0),  # 0-100
                'message': info.get('status', 'Procesando...'),
            })

        elif state == 'SUCCESS':
            return Response({
                'status': state,
                'result': task_result.result,  # lo que retornó la tarea
                'message': 'Reporte generado exitosamente',
            })

        elif state == 'FAILURE':
            return Response({
                'status': state,
                'error': str(task_result.info),
                'message': 'Error al generar el reporte',
            })
```

### 12.6 Configuración de Celery

```python
# Cabildoapp/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cabildoapp.settings')

app = Celery('Cabildoapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()  # busca tasks.py en cada app instalada
```

```python
# settings.py
CELERY_BROKER_URL    = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'America/Guayaquil'
CELERY_TASK_TIME_LIMIT = 3600  # 1 hora — mata la tarea si se pasa
```

### 12.7 Estados de una tarea

| Estado | Descripción |
|--------|-------------|
| `PENDING` | En cola, esperando worker disponible |
| `PROCESSING` | Ejecutándose (estado personalizado con `update_state`) |
| `SUCCESS` | Completada correctamente |
| `FAILURE` | Falló con excepción |
| `REVOKED` | Cancelada manualmente |

---

## 13. Logging — Registrar eventos

### 13.1 ¿Por qué registrar logs?

Los logs permiten saber qué pasó en el servidor sin tener que reproducir el error:
- Qué endpoint fue llamado
- Con qué parámetros
- Cuánto tardó
- Qué error ocurrió y en qué línea

### 13.2 Configuración en `settings.py`

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} | {levelname} | {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'api': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### 13.3 Uso en el proyecto

```python
import logging
logger = logging.getLogger('api')

class RecaudacionImpuestoAPIView(BaseRecaudacionAPIView):
    def get(self, request):
        try:
            fecha_inicio, fecha_fin = self._get_fechas(request)

            # INFO — eventos normales
            logger.info(f"Consulta iniciada: {fecha_inicio} → {fecha_fin}")

            task = generar_reporte_recaudacion.delay(fecha_inicio, fecha_fin)

            logger.info(f"Tarea lanzada: {task.id}")
            return Response({'task_id': task.id}, status=202)

        except Exception as e:
            # ERROR — algo salió mal
            logger.error(f"Error inesperado: {str(e)}", exc_info=True)
            return Response({"detail": str(e)}, status=500)
```

### 13.4 Niveles de log

```python
logger.debug("Mensaje de depuración — muy detallado")    # solo en desarrollo
logger.info("Evento normal — consulta iniciada")          # producción
logger.warning("Algo raro pero no crítico")               # producción
logger.error("Algo falló — con traceback")                # producción
logger.critical("Fallo crítico del sistema")              # producción
```

---

## 14. Buenas prácticas

### 14.1 Validar parámetros siempre

```python
def _get_fechas(self, request):
    fecha_inicio = request.query_params.get('fecha_inicio')
    fecha_fin    = request.query_params.get('fecha_fin')

    # 1. Verificar que existan
    if not fecha_inicio or not fecha_fin:
        raise ValueError("Los parámetros 'fecha_inicio' y 'fecha_fin' son requeridos")

    # 2. Verificar formato
    datetime.strptime(fecha_inicio, '%Y-%m-%d')
    datetime.strptime(fecha_fin,    '%Y-%m-%d')

    # 3. Verificar lógica de negocio
    if fecha_inicio > fecha_fin:
        raise ValueError("'fecha_inicio' no puede ser mayor que 'fecha_fin'")

    return fecha_inicio, fecha_fin
```

### 14.2 Separar responsabilidades

```
urls.py         → solo rutas
views/          → solo recibir request, llamar lógica, devolver response
serializers/    → solo transformar y validar datos
tasks/          → solo lógica de negocio pesada (Celery)
permissions.py  → solo control de acceso
```

### 14.3 Usar variables de entorno para configuración sensible

```python
# settings.py — nunca hardcodear secretos
API_KEYS         = os.getenv('API_KEYS', '').split(',')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
```

```bash
# .env — este archivo NO va al repositorio git
API_KEYS=ClaveSecreta123,OtraClave456
CELERY_BROKER_URL=redis://redis:6379/0
```

### 14.4 Respuestas consistentes

Mantener siempre la misma estructura en los errores facilita el manejo en el frontend:

```python
# Siempre usar "detail" para el mensaje principal
{"detail": "Los parámetros son requeridos"}

# Siempre usar "error" para el detalle técnico
{"detail": "Error al ejecutar query", "error": "ORA-00942: table or view does not exist"}
```

### 14.5 Documentar los endpoints en el docstring

```python
class RecaudacionImpuestoAPIView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion/
    Inicia la generación asíncrona del reporte de recaudación por impuesto.
    Responde con HTTP 202 (Accepted) inmediatamente con un task_id.

    Query params requeridos:
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final   en formato YYYY-MM-DD

    Ejemplo: GET /api/recaudacion/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31
    """
```

---

## Resumen del flujo completo del proyecto

```
1. Cliente hace GET /api/recaudacion/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31
                │
                ▼
2. HasAPIKey.has_permission() verifica el header x-api-key
                │
          Inválida → 403
                │
          Válida  ↓
                ▼
3. RecaudacionImpuestoAPIView.get() se ejecuta
   - _get_fechas() valida los parámetros
   - generar_reporte_recaudacion.delay() encola la tarea en Redis
   - Retorna 202 con task_id
                │
                ▼
4. Celery Worker ejecuta generar_reporte_recaudacion()
   - Consulta Oracle con connection.cursor()
   - Actualiza progreso con self.update_state()
   - Guarda resultado en /media/reportes/recaudacion_....json
   - Retorna metadata con records y file
                │
                ▼
5. Cliente consulta GET /api/status/<task_id>/ cada 2 segundos
   - TaskStatusAPIView usa AsyncResult para consultar Redis
   - Retorna estado: PENDING → PROCESSING (0-100%) → SUCCESS
                │
                ▼
6. Cuando status = SUCCESS, cliente hace GET /api/recaudacion/datos/
   - RecaudacionDatosAPIView lee el archivo JSON del disco
   - Retorna los datos al cliente
```

---

*Guía generada en base al código real del proyecto Cabildo API*
