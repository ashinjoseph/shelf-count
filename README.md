# Shelf Count — temporary stock capture for ePOS

A standalone, throwaway app. Its only job is to get a stock number against every
real product once, so those numbers can be loaded into the **ePOS product
catalog**, which is where stock lives from then on.

```
ePOS product export  →  filter to real products  →  staff count on phones
                                                          ↓
                        ePOS catalog  ←  import file in ePOS's format
```

Once the numbers are in ePOS and ePOS is maintaining them, this app has done its
job and can be dropped. Nothing here is meant to become permanent.

**Built to be thrown away.** It has its own repo, its own spreadsheet, its own
Apps Script project and its own deployment. It shares no code, no sheet and no
login with anything else, so deleting this repo once the counts are in ePOS
breaks nothing.

It is deliberately small: `doGet` serves the UI, `rpcSubmit` writes what the UI
collects into a sheet, `rpcBootstrap` reads the product list back out. The rest
of the code is the offline queue, which runs in the browser.

## Status

| Step | State |
|---|---|
| Filter the export down to real products | done — 905 of 931 rows |
| Phone UI for entry | done — `src/Index.html` |
| Capture + offline-safe sync | done — `src/Code.gs` |
| Spreadsheet to upload | done — `Shelf Count.xlsx` |
| Deploy | ready — see [`SETUP.md`](SETUP.md) |
| Export in ePOS import format | **blocked — need the ePOS Bulk Import template** |

## Layout

```
shelf-count/
├── build_stock_count_list.py   POS export → countable product list
├── build_stock_count_sheet.py  that list → the workbook you upload
├── build_single_file.py        src/ → dist/Code.gs, one file to paste by hand
├── dist/Code.gs                generated; for setting up without a terminal
├── Shelf Count.xlsx            upload this to Drive; barcodes typed as text
├── stock_count_list.csv        905 products, source for the workbook
├── stock_count_excluded.csv    the 26 dropped rows and why
├── ui-sample.html              standalone mockup, opens in any browser
├── SETUP.md                    spreadsheet + deployment steps
├── package.json                clasp, for pushing src/ to Apps Script
├── .clasp.json.example          copy to .clasp.json, add the script id
└── src/                        the Apps Script project (its own, not StoreOps')
    ├── appsscript.json
    ├── Code.gs                 roster + batched count writes
    └── Index.html              the phone UI
```

The exact column layout ePOS accepts is not published; it comes from the
template the Bulk Import app itself hands you. Until that template is in hand,
the export step cannot be written without guessing.

### Careful with leading zeros

Most barcodes in this catalog are zero-padded (`072890000224`). **Excel strips
leading zeros on open**, silently, which would break the barcode match on import
and is easy to miss until the upload fails or — worse — matches the wrong
product. Import the CSV into Google Sheets rather than opening it in Excel, and
set the barcode column to plain text before anything else.

### One barcode collides

`072890000224` and `72890000224` are the same Heineken bottle entered twice in
ePOS at two different prices ($3.01 and $3.60). A barcode-keyed import has no
way to tell which row a count belongs to, so this wants fixing in ePOS before
the upload, not after.

## Building the list

```bash
python build_stock_count_list.py <ProductList*.csv> -o .
```

Reads the semicolon-delimited POS export
(`Name;CategoryId;SalePriceExTax;SalePriceIncTax;Barcode;SalePriceTaxGroupId`)
and writes two files:

| File | Contents |
|---|---|
| `stock_count_list.csv` | the trackable products, grouped for shelf-by-shelf counting |
| `stock_count_excluded.csv` | every dropped row with the reason, so the call can be reviewed |

Re-running is safe — both files are rewritten from the exports each time.

## Current result

905 trackable products out of 931 exported rows; 26 excluded.

| Section | Products |
|---|---|
| Tobacco | 95 |
| Vape & Smoke Acc. | 22 |
| Beer & Coolers | 104 |
| Drinks | 170 |
| Chips & Snacks | 74 |
| Candy & Chocolate | 80 |
| Ice Cream & Frozen | 27 |
| Dairy | 8 |
| Grocery | 138 |
| Health & Beauty | 95 |
| Household & General | 36 |
| Electronics | 56 |

## What was excluded, and why

| Reason | Count | Examples |
|---|---|---|
| Department / open key — no barcode | 10 | `Grocery (Tax)`, `Miscellaneous`, `Cigars`, `Alcohol` |
| Lottery — sold from the terminal | 2 | `Lotto`, `Instant` |
| Service / fee PLU | 7 | `Key Cut`, `Photo`, `Fob`, `Bottle Deposit`, `Debit Card Fees` |
| Hot food, made to order | 2 | `Patty`, `Patty Combo` |
| Unidentified scan (name is the barcode, or a URL) | 6 | `06215718`, `http://pepsico.info/4yLCUx` |
| Duplicate barcode | 1 | `HEINEKEN 330UNIT` (same barcode as `Heineken Bottle 330ml`) |

Two judgement calls worth knowing about:

- **Kept** `Captain Black` (PLU `24333`/`24332`) and `RXBAR` (PLU `24435`).
  They sit on internal PLUs like the services do, but they are real goods on a
  shelf.
- **The Heineken duplicate** is a genuine POS data problem, not just an export
  artifact: `072890000224` and `72890000224` are the same barcode entered twice
  at two different prices ($3.01 and $3.60). The zero-padded row is kept. Worth
  fixing in the POS so the till stops ringing the same bottle at two prices.

## Columns

| Column | Filled by | Notes |
|---|---|---|
| `count_group` | import | the section a counter walks |
| `product_name`, `barcode`, `price` | import | `price` is tax-inclusive, to help identify the item on the shelf |
| `pos_category` | import | the POS's own category, kept for traceability |
| `priority` | import | `A` = tobacco, beer, electronics, or anything $15+; count these first |
| `stock` | **staff, on the shelf** | the only field the phone UI requires |
| `min`, `max` | later, in the sheet | far quicker to fill by dragging down a column |
| `counted_by`, `counted_at` | the app | who entered the number and when |
| `notes` | anyone | damaged stock, wrong barcode, and so on |

## Grouping

Sections are derived from `CategoryId`, which the POS spells inconsistently
(`GENERAL ITEMS` / `GENERAL ITMES`, `Ice cream` / `ICE CREAMS`,
`CHIPS` / `CHIPS & SNACKS`). `COUNT_GROUPS` in the script maps every spelling
onto one section. A category that appears in a future export without a mapping
lands in `Unsorted` rather than being dropped — check for that group after any
re-import.
