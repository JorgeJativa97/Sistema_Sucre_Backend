from celery import shared_task
from Cabildo_api.consultas.serializers.ct_vencida import CtVencidaSerializer
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
            'data': data  # Devolver los datos también
        }
        
    except Exception as e:
        logger.error(f"Error generando reporte: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise