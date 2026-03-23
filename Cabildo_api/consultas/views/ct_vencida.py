from datetime import datetime
from decimal import Decimal
import traceback
import json
import os

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.conf import settings
from celery.result import AsyncResult

from Cabildo_api.consultas.serializers.ct_vencida import CtVencidaSerializer
from Cabildo_api.permissions import HasAPIKey
from Cabildo_api.task.tasks import generar_reporte_cartera_vencida, generar_reporte_cartera_vencida_impuesto
import logging

logger = logging.getLogger('api')


# ── SQL Queries ────────────────────────────────────────────────────────────────
# Las queries están definidas como constantes al nivel del módulo para
# mantenerlas separadas de la lógica de las vistas y facilitar su mantenimiento.
# Todas usan funciones Oracle del ERP (web_interes, web_coactiva, etc.)
# y combinan dos grupos de registros con UNION ALL:
#   - Estado 'E' (Emitido): montos originales sin abonos
#   - Estado 'A' (abonado):  montos descontando pagos parciales (f_pagoabono)

SQL_IMPUESTO = """
SELECT COD,
       IMPUESTO,
       ANIO,
       SUM(EMISION) EMISION,
       SUM(INTERES) INTERES,
       SUM(COACTIVA) COACTIVA,
       SUM(RECARGO) RECARGO,
       SUM(DESCUENTO) DESCUENTO,
       SUM(IVA) IVA,
       SUM(TOTAL) TOTAL
FROM (
    SELECT
        a.emi01seri as COD,
        b.emi03des as IMPUESTO,
        a.emi01anio as ANIO,
        emi01vtot AS EMISION,
        NVL(CASE WHEN web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') < 0 THEN 0
             ELSE web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') END, 0) AS INTERES,
        NVL(web_coactiva(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01nrocoa,emi01fcoa),0) AS COACTIVA,
        web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) AS RECARGO,
        web_descuento(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) AS DESCUENTO,
        web_iva(emi01codi, emi01seri) AS IVA,
        emi01vtot
          + NVL(CASE WHEN web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') < 0 THEN 0
               ELSE web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') END, 0)
          + NVL(web_coactiva(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01nrocoa,emi01fcoa),0)
          + web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio)
          - web_descuento(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio)
          + web_iva(emi01codi, emi01seri) AS TOTAL,
        a.gen01codi,
        a.emi01clave
    FROM emi01 a
    LEFT JOIN emi03 b ON b.emi03codi = a.emi01seri
    WHERE emi01esta = 'E'
      AND EMI01ANIO <= :year

    UNION ALL

    SELECT
        a.emi01seri as COD,
        b.emi03des as IMPUESTO,
        a.emi01anio as ANIO,
        emi01vtot - f_pagoabono(emi01codi, 'E') AS EMISION,
        NVL(CASE WHEN web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') < 0 THEN 0
             ELSE web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') END, 0) AS INTERES,
        NVL(web_coactiva(emi01codi,emi01fobl,EMI01SERI,EMI01VTOT,EMI01NROCOA,EMI01FCOA),0) - f_pagoabono(emi01codi, 'C') AS COACTIVA,
        web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) - f_pagoabono(emi01codi, 'R') AS RECARGO,
        0 AS DESCUENTO,
        web_iva(emi01codi, emi01seri) - f_pagoabono(emi01codi, 'V') AS IVA,
        emi01vtot - f_pagoabono(emi01codi, 'E')
          + NVL(CASE WHEN web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') < 0 THEN 0
               ELSE web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') END, 0)
          + NVL(web_coactiva(emi01codi,emi01fobl,EMI01SERI,EMI01VTOT,EMI01NROCOA,EMI01FCOA),0) - f_pagoabono(emi01codi, 'C')
          + web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) - f_pagoabono(emi01codi, 'R')
          + web_iva(emi01codi, emi01seri) - f_pagoabono(emi01codi, 'V') AS TOTAL,
        a.gen01codi,
        a.emi01clave
    FROM emi01 a
    LEFT JOIN emi03 b ON b.emi03codi = a.emi01seri
    WHERE emi01esta = 'A'
      AND EMI01ANIO <= :year
)
GROUP BY COD, IMPUESTO, ANIO
ORDER BY ANIO DESC
"""

SQL_TITULOS = """
SELECT
    emi03codi as CODIGO,
    emi03des as DESCRIPCION
FROM emi03
WHERE EMI03CODI IN (1,2,3,5,6,7,8,11,13,19,22,
    24,28,34,35,45,47,51,54,55,60,76,77,78,92,95,100,
    125,129,130,133,135,136,140,141,142,146,167,169,184,
    201,401,402,403,404,407,408,421,427,430,1028,1029,1030)
ORDER BY 1 DESC
"""

