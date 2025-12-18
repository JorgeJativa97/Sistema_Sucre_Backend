"""
URL configuration for Cabildoapp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from Cabildo_api.consultas.views.ct_vencida import CtVencidaImpuestoAPIView, CtVencidaPorTituloAPIView, CtVencidaSerializerAPIView, CtVencidaPorTituloDetalleAPIView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/ct_vencida/<int:year>/', CtVencidaSerializerAPIView.as_view(), name='ct_vencida_year'),
    path('api/ct_vencida_impuesto/<str:year>/', CtVencidaImpuestoAPIView.as_view(), name='ct_vencida_impuesto'),
    path('api/ct_vencida_titulo/', CtVencidaPorTituloAPIView.as_view(), name='ct_vencida_rubro'),
    path('api/ct_vencida_titulo_detalle/<str:year>/', CtVencidaPorTituloDetalleAPIView.as_view(), name='ct_vencida_desglosada_detalle')
]

