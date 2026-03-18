import os
import traceback
from decimal import Decimal
from datetime import datetime
from io import BytesIO

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.db import connection

from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from PIL import Image as PILImage
from reportlab.lib.utils import ImageReader

from Cabildo_api.permissions import HasAPIKey
import logging

logger = logging.getLogger('api')


# ── Imágenes ────────────────────────────────────────────────────────────────────

IMG_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'img')
IMG_ESCUDO = os.path.join(IMG_DIR, 'escudo.jpg')
IMG_SUCRE  = os.path.join(IMG_DIR, 'sucre.jpg')
IMG_SELLO  = os.path.join(IMG_DIR, 'sello.jpg')

from reportlab.lib.pagesizes import A4

# Media hoja A4: 21 x 14.85 cm
MEDIA_CARTA = (A4[0], A4[1] / 2)


# ── SQL Queries ─────────────────────────────────────────────────────────────────

SQL_TITULO = """
SELECT
    e.emi01codi        AS NRO_EMISION,
    e.emi01clave       AS CLAVE,
    e.emi01anio        AS ANIO,
    e.emi01mes         AS MES,
    e.emi01fobl        AS FECHA_OBLIGACION,
    e.emi01femi        AS FECHA_EMISION,
    e.emi01fpag        AS FECHA_PAGO,
    e.emi01npag        AS NRO_PAGO,
    e.emi01lpag        AS LOGIN_PAGO,
    e.emi01vtot        AS VALOR_TOTAL,
    e.emi01inte        AS INTERES,
    e.emi01desc        AS DESCUENTO,
    e.emi01reca        AS RECARGO,
    NVL(e.emi01iva, 0) AS IVA,
    e.emi01esta        AS ESTADO,
    e.emi01titu        AS DESCRIPCION,
    g.gen01codi        AS CIU,
    g.gen01com         AS CONTRIBUYENTE,
    g.gen01ruc         AS RUC,
    g.gen01dir         AS DIRECCION,
    s.emi03des         AS SERIE
FROM emi01 e
JOIN gen01 g ON g.gen01codi = e.gen01codi
JOIN emi03 s ON s.emi03codi = e.emi01seri
WHERE e.emi01codi = :emi01codi
"""

SQL_RUBROS = """
SELECT
    t.emi04desd  AS RUBRO,
    d.emi02vdet  AS VALOR
FROM emi02 d
JOIN emi04 t ON t.emi04codi = d.emi04codi
WHERE d.emi01codi = :emi01codi
  AND d.emi04codi <> 2500
"""

SQL_ABONO = """
SELECT
    f.fpd01codi             AS CODI,
    f.fpd01nroabonos        AS NRO_ABONO,
    f.fpd01npago            AS NRO_PAGO,
    f.fpd01fpago            AS FECHA_PAGO,
    f.fpd01valortotalabono  AS VALOR_TOTAL,
    f.fpd01capital          AS CAPITAL,
    NVL(f.fpd01interes, 0)  AS INTERES,
    NVL(f.fpd01descue, 0)   AS DESCUENTO,
    NVL(f.fpd01recar, 0)    AS RECARGO,
    NVL(f.fpd01iva, 0)      AS IVA,
    NVL(f.fpd01coa, 0)      AS COACTIVA,
    f.fpd01estado           AS ESTADO,
    f.fpd01lingreso         AS LOGIN_PAGO
FROM fpd01 f
WHERE f.emi01codi = :emi01codi
  AND f.fpd01nroabonos = :nro_abono
"""

SQL_DETALLE_ABONO = """
SELECT
    t.emi04desd       AS RUBRO,
    d.fpd02devalor    AS VALOR_ORIGINAL,
    d.fpd02valorabo   AS VALOR_ABONADO
FROM fpd02 d
JOIN emi04 t ON t.emi04codi = d.emi04codi
WHERE d.emi01codi = :emi01codi
  AND d.fpd01nroabonos = :nro_abono
  AND d.emi04codi NOT IN (2500, 2502, 2503, 2505)
"""

SQL_CAJERO = """
SELECT r.rc01nombre AS CAJERO
FROM rc01 r
WHERE UPPER(TRIM(r.seg03codi)) = UPPER(TRIM(:lpag))
"""


# ── Helper ──────────────────────────────────────────────────────────────────────