SQL_TITULO_DETALLE = """
SELECT CEDULA,
       NOMBRE,
       CIU,
       IMPUESTO,
       EMISION,
       INTERES,
       COACTIVA,
       RECARGO,
       DESCUENTO,
       IVA,
       TOTAL
FROM (
    SELECT
        g.gen01ruc as CEDULA,
        g.gen01com as NOMBRE,
        a.emi01seri as COD,
        b.emi03des as IMPUESTO,
        a.emi01anio as ANIO,
        emi01vtot AS EMISION,
        NVL(CASE WHEN web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') < 0 THEN 0
            ELSE web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') END, 0) AS INTERES,
        NVL(web_coactiva(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01nrocoa,emi01fcoa),0) AS COACTIVA,
        web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) AS RECARGO,
        web_descuento(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) AS DESCUENTO,
        web_iva(emi01codi, emi01seri) AS IVA,
        emi01vtot
            + NVL(CASE WHEN web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') < 0 THEN 0
                ELSE web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') END, 0)
            + NVL(web_coactiva(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01nrocoa,emi01fcoa),0)
            + web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio)
            - web_descuento(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio)
            + web_iva(emi01codi, emi01seri) AS TOTAL,
        a.gen01codi as CIU,
        a.emi01clave
    FROM emi01 a
    LEFT JOIN emi03 b ON b.emi03codi = a.emi01seri
    INNER JOIN GEN01 g on a.gen01codi = g.gen01codi
    WHERE emi01esta = 'E'
        AND EMI01ANIO <= :year

    UNION ALL

    SELECT
        g.gen01ruc as CEDULA,
        g.gen01com as NOMBRE,
        a.emi01seri as COD,
        b.emi03des as IMPUESTO,
        a.emi01anio as ANIO,
        emi01vtot - f_pagoabono(emi01codi, 'E') AS EMISION,
        NVL(CASE WHEN web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') < 0 THEN 0
            ELSE web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') END, 0) AS INTERES,
        NVL(web_coactiva(emi01codi,emi01fobl,EMI01SERI,EMI01VTOT,EMI01NROCOA,EMI01FCOA),0) - f_pagoabono(emi01codi, 'C') AS COACTIVA,
        web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) - f_pagoabono(emi01codi, 'R') AS RECARGO,
        0 AS DESCUENTO,
        web_iva(emi01codi, emi01seri) - f_pagoabono(emi01codi, 'V') AS IVA,
        emi01vtot - f_pagoabono(emi01codi, 'E')
            + NVL(CASE WHEN web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') < 0 THEN 0
                ELSE web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') END, 0)
            + NVL(web_coactiva(emi01codi,emi01fobl,EMI01SERI,EMI01VTOT,EMI01NROCOA,EMI01FCOA),0) - f_pagoabono(emi01codi, 'C')
            + web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) - f_pagoabono(emi01codi, 'R')
            + web_iva(emi01codi, emi01seri) - f_pagoabono(emi01codi, 'V') AS TOTAL,
        a.gen01codi AS CIU,
        a.emi01clave
    FROM emi01 a
    LEFT JOIN emi03 b ON b.emi03codi = a.emi01seri
    INNER JOIN GEN01 g on a.gen01codi = g.gen01codi
    WHERE emi01esta = 'A'
        AND EMI01ANIO <= :year
)
ORDER BY 1 DESC
"""

