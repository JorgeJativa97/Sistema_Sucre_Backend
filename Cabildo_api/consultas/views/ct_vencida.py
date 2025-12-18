from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from Cabildo_api.consultas.serializers.ct_vencida import CtVencidaSerializer
from Cabildo_api.permissions import HasAPIKey
import logging
import traceback
from django.db import connection
from decimal import Decimal

logger = logging.getLogger('api')


class CtVencidaSerializerAPIView(APIView):
    permission_classes = [HasAPIKey]

    def get(self, request, year=None):
        try:
            # Si no viene en la URL, intentar obtenerlo del query param
            if year is None:
                year_param = request.query_params.get('year', None)
                if year_param:
                    year = int(year_param)
            
            logger.info(f"CtVencidaSerializerAPIView - Consulta iniciada para year={year}")

            # Ejecutar query y obtener datos crudos
            raw_data = CtVencidaSerializer.execute_query(year=year)

            # Serializar los datos (opcional, para validación y formato)
            serializer = CtVencidaSerializer(raw_data, many=True)
            
            logger.info(f"CtVencidaSerializerAPIView - Consulta exitosa. Registros: {len(serializer.data)}")

            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            logger.warning(f"CtVencidaSerializerAPIView - Parámetro year inválido: {e}")
            return Response(
                {
                    "error": "Parámetro year inválido",
                    "detail": str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            error_detail = traceback.format_exc()
            logger.error(
                f"CtVencidaSerializerAPIView - Error inesperado: {str(e)}\n{error_detail}",
                exc_info=True,
                extra={
                    'year': year,
                    'method': 'GET',
                    'path': request.path,
                    'user': getattr(request.user, 'username', 'anonymous')
                }
            )
            return Response(
                {
                    "error": "Error al procesar la solicitud",
                    "detail": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CtVencidaImpuestoAPIView(APIView):
    permission_classes = [HasAPIKey]

    def get(self, request, year=None):
        try:
            # Si no viene year en la URL, buscar en query params
            if year is None:
                year_param = request.query_params.get('year')
                if year_param:
                    year = int(year_param)
                else:
                    # Si no se proporciona, usar año actual
                    from datetime import datetime
                    year = datetime.now().year
            
            # Validar que year sea un entero válido
            try:
                year_int = int(year)
                if year_int <= 0:
                    raise ValueError("El año debe ser un número positivo")
            except ValueError as ve:
                logger.warning(f"CtVencidaImpuestoAPIView - Parámetro year inválido: '{year}' - {ve}")
                return Response(
                    {"detail": f"Parámetro year inválido: '{year}'", "error": str(ve)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info(f"CtVencidaImpuestoAPIView - Consulta iniciada para year={year}")

            sql = """
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

            with connection.cursor() as cursor:
                cursor.execute(sql, {'year': year})
                cols = [c[0] for c in cursor.description]
                rows = cursor.fetchall()

            # Normalizar Decimals a float
            result = [
                {col: (float(val) if isinstance(val, Decimal) else val) for col, val in zip(cols, row)}
                for row in rows
            ]
            
            logger.info(f"CtVencidaImpuestoAPIView - Consulta exitosa. Registros: {len(result)}")
            
            return Response(result, status=status.HTTP_200_OK)

        except ValueError as e:
            logger.warning(f"CtVencidaImpuestoAPIView - Parámetro year inválido: {e}")
            return Response(
                {"detail": "Parámetro year inválido", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            error_detail = traceback.format_exc()
            logger.error(
                f"CtVencidaImpuestoAPIView - Error inesperado: {str(e)}\n{error_detail}",
                exc_info=True,
                extra={
                    'year': year,
                    'method': 'GET',
                    'path': request.path,
                    'user': getattr(request.user, 'username', 'anonymous')
                }
            )
            return Response(
                {"detail": "Error al ejecutar query", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CtVencidaPorTituloAPIView(APIView):
    permission_classes = [HasAPIKey]

    def get(self, request):
        try:
            logger.info("CtVencidaPorTituloAPIView - Consulta iniciada")

            sql = """
             select 
                emi03codi as CODIGO,
                emi03des as DESCRIPCION
                from emi03
                WHERE EMI03CODI IN (1,2,3,5,6,7,8,11,13,19,22,
                24,28,34,35,45,47,51,54,55,60,76,77,78,92,95,100,
                125,129,130,133,135,136,140,141,142,146,167,169,184,
                201,401,402,403,404,407,408,421,427,430,1028,1029,1030)
                order by 1 desc
            """

            with connection.cursor() as cursor:
                cursor.execute(sql)
                cols = [c[0] for c in cursor.description]
                rows = cursor.fetchall()

            result = [
                {col: val for col, val in zip(cols, row)}
                for row in rows
            ]
            
            logger.info(f"CtVencidaPorTituloAPIView - Consulta exitosa. Registros: {len(result)}")
            
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            error_detail = traceback.format_exc()
            logger.error(
                f"CtVencidaPorTituloAPIView - Error inesperado: {str(e)}\n{error_detail}",
                exc_info=True,
                extra={
                    'method': 'GET',
                    'path': request.path,
                    'user': getattr(request.user, 'username', 'anonymous')
                }
            )
            return Response(
                {"detail": "Error al ejecutar query", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class CtVencidaPorTituloDetalleAPIView(APIView):
    permission_classes = [HasAPIKey]

    def get(self, request, year=None):
        try:
            # Si no viene year en la URL, buscar en query params
            if year is None:
                year_param = request.query_params.get('year')
                if year_param:
                    year = int(year_param)
                else:
                    # Si no se proporciona, usar año actual
                    from datetime import datetime
                    year = datetime.now().year
            
            # Validar que year sea un entero válido
            try:
                year_int = int(year)
                if year_int <= 0:
                    raise ValueError("El año debe ser un número positivo")
            except ValueError as ve:
                logger.warning(f"CtVencidaImpuestoAPIView - Parámetro year inválido: '{year}' - {ve}")
                return Response(
                    {"detail": f"Parámetro year inválido: '{year}'", "error": str(ve)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info(f"CtVencidaImpuestoAPIView - Consulta iniciada para year={year}")

            sql = """
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

            with connection.cursor() as cursor:
                cursor.execute(sql, {'year': year})
                cols = [c[0] for c in cursor.description]
                rows = cursor.fetchall()

            # Normalizar Decimals a float
            result = [
                {col: (float(val) if isinstance(val, Decimal) else val) for col, val in zip(cols, row)}
                for row in rows
            ]
            
            logger.info(f"CtVencidaImpuestoDetalleAPIView - Consulta exitosa. Registros: {len(result)}")
            
            return Response(result, status=status.HTTP_200_OK)

        except ValueError as e:
            logger.warning(f"CtVencidaImpuestoDetalleAPIView - Parámetro year inválido: {e}")
            return Response(
                {"detail": "Parámetro year inválido", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            error_detail = traceback.format_exc()
            logger.error(
                f"CtVencidaImpuestoDetalleAPIView - Error inesperado: {str(e)}\n{error_detail}",
                exc_info=True,
                extra={
                    'year': year,
                    'method': 'GET',
                    'path': request.path,
                    'user': getattr(request.user, 'username', 'anonymous')
                }
            )
            return Response(
                {"detail": "Error al ejecutar query", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


