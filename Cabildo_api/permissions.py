from rest_framework.permissions import BasePermission
from django.conf import settings


class HasAPIKey(BasePermission):
    """
    Permiso personalizado que valida el header X-API-Key.
    Rechaza peticiones con clave vacía, ausente o no registrada en settings.API_KEYS.
    """

    message = "API Key inválida o faltante"

    def has_permission(self, request, view):
        api_key = request.headers.get('X-API-Key', '')
        # Rechazar explícitamente claves vacías para evitar que una
        # configuración incorrecta de API_KEYS=[''] permita acceso sin clave
        if not api_key:
            return False
        return api_key in settings.API_KEYS