# Usa .format(placeholders=...) antes de ejecutar
SQL_POR_IMPUESTO_TEMPLATE = """
SELECT
    COD,
    IMPUESTO,
    ANIO,
    SUM(EMISION) EMISION,
    SUM(INTERES) INTERES,
    SUM(COACTIVA) COACTIVA,
    SUM(RECARGO) RECARGO,
    SUM(DESCUENTO) DESCUENTO,
    SUM(IVA) IVA,
    SUM(TOTAL) TOTAL
FROM (
    SELECT
        a.emi01seri as COD,
        b.emi03des as IMPUESTO,
        a.emi01anio as ANIO,
        emi01vtot AS EMISION,
        NVL(CASE WHEN web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') < 0 THEN 0
            ELSE web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') END, 0) AS INTERES,
        NVL(web_coactiva(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01nrocoa,emi01fcoa),0) AS COACTIVA,
        web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) AS RECARGO,
        web_descuento(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) AS DESCUENTO,
        web_iva(emi01codi, emi01seri) AS IVA,
        emi01vtot
            + NVL(CASE WHEN web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') < 0 THEN 0
                ELSE web_interes(emi01codi,emi01fobl,emi01seri,emi01vtot) - F_PAGOABONO(EMI01CODI, 'I') END, 0)
            + NVL(web_coactiva(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01nrocoa,emi01fcoa),0)
            + web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio)
            - web_descuento(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio)
            + web_iva(emi01codi, emi01seri) AS TOTAL,
        a.gen01codi as CIU,
        a.emi01clave,
        G.GEN01COM AS NOMBRE,
        G.GEN01RUC AS IDENTIFICACION
    FROM emi01 a
    LEFT JOIN emi03 b ON b.emi03codi = a.emi01seri
    INNER JOIN GEN01 G ON G.GEN01CODI = A.GEN01CODI
    WHERE emi01esta = 'E'
        AND EMI01ANIO <= :year
        AND b.emi03codi IN ({placeholders})

    UNION ALL

    SELECT
        a.emi01seri as COD,
        b.emi03des as IMPUESTO,
        a.emi01anio as ANIO,
        emi01vtot - f_pagoabono(emi01codi, 'E') AS EMISION,
        NVL(CASE WHEN web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') < 0 THEN 0
            ELSE web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') END, 0) AS INTERES,
        NVL(web_coactiva(emi01codi,emi01fobl,EMI01SERI,EMI01VTOT,EMI01NROCOA,EMI01FCOA),0) - f_pagoabono(emi01codi, 'C') AS COACTIVA,
        web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) - f_pagoabono(emi01codi, 'R') AS RECARGO,
        0 AS DESCUENTO,
        web_iva(emi01codi, emi01seri) - f_pagoabono(emi01codi, 'V') AS IVA,
        emi01vtot - f_pagoabono(emi01codi, 'E')
            + NVL(CASE WHEN web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') < 0 THEN 0
                ELSE web_interesabono(emi01codi,emi01fobl,emi01seri,emi01vtot) - f_pagoabono(emi01codi, 'I') END, 0)
            + NVL(web_coactiva(emi01codi,emi01fobl,EMI01SERI,EMI01VTOT,EMI01NROCOA,EMI01FCOA),0) - f_pagoabono(emi01codi, 'C')
            + web_recargo(emi01codi,emi01fobl,emi01seri,emi01vtot,emi01anio) - f_pagoabono(emi01codi, 'R')
            + web_iva(emi01codi, emi01seri) - f_pagoabono(emi01codi, 'V') AS TOTAL,
        a.gen01codi AS CIU,
        a.emi01clave,
        G.GEN01COM AS NOMBRE,
        G.GEN01RUC AS IDENTIFICACION
    FROM emi01 a
    LEFT JOIN emi03 b ON b.emi03codi = a.emi01seri
    INNER JOIN GEN01 G ON G.GEN01CODI = A.GEN01CODI
    WHERE emi01esta = 'A'
        AND EMI01ANIO <= :year
        AND b.emi03codi IN ({placeholders})
)
GROUP BY COD, IMPUESTO, ANIO
ORDER BY ANIO DESC
"""


# ── Clase Base ─────────────────────────────────────────────────────────────────

