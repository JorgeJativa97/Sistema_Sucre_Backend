import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from Cabildo_api.consultas.serializers.bienes_inmuebles import BienesInmueblesSerializer
from Cabildo_api.permissions import HasAPIKey

logger = logging.getLogger('api')


class BienesInmueblesAPIView(APIView):
    """
    Endpoint: GET /api/bienes_inmuebles/
    Retorna el listado de bienes inmuebles (predios urbanos y rurales)
    en el formato requerido por el Anexo GAD del SRI
    (Resolución NAC-DGERCGC22-00000041).

    Combina mediante UNION ALL:
      - Predios urbanos: GEN01 / PUR06 / PUR01
      - Predios rurales: GEN01 / PRU10 / PRU01 / pru05
    """
    permission_classes = [HasAPIKey]

    def get(self, request):
        try:
            logger.info("BienesInmueblesAPIView - Consulta iniciada")

            data = BienesInmueblesSerializer.execute_query()
            serializer = BienesInmueblesSerializer(data, many=True)

            logger.info(f"BienesInmueblesAPIView - Consulta exitosa. Registros: {len(data)}")
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(
                f"BienesInmueblesAPIView - Error inesperado: {str(e)}",
                exc_info=True,
                extra={'method': 'GET', 'path': request.path},
            )
            return Response(
                {"detail": "Error al ejecutar consulta de bienes inmuebles", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
