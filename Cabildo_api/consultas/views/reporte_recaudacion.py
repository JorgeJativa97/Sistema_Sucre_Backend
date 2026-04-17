from datetime import datetime
import json
import os

from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from Cabildo_api.consultas.views.base import BaseAPIView
from Cabildo_api.task.tasks import (
    generar_reporte_recaudacion,
    generar_reporte_recaudacion_impuesto_emi_ids,
    generar_reporte_recaudacion_rubro,
    generar_reporte_recaudacion_rubro_anio_emi,
    generar_reporte_recaudacion_rubro_anio_emi_ids,
)
import logging

logger = logging.getLogger('api')

_SQL_RUBROS = """
SELECT EMI04CODI, EMI04DESD, EMI03DES
FROM EMI04
INNER JOIN EMI03 ON EMI03.EMI03CODI = EMI04.EMI03CODI
WHERE EMI03BLOQ = 'N'
AND emi03.emi03codi <> 99999
ORDER BY EMI03DES, EMI04DESD
"""

_SQL_impuesto = """
SELECT * FROM EMI03 WHERE EMI03BLOQ = 'N' 
AND emi03.emi03codi <> 99999 
ORDER BY 1 DESC
"""


class BaseRecaudacionAPIView(BaseAPIView):
    """
    Clase base para los endpoints de recaudación.
    Hereda autenticación, conexión a BD y manejo de errores de BaseAPIView.
    Centraliza la validación de los parámetros de fechas comunes a todos
    los reportes de recaudación.
    """

    def _get_fechas(self, request):
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin    = request.query_params.get('fecha_fin')

        if not fecha_inicio or not fecha_fin:
            raise ValueError("Los parámetros 'fecha_inicio' y 'fecha_fin' son requeridos (formato YYYY-MM-DD)")

        datetime.strptime(fecha_inicio, '%Y-%m-%d')
        datetime.strptime(fecha_fin,    '%Y-%m-%d')

        if fecha_inicio > fecha_fin:
            raise ValueError("'fecha_inicio' no puede ser mayor que 'fecha_fin'")

        return fecha_inicio, fecha_fin
    
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

    def get(self, request):
        try:
            fecha_inicio, fecha_fin = self._get_fechas(request)
            logger.info(f"RecaudacionImpuestoAPIView - Consulta iniciada: {fecha_inicio} → {fecha_fin}")

            task = generar_reporte_recaudacion.delay(fecha_inicio, fecha_fin)

            return Response({
                'task_id': task.id,
                'status': 'PENDING',
                'message': f'Generando reporte de recaudación del {fecha_inicio} al {fecha_fin}. Use el task_id para consultar el estado.',
            }, status=status.HTTP_202_ACCEPTED)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionImpuestoAPIView', request,
                fecha_inicio=request.query_params.get('fecha_inicio'),
                fecha_fin=request.query_params.get('fecha_fin'),
            )


class RecaudacionDatosAPIView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion/datos/
    Retorna el contenido del reporte JSON generado por la tarea Celery.
    Se llama después de que el status es SUCCESS para obtener los datos completos.

    Query params requeridos:
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final   en formato YYYY-MM-DD
    """

    def get(self, request):
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin    = request.query_params.get('fecha_fin')

        if not fecha_inicio or not fecha_fin:
            return Response(
                {"detail": "Los parámetros 'fecha_inicio' y 'fecha_fin' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            filename = f'recaudacion_{fecha_inicio}_{fecha_fin}.json'
            filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', filename)

            if not os.path.exists(filepath):
                logger.warning(f"RecaudacionDatosAPIView - Archivo no encontrado: {filepath}")
                return Response(
                    {"detail": f"No se encontró el reporte para el rango {fecha_inicio} / {fecha_fin}. Genérelo primero."},
                    status=status.HTTP_404_NOT_FOUND
                )

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"RecaudacionDatosAPIView - Archivo servido: {filename} ({len(data)} registros)")
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionDatosAPIView', request,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )


class RecaudacionRubroApiView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion_rubro/
    Inicia la generación asíncrona del reporte de recaudación por rubro.
    Responde con HTTP 202 (Accepted) inmediatamente con un task_id.

    Query params requeridos:
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final   en formato YYYY-MM-DD

    Ejemplo: GET /api/recaudacion_rubro/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31
    """

    def get(self, request):
        try:
            fecha_inicio, fecha_fin = self._get_fechas(request)
            logger.info(f"RecaudacionRubroApiView - Consulta iniciada: {fecha_inicio} → {fecha_fin}")

            task = generar_reporte_recaudacion_rubro.delay(fecha_inicio, fecha_fin)

            return Response({
                'task_id': task.id,
                'status': 'PENDING',
                'message': f'Generando reporte de recaudación por rubro del {fecha_inicio} al {fecha_fin}. Use el task_id para consultar el estado.',
            }, status=status.HTTP_202_ACCEPTED)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionRubroApiView', request,
                fecha_inicio=request.query_params.get('fecha_inicio'),
                fecha_fin=request.query_params.get('fecha_fin'),
            )


class RecaudacionRubroDatosAPIView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion_rubro/datos/
    Retorna el contenido del reporte JSON de recaudación por rubro generado por Celery.
    Se llama después de que el status es SUCCESS para obtener los datos completos.

    Query params requeridos:
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final   en formato YYYY-MM-DD
    """

    def get(self, request):
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin    = request.query_params.get('fecha_fin')

        if not fecha_inicio or not fecha_fin:
            return Response(
                {"detail": "Los parámetros 'fecha_inicio' y 'fecha_fin' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            filename = f'recaudacion_rubro_{fecha_inicio}_{fecha_fin}.json'
            filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', filename)

            if not os.path.exists(filepath):
                logger.warning(f"RecaudacionRubroDatosAPIView - Archivo no encontrado: {filepath}")
                return Response(
                    {"detail": f"No se encontró el reporte por rubro para el rango {fecha_inicio} / {fecha_fin}. Genérelo primero."},
                    status=status.HTTP_404_NOT_FOUND
                )

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"RecaudacionRubroDatosAPIView - Archivo servido: {filename} ({len(data)} registros)")
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionRubroDatosAPIView', request,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )

class RecaudacionRubroAnioEmiApiView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion_rubro_anioemi/
    Inicia la generación asíncrona del reporte de recaudación por rubro por año de emision.
    Responde con HTTP 202 (Accepted) inmediatamente con un task_id.

    Query params requeridos:
        anio 
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final   en formato YYYY-MM-DD

    Ejemplo: GET /api/recaudacion_rubro/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31
    """
    def get(self, request, year=None):
        try:
            year = self._get_year(request, year)
            fecha_inicio, fecha_fin = self._get_fechas(request)

            logger.info(f"RecaudacionRubAnioEmisionroApiView - Consulta iniciada:{year} → {fecha_inicio} → {fecha_fin}")

            task = generar_reporte_recaudacion_rubro_anio_emi.delay(year,fecha_inicio, fecha_fin)

            return Response({
                'task_id': task.id,
                'status': 'PENDING',
                'message': f'Generando reporte de recaudación de rubro por año de emision del año {year} desde {fecha_inicio} al {fecha_fin}. Use el task_id para consultar el estado.',
            }, status=status.HTTP_202_ACCEPTED)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionRubroAnioEmiApiView', request,
                year = request.query_params.get('year'),
                fecha_inicio=request.query_params.get('fecha_inicio'),
                fecha_fin=request.query_params.get('fecha_fin'),
            ) 
        