class BaseCarteraAPIView(APIView):
    """
    Clase base para todos los endpoints de cartera vencida.
    Centraliza la validación del año, la ejecución de queries y el manejo de errores
    para evitar repetir el mismo código en cada vista.
    Requiere API Key en el header X-API-Key para acceder.
    """
    permission_classes = [HasAPIKey]

    def _get_year(self, request, year=None):
        """
        Resuelve el año desde el parámetro de URL o desde el query param ?year=.
        Si no se proporciona ninguno, usa el año actual.
        Lanza ValueError si el año no es un número positivo.
        """
        if year is None:
            year = request.query_params.get('year', datetime.now().year)
        year = int(year)
        if year <= 0:
            raise ValueError("El año debe ser un número positivo")
        return year

    def _fetch_query(self, sql, params=None):
        """
        Ejecuta una query SQL contra la base de datos Oracle y retorna
        una lista de diccionarios con los resultados.
        Convierte automáticamente los valores Decimal a float para
        que sean serializables en JSON.
        """
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
        """
        Registra el error en el log con contexto de la petición
        y retorna una respuesta HTTP 500 estandarizada.
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


# ── Views ───────────────────────────────────────────────────────────────────────

class CtVencidaSerializerAPIView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida/<year>/
    Inicia la generación asíncrona del reporte completo de cartera vencida.
    No espera a que termine — delega el trabajo a Celery y devuelve un task_id
    que el cliente puede usar para consultar el progreso.
    Responde con HTTP 202 (Accepted) inmediatamente.
    """

    def get(self, request, year=None):
        try:
            year = self._get_year(request, year)
            logger.info(f"CtVencidaSerializerAPIView - Consulta iniciada para year={year}")

            # Encola la tarea en Celery para ejecutarse en segundo plano
            task = generar_reporte_cartera_vencida.delay(year)

            return Response({
                'task_id': task.id,
                'status': 'PENDING',
                'message': f'Generando reporte para el año {year}. Use el task_id para consultar el estado.'
            }, status=status.HTTP_202_ACCEPTED)
        except ValueError as e:
            return Response(
                {"error": "Parámetro year inválido", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class CtVencidaStatusAPIView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida/status/<task_id>/
    Consulta el estado de una tarea asíncrona previamente iniciada.
    Retorna el progreso (0-100%) mientras procesa, o el resultado final
    cuando termina. Estados posibles: PENDING, PROCESSING, SUCCESS, FAILURE.
    """

    def get(self, request, task_id):
        try:
            # AsyncResult permite consultar el estado de una tarea Celery por su ID.
            # Puede lanzar redis.exceptions.ConnectionError si Redis no está disponible.
            task_result = AsyncResult(task_id)
            state = task_result.state

            response_data = {
                'task_id': task_id,
                'status': state,
            }

            if state == 'PENDING':
                response_data['message'] = 'El reporte está en cola...'
            elif state == 'PROCESSING':
                # task_result.info puede ser None si update_state aún no fue llamado
                info = task_result.info or {}
                response_data['progress'] = info.get('progress', 0)
                response_data['message'] = info.get('status', 'Procesando...')
            elif state == 'SUCCESS':
                response_data['result'] = task_result.result
                response_data['message'] = 'Reporte generado exitosamente'
            elif state == 'FAILURE':
                response_data['error'] = str(task_result.info)
                response_data['message'] = 'Error al generar el reporte'

            return Response(response_data)
        except Exception as e:
            return self._handle_error(e, 'CtVencidaStatusAPIView', request, task_id=task_id)


class CtVencidaImpuestoAPIView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida_impuesto/<year>/
    Inicia la generación asíncrona del reporte de cartera vencida por impuesto.
    Responde con HTTP 202 (Accepted) inmediatamente con un task_id.
    """

    def get(self, request, year=None):
        try:
            year = self._get_year(request, year)
            logger.info(f"CtVencidaImpuestoAPIView - Consulta iniciada para year={year}")

            task = generar_reporte_cartera_vencida_impuesto.delay(year)

            return Response({
                'task_id': task.id,
                'status': 'PENDING',
                'message': f'Generando reporte por impuesto para el año {year}. Use el task_id para consultar el estado.'
            }, status=status.HTTP_202_ACCEPTED)
        except ValueError as e:
            logger.warning(f"CtVencidaImpuestoAPIView - Parámetro year inválido: {e}")
            return Response(
                {"detail": "Parámetro year inválido", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class CtVencidaImpuestoDatosAPIView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida_impuesto/datos/<year>/
    Retorna el contenido del reporte JSON generado por la tarea Celery.
    Se llama después de que el status es SUCCESS para obtener los datos completos.
    """

    def get(self, request, year):
        try:
            year = self._get_year(request, year)
            filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', f'cartera_vencida_impuesto_{year}.json')

            if not os.path.exists(filepath):
                logger.warning(f"CtVencidaImpuestoDatosAPIView - Archivo no encontrado: {filepath}")
                return Response(
                    {"detail": f"No se encontró el reporte por impuesto para el año {year}. Genérelo primero."},
                    status=status.HTTP_404_NOT_FOUND
                )

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"CtVencidaImpuestoDatosAPIView - Archivo servido: {filepath} ({len(data)} registros)")
            return Response(data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(e, 'CtVencidaImpuestoDatosAPIView', request, year=year)


class CtVencidaPorTituloAPIView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida_titulo/
    Retorna la lista de títulos/tipos de impuesto disponibles (código y descripción).
    No requiere parámetros. Útil para poblar filtros o selectores en el frontend.
    """

    def get(self, request):
        try:
            logger.info("CtVencidaPorTituloAPIView - Consulta iniciada")

            result = self._fetch_query(SQL_TITULOS)

            logger.info(f"CtVencidaPorTituloAPIView - Consulta exitosa. Registros: {len(result)}")
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return self._handle_error(e, 'CtVencidaPorTituloAPIView', request)


class CtVencidaPorTituloDetalleAPIView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida_titulo_detalle/<year>/
    Retorna el detalle de cartera vencida por contribuyente (cédula, nombre)
    incluyendo todos los valores de cada título de impuesto hasta el año indicado.
    """

    def get(self, request, year=None):
        try:
            year = self._get_year(request, year)
            logger.info(f"CtVencidaPorTituloDetalleAPIView - Consulta iniciada para year={year}")

            result = self._fetch_query(SQL_TITULO_DETALLE, {'year': year})

            logger.info(f"CtVencidaPorTituloDetalleAPIView - Consulta exitosa. Registros: {len(result)}")
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            logger.warning(f"CtVencidaPorTituloDetalleAPIView - Parámetro year inválido: {e}")
            return Response(
                {"detail": "Parámetro year inválido", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return self._handle_error(e, 'CtVencidaPorTituloDetalleAPIView', request, year=year)


class CtVPorimpuestoSerializerApiView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida_porimpuesto/<year>/?codigos=95,140,200
    Retorna la cartera vencida filtrada por uno o varios códigos de impuesto específicos.
    El parámetro 'codigos' es obligatorio y acepta valores separados por coma.
    Los resultados se agrupan por tipo de impuesto y año.
    """

    def get(self, request, year=None):
        try:
            year = self._get_year(request, year)

            # Validar que se proporcionó el parámetro codigos
            codigos_param = request.query_params.get('codigos')
            if not codigos_param or not codigos_param.strip():
                logger.warning("CtVPorimpuestoSerializerApiView - Parámetro codigos no proporcionado")
                return Response(
                    {"detail": "El parámetro 'codigos' es requerido",
                     "error": "Debe proporcionar al menos un código de impuesto. Ejemplo: ?codigos=95 o ?codigos=95,140,200"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Convertir "95,140,200" → [95, 140, 200] validando que sean enteros
            try:
                codigos_list = [int(c.strip()) for c in codigos_param.split(',') if c.strip()]
                if not codigos_list:
                    raise ValueError("Debe proporcionar al menos un código de impuesto válido")
            except ValueError as ve:
                logger.warning(f"CtVPorimpuestoSerializerApiView - Parámetro codigos inválido: '{codigos_param}' - {ve}")
                return Response(
                    {"detail": f"Parámetro codigos inválido: '{codigos_param}'", "error": str(ve)},
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"CtVPorimpuestoSerializerApiView - Consulta iniciada para year={year}, codigos={codigos_list}")

            # Construir placeholders Oracle (:cod0, :cod1, ...) para la cláusula IN
            # Esto evita SQL injection al no concatenar los valores directamente
            placeholders = ', '.join([f':cod{i}' for i in range(len(codigos_list))])
            sql = SQL_POR_IMPUESTO_TEMPLATE.format(placeholders=placeholders)

            # Armar el diccionario de parámetros: {year: X, cod0: 95, cod1: 140, ...}
            params = {'year': year}
            params.update({f'cod{i}': cod for i, cod in enumerate(codigos_list)})

            result = self._fetch_query(sql, params)
            logger.info(f"CtVPorimpuestoSerializerApiView - Consulta exitosa. Registros: {len(result)}")
            return Response(result, status=status.HTTP_200_OK)

        except ValueError as e:
            logger.warning(f"CtVPorimpuestoSerializerApiView - Parámetro inválido: {e}")
            return Response(
                {"detail": "Parámetro inválido", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return self._handle_error(e, 'CtVPorimpuestoSerializerApiView', request, year=year)


class CtVencidaDatosAPIView(BaseCarteraAPIView):
    """
    Endpoint: GET /api/ct_vencida/datos/<year>/
    Retorna el contenido del reporte JSON generado por la tarea Celery.
    Se llama después de que el status es SUCCESS para obtener los datos completos.
    El archivo fue guardado en MEDIA_ROOT/reportes/cartera_vencida_<year>.json
    por la tarea generar_reporte_cartera_vencida.
    """

    def get(self, request, year):
        try:
            year = self._get_year(request, year)
            filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', f'cartera_vencida_{year}.json')

            if not os.path.exists(filepath):
                logger.warning(f"CtVencidaDatosAPIView - Archivo no encontrado: {filepath}")
                return Response(
                    {"detail": f"No se encontró el reporte para el año {year}. Genérelo primero."},
                    status=status.HTTP_404_NOT_FOUND
                )

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"CtVencidaDatosAPIView - Archivo servido: {filepath} ({len(data)} registros)")
            return Response(data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(e, 'CtVencidaDatosAPIView', request, year=year)
