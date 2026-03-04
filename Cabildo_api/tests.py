from django.test import TestCase
from django.conf import settings
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock


# ── Helpers ─────────────────────────────────────────────────────────────────────

API_KEY_VALIDA = 'test-api-key-123'

def mock_cursor(cols, rows=None):
    """
    Retorna un mock de connection.cursor() listo para usar como context manager.
    cols: lista de nombres de columnas, ej. ['COD', 'IMPUESTO']
    rows: lista de tuplas con los datos, por defecto lista vacía.
    """
    cursor = MagicMock()
    cursor.description = [(c,) for c in cols]
    cursor.fetchall.return_value = rows or []
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cursor)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


# ── Tests de Permisos ────────────────────────────────────────────────────────────

class HasAPIKeyPermissionTest(TestCase):
    """
    Verifica que el permiso HasAPIKey rechace correctamente
    peticiones sin clave, con clave vacía o con clave inválida.
    Usa /api/ct_vencida_titulo/ como endpoint de prueba por ser el más simple.
    """

    def setUp(self):
        self.client = APIClient()
        settings.API_KEYS = [API_KEY_VALIDA]

    def test_sin_api_key_retorna_403(self):
        response = self.client.get('/api/ct_vencida_titulo/')
        self.assertEqual(response.status_code, 403)

    def test_api_key_invalida_retorna_403(self):
        response = self.client.get('/api/ct_vencida_titulo/',
                                   HTTP_X_API_KEY='clave-incorrecta')
        self.assertEqual(response.status_code, 403)

    def test_api_key_vacia_retorna_403(self):
        response = self.client.get('/api/ct_vencida_titulo/',
                                   HTTP_X_API_KEY='')
        self.assertEqual(response.status_code, 403)

    @patch('django.db.connection.cursor')
    def test_api_key_valida_no_retorna_403(self, mock_cur):
        mock_cur.return_value = mock_cursor(['CODIGO', 'DESCRIPCION'])
        response = self.client.get('/api/ct_vencida_titulo/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertNotEqual(response.status_code, 403)


# ── Tests: /api/ct_vencida/<year>/ ──────────────────────────────────────────────

class CtVencidaAsyncTest(TestCase):
    """Tests para el endpoint asíncrono de generación de reporte."""

    def setUp(self):
        self.client = APIClient()
        settings.API_KEYS = [API_KEY_VALIDA]

    @patch('Cabildo_api.consultas.views.ct_vencida.generar_reporte_cartera_vencida')
    def test_retorna_202_con_task_id(self, mock_task):
        mock_task.delay.return_value.id = 'fake-task-uuid'
        response = self.client.get('/api/ct_vencida/2024/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['task_id'], 'fake-task-uuid')
        self.assertEqual(response.data['status'], 'PENDING')
        mock_task.delay.assert_called_once_with(2024)

    def test_sin_api_key_retorna_403(self):
        response = self.client.get('/api/ct_vencida/2024/')
        self.assertEqual(response.status_code, 403)

    def test_year_no_numerico_retorna_404(self):
        # Django rechaza la URL porque el tipo es <int:year>
        response = self.client.get('/api/ct_vencida/abc/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 404)


# ── Tests: /api/ct_vencida/status/<task_id>/ ────────────────────────────────────

class CtVencidaStatusTest(TestCase):
    """Tests para el endpoint de consulta de estado de tarea Celery."""

    def setUp(self):
        self.client = APIClient()
        settings.API_KEYS = [API_KEY_VALIDA]
        self.url = '/api/ct_vencida/status/fake-task-id/'

    def _get(self):
        return self.client.get(self.url, HTTP_X_API_KEY=API_KEY_VALIDA)

    @patch('Cabildo_api.consultas.views.ct_vencida.AsyncResult')
    def test_estado_pending(self, mock_async):
        mock_async.return_value.state = 'PENDING'
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'PENDING')

    @patch('Cabildo_api.consultas.views.ct_vencida.AsyncResult')
    def test_estado_processing_incluye_progreso(self, mock_async):
        mock_async.return_value.state = 'PROCESSING'
        mock_async.return_value.info = {'progress': 50, 'status': 'Procesando...'}
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['progress'], 50)

    @patch('Cabildo_api.consultas.views.ct_vencida.AsyncResult')
    def test_estado_success_incluye_resultado(self, mock_async):
        mock_async.return_value.state = 'SUCCESS'
        mock_async.return_value.result = {'records': 500, 'file': '/media/reportes/x.json'}
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.data)

    @patch('Cabildo_api.consultas.views.ct_vencida.AsyncResult')
    def test_estado_failure_incluye_error(self, mock_async):
        mock_async.return_value.state = 'FAILURE'
        mock_async.return_value.info = Exception('Error de conexión Oracle')
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.data)

    def test_sin_api_key_retorna_403(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


# ── Tests: /api/ct_vencida_impuesto/<year>/ ──────────────────────────────────────

class CtVencidaImpuestoTest(TestCase):
    """Tests para el endpoint de cartera vencida agrupada por tipo de impuesto."""

    COLS = ['COD', 'IMPUESTO', 'ANIO', 'EMISION', 'INTERES',
            'COACTIVA', 'RECARGO', 'DESCUENTO', 'IVA', 'TOTAL']

    def setUp(self):
        self.client = APIClient()
        settings.API_KEYS = [API_KEY_VALIDA]

    @patch('django.db.connection.cursor')
    def test_retorna_200_con_lista(self, mock_cur):
        mock_cur.return_value = mock_cursor(self.COLS, [(95, 'PREDIAL', 2024, 1000.0, 50.0, 0.0, 0.0, 0.0, 0.0, 1050.0)])
        response = self.client.get('/api/ct_vencida_impuesto/2024/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)

    @patch('django.db.connection.cursor')
    def test_retorna_lista_vacia_sin_registros(self, mock_cur):
        mock_cur.return_value = mock_cursor(self.COLS)
        response = self.client.get('/api/ct_vencida_impuesto/2024/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_sin_api_key_retorna_403(self):
        response = self.client.get('/api/ct_vencida_impuesto/2024/')
        self.assertEqual(response.status_code, 403)

    def test_year_no_numerico_retorna_404(self):
        response = self.client.get('/api/ct_vencida_impuesto/abc/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 404)


# ── Tests: /api/ct_vencida_titulo/ ───────────────────────────────────────────────

class CtVencidaTituloTest(TestCase):
    """Tests para el endpoint de listado de títulos de impuesto."""

    def setUp(self):
        self.client = APIClient()
        settings.API_KEYS = [API_KEY_VALIDA]

    @patch('django.db.connection.cursor')
    def test_retorna_200_con_titulos(self, mock_cur):
        mock_cur.return_value = mock_cursor(
            ['CODIGO', 'DESCRIPCION'],
            [(95, 'IMPUESTO PREDIAL URBANO'), (140, 'AGUA POTABLE')]
        )
        response = self.client.get('/api/ct_vencida_titulo/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_sin_api_key_retorna_403(self):
        response = self.client.get('/api/ct_vencida_titulo/')
        self.assertEqual(response.status_code, 403)


# ── Tests: /api/ct_vencida_titulo_detalle/<year>/ ────────────────────────────────

class CtVencidaTituloDetalleTest(TestCase):
    """Tests para el endpoint de detalle de cartera por contribuyente."""

    COLS = ['CEDULA', 'NOMBRE', 'CIU', 'IMPUESTO', 'EMISION',
            'INTERES', 'COACTIVA', 'RECARGO', 'DESCUENTO', 'IVA', 'TOTAL']

    def setUp(self):
        self.client = APIClient()
        settings.API_KEYS = [API_KEY_VALIDA]

    @patch('django.db.connection.cursor')
    def test_retorna_200_con_detalle(self, mock_cur):
        mock_cur.return_value = mock_cursor(self.COLS)
        response = self.client.get('/api/ct_vencida_titulo_detalle/2024/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 200)

    def test_sin_api_key_retorna_403(self):
        response = self.client.get('/api/ct_vencida_titulo_detalle/2024/')
        self.assertEqual(response.status_code, 403)

    def test_year_no_numerico_retorna_404(self):
        response = self.client.get('/api/ct_vencida_titulo_detalle/abc/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 404)


# ── Tests: /api/ct_vencida_porimpuesto/<year>/ ───────────────────────────────────

class CtVPorimpuestoTest(TestCase):
    """Tests para el endpoint filtrado por códigos de impuesto específicos."""

    COLS = ['COD', 'IMPUESTO', 'ANIO', 'EMISION', 'INTERES',
            'COACTIVA', 'RECARGO', 'DESCUENTO', 'IVA', 'TOTAL']

    def setUp(self):
        self.client = APIClient()
        settings.API_KEYS = [API_KEY_VALIDA]

    def test_sin_parametro_codigos_retorna_400(self):
        response = self.client.get('/api/ct_vencida_porimpuesto/2024/',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 400)
        self.assertIn('codigos', response.data.get('detail', ''))

    def test_codigos_no_numericos_retorna_400(self):
        response = self.client.get('/api/ct_vencida_porimpuesto/2024/?codigos=abc,xyz',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 400)

    @patch('django.db.connection.cursor')
    def test_retorna_200_con_codigos_validos(self, mock_cur):
        mock_cur.return_value = mock_cursor(self.COLS)
        response = self.client.get('/api/ct_vencida_porimpuesto/2024/?codigos=95,140',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 200)

    @patch('django.db.connection.cursor')
    def test_acepta_un_solo_codigo(self, mock_cur):
        mock_cur.return_value = mock_cursor(self.COLS)
        response = self.client.get('/api/ct_vencida_porimpuesto/2024/?codigos=95',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 200)

    def test_sin_api_key_retorna_403(self):
        response = self.client.get('/api/ct_vencida_porimpuesto/2024/?codigos=95')
        self.assertEqual(response.status_code, 403)

    def test_year_no_numerico_retorna_404(self):
        response = self.client.get('/api/ct_vencida_porimpuesto/abc/?codigos=95',
                                   HTTP_X_API_KEY=API_KEY_VALIDA)
        self.assertEqual(response.status_code, 404)
