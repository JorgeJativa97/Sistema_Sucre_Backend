from django.contrib import admin
from django.urls import path
from Cabildo_api.consultas.views.ct_vencida import (
    CtVencidaSerializerAPIView,
    CtVencidaDatosAPIView,
    CtVencidaImpuestoAPIView,
    CtVencidaImpuestoDatosAPIView,
    CtVencidaPorTituloAPIView,
    CtVencidaPorTituloDetalleAPIView,
    CtVencidaTituloDetalleDatosAPIView,
    CtVPorimpuestoSerializerApiView,
    CtVPorimpuestoDatosAPIView,
)
from Cabildo_api.consultas.views.base import TaskStatusAPIView
from Cabildo_api.consultas.views.bienes_inmuebles import BienesInmueblesAPIView
from Cabildo_api.consultas.views.comprobante import ComprobanteAPIView
from Cabildo_api.consultas.views.reporte_recaudacion import (
    RecaudacionImpuestoAPIView,
    RecaudacionDatosAPIView,
    RecaudacionImpuestoFiltradoAPIView,
    RecaudacionRubroApiView,
    RecaudacionRubroDatosAPIView,
    RecaudacionRubroAnioEmiApiView,
    RecaudacionRubroAnioEmiDatosAPIView,
    RecaudacionRubroAnioEmiIdsApiView,
    RecaudacionRubroAnioEmiIdsDatosAPIView,
    RubrosListAPIView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Reporte completo asíncrono (Celery)
    path('api/ct_vencida/<int:year>/', CtVencidaSerializerAPIView.as_view(), name='ct_vencida_async'),
    # Endpoint genérico de status para cualquier tarea Celery
    path('api/status/<str:task_id>/', TaskStatusAPIView.as_view(), name='task_status'),
    path('api/ct_vencida/datos/<int:year>/', CtVencidaDatosAPIView.as_view(), name='ct_vencida_datos'),
    # Reporte por impuesto asíncrono (Celery)
    path('api/ct_vencida_impuesto/<int:year>/', CtVencidaImpuestoAPIView.as_view(), name='ct_vencida_impuesto'),
    path('api/ct_vencida_impuesto/datos/<int:year>/', CtVencidaImpuestoDatosAPIView.as_view(), name='ct_vencida_impuesto_datos'),
    # Consultas síncronas
    path('api/ct_vencida_titulo/', CtVencidaPorTituloAPIView.as_view(), name='ct_vencida_rubro'),
    path('api/ct_vencida_titulo_detalle/<int:year>/', CtVencidaPorTituloDetalleAPIView.as_view(), name='ct_vencida_desglosada_detalle'),
    path('api/ct_vencida_titulo_detalle/datos/<int:year>/', CtVencidaTituloDetalleDatosAPIView.as_view(), name='ct_vencida_titulo_detalle_datos'),
    path('api/ct_vencida_porimpuesto/<int:year>/', CtVPorimpuestoSerializerApiView.as_view(), name='ct_vencida_porimpuesto'),
    path('api/ct_vencida_porimpuesto/datos/<int:year>/', CtVPorimpuestoDatosAPIView.as_view(), name='ct_vencida_porimpuesto_datos'),
    # Anexo GAD - Bienes Inmuebles
    path('api/bienes_inmuebles/', BienesInmueblesAPIView.as_view(), name='bienes_inmuebles'),
    # Reporte de recaudación por impuesto
    path('api/recaudacion/', RecaudacionImpuestoAPIView.as_view(), name='recaudacion_impuesto'),
    path('api/recaudacion/datos/', RecaudacionDatosAPIView.as_view(), name='recaudacion_datos'),
    # Reporte de recaudación por rubro
    path('api/recaudacion_rubro/', RecaudacionRubroApiView.as_view(), name='recaudacion_rubro'),
    path('api/recaudacion_rubro/datos/', RecaudacionRubroDatosAPIView.as_view(), name='recaudacion_rubro_datos'),
     # Comprobante de pago
    path('api/comprobante/<int:emi01codi>/', ComprobanteAPIView.as_view(), name='comprobante'),
    path('api/comprobante/<int:emi01codi>/<int:nro_abono>/', ComprobanteAPIView.as_view(), name='comprobante_abono'),
      # Reporte de recaudacion por año de emision
    path('api/recaudacion_rubro_anioemi/', RecaudacionRubroAnioEmiApiView.as_view(), name='recaudacion_rubro_anioemi'),
    path('api/recaudacion_rubro_anio_emi/datos/', RecaudacionRubroAnioEmiDatosAPIView.as_view(), name='recaudacion_rubro_anio_emi_datos'),
    # Reporte de recaudacion por año de emision filtrado por ids de rubro (máx 4)
    path('api/recaudacion_rubro_anio_emi_ids/', RecaudacionRubroAnioEmiIdsApiView.as_view(), name='recaudacion_rubro_anio_emi_ids'),
    path('api/recaudacion_rubro_anio_emi_ids/datos/', RecaudacionRubroAnioEmiIdsDatosAPIView.as_view(), name='recaudacion_rubro_anio_emi_ids_datos'),
     # Reporte de recaudacion por año de emision filtrado por ids de rubro (máx 4)
     path('api/recaudacion_impuesto_filtro_emi_ids/',RecaudacionImpuestoFiltradoAPIView.as_view(), name='generar_reporte_recaudacion_impuesto_emi_ids'),
     path('api/recaudacion_impuesto_filtro_emi_ids/datos',RecaudacionImpuestoFiltradoDatosAPIView.as_view(), name='generar_reporte_recaudacion_impuesto_emi_ids_datos')
    # Catálogo de rubros
    path('api/rubros/', RubrosListAPIView.as_view(), name='rubros_list'),
]

