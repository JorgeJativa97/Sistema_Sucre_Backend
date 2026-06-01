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
                SELECT 
                        CASE
                            WHEN UPPER(GEN01.gen01ruc) LIKE '%HEREDEROS%' THEN 'P'
                            WHEN UPPER(GEN01.gen01ruc) LIKE '%SOCIEDAD%'  THEN 'P'
                            WHEN UPPER(GEN01.gen01ruc) LIKE '%FALLECIDO%'  THEN 'P'
                            WHEN LENGTH(GEN01.gen01ruc) = 10 THEN 'C'
                            WHEN LENGTH(GEN01.gen01ruc) = 13 THEN 'R'
                            ELSE 'P'
                        END AS tipIdent, --TIPO DE IDENTIFICACION
                        GEN01.gen01ruc idIdent, --NUMERO DE IDENTIFICACION
                        GEN01.gen01com razSoc, --NOMBRE COMPLETO O RAZON SOCIAL
                        decode(PUR01.pur01esta ,'TT','02','01') tipTrans, --TIPO DE TRANSACCION A REPORTAR
                        'NINGUNO' otroTipTrans,
                        PUR06.PUR06POR porPropiedad, --OTRO TIPO DE TRANSACCION A REPORTAR
                        '01' tipBien, --TIPO DE BIEN INMUEBLE
                        'NINGUNO' otroTipBien, --OTRO TIPO DE BIEN INMUEBLE 
                        NVL (PUR01.PUR01PRED ,'0') numPred, --NUMERO DE PREDIO
                        NVL (PUR01.PUR01PRED ,'0') clavCat, --CLAVE CATASTRAL
                        TO_CHAR(NVL(PUR01.PUR01AVTTS, 0), 'FM999999999990.00') AS avalInm, ---AVALUO DEL TERRENO
                        TO_CHAR(NVL(PUR01.PURAVACONS, 0), 'FM999999999990.00') AS avalConst, --AVALUO AREA DE CONSTRUCCION DEL BIEN INMUEBLE
                        REPLACE(TO_CHAR(NVL(PUR01.PUR01ATTER,0), 'FM999999999990.00'),'0.00', '0.01') arTotal, --AREA TOTAL DEL BIEN INMUEBLE
                        REPLACE(TO_CHAR(NVL(PUR01.PUR01TAVRE,0), 'FM999999999990.00'),'0.00', '0.01') avalTotal, -- AVALUO TOTAL DEL BIEN INMUEBLE,
                        '113' AS provincia,
                        '11314' AS canton,
                        CASE
                            WHEN (PUR01.PUR01PARRO) = 57 THEN '1131457'
                            WHEN (PUR01.PUR01PARRO) = 53 THEN '1131453'
                            WHEN (PUR01.PUR01PARRO) = 02 THEN '1131402'
                            WHEN (PUR01.PUR01PARRO) = 01 THEN '1131401'
                            ELSE '1131457'
                            END AS parroquia,
                        CASE 
                            WHEN LENGTH(NVL(PUR01.PUR01DIR,'Sucre')) < 5 THEN 'sucre'
                            ELSE NVL(PUR01.PUR01DIR,'Sucre')
                        END AS direccion
                    FROM GEN01 
                    INNER JOIN PUR06 ON GEN01.GEN01CODI = PUR06.GEN01CODI
                    INNER JOIN PUR01 ON PUR01.PUR01PRED = PUR06.PUR01PRED
                    WHERE PUR01.PUR01ESTA IN ('IG','MD','TT','CO')
                    AND PUR06.PUR06POR != 0
                    AND GEN01.gen01ruc NOT LIKE '%ELI%'
                    AND GEN01.gen01ruc NOT LIKE '%-1%'
                    --AND PUR01.PUR01PRED = 1314010101046002
                    UNION ALL
                    SELECT 
                    CASE   
                            WHEN UPPER(GEN01.gen01ruc) LIKE '%HEREDEROS%' THEN 'P'
                            WHEN UPPER(GEN01.gen01ruc) LIKE '%SOCIEDAD%'  THEN 'P'
                            WHEN UPPER(GEN01.gen01ruc) LIKE '%FALLECIDO%'  THEN 'P'
                            WHEN LENGTH(GEN01.gen01ruc) = 10 THEN 'C'
                            WHEN LENGTH(GEN01.gen01ruc) = 13 THEN 'R'
                            ELSE 'P'
                        END AS tipIdent, --TIPO DE IDENTIFICACION 
                        GEN01.gen01ruc idIdent, --NUMERO DE IDENTIFICACION
                        GEN01.gen01com razSoc, --NOMBRE COMPLETO O RAZON SOCIAL
                        decode(PRU01.PRU01ESTA ,'TT','02','01') tipTrans, --TIPO DE TRANSACCION A REPORTAR
                        'NNGUNO' otroTipTrans, --OTRO TIPO DE TRANSACCION A REPORTAR
                        PRU10.PRU10PORC proPropiedad, --PORCENTAJE DE PROPIEDAD
                        '01' tipBien, --TIPO DE BIEN INMUEBLE
                        'NINGUNO' otroTipBien, --OTRO TIPO DE BIEN INMUEBLE 
                        NVL (PRU01.PRU01CLA ,'0') numPred, --NUMERO DE PREDIO
                        NVL (PRU01.PRU01CLA ,'0') clavCat, --CLAVE CATASTRAL
                        TO_CHAR(
                            ABS(
                                NVL(prU01.PRU01AVAL, 0) - 
                                NVL((
                                    SELECT pur05aREAL 
                                    FROM pru05 pru 
                                    WHERE prU01.PRU01CLA = pru.pru01cla 
                                    AND rownum = 1
                                ), 0)
                            ), 
                            'FM999999999990.00'
                        ) avalInm, --AVALUO DEL TERRENO,
                        TO_CHAR(NVL((select pur05aREAL from pru05 pru where PRU01.PRU01CLA=pru.pru01cla and rownum=1),0), 'FM999999999990.00') avalConst, --AVALUO AREA DE CONSTRUCCION DEL BIEN INMUEBLE
                        REPLACE(TO_CHAR(NVL(PRU01.Pru01supe,0), 'FM999999999990.00'),'0.00', '0.01') arTotal, --AREA TOTAL DEL BIEN INMUEBLE
                        REPLACE(TO_CHAR(NVL(PRU01.PRU01AVAL,0), 'FM999999999990.00'),'0.00', '0.01') avalTotal, -- AREA TOTAL DEL BIEN INMUEBLE,
                        '113' AS provincia,
                        '11314' AS canton,
                        '1131401' AS parroquia,
                        -- Reemplazo en dirección cuando tiene 5 caracteres
                        CASE 
                            WHEN LENGTH(NVL(PRU01.pru01npre,'Sucre')) < 5 THEN 'sucre'
                            ELSE NVL(PRU01.pru01npre,'Sucre')
                        END AS direccion
                    FROM PRU01
                    INNER JOIN PRU10
                    ON PRU01.PRU01CLA = PRU10.PRU01CLA
                    INNER JOIN GEN01
                    ON PRU10.GEN01CODI = GEN01.GEN01CODI
                    WHERE PRU01.PRU01ESTA NOT IN ('PE','DU')
                    AND PRU10.PRU10PORC != 0
                    AND GEN01.gen01ruc NOT LIKE '%ELI%'
                    AND GEN01.gen01ruc NOT LIKE '%-1%'

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
