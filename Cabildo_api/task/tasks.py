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


_SQL_POR_IMPUESTO_TEMPLATE = """
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


@shared_task(bind=True, name='generar_reporte_cartera_vencida_porimpuesto')
def generar_reporte_cartera_vencida_porimpuesto(self, year, codigos_list):
    """
    Tarea asíncrona para generar reporte de cartera vencida por títulos seleccionados.
    codigos_list: lista de enteros con los códigos de impuesto a filtrar.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})

        logger.info(f"Iniciando generación de reporte por títulos para año {year}, codigos={codigos_list}")

        placeholders = ', '.join([f':cod{i}' for i in range(len(codigos_list))])
        sql = _SQL_POR_IMPUESTO_TEMPLATE.format(placeholders=placeholders)

        params = {'year': year}
        params.update({f'cod{i}': cod for i, cod in enumerate(codigos_list)})

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
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

        codigos_str = '_'.join(str(c) for c in sorted(codigos_list))
        filename = f'cartera_vencida_porimpuesto_{year}_{codigos_str}.json'
        filepath = os.path.join(media_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Reporte por títulos generado exitosamente: {filename}")

        return {
            'status': 'SUCCESS',
            'year': year,
            'codigos': codigos_list,
            'records': len(data),
            'file': f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(f"Error generando reporte por títulos: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


_SQL_RECAUDACION = """
SELECT
    pk_uti.FIND_IMPUESTO(impuesto)  AS IMPUESTO,
    SUM(total)                       AS EMISIONTITULO,
    SUM(interes)                     AS INTERES,
    SUM(coactiva)                    AS COACTIVA,
    SUM(descuento)                   AS DESCUENTO,
    SUM(recargo)                     AS RECARGO,
    SUM(NVL(iva, 0))                 AS IVA,
    SUM(nro_titulos)                 AS NRO_TITULOS,
    SUM(total) + SUM(interes) + SUM(coactiva) + SUM(recargo)
        - SUM(descuento) + SUM(NVL(iva, 0)) AS TOTAL
FROM V_COBROMAES
WHERE fpago BETWEEN TO_DATE(:fecha_inicio, 'YYYY-MM-DD')
                AND TO_DATE(:fecha_fin,    'YYYY-MM-DD')
GROUP BY pk_uti.FIND_IMPUESTO(impuesto)
ORDER BY 1
"""


@shared_task(bind=True, name='generar_reporte_recaudacion')
def generar_reporte_recaudacion(self, fecha_inicio, fecha_fin):
    """
    Tarea asíncrona para generar reporte de recaudación por impuesto.
    fecha_inicio / fecha_fin: strings en formato 'YYYY-MM-DD'.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})

        logger.info(f"Iniciando generación de reporte de recaudación: {fecha_inicio} → {fecha_fin}")

        with connection.cursor() as cursor:
            cursor.execute(_SQL_RECAUDACION, {
                'fecha_inicio': fecha_inicio,
                'fecha_fin':    fecha_fin,
            })
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

        filename = f'recaudacion_{fecha_inicio}_{fecha_fin}.json'
        filepath = os.path.join(media_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Reporte de recaudación generado exitosamente: {filename}")

        return {
            'status': 'SUCCESS',
            'fecha_inicio': fecha_inicio,
            'fecha_fin':    fecha_fin,
            'records': len(data),
            'file': f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(f"Error generando reporte de recaudación: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


_SQL_CT_VENCIDA_TITULO_DETALLE = """
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


@shared_task(bind=True, name='generar_reporte_cartera_vencida_titulo_detalle')
def generar_reporte_cartera_vencida_titulo_detalle(self, year):
    """
    Tarea asíncrona para generar reporte de cartera vencida detalle por contribuyente.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})

        logger.info(f"Iniciando generación de reporte título detalle para año {year}")

        with connection.cursor() as cursor:
            cursor.execute(_SQL_CT_VENCIDA_TITULO_DETALLE, {'year': year})
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

        filename = f'cartera_vencida_titulo_detalle_{year}.json'
        filepath = os.path.join(media_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Reporte título detalle generado exitosamente: {filename}")

        return {
            'status': 'SUCCESS',
            'year': year,
            'records': len(data),
            'file': f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(f"Error generando reporte título detalle: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise

_SQL_RECAUDACION_RUBRO = """
SELECT 
F_DESCCOMPONENTE(EMI04CODI) RUBRO,SUM(VALOR) TOTAL
FROM V_COBROSORIGEN
WHERE FPAGO BETWEEN TO_DATE(:fecha_inicio, 'YYYY-MM-DD') AND TO_DATE(:fecha_fin, 'YYYY-MM-DD')
AND TIPO LIKE '%%NORMAL%%'
GROUP BY  F_DESCCOMPONENTE(EMI04CODI)
ORDER BY F_DESCCOMPONENTE(EMI04CODI)
"""

@shared_task(bind=True, name='generar_reporte_recaudacion_rubro')
def generar_reporte_recaudacion_rubro(self, fecha_inicio, fecha_fin):
    """
    Tarea asíncrona para generar reporte de recaudación por rubro.
    fecha_inicio / fecha_fin: strings en formato 'YYYY-MM-DD'.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})

        logger.info(f"Iniciando generación de reporte de recaudación por rubro: {fecha_inicio} → {fecha_fin}")

        with connection.cursor() as cursor:
            cursor.execute(_SQL_RECAUDACION_RUBRO, {
                'fecha_inicio': fecha_inicio,
                'fecha_fin':    fecha_fin,
            })
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

        filename = f'recaudacion_rubro_{fecha_inicio}_{fecha_fin}.json'
        filepath = os.path.join(media_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Reporte de recaudación por rubro generado exitosamente: {filename}")

        return {
            'status': 'SUCCESS',
            'fecha_inicio': fecha_inicio,
            'fecha_fin':    fecha_fin,
            'records': len(data),
            'file': f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(f"Error generando reporte de recaudación por rubro: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


_SQL_RECAUDACION_RUBRO_ANIO_EMI = """
SELECT F_DESCCOMPONENTE(EMI04CODI) RUBRO,SUM(VALOR) TOTAL
FROM V_COBROSORIGEN
WHERE FPAGO BETWEEN TO_DATE(:fecha_inicio, 'YYYY-MM-DD') AND TO_DATE(:fecha_fin, 'YYYY-MM-DD')
AND TIPO LIKE '%%NORMAL%%'
AND EMI01ANIO = :year
GROUP BY  F_DESCCOMPONENTE(EMI04CODI)
ORDER BY F_DESCCOMPONENTE(EMI04CODI)
"""

@shared_task(bind=True, name='generar_reporte_recaudacion_rubro_anio_emi')
def generar_reporte_recaudacion_rubro_anio_emi(self, year, fecha_inicio, fecha_fin):
    """
    Tarea asíncrona para generar reporte de recaudación por rubro por anio de emision.
    fecha_inicio / fecha_fin: strings en formato 'YYYY-MM-DD'.
    year: int en formato 'YYYY'
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})

        logger.info(f"Iniciando generación de reporte de recaudación por rubro POR ANIO DE EMISION:{year} → {fecha_inicio} → {fecha_fin}")

        with connection.cursor() as cursor:
            cursor.execute(_SQL_RECAUDACION_RUBRO_ANIO_EMI, {
                'year' : year,
                'fecha_inicio': fecha_inicio,
                'fecha_fin':    fecha_fin,
            })
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

        filename = f'recaudacion_rubro_anio_emi_{year}_{fecha_inicio}_{fecha_fin}.json'
        filepath = os.path.join(media_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Reporte de recaudación por rubro por año de emisión generado exitosamente: {filename}")

        return {
            'status': 'SUCCESS',
            'fecha_inicio': fecha_inicio,
            'fecha_fin':    fecha_fin,
            'year' : year,
            'records': len(data),
            'file': f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(f"Error generando reporte de recaudación por rubro por anio de emision: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


_SQL_RECAUDACION_RUBRO_ANIO_EMI_IDS = """
SELECT F_DESCCOMPONENTE(EMI04CODI) RUBRO, SUM(VALOR) TOTAL
FROM V_COBROSORIGEN
WHERE FPAGO BETWEEN TO_DATE(:fecha_inicio, 'YYYY-MM-DD') AND TO_DATE(:fecha_fin, 'YYYY-MM-DD')
AND TIPO LIKE '%%NORMAL%%'
AND EMI01ANIO = :year
AND EMI04CODI IN ({placeholders})
GROUP BY F_DESCCOMPONENTE(EMI04CODI)
ORDER BY F_DESCCOMPONENTE(EMI04CODI)
"""

@shared_task(bind=True, name='generar_reporte_recaudacion_rubro_anio_emi_ids')
def generar_reporte_recaudacion_rubro_anio_emi_ids(self, year, fecha_inicio, fecha_fin, emi04codi_ids):
    """
    Tarea asíncrona para generar reporte de recaudación por rubro por año de emisión
    filtrando por una lista de hasta 4 ids de rubro (EMI04CODI).
    year: int en formato 'YYYY'
    fecha_inicio / fecha_fin: strings en formato 'YYYY-MM-DD'.
    emi04codi_ids: lista de enteros (máximo 4).
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'Consultando datos...'})

        logger.info(
            f"Iniciando generación de reporte de recaudación por rubro/anio emision/ids: "
            f"{year} → {fecha_inicio} → {fecha_fin} → ids={emi04codi_ids}"
        )

        placeholders = ','.join(f':id{i}' for i in range(len(emi04codi_ids)))
        sql = _SQL_RECAUDACION_RUBRO_ANIO_EMI_IDS.format(placeholders=placeholders)

        params = {
            'year':         year,
            'fecha_inicio': fecha_inicio,
            'fecha_fin':    fecha_fin,
        }
        for i, rubro_id in enumerate(emi04codi_ids):
            params[f'id{i}'] = rubro_id

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
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

        ids_str = '-'.join(str(i) for i in emi04codi_ids)
        filename = f'recaudacion_rubro_anio_emi_ids_{year}_{fecha_inicio}_{fecha_fin}_{ids_str}.json'
        filepath = os.path.join(media_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Reporte de recaudación por rubro/anio emision/ids generado: {filename}")

        return {
            'status':        'SUCCESS',
            'year':          year,
            'fecha_inicio':  fecha_inicio,
            'fecha_fin':     fecha_fin,
            'emi04codi_ids': emi04codi_ids,
            'records':       len(data),
            'file':          f'/media/reportes/{filename}',
        }

    except Exception as e:
        logger.error(
            f"Error generando reporte de recaudación por rubro/anio emision/ids: {str(e)}",
            exc_info=True,
        )
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise