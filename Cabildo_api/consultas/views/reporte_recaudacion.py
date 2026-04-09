from datetime import datetime
import json
import os

from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from Cabildo_api.consultas.views.base import BaseAPIView
from Cabildo_api.task.tasks import generar_reporte_recaudacion, generar_reporte_recaudacion_rubro, generar_reporte_recaudacion_rubro_anio_emi
import logging

logger = logging.getLogger('api')


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