def _fetch(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    return [
        {col: (float(val) if isinstance(val, Decimal) else val)
         for col, val in zip(cols, row)}
        for row in rows
    ]

#__________marca de agua para pdf___________
def _watermark_sello(canvas, doc):
    img = PILImage.open(IMG_SELLO).convert('RGBA')
    r, g, b, a = img.split()
    a = a.point(lambda x: int(x * 0.15))
    img.putalpha(a)
    wm_buffer = BytesIO()
    img.save(wm_buffer, format='PNG')
    wm_buffer.seek(0)

    w, h = doc.pagesize
    img_w = 5 * cm
    img_h = 5 * cm
    x = (w - img_w) / 2
    y = (h - img_h) / 2

    canvas.saveState()
    canvas.drawImage(ImageReader(wm_buffer), x, y, width=img_w, height=img_h, mask='auto')
    canvas.restoreState()

# ── PDF ─────────────────────────────────────────────────────────────────────────

def _fmt_fecha(f):
    return f.strftime('%d-%m-%Y') if f else '-'


def generar_pdf(titulo, rubros, abono, detalle_abono, cajero=None):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=MEDIA_CARTA,
        rightMargin=0.7 * cm,
        leftMargin=0.7 * cm,
        topMargin=0.4 * cm,
        bottomMargin=0.4 * cm,
    )

    estilo_inst   = ParagraphStyle('inst',   fontSize=9,   alignment=TA_CENTER, fontName='Helvetica-Bold', leading=9,  spaceAfter=0, spaceBefore=0)
    estilo_sub    = ParagraphStyle('sub',    fontSize=6.5, alignment=TA_CENTER, fontName='Helvetica',      leading=7.5,spaceAfter=0, spaceBefore=0)
    estilo_label  = ParagraphStyle('label',  fontSize=7,   fontName='Helvetica-Bold', leading=8, spaceAfter=0, spaceBefore=0)
    estilo_valor  = ParagraphStyle('valor',  fontSize=7,   fontName='Helvetica',      leading=8, spaceAfter=0, spaceBefore=0)
    estilo_valor_rubro  = ParagraphStyle('valor_rubro',  fontSize=7, fontName='Helvetica', leading=8, spaceAfter=0, spaceBefore=0, alignment=TA_RIGHT)
    estilo_desc   = ParagraphStyle('desc',   fontSize=6,   fontName='Helvetica', leading=7.5)
    estilo_footer = ParagraphStyle('footer', fontSize=6,   fontName='Helvetica', leading=7.5, spaceAfter=0, spaceBefore=0, alignment=TA_RIGHT)
    estilo_nro    = ParagraphStyle('nro',    fontSize=7,   alignment=TA_RIGHT, fontName='Helvetica-Bold')
    estilo_totales = ParagraphStyle('totales', fontSize=7, alignment=TA_RIGHT, fontName='Helvetica-Bold')
    estilos_totales_label = ParagraphStyle('totales_label', fontSize=7, alignment=TA_RIGHT, fontName='Helvetica')
    

    elementos = []

    # ── Encabezado ───────────────────────────────────────────────────────────────
    encabezado = Table(
        [[
            Image(IMG_ESCUDO, width=1.1*cm, height=1.4*cm),
            Table([
                [Paragraph('GAD MUNICIPAL DE SUCRE', estilo_inst)],
                [Paragraph('<b>Avenida Bolivar y Ascazubi</b>', estilo_sub)],
                [Paragraph('<b>Bahia de Caraquez - Sucre - Ecuador</b>', estilo_sub)],
                [Paragraph('<b>info@sucre.gob.ec</b>', estilo_sub)],
            ], colWidths=[12.8*cm], rowHeights=[0.38*cm, 0.28*cm, 0.28*cm, 0.28*cm]),
            Image(IMG_SUCRE, width=2.2*cm, height=1.0*cm),
        ]],
        colWidths=[2.2*cm, 13.5*cm, 2.5*cm]
    )
    encabezado.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    elementos.append(encabezado)
   # elementos.append(HRFlowable(width='100%', thickness=0.5, color=colors.grey))
    elementos.append(Spacer(1, 0.08*cm))

    # ── Contribuyente + Nro. Emisión ─────────────────────────────────────────────
    mes_nombre = {
        1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
        5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
        9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE'
    }.get(titulo.get('MES', 0), '')

    ruc_ciu = f"{titulo.get('RUC', '')}   Ciu: {titulo.get('CIU', '')}"
    concepto = titulo.get('SERIE', '')

    estilo_concepto = ParagraphStyle('concepto', fontSize=7.5, alignment=TA_CENTER, fontName='Helvetica-Bold', leading=9)
    estilo_abono    = ParagraphStyle('abono',    fontSize=6,   alignment=TA_CENTER, fontName='Helvetica', leading=8)

    # Fila del concepto: siempre se muestra
    clave = titulo.get('CLAVE', '') or ''

    caja_concepto = Table(
        [[Paragraph(concepto, estilo_concepto)]],
        colWidths=[9*cm]
    )
    caja_concepto.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.5, colors.black),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    tabla_concepto = Table(
        [[caja_concepto, Paragraph(f"Clave: <b>{clave}</b>", estilo_label)]],
        colWidths=[9.5*cm, 8*cm]
    )
    tabla_concepto.setStyle(TableStyle([
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',       (1, 0), (1, 0), 'LEFT'),
        ('LEFTPADDING', (1, 0), (1, 0), 5),
    ]))

    filas_info = [
        [Paragraph('<b>CONTRIBUYENTE:</b>', estilo_label), Paragraph(f"<b>{titulo.get('CONTRIBUYENTE', '')}</b>", estilo_valor)],
        [Paragraph('<b>RUC/Cedula:</b>',    estilo_label), Paragraph(ruc_ciu, estilo_valor)],
        [tabla_concepto, ''],
    ]
    spans = [('SPAN', (0, 2), (1, 2))]

    direccion_txt = f"<b>Direccion de contribuyente:</b> {titulo.get('DIRECCION', '') or ''}"

    if abono:
        texto_abono = (
            f"<b>PAGO DE ABONOS NRO {abono['NRO_ABONO']}</b>   "
            f"Correspondiente: <b>{mes_nombre} - {titulo.get('ANIO', '')}</b>"
        )
        filas_info.append([Paragraph(texto_abono, estilo_abono), ''])
        spans.append(('SPAN', (0, 3), (1, 3)))
        filas_info.append([Paragraph(direccion_txt, estilo_valor), ''])
        spans.append(('SPAN', (0, 4), (1, 4)))
    else:
        estilo_correspondiente = ParagraphStyle(
            'correspondiente', fontSize=6, alignment=TA_CENTER,
            fontName='Helvetica', leading=8, spaceAfter=0, spaceBefore=0
        )
        texto_correspondiente = f"Correspondiente: <b>{mes_nombre} - {titulo.get('ANIO', '')}</b>"
        filas_info.append([Paragraph(texto_correspondiente, estilo_correspondiente), ''])
        spans.append(('SPAN', (0, 3), (1, 3)))
        filas_info.append([Paragraph(direccion_txt, estilo_valor), ''])
        spans.append(('SPAN', (0, 4), (1, 4)))

    info_izq = Table(filas_info, colWidths=[3.2*cm, 8.4*cm])
    info_izq.setStyle(TableStyle([
        ('FONTSIZE',      (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 0),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        *spans,
    ]))

    info_der = Table([
        [Paragraph(f"Nro. Emision: {titulo.get('NRO_EMISION', '')}", estilo_nro)],
    ], colWidths=[4.5*cm])

    seccion_info = Table([[info_izq, info_der]], colWidths=[12.1*cm, 4.5*cm])
    seccion_info.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementos.append(seccion_info)

    # ── Rubros + Totales (2 columnas) ────────────────────────────────────────────
    lista_rubros = detalle_abono if abono else rubros

    filas_rubros = [[
        Paragraph('<b>Rubros / Componente</b>', estilo_label),
        Paragraph('<b>Valor</b>', estilo_valor_rubro),
    ]]
    for r in lista_rubros:
        valor = r.get('VALOR_ABONADO', r.get('VALOR', 0)) or 0
        filas_rubros.append([
            Paragraph(r.get('RUBRO', ''), estilo_valor),
            Paragraph(f"{valor:.2f}", estilo_valor_rubro),
        ])

    tabla_rubros = Table(filas_rubros, colWidths=[8.5*cm, 2.5*cm])
    tabla_rubros.setStyle(TableStyle([
        ('FONTSIZE',      (0, 0), (-1, -1), 7),
        ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('TOPPADDING',    (0, 0), (-1,  0), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('BOX',           (0, 0), (-1, 0), 0.5, colors.black),
        ('LINEBEFORE',    (1, 0), (1, 0), 0.5, colors.black),
    ]))

    if abono:
        capital   = abono.get('CAPITAL', 0) or 0
        interes   = abono.get('INTERES', 0) or 0
        descuento = abono.get('DESCUENTO', 0) or 0
        recargo   = abono.get('RECARGO', 0) or 0
        iva       = abono.get('IVA', 0) or 0
        total     = abono.get('VALOR_TOTAL', 0) or 0
    else:
        capital   = titulo.get('VALOR_TOTAL', 0) or 0
        interes   = titulo.get('INTERES', 0) or 0
        descuento = titulo.get('DESCUENTO', 0) or 0
        recargo   = titulo.get('RECARGO', 0) or 0
        iva       = titulo.get('IVA', 0) or 0
        total     = capital + interes - descuento + recargo + iva

    filas_totales = [
        [Paragraph('<b>Subtotal:</b>', estilos_totales_label), Paragraph(f"*** {capital:.2f}",             estilo_totales)],
        [Paragraph('Desc:',           estilos_totales_label), Paragraph(f"*** {descuento:.2f}",               estilo_totales)],
        [Paragraph('Total:',          estilos_totales_label), Paragraph(f"*** {(capital - descuento):.2f}",   estilo_totales)],
        [Paragraph('Interes:',        estilos_totales_label), Paragraph(f"*** {interes:.2f}",                 estilo_totales)],
        [Paragraph('Iva:',            estilos_totales_label), Paragraph(f"*** {iva:.2f}",                     estilo_totales)],
        [Paragraph('',   estilos_totales_label), Paragraph(f"*** {total:.2f}",               estilo_totales)],
    ]

    tabla_totales = Table(filas_totales, colWidths=[2*cm, 1.9*cm])
    tabla_totales.setStyle(TableStyle([
        ('FONTSIZE',      (0, 0), (-1, -1), 7),
        ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('BOX',           (0, 0), (-1, -1), 0.5, colors.black),
    ]))

    # ── Datos de pago (columna derecha, debajo de totales) ───────────────────────
    nro_pago   = abono.get('NRO_PAGO')   if abono else titulo.get('NRO_PAGO')
    fecha_pago = abono.get('FECHA_PAGO') if abono else titulo.get('FECHA_PAGO')

    filas_pago = [
        [Paragraph(f"<b>Fecha Impresion:</b> {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}", estilo_footer)],
        [Paragraph(f"<b>Número de Pago:</b> {nro_pago or '-'}", estilo_footer)],
        [Paragraph(f"<b>Fecha Emision:</b> {_fmt_fecha(titulo.get('FECHA_EMISION'))}", estilo_footer)],
        [Paragraph(f"<b>Fecha Obligacion:</b> {_fmt_fecha(titulo.get('FECHA_OBLIGACION'))}", estilo_footer)],
        [Paragraph(f"<b>Fecha Pago:</b> {_fmt_fecha(fecha_pago)}", estilo_footer)],
    ]
    tabla_pago = Table(filas_pago, colWidths=[4.7*cm])
    tabla_pago.setStyle(TableStyle([
        ('FONTSIZE',      (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
    ]))

    # Columna derecha: solo totales
    col_derecha = Table([
        [tabla_totales],
    ], colWidths=[5*cm])
    col_derecha.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (0, 0), 0.5*cm),
        ('RIGHTPADDING', (0, 0), (0, 0), 0),
    ]))

    # Columna izquierda: solo rubros
    col_izquierda = Table([
        [tabla_rubros],
    ], colWidths=[11.3*cm])
    col_izquierda.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    seccion_principal = Table([[col_izquierda, col_derecha]], colWidths=[11.3*cm, 5*cm])
    seccion_principal.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementos.append(seccion_principal)

    # ── Descripción + Datos de pago (misma fila) ─────────────────────────────────
    descripcion = titulo.get('DESCRIPCION') or ''
    if descripcion:
        desc_tabla = Table(
            [[Paragraph(f"<b>Descripcion:</b> {descripcion}", estilo_desc)]],
            colWidths=[11*cm]
        )
        desc_tabla.setStyle(TableStyle([
            ('BOX',           (0, 0), (-1, -1), 0.75, colors.black),
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 30),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ]))
    else:
        desc_tabla = Spacer(1, 0.1*cm)

    seccion_inferior = Table(
        [[desc_tabla, tabla_pago]],
        colWidths=[11.3*cm, 5*cm]
    )
    seccion_inferior.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementos.append(seccion_inferior)

    # ── Cajero recaudador ─────────────────────────────────────────────────────────
    if cajero:
        estilo_cajero_nombre = ParagraphStyle(
            'cajero_nombre', fontSize=7, alignment=TA_CENTER,
            fontName='Helvetica-Bold', leading=9, spaceAfter=0, spaceBefore=0
        )
        estilo_cajero_label = ParagraphStyle(
            'cajero_label', fontSize=6.5, alignment=TA_CENTER,
            fontName='Helvetica', leading=8, spaceAfter=0, spaceBefore=0
        )
        caja_cajero = Table(
            [
                [HRFlowable(width='60%', thickness=0.5, color=colors.black, spaceAfter=0, spaceBefore=0)],
                [Paragraph(cajero, estilo_cajero_nombre)],
                [Paragraph('Recaudador', estilo_cajero_label)],
            ],
            colWidths=[16*cm]
        )
        caja_cajero.setStyle(TableStyle([
            ('BOX',           (0, 0), (-1, -1), 0.5, colors.black),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING',    (0, 0), (-1, -1), 25),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1,  0), 0),
            ('BOTTOMPADDING', (0, 0), (-1,  0), 2),
            ('BOTTOMPADDING', (0, 1), (-1,  1), 0),
            ('TOPPADDING',    (0, 2), (-1,  2), 0),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ]))
        tabla_cajero = Table([[caja_cajero]], colWidths=[19.4*cm])
        tabla_cajero.setStyle(TableStyle([
            ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        elementos.append(tabla_cajero)

    doc.build(elementos, onFirstPage=_watermark_sello, onLaterPages=_watermark_sello)
    buffer.seek(0)
    return buffer.read()


# ── View ────────────────────────────────────────────────────────────────────────

class ComprobanteAPIView(APIView):
    """
    GET /api/comprobante/<emi01codi>/
    GET /api/comprobante/<emi01codi>/<nro_abono>/

    Retorna el comprobante de pago en PDF.
    Sin nro_abono: título pagado completo.
    Con nro_abono: abono específico.
    """
    permission_classes = [HasAPIKey]

    def get(self, request, emi01codi, nro_abono=None):
        try:
            titulo_rows = _fetch(SQL_TITULO, {'emi01codi': emi01codi})
            if not titulo_rows:
                return Response(
                    {'detail': f'No se encontro el titulo {emi01codi}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            titulo = titulo_rows[0]

            rubros = _fetch(SQL_RUBROS, {'emi01codi': emi01codi})

            abono = None
            detalle_abono = []
            if nro_abono is not None:
                abono_rows = _fetch(SQL_ABONO, {'emi01codi': emi01codi, 'nro_abono': nro_abono})
                if not abono_rows:
                    return Response(
                        {'detail': f'No se encontro el abono {nro_abono} para el titulo {emi01codi}'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                abono = abono_rows[0]
                detalle_abono = _fetch(SQL_DETALLE_ABONO, {'emi01codi': emi01codi, 'nro_abono': nro_abono})

            cajero = None
            lpag_val = abono.get('LOGIN_PAGO') if abono else titulo.get('LOGIN_PAGO')
            if lpag_val:
                cajero_rows = _fetch(SQL_CAJERO, {'lpag': lpag_val})
                if cajero_rows:
                    cajero = cajero_rows[0].get('CAJERO')

            pdf_bytes = generar_pdf(titulo, rubros, abono, detalle_abono, cajero)

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="comprobante_{emi01codi}.pdf"'
            return response

        except Exception as e:
            logger.error(
                f"ComprobanteAPIView - Error: {str(e)}\n{traceback.format_exc()}",
                extra={'method': 'GET', 'path': request.path}
            )
            return Response(
                {'detail': 'Error al generar el comprobante', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
