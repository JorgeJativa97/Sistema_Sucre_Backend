from celery import shared_task
from Cabildo_api.consultas.serializers.ct_vencida import CtVencidaSerializer
from django.db import connection
from decimal import Decimal

_SQL_CT_VENCIDA_IMPUESTO = """
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
import json
import os
from django.conf import settings
import logging

logger = logging.getLogger('api')

@shared_task(bind=True, name='generar_reporte_cartera_vencida')
def generar_reporte_cartera_vencida(self, year):
    """
    Tarea asíncrona para generar reporte de cartera vencida
    """
    try:
        # Actualizar estado a "PROCESSING"
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})
        
        logger.info(f"Iniciando generación de reporte para año {year}")
        
        # Ejecutar query
        raw_data = CtVencidaSerializer.execute_query(year=year)
        
        self.update_state(state='PROCESSING', meta={'progress': 50, 'status': 'Procesando datos...'})
        
        # Serializar datos
        serializer = CtVencidaSerializer(raw_data, many=True)
        data = serializer.data
        
        self.update_state(state='PROCESSING', meta={'progress': 80, 'status': 'Guardando reporte...'})
        
        # Guardar en archivo JSON (opcional, para histórico)
        media_dir = os.path.join(settings.MEDIA_ROOT, 'reportes')
        os.makedirs(media_dir, exist_ok=True)
        
        filename = f'cartera_vencida_{year}.json'
        filepath = os.path.join(media_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Reporte generado exitosamente: {filename}")
        
        return {
            'status': 'SUCCESS',
            'year': year,
            'records': len(data),
            'file': f'/media/reportes/{filename}',
            # No se retorna 'data' para no saturar Redis con miles de registros.
            # El reporte completo está disponible en el archivo JSON guardado.
        }
        
    except Exception as e:
        logger.error(f"Error generando reporte: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@shared_task(bind=True, name='generar_reporte_cartera_vencida_impuesto')
def generar_reporte_cartera_vencida_impuesto(self, year):
    """
    Tarea asíncrona para generar reporte de cartera vencida por impuesto.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})

        logger.info(f"Iniciando generación de reporte por impuesto para año {year}")

        with connection.cursor() as cursor:
            cursor.execute(_SQL_CT_VENCIDA_IMPUESTO, {'year': year})
            cols = [c[0] for c in cursor.description]
            rows = cursor.fetchall()

        self.update_state(state='PROCESSING', meta={'progress': 50, 'status': 'Procesando datos...'})

        data = [
            {col: (float(val) if isinstance(val, Decimal) else val)
             for col, val in zip(cols, row)}
            for row in rows
        ]

        self.update_state(state='PROCESSING', meta={'progress': 80, 'status': 'Guardando reporte...'})

        media_dir = os.path.join(settings.MEDIA_ROOT, 'reportes')
        os.makedirs(media_dir, exist_ok=True)

        filename = f'cartera_vencida_impuesto_{year}.json'
        filepath = os.path.join(media_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Reporte por impuesto generado exitosamente: {filename}")

        return {
            'status': 'SUCCESS',
            'year': year,
            'records': len(data),
            'file': f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(f"Error generando reporte por impuesto: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise