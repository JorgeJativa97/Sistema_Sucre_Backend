from decimal import Decimal
import traceback

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from celery.result import AsyncResult

from Cabildo_api.permissions import HasAPIKey
import logging

logger = logging.getLogger('api')


class BaseAPIView(APIView):
    """
    Clase base global para todos los endpoints de la API.
    Provee:
      - Autenticación por API Key (header X-API-Key)
      - Ejecución de queries SQL contra la base de datos Oracle
      - Manejo de errores estandarizado con log y HTTP 500
    """
    permission_classes = [HasAPIKey]

    def _fetch_query(self, sql, params=None):
        """
        Ejecuta una query SQL y retorna una lista de diccionarios.
        Convierte automáticamente Decimal a float para serialización JSON.
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


class TaskStatusAPIView(BaseAPIView):
    """
    Endpoint: GET /api/status/<task_id>/
    Consulta el estado de cualquier tarea asíncrona Celery.
    Estados posibles: PENDING, PROCESSING, SUCCESS, FAILURE.
    """

    def get(self, request, task_id):
        try:
            task_result = AsyncResult(task_id)
            state = task_result.state

            response_data = {
                'task_id': task_id,
                'status': state,
            }

            if state == 'PENDING':
                response_data['message'] = 'El reporte está en cola...'
            elif state == 'PROCESSING':
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
            return self._handle_error(e, 'TaskStatusAPIView', request, task_id=task_id)
