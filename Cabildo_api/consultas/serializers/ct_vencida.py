from rest_framework import serializers
from django.db import connection
import logging

logger = logging.getLogger('api')


class CtVencidaSerializer(serializers.Serializer):
    cedula = serializers.CharField(source='CEDULA')
    nombre = serializers.CharField(source='NOMBRE')
    ciu = serializers.IntegerField(source='CIU')
    emision = serializers.DecimalField(max_digits=15, decimal_places=2, source='EMISION')
    interes = serializers.DecimalField(max_digits=15, decimal_places=2, source='INTERES')
    coactiva = serializers.DecimalField(max_digits=15, decimal_places=2, source='COACTIVA')
    recargo = serializers.DecimalField(max_digits=15, decimal_places=2, source='RECARGO')
    descuento = serializers.DecimalField(max_digits=15, decimal_places=2, source='DESCUENTO')
    iva = serializers.DecimalField(max_digits=15, decimal_places=2, source='IVA')
    total = serializers.DecimalField(max_digits=15, decimal_places=2, source='TOTAL')

    @staticmethod
    def execute_query(year=None):
        """Ejecuta la consulta y retorna datos crudos"""
        try:
            from datetime import datetime

            if year is None:
                year = datetime.now().year

            with connection.cursor() as cursor:
                # Nota: Todos los % en strings SQL deben duplicarse como %%
                query = """
                SELECT 
                    CEDULA,
                    NOMBRE,
                    CIU,
                    SUM(EMISION) EMISION,
                    SUM(INTERES) INTERES,
                    SUM(COACTIVA) COACTIVA,
                    SUM(RECARGO) RECARGO,
                    SUM(DESCUENTO) DESCUENTO,
                    SUM(IVA) IVA,
                    SUM(TOTAL) TOTAL
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
                GROUP BY CEDULA, CIU, NOMBRE
                """
                # Usar parámetros nombrados para Oracle
                cursor.execute(query, {'year': year})

                def safe_float(v):
                    try:
                        return float(v) if v is not None else 0.0
                    except Exception:
                        return 0.0

                results = []
                for row in cursor.fetchall():
                    results.append({
                        "CEDULA": row[0],
                        "NOMBRE": row[1],
                        "CIU": int(row[2]) if row[2] is not None else None,
                        "EMISION": safe_float(row[3]),
                        "INTERES": safe_float(row[4]),
                        "COACTIVA": safe_float(row[5]),
                        "RECARGO": safe_float(row[6]),
                        "DESCUENTO": safe_float(row[7]),
                        "IVA": safe_float(row[8]),
                        "TOTAL": safe_float(row[9])
                    })
                return results
        except Exception as e:
            logger.error(
                f"Error al ejecutar la consulta: {str(e)}",
                exc_info=True,
                extra={'year': year}
            )
            raise e

class CtVencidaImpuestoSerializer(serializers.Serializer):
        COD = serializers.CharField()
        IMPUESTO = serializers.CharField(allow_null=True)
        ANIO = serializers.IntegerField()
        EMISION = serializers.DecimalField(max_digits=30, decimal_places=2)
        INTERES = serializers.DecimalField(max_digits=30, decimal_places=2)
        COACTIVA = serializers.DecimalField(max_digits=30, decimal_places=2)
        RECARGO = serializers.DecimalField(max_digits=30, decimal_places=2)
        DESCUENTO = serializers.DecimalField(max_digits=30, decimal_places=2)
        IVA = serializers.DecimalField(max_digits=30, decimal_places=2)
        TOTAL = serializers.DecimalField(max_digits=30, decimal_places=2)     

class CtVencidaPorTituloSerializer(serializers.Serializer):
    CODIGO = serializers.CharField(source='COD')
    IMPUESTO = serializers.CharField(source='IMPUESTO')

class CtVencidaPorTituloDetalleSerializer(serializers.Serializer):
        cedula = serializers.CharField(source='CEDULA')
        nombre = serializers.CharField(source='NOMBRE')
        ciu = serializers.IntegerField(source='CIU')
        IMPUESTO = serializers.CharField(source='IMPUESTO')
        emision = serializers.DecimalField(max_digits=15, decimal_places=2, source='EMISION')
        interes = serializers.DecimalField(max_digits=15, decimal_places=2, source='INTERES')
        coactiva = serializers.DecimalField(max_digits=15, decimal_places=2, source='COACTIVA')
        recargo = serializers.DecimalField(max_digits=15, decimal_places=2, source='RECARGO')
        descuento = serializers.DecimalField(max_digits=15, decimal_places=2, source='DESCUENTO')
        iva = serializers.DecimalField(max_digits=15, decimal_places=2, source='IVA')
        total = serializers.DecimalField(max_digits=15, decimal_places=2, source='TOTAL')

class CtVPorimpuesto(serializers.Serializer):
    COD = serializers.CharField()
    IMPUESTO = serializers.CharField(allow_null=True)
    ANIO = serializers.IntegerField()
    EMISION = serializers.DecimalField(max_digits=30, decimal_places=2)
    INTERES = serializers.DecimalField(max_digits=30, decimal_places=2)
    COACTIVA = serializers.DecimalField(max_digits=30, decimal_places=2)
    RECARGO = serializers.DecimalField(max_digits=30, decimal_places=2)
    DESCUENTO = serializers.DecimalField(max_digits=30, decimal_places=2)
    IVA = serializers.DecimalField(max_digits=30, decimal_places=2)
    TOTAL = serializers.DecimalField(max_digits=30, decimal_places=2)