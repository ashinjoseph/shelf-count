#!/usr/bin/env python3
"""
build_stock_count_list.py — turn raw POS product exports into a stock-count list.

The POS exports every button on the till, not every product: department keys
("Grocery (Tax)"), services (Key Cut, Photo, Fob), lottery and unidentified
scans all come through as rows. None of those hold stock, so counting them
wastes staff time and pollutes min/max reporting.

Reads the semicolon-delimited exports:
    Name;CategoryId;SalePriceExTax;SalePriceIncTax;Barcode;SalePriceTaxGroupId

Writes:
    stock_count_list.csv   — trackable products, grouped for shelf-by-shelf counting
    stock_count_excluded.csv — everything dropped, with the reason (for review)

The kept list is the roster staff count against; the counts collected go back to
the ePOS catalog, which owns stock from then on. This script only prepares the
roster — writing the ePOS import file is a separate step, pending that template.

Usage:
    python build_stock_count_list.py <export.csv> [...] -o .
"""

import argparse
import csv
import os
import re
import sys
from collections import OrderedDict

# --- rows that are till buttons, not stock -----------------------------------

# Internal PLUs the till uses for services. These carry a price but no goods.
SERVICE_PLUS = {
    '24185': 'Key cut — service',
    '24343': 'Photo — service',
    '24348': 'Bottle deposit — levy',
    '24188': 'Debit card fee — fee',
    '24564': 'Fob — service',
    '24542': 'Patty — hot food, made to order',
    '24543': 'Patty combo — hot food, made to order',
}

# Categories that never hold countable stock.
SERVICE_CATEGORIES = {'LOTTERY'}

# --- shelf grouping ----------------------------------------------------------

# Staff count one section at a time, so the list is grouped the way the store is
# walked, not the way the POS happens to spell its categories.
COUNT_GROUPS = OrderedDict([
    ('Tobacco',            ['TOBACCO', 'JTI VAPE & CIGARATE']),
    ('Vape & Smoke Acc.',  ['TOBACCO Accessories', 'VAPE & CIGAR', 'BONG AND PIPES', 'LIGHTER']),
    ('Beer & Coolers',     ['Beer', 'Beer 6 Pack', 'ALCOHOL', 'Alcoholic Cocktails', 'R.T.D.', 'Wine']),
    ('Drinks',             ['DRINKS', 'DRINKS NO TAX', 'DRINK/SLUSHY', 'ENERGY DRINK',
                            'JUICE', 'WATER', 'bevrages']),
    ('Chips & Snacks',     ['CHIPS', 'CHIPS & SNACKS', 'SNACK', 'SNACKS', 'COOKIES']),
    ('Candy & Chocolate',  ['CANDY GUMS CHOCOLATES']),
    ('Ice Cream & Frozen', ['ICE CREAMS', 'Ice cream', 'ICE']),
    ('Dairy',              ['DAIRY PRODUCTS', 'DAIRY PRODUCTS TAXABLE']),
    ('Grocery',            ['GROCERY', 'GROCERY NO TAX', 'BAKERY', 'DELI', 'FOOD ITMES', 'PET FOOD']),
    ('Health & Beauty',    ['HEALTH & BEAUTY']),
    ('Household & General',['GENERAL ITEMS', 'GENERAL ITMES', 'GENERAL NO TAX', 'HOUSE HOLD ITEM',
                            'OTHER', 'SEASONAL', 'STATIONARY', 'HARDWARE']),
    ('Electronics',        ['Electronics - My top gift', 'ELECTRONICS', 'cell phone accesroies',
                            'Cables and Chargers', 'phone card']),
])

CATEGORY_TO_GROUP = {cat: grp for grp, cats in COUNT_GROUPS.items() for cat in cats}
GROUP_ORDER = {grp: i for i, grp in enumerate(COUNT_GROUPS)}
UNGROUPED = 'Unsorted'

# Sections worth a tighter count cadence: high value, high shrink, or bought by
# the carton. Flagged so min/max can be filled here first.
PRIORITY_GROUPS = {'Tobacco', 'Beer & Coolers', 'Electronics', 'Vape & Smoke Acc.'}
PRIORITY_PRICE = 15.00


