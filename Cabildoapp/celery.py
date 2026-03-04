import os
from celery import Celery

# Apunta a la configuración de Django para que Celery use los mismos settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cabildoapp.settings')

# Instancia principal de Celery para el proyecto
app = Celery('Cabildoapp')

# Lee toda la configuración con prefijo CELERY_ desde settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descubre automáticamente tareas en los archivos task/tasks.py de cada app
app.autodiscover_tasks()