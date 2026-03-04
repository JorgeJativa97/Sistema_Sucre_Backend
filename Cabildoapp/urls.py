from django.contrib import admin
from django.urls import path
from Cabildo_api.consultas.views.ct_vencida import (
    CtVencidaSerializerAPIView,
    CtVencidaStatusAPIView,
    CtVencidaImpuestoAPIView,
    CtVencidaPorTituloAPIView,
    CtVencidaPorTituloDetalleAPIView,
    CtVPorimpuestoSerializerApiView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Reporte completo asíncrono (Celery)
    path('api/ct_vencida/<int:year>/', CtVencidaSerializerAPIView.as_view(), name='ct_vencida_async'),
    path('api/ct_vencida/status/<str:task_id>/', CtVencidaStatusAPIView.as_view(), name='ct_vencida_status'),
    # Consultas síncronas
    path('api/ct_vencida_impuesto/<int:year>/', CtVencidaImpuestoAPIView.as_view(), name='ct_vencida_impuesto'),
    path('api/ct_vencida_titulo/', CtVencidaPorTituloAPIView.as_view(), name='ct_vencida_rubro'),
    path('api/ct_vencida_titulo_detalle/<int:year>/', CtVencidaPorTituloDetalleAPIView.as_view(), name='ct_vencida_desglosada_detalle'),
    path('api/ct_vencida_porimpuesto/<int:year>/', CtVPorimpuestoSerializerApiView.as_view(), name='ct_vencida_porimpuesto'),
]

