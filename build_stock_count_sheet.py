#!/usr/bin/env python3
"""
build_stock_count_sheet.py — turn stock_count_list.csv into the workbook to upload.

Why a workbook and not the CSV: 640 of these barcodes are zero-padded
(`072890000224`). CSV carries no type information, so Sheets and Excel both
guess "number" on import and throw the leading zero away — silently, and
irreversibly once saved. An xlsx stores each barcode as a typed text cell, so it
survives the upload with no formatting step and nothing for anyone to remember.

Usage:
    python build_stock_count_sheet.py [-i stock_count_list.csv] [-o "Shelf Count.xlsx"]
"""

import argparse
import csv

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADERS = ['count_group', 'product_name', 'barcode', 'price', 'pos_category', 'priority',
           'stock', 'min', 'max', 'counted_by', 'counted_at', 'notes']

# Written by the app or filled in by a manager; headed in green so the columns
# that identify the product to ePOS are visibly not for editing.
FILLABLE = {'stock', 'min', 'max', 'counted_by', 'counted_at', 'notes'}

FONT = 'Arial'
INK = '14181F'
PINE = '1F5F52'

README_LINES = [
    ('Shelf Count — product list for the ePOS stock count', True),
    ('', False),
    ('Upload this file to Google Drive and open it with Google Sheets.', False),
    ('Do NOT open it in Excel and re-save — Excel strips the leading zeros from', False),
    ('barcodes, which breaks the match when the counts go back into ePOS.', False),
    ('', False),
    ('The stock_count tab holds the products. The script reads that tab by name,', False),
    ('so leave it exactly as it is.', False),
    ('', False),
    ('Filled in by the app as staff count:', True),
    ('    stock, counted_by, counted_at', False),
    ('', False),
    ('Filled in by you, in the sheet, whenever suits:', True),
    ('    min, max, notes   — optional; quickest by dragging a column down', False),
    ('', False),
    ('Do not edit — these identify the product to ePOS:', True),
    ('    count_group, product_name, barcode, price, pos_category, priority', False),
    ('', False),
    ('Example of a filled row (shown here, deliberately not in the data):', True),
]

EXAMPLE = ['Tobacco', 'Belmont 20 ks', '061900000132', 18.50, 'TOBACCO', 'A',
           12, 10, 40, 'Ashin', '2026-09-11 18:40', 'damaged pack pulled']


def build_readme(ws):
    """
    The legend gets its own tab deliberately. rpcBootstrap reads every row of
    stock_count that carries a product name, so a sample row sitting in the data
    would be served to the phones as a real product to count.
    """
    for i, (text, bold) in enumerate(README_LINES, start=1):
        ws.cell(row=i, column=1, value=text).font = Font(name=FONT, size=11, bold=bold)

    head = len(README_LINES) + 1
    for j, (name, value) in enumerate(zip(HEADERS, EXAMPLE), start=1):
        hc = ws.cell(row=head, column=j, value=name)
        hc.font = Font(name=FONT, size=9, bold=True, color='FFFFFF')
        hc.fill = PatternFill('solid', fgColor=PINE)
        vc = ws.cell(row=head + 1, column=j, value=value)
        vc.font = Font(name=FONT, size=10)
        if name == 'barcode':
            vc.number_format = '@'

    ws.column_dimensions['A'].width = 74
    for j in range(2, len(HEADERS) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 14


def build_products(ws, rows):
    thin = Side(style='thin', color='D2CEC6')
    for j, name in enumerate(HEADERS, start=1):
        c = ws.cell(row=1, column=j, value=name)
        c.font = Font(name=FONT, size=10, bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=PINE if name in FILLABLE else INK)
        c.alignment = Alignment(horizontal='left', vertical='center')
        c.border = Border(bottom=thin)
    ws.row_dimensions[1].height = 22

    for i, r in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=r['count_group'])
        ws.cell(row=i, column=2, value=r['product_name'])
        # A string in a text-formatted cell — the point of the whole file.
        ws.cell(row=i, column=3, value=r['barcode']).number_format = '@'
        ws.cell(row=i, column=4, value=float(r['price'])).number_format = '$#,##0.00'
        ws.cell(row=i, column=5, value=r['pos_category'])
        ws.cell(row=i, column=6, value=r['priority'])
        for j in (7, 8, 9):
            ws.cell(row=i, column=j).number_format = '0'
        ws.cell(row=i, column=11).number_format = 'yyyy-mm-dd hh:mm'
        for j in range(1, len(HEADERS) + 1):
            ws.cell(row=i, column=j).font = Font(name=FONT, size=10)

    for col, width in {'A': 19, 'B': 40, 'C': 16, 'D': 10, 'E': 23, 'F': 8,
                       'G': 8, 'H': 7, 'I': 7, 'J': 13, 'K': 17, 'L': 26}.items():
        ws.column_dimensions[col].width = width

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = 'A1:%s%d' % (get_column_letter(len(HEADERS)), len(rows) + 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-i', '--input', default='stock_count_list.csv')
    ap.add_argument('-o', '--output', default='Shelf Count.xlsx')
    args = ap.parse_args()

    with open(args.input, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != HEADERS:
            raise SystemExit('%s has unexpected columns: %r' % (args.input, reader.fieldnames))
        rows = list(reader)

    wb = Workbook()
    build_readme(wb.active)
    wb.active.title = 'readme'
    products = wb.create_sheet('stock_count')
    build_products(products, rows)
    wb.active = wb.index(products)
    wb.save(args.output)

    padded = sum(1 for r in rows if r['barcode'].startswith('0'))
    print('%d products -> %s (%d zero-padded barcodes kept as text)'
          % (len(rows), args.output, padded))


if __name__ == '__main__':
    main()
