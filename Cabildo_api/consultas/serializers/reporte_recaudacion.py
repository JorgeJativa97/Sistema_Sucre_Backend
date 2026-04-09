from rest_framework import serializers


class RecaudacionImpuestoSerializer(serializers.Serializer):
    """
    Serializer para reporte de recaudacion por impuesto.
    Usado por el endpoint GET /api/recaudacion/.
    Los campos en mayúsculas coinciden con los nombres de columna que retorna Oracle.
    """
    IMPUESTO      = serializers.CharField(allow_null=True)
    EMISIONTITULO = serializers.DecimalField(max_digits=30, decimal_places=2)
    INTERES       = serializers.DecimalField(max_digits=30, decimal_places=2)
    COACTIVA      = serializers.DecimalField(max_digits=30, decimal_places=2)
    DESCUENTO     = serializers.DecimalField(max_digits=30, decimal_places=2)
    RECARGO       = serializers.DecimalField(max_digits=30, decimal_places=2)
    IVA           = serializers.DecimalField(max_digits=30, decimal_places=2)
    NRO_TITULOS   = serializers.IntegerField()
    TOTAL         = serializers.DecimalField(max_digits=30, decimal_places=2)

class RecaudacionImpuestoRubroSerializer(serializers.Serializer):
    """
    Serializer para reporte de recaudacion por rubro.
    Usado por el endpoint GET /api/recaudacion_rubro/.
    Los campos en mayúsculas coinciden con los nombres de columna que retorna Oracle.
    """
    RUBRO = serializers.CharField(allow_null=True)
    TOTAL = serializers.DecimalField(max_digits=30, decimal_places=2)

class RecaudacionImpuestoRubroAnio(serializers.Serializer):
    """
    Serializer para reporte de recaudacion por rubro por año de emision.
    Usado por el endpoint GET /api/recaudacion_rubro_anioemi/.
    Los campos en mayúsculas coinciden con los nombres de columna que retorna Oracle.
    """
    RUBRO = serializers.CharField(allow_null=True)
    TOTAL = serializers.DecimalField(max_digits=30, decimal_places=2)
