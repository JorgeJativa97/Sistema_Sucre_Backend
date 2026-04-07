from decimal import Decimal
import traceback

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection

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
