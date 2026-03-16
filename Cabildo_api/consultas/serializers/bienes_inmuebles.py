from rest_framework import serializers
from django.db import connection
import logging

logger = logging.getLogger('api')


class BienesInmueblesSerializer(serializers.Serializer):
    """
    Serializer para el Anexo GAD - Sección Bienes Inmuebles.
    Formato requerido por el SRI según Resolución NAC-DGERCGC22-00000041.

    Tablas Oracle usadas:
      - GEN01  : datos del catastrado (contribuyente)
      - PUR06  : relación predio-propietario y porcentaje de propiedad (predios urbanos)
      - PUR01  : datos del predio urbano
      - PRR01  : datos del predio rural (pendiente - se unirá con UNION ALL)

    Campos XML del SRI:
      tipIdent     - Tipo de identificación (R/C/P)
      idIdent      - RUC, cédula o pasaporte
      razSoc       - Nombre completo o razón social
      tipTrans     - Tipo de transacción (01-05, Tabla 2)
      otroTipTrans - Solo si tipTrans='05' (condicional)
      porPropied   - Porcentaje de propiedad (ej: 100.00)
      tipBien      - Tipo de bien inmueble (01-07, Tabla 3)
      otroTipBien  - Solo si tipBien='07' (condicional)
      numPred      - Número de predio
      clavCat      - Clave catastral
      avalInm      - Avalúo del terreno
      avalConst    - Avalúo área de construcción
      arTotal      - Área total en m²
      avalTotal    - Avalúo total del bien
      prov         - Código provincia SRI Tabla 7 (3 dígitos)
      cant         - Código cantón SRI Tabla 8 (5 dígitos)
      parr         - Código parroquia SRI Tabla 9 (7 dígitos)
      dir          - Dirección del predio
    """
    tipIdent     = serializers.CharField(source='TIP_IDENT')
    idIdent      = serializers.CharField(source='ID_IDENT')
    razSoc       = serializers.CharField(source='RAZ_SOC')
    tipTrans     = serializers.CharField(source='TIP_TRANS')
    otroTipTrans = serializers.CharField(source='OTRO_TIP_TRANS', allow_null=True, required=False)
    porPropied   = serializers.DecimalField(max_digits=6, decimal_places=2, source='POR_PROPIED')
    tipBien      = serializers.CharField(source='TIP_BIEN')
    otroTipBien  = serializers.CharField(source='OTRO_TIP_BIEN', allow_null=True, required=False)
    numPred      = serializers.CharField(source='NUM_PRED')
    clavCat      = serializers.CharField(source='CLAV_CAT')
    avalInm      = serializers.DecimalField(max_digits=22, decimal_places=2, source='AVAL_INM')
    avalConst    = serializers.DecimalField(max_digits=22, decimal_places=2, source='AVAL_CONST')
    arTotal      = serializers.DecimalField(max_digits=22, decimal_places=2, source='AR_TOTAL')
    avalTotal    = serializers.DecimalField(max_digits=22, decimal_places=2, source='AVAL_TOTAL')
    prov         = serializers.CharField(source='PROV')
    cant         = serializers.CharField(source='CANT')
    parr         = serializers.CharField(source='PARR')
    dir          = serializers.CharField(source='DIR')

    @staticmethod
    def execute_query(year=None):
        """
        Ejecuta la consulta de bienes inmuebles (urbanos + rurales) desde Oracle.

        Combina con UNION ALL:
          - SQL_URBANOS : predios urbanos desde PUR01 / PUR06
          - SQL_RURALES : predios rurales desde PRU01 / PRU10 / pru05

        Retorna lista de diccionarios con los campos requeridos por el SRI.

        ESTADOS de PUR01.PUR01ESTA incluidos (urbanos):
          IG = Ingresado
          MD = Modificado
          TT = Transferido (tipTrans='02')
          CO = Consolidado

        ESTADOS excluidos en PRU01.PRU01ESTA (rurales):
          PE = Pendiente
          DU = Duplicado

        PARROQUIAS configuradas (cantón Sucre - Manabí, código SRI 11314):
          Urbanos:
            57 -> 1131457
            53 -> 1131453
            02 -> 1131402
            01 -> 1131401
            (otros) -> 1131457 (por defecto)
          Rurales: 1131401 (fijo)
        """
        try:
            with connection.cursor() as cursor:
                query = """
                -- =============================================
                -- PREDIOS URBANOS
                -- =============================================
                SELECT
                    CASE
                        WHEN LENGTH(GEN01.gen01ruc) = 10 THEN 'C'
                        WHEN LENGTH(GEN01.gen01ruc) = 13 THEN 'R'
                        ELSE 'P'
                    END                                                        AS TIP_IDENT,
                    GEN01.gen01ruc                                             AS ID_IDENT,
                    GEN01.gen01com                                             AS RAZ_SOC,
                    DECODE(PUR01.pur01esta, 'TT', '02', '01')                 AS TIP_TRANS,
                    'NINGUNO'                                                  AS OTRO_TIP_TRANS,
                    PUR06.PUR06POR                                             AS POR_PROPIED,
                    '01'                                                       AS TIP_BIEN,
                    'NINGUNO'                                                  AS OTRO_TIP_BIEN,
                    NVL(PUR01.PUR01PRED, '0')                                 AS NUM_PRED,
                    NVL(PUR01.PUR01PRED, '0')                                 AS CLAV_CAT,
                    TO_CHAR(NVL(PUR01.PUR01AVTTS, 0), 'FM999999999990.00')   AS AVAL_INM,
                    TO_CHAR(NVL(PUR01.PURAVACONS, 0), 'FM999999999990.00')   AS AVAL_CONST,
                    REPLACE(TO_CHAR(NVL(PUR01.PUR01ATTER, 0),
                        'FM999999999990.00'), '0.00', '0.01')                 AS AR_TOTAL,
                    REPLACE(TO_CHAR(NVL(PUR01.PUR01TAVRE, 0),
                        'FM999999999990.00'), '0.00', '0.01')                 AS AVAL_TOTAL,
                    '113'                                                      AS PROV,
                    '11314'                                                    AS CANT,
                    CASE
                        WHEN (PUR01.PUR01PARRO) = 57 THEN '1131457'
                        WHEN (PUR01.PUR01PARRO) = 53 THEN '1131453'
                        WHEN (PUR01.PUR01PARRO) = 02 THEN '1131402'
                        WHEN (PUR01.PUR01PARRO) = 01 THEN '1131401'
                        ELSE '1131457'
                    END                                                        AS PARR,
                    CASE
                        WHEN LENGTH(NVL(PUR01.PUR01DIR, 'Sucre')) < 5
                            THEN 'sucre'
                        ELSE NVL(PUR01.PUR01DIR, 'Sucre')
                    END                                                        AS DIR
                FROM GEN01
                INNER JOIN PUR06 ON GEN01.GEN01CODI = PUR06.GEN01CODI
                INNER JOIN PUR01 ON PUR01.PUR01PRED  = PUR06.PUR01PRED
                WHERE PUR01.PUR01ESTA IN ('IG', 'MD', 'TT', 'CO')
                  AND PUR06.PUR06POR  != 0
                  AND GEN01.gen01ruc NOT LIKE '%ELI%'

                -- =============================================
                -- PREDIOS RURALES
                -- =============================================
                UNION ALL
                SELECT
                    CASE
                        WHEN LENGTH(GEN01.gen01ruc) = 10 THEN 'C'
                        WHEN LENGTH(GEN01.gen01ruc) = 13 THEN 'R'
                        ELSE 'P'
                    END                                                        AS TIP_IDENT,
                    GEN01.gen01ruc                                             AS ID_IDENT,
                    GEN01.gen01com                                             AS RAZ_SOC,
                    DECODE(PRU01.PRU01ESTA, 'TT', '02', '01')                AS TIP_TRANS,
                    'NINGUNO'                                                  AS OTRO_TIP_TRANS,
                    PRU10.PRU10PORC                                            AS POR_PROPIED,
                    '01'                                                       AS TIP_BIEN,
                    'NINGUNO'                                                  AS OTRO_TIP_BIEN,
                    NVL(PRU01.PRU01CLA, '0')                                  AS NUM_PRED,
                    NVL(PRU01.PRU01CLA, '0')                                  AS CLAV_CAT,
                    TO_CHAR(
                        ABS(
                            NVL(PRU01.PRU01AVAL, 0) -
                            NVL((
                                SELECT pur05aREAL
                                FROM pru05 pru
                                WHERE PRU01.PRU01CLA = pru.pru01cla
                                AND rownum = 1
                            ), 0)
                        ),
                        'FM999999999990.00'
                    )                                                          AS AVAL_INM,
                    TO_CHAR(
                        NVL((
                            SELECT pur05aREAL
                            FROM pru05 pru
                            WHERE PRU01.PRU01CLA = pru.pru01cla
                            AND rownum = 1
                        ), 0),
                        'FM999999999990.00'
                    )                                                          AS AVAL_CONST,
                    REPLACE(TO_CHAR(NVL(PRU01.Pru01supe, 0),
                        'FM999999999990.00'), '0.00', '0.01')                 AS AR_TOTAL,
                    REPLACE(TO_CHAR(NVL(PRU01.PRU01AVAL, 0),
                        'FM999999999990.00'), '0.00', '0.01')                 AS AVAL_TOTAL,
                    '113'                                                      AS PROV,
                    '11314'                                                    AS CANT,
                    '1131401'                                                  AS PARR,
                    CASE
                        WHEN LENGTH(NVL(PRU01.pru01npre, 'Sucre')) < 5
                            THEN 'sucre'
                        ELSE NVL(PRU01.pru01npre, 'Sucre')
                    END                                                        AS DIR
                FROM PRU01
                INNER JOIN PRU10 ON PRU01.PRU01CLA  = PRU10.PRU01CLA
                INNER JOIN GEN01 ON PRU10.GEN01CODI = GEN01.GEN01CODI
                WHERE PRU01.PRU01ESTA NOT IN ('PE', 'DU')
                  AND PRU10.PRU10PORC != 0
                  AND GEN01.gen01ruc NOT LIKE '%ELI%'
                """

                cursor.execute(query)

                def safe_decimal(v):
                    try:
                        return float(v) if v is not None else 0.0
                    except Exception:
                        return 0.0

                results = []
                batch_size = 500
                while True:
                    batch = cursor.fetchmany(batch_size)
                    if not batch:
                        break
                    for row in batch:
                        results.append({
                            "TIP_IDENT":      row[0]  or 'P',
                            "ID_IDENT":       str(row[1]).strip()  if row[1]  else '',
                            "RAZ_SOC":        str(row[2]).strip()  if row[2]  else '',
                            "TIP_TRANS":      row[3]  or '01',
                            "OTRO_TIP_TRANS": row[4],
                            "POR_PROPIED":    safe_decimal(row[5]),
                            "TIP_BIEN":       row[6]  or '01',
                            "OTRO_TIP_BIEN":  row[7],
                            "NUM_PRED":       str(row[8]).strip()  if row[8]  else '',
                            "CLAV_CAT":       str(row[9]).strip()  if row[9]  else '',
                            "AVAL_INM":       safe_decimal(row[10]),
                            "AVAL_CONST":     safe_decimal(row[11]),
                            "AR_TOTAL":       safe_decimal(row[12]),
                            "AVAL_TOTAL":     safe_decimal(row[13]),
                            "PROV":           str(row[14]) if row[14] else '',
                            "CANT":           str(row[15]) if row[15] else '',
                            "PARR":           str(row[16]) if row[16] else '',
                            "DIR":            str(row[17]).strip() if row[17] else '',
                        })
                return results

        except Exception as e:
            logger.error(
                f"Error al ejecutar consulta bienes inmuebles: {str(e)}",
                exc_info=True,
            )
            raise e