class RecaudacionRubroAnioEmiDatosAPIView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion_rubro_anio_emi/datos/
    Retorna el contenido del reporte JSON de recaudación por rubro por año de emisión generado por Celery.
    Se llama después de que el status es SUCCESS para obtener los datos completos.

    Query params requeridos:
        year          — año de emisión (ej: 2025)
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final   en formato YYYY-MM-DD
    """
    def get(self, request):
        year         = request.query_params.get('year')
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin    = request.query_params.get('fecha_fin')

        if not fecha_inicio or not fecha_fin or not year:
            return Response(
                {"detail": "Los parámetros 'year', 'fecha_inicio' y 'fecha_fin' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            filename = f'recaudacion_rubro_anio_emi_{year}_{fecha_inicio}_{fecha_fin}.json'
            filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', filename)

            if not os.path.exists(filepath):
                logger.warning(f"RecaudacionRubroAnioEmiDatosAPIView - Archivo no encontrado: {filepath}")
                return Response(
                    {"detail": f"No se encontró el reporte de rubro por año de emision para el rango {year} / {fecha_inicio} / {fecha_fin}. Genérelo primero."},
                    status=status.HTTP_404_NOT_FOUND
                )

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"RecaudacionRubroAnioEmiDatosAPIView - Archivo servido: {filename} ({len(data)} registros)")
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionRubroAnioEmiDatosAPIView', request,
                year=year,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )


class RecaudacionRubroAnioEmiIdsApiView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion_rubro_anio_emi_ids/
    Inicia la generación asíncrona del reporte de recaudación por rubro por año de
    emisión filtrando por una lista de hasta 4 ids de rubro (EMI04CODI).
    Responde con HTTP 202 (Accepted) con un task_id.

    Query params requeridos:
        year          — año de emisión (ej: 2026)
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final en formato YYYY-MM-DD
        emi04codi     — lista de ids separados por coma (máximo 4), ej: 138,1,108,133

    Ejemplo:
        GET /api/recaudacion_rubro_anio_emi_ids/?year=2026
            &fecha_inicio=2026-01-01&fecha_fin=2026-03-24
            &emi04codi=138,1,108,133
    """

    MAX_IDS = 4

    def _get_emi04codi_ids(self, request):
        raw = request.query_params.get('emi04codi')
        if not raw:
            raise ValueError("El parámetro 'emi04codi' es requerido (ej: 138,1,108,133)")

        try:
            ids = [int(x) for x in raw.split(',') if x.strip() != '']
        except ValueError:
            raise ValueError("'emi04codi' debe ser una lista de enteros separados por coma")

        if not ids:
            raise ValueError("Debe proporcionar al menos un id en 'emi04codi'")
        if len(ids) > self.MAX_IDS:
            raise ValueError(f"'emi04codi' admite un máximo de {self.MAX_IDS} ids")

        return ids

    def get(self, request, year=None):
        try:
            year = self._get_year(request, year)
            fecha_inicio, fecha_fin = self._get_fechas(request)
            emi04codi_ids = self._get_emi04codi_ids(request)

            logger.info(
                f"RecaudacionRubroAnioEmiIdsApiView - Consulta iniciada: "
                f"{year} → {fecha_inicio} → {fecha_fin} → ids={emi04codi_ids}"
            )

            task = generar_reporte_recaudacion_rubro_anio_emi_ids.delay(
                year, fecha_inicio, fecha_fin, emi04codi_ids
            )

            return Response({
                'task_id': task.id,
                'status':  'PENDING',
                'message': (
                    f'Generando reporte de recaudación por rubro del año {year} '
                    f'desde {fecha_inicio} al {fecha_fin} para los rubros {emi04codi_ids}. '
                    f'Use el task_id para consultar el estado.'
                ),
            }, status=status.HTTP_202_ACCEPTED)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionRubroAnioEmiIdsApiView', request,
                year=request.query_params.get('year'),
                fecha_inicio=request.query_params.get('fecha_inicio'),
                fecha_fin=request.query_params.get('fecha_fin'),
                emi04codi=request.query_params.get('emi04codi'),
            )