def norm_barcode(barcode):
    """Leading zeros are cosmetic in POS exports — compare without them."""
    return (barcode or '').strip().lstrip('0')


def money(value):
    try:
        return float((value or '').strip())
    except ValueError:
        return 0.0


def classify(row):
    """Return None to keep the row, or a reason string to drop it."""
    name = (row.get('Name') or '').strip()
    barcode = (row.get('Barcode') or '').strip()
    category = (row.get('CategoryId') or '').strip()

    if not name:
        return 'No product name'
    if category in SERVICE_CATEGORIES:
        return 'Lottery — sold from the terminal, not from stock'
    if not barcode:
        return 'Department / open key — no barcode, nothing to count'
    if barcode in SERVICE_PLUS:
        return SERVICE_PLUS[barcode]
    if re.fullmatch(r'\d{6,}', name):
        return 'Unidentified scan — name is just the barcode'
    if name.lower().startswith(('http://', 'https://')):
        return 'Unidentified scan — name is a URL'
    return None


def count_group(category):
    return CATEGORY_TO_GROUP.get(category, UNGROUPED)


def read_exports(paths):
    rows = []
    for path in paths:
        with open(path, encoding='utf-8-sig', newline='') as fh:
            reader = csv.DictReader(fh, delimiter=';')
            if 'Name' not in (reader.fieldnames or []):
                sys.exit('%s: not a POS export (no Name column)' % path)
            for row in reader:
                row['_source'] = os.path.basename(path)
                rows.append(row)
    return rows


def build(rows):
    kept, dropped = OrderedDict(), []

    for row in rows:
        reason = classify(row)
        name = (row.get('Name') or '').strip()
        barcode = (row.get('Barcode') or '').strip()
        category = (row.get('CategoryId') or '').strip()

        if reason:
            dropped.append({
                'product_name': name, 'barcode': barcode,
                'category': category, 'reason': reason, 'source_file': row['_source'],
            })
            continue

        key = norm_barcode(barcode)
        if key in kept:
            first = kept[key]
            dropped.append({
                'product_name': name, 'barcode': barcode, 'category': category,
                'reason': 'Duplicate barcode — already listed as "%s"' % first['product_name'],
                'source_file': row['_source'],
            })
            continue

        group = count_group(category)
        price = money(row.get('SalePriceIncTax'))
        kept[key] = {
            'count_group': group,
            'product_name': name,
            'barcode': barcode,
            'price': '%.2f' % price,
            'pos_category': category,
            'priority': 'A' if (group in PRIORITY_GROUPS or price >= PRIORITY_PRICE) else 'B',
            'stock': '',
            'min': '',
            'max': '',
            'counted_by': '',
            'counted_at': '',
            'notes': '',
        }

    products = sorted(
        kept.values(),
        key=lambda p: (GROUP_ORDER.get(p['count_group'], len(GROUP_ORDER)),
                       p['product_name'].lower()),
    )
    return products, dropped


FIELDS = ['count_group', 'product_name', 'barcode', 'price', 'pos_category',
          'priority', 'stock', 'min', 'max', 'counted_by', 'counted_at', 'notes']
DROP_FIELDS = ['product_name', 'barcode', 'category', 'reason', 'source_file']


def write_csv(path, fields, rows):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('exports', nargs='+', help='POS export CSV files')
    ap.add_argument('-o', '--outdir', default='.', help='where to write the output CSVs')
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    rows = read_exports(args.exports)
    products, dropped = build(rows)

    list_path = os.path.join(args.outdir, 'stock_count_list.csv')
    drop_path = os.path.join(args.outdir, 'stock_count_excluded.csv')
    write_csv(list_path, FIELDS, products)
    write_csv(drop_path, DROP_FIELDS, dropped)

    print('Read      %d rows from %d export(s)' % (len(rows), len(args.exports)))
    print('Trackable %d  -> %s' % (len(products), list_path))
    print('Excluded  %d  -> %s' % (len(dropped), drop_path))
    print()
    counts = OrderedDict()
    for p in products:
        counts[p['count_group']] = counts.get(p['count_group'], 0) + 1
    for group in list(COUNT_GROUPS) + [UNGROUPED]:
        if group in counts:
            print('  %-20s %4d' % (group, counts[group]))


if __name__ == '__main__':
    main()
