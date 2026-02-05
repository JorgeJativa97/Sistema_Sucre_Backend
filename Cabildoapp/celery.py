import os
from celery import Celery

#configurar la variable de entorno para Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Cabildoapp.settings')

#crear la instancia de Celery
app = Celery('Cabildoapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Definir una tarea de ejemplo
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')