class RecaudacionRubroAnioEmiIdsDatosAPIView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion_rubro_anio_emi_ids/datos/
    Retorna el contenido del reporte JSON generado por la tarea Celery.

    Query params requeridos:
        year          — año de emisión (ej: 2026)
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final en formato YYYY-MM-DD
        emi04codi     — lista de ids separados por coma (máximo 4)
    """

    def get(self, request):
        year         = request.query_params.get('year')
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin    = request.query_params.get('fecha_fin')
        emi04codi    = request.query_params.get('emi04codi')

        if not year or not fecha_inicio or not fecha_fin or not emi04codi:
            return Response(
                {"detail": "Los parámetros 'year', 'fecha_inicio', 'fecha_fin' y 'emi04codi' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            try:
                ids = [int(x) for x in emi04codi.split(',') if x.strip() != '']
            except ValueError:
                return Response(
                    {"detail": "'emi04codi' debe ser una lista de enteros separados por coma"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            ids_str = '-'.join(str(i) for i in ids)
            filename = f'recaudacion_rubro_anio_emi_ids_{year}_{fecha_inicio}_{fecha_fin}_{ids_str}.json'
            filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', filename)

            if not os.path.exists(filepath):
                logger.warning(f"RecaudacionRubroAnioEmiIdsDatosAPIView - Archivo no encontrado: {filepath}")
                return Response(
                    {"detail": f"No se encontró el reporte para {year}/{fecha_inicio}/{fecha_fin}/{ids}. Genérelo primero."},
                    status=status.HTTP_404_NOT_FOUND
                )

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"RecaudacionRubroAnioEmiIdsDatosAPIView - Archivo servido: {filename} ({len(data)} registros)")
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionRubroAnioEmiIdsDatosAPIView', request,
                year=year,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                emi04codi=emi04codi,
            )



class RubrosListAPIView(BaseAPIView):
    """
    Endpoint: GET /api/rubros/
    Retorna el catálogo de rubros activos (EMI03BLOQ = 'N').

    Respuesta: lista de objetos con EMI04CODI, EMI04DESD y EMI03DES.
    """

    def get(self, request):
        try:
            data = self._fetch_query(_SQL_RUBROS)
            logger.info(f"RubrosListAPIView - {len(data)} rubros retornados")
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return self._handle_error(e, 'RubrosListAPIView', request)
        

class RecaudacionImpuestoFiltradoAPIView(BaseAPIView):
    """
    Endpoint: GET /api/recaudacion_impuesto/
    Inicia la generación asíncrona del reporte de recaudación por impuesto filtrado por impuesto.
    Responde con HTTP 202 (Accepted) inmediatamente con un task_id.

    Query params requeridos:
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final   en formato YYYY-MM-DD
        emi03codi     — lista de ids separados por coma (máximo 4)

    Ejemplo: GET /api/recaudacion_impuesto_filtro/?fecha_inicio=2025-01-01&fecha_fin=2025-12-31&emi03codi=138,1,108,133
    """
    MAX_IDS = 4

    def _get_emi03codi_ids(self, request):
        raw = request.query_params.get('emi03codi')
        if not raw:
            raise ValueError("El parámetro 'emi03codi' es requerido (ej: 138,1,108,133)")

        try:
            ids = [int(x) for x in raw.split(',') if x.strip() != '']
        except ValueError:
            raise ValueError("'emi03codi' debe ser una lista de enteros separados por coma")

        if not ids:
            raise ValueError("Debe proporcionar al menos un id en 'emi03codi'")
        if len(ids) > self.MAX_IDS:
            raise ValueError(f"'emi03codi' admite un máximo de {self.MAX_IDS} ids")

        return ids

    def get(self, request):
        try:
            fecha_inicio, fecha_fin = self._get_fechas(request)
            emi03codi_ids = self._get_emi03codi_ids(request)

            logger.info(
                f"RecaudacionRubroAnioEmiIdsApiView - Consulta iniciada: "
                f"{fecha_inicio} → {fecha_fin} → ids={emi03codi_ids}"
            )

            task = generar_reporte_recaudacion_impuesto_emi_ids.delay(
                fecha_inicio, fecha_fin, emi03codi_ids
            )

            return Response({
                'task_id': task.id,
                'status':  'PENDING',
                'message': (
                    f'Generando reporte de recaudación filtrado por impuesto '
                    f'desde {fecha_inicio} al {fecha_fin} para los impuestos {emi03codi_ids}. '
                    f'Use el task_id para consultar el estado.'
                ),
            }, status=status.HTTP_202_ACCEPTED)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionImpuestoFiltradoAPIView', request,
                fecha_inicio=request.query_params.get('fecha_inicio'),
                fecha_fin=request.query_params.get('fecha_fin'),
                emi04codi=request.query_params.get('emi04codi'),
            )

class RecaudacionImpuestoFiltradoDatosAPIView(BaseRecaudacionAPIView):
    """
    Endpoint: GET /api/recaudacion_impuesto_ids/datos/
    Retorna el contenido del reporte JSON generado por la tarea Celery.

    Query params requeridos:
        fecha_inicio  — fecha inicial en formato YYYY-MM-DD
        fecha_fin     — fecha final en formato YYYY-MM-DD
        emi03codi     — lista de ids separados por coma (máximo 4)
    """

    def get(self, request):
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin    = request.query_params.get('fecha_fin')
        emi03codi    = request.query_params.get('emi03codi')

        try:
            try:
                ids = [int(x) for x in emi03codi.split(',') if x.strip() != '']
            except ValueError:
                return Response(
                    {"detail": "'emi03codi' debe ser una lista de enteros separados por coma"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            ids_str = '-'.join(str(i) for i in ids)
            filename = f'recaudacion_impuesto_emi_ids_{fecha_inicio}_{fecha_fin}_{ids_str}.json'
            filepath = os.path.join(settings.MEDIA_ROOT, 'reportes', filename)

            if not os.path.exists(filepath):
                logger.warning(f"RecaudacionImpuestoFiltradoDatosAPIView - Archivo no encontrado: {filepath}")
                return Response(
                    {"detail": f"No se encontró el reporte para {fecha_inicio}/{fecha_fin}/{ids}. Genérelo primero."},
                    status=status.HTTP_404_NOT_FOUND
                )

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"RecaudacionImpuestoFiltradoDatosAPIView - Archivo servido: {filename} ({len(data)} registros)")
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return self._handle_error(
                e, 'RecaudacionImpuestoFiltradoDatosAPIView', request,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                emi03codi=emi03codi,
            )
        
class ImpuestoListAPIView(BaseAPIView):
    """
    Endpoint: GET /api/impuesto/
    Retorna el catálogo de impuesto activos (EMI03BLOQ = 'N').

    Respuesta: lista de objetos con EMI03DES.
    """

    def get(self, request):
        try:
            data = self._fetch_query(_SQL_impuesto)
            logger.info(f"impuestoListAPIView - {len(data)} impuesto retornados")
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return self._handle_error(e, 'impuestoListAPIView', request)