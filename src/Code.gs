// ============================================================
//  Code.gs — Shelf Count: temporary stock capture for ePOS
// ============================================================
//  Standalone. Bound to its own spreadsheet, deployed as its own web
//  app, shares nothing with StoreOps. Counts collected here are loaded
//  into the ePOS product catalog, which owns stock from then on.
//
//  One person counts at a time, so there is no section claiming and no
//  conflict resolution: a later write for a barcode simply wins. What
//  the code does defend against is the network, because a phone in a
//  stockroom loses signal and suspends backgrounded tabs. Entries are
//  queued on the device and submitted in batches; a batch that fails is
//  retried, and submitting the same batch twice is harmless.
// ============================================================

const SHEET_NAME = 'stock_count';
const HEADER_ROW = 1;
const DATA_START_ROW = 2;

// Columns as laid out by build_stock_count_list.py.
const COL = {
  count_group: 1, product_name: 2, barcode: 3, price: 4, pos_category: 5,
  priority: 6, stock: 7, min: 8, max: 9, counted_by: 10, counted_at: 11, notes: 12
};
const NUM_COLS = 12;

// stock..notes is one contiguous block, which is what a submit writes.
const WRITE_FIRST = COL.stock;
const WRITE_LAST = COL.notes;
const WRITE_WIDTH = WRITE_LAST - WRITE_FIRST + 1;

// Above this many touched rows, one big write beats many small ones.
const BULK_WRITE_THRESHOLD = 60;

// ── Web app entry point ────────────────────────────────────

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Shelf Count')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag(
      'viewport',
      'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover'
    );
}

// ── Access ─────────────────────────────────────────────────
//  The deployment has to be reachable by anyone with the link, because
//  staff open it on personal phones without Google accounts. A shared
//  code in Script Properties is the proportionate gate for a temporary
//  tool; leave the property unset and the gate is simply off.

function accessCode_() {
  return (PropertiesService.getScriptProperties().getProperty('ACCESS_CODE') || '').trim();
}

function checkAccess_(code) {
  const required = accessCode_();
  if (!required) return;
  if ((code || '').toString().trim() !== required) {
    throw new Error('BAD_CODE');
  }
}

// ── Sheet helpers ──────────────────────────────────────────

function sheet_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (!sh) throw new Error('Sheet "' + SHEET_NAME + '" not found — see SETUP.md');
  return sh;
}

/**
 * Leading zeros are the single most fragile thing about this catalog:
 * most barcodes are zero-padded, Excel strips them on open, and Sheets
 * strips them on paste unless the column was set to plain text first.
 * Matching on the zero-stripped form means a roster that lost its
 * padding still lines up with a scan that kept it.
 */
function normBarcode_(barcode) {
  return (barcode === null || barcode === undefined ? '' : barcode)
    .toString().trim().replace(/\.0$/, '').replace(/^0+/, '');
}

function readRows_(sh) {
  const last = sh.getLastRow();
  if (last < DATA_START_ROW) return [];
  return sh.getRange(DATA_START_ROW, 1, last - DATA_START_ROW + 1, NUM_COLS).getValues();
}

/**
 * Anything a counter types that lands in a cell has to be inert. setValues
 * treats a leading =, +, - or @ as a formula, so a name typed as
 * "=IMPORTXML(...)" would execute against this sheet on write.
 */
function safeText_(value) {
  const s = (value === null || value === undefined ? '' : value).toString().slice(0, 60);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function numOrBlank_(value) {
  if (value === '' || value === null || value === undefined) return '';
  const n = Number(value);
  return isNaN(n) ? '' : n;
}

// ── RPC: load the roster ───────────────────────────────────

/**
 * Everything the phone needs in one call: the product list plus whatever
 * has already been counted, so a counter who switches phones mid-shift
 * picks up where the sheet is rather than where their old device was.
 */
function rpcBootstrap(code) {
  checkAccess_(code);

  const roster = readRows_(sheet_())
    .filter(function (row) { return (row[COL.product_name - 1] || '').toString().trim(); })
    .map(function (row) {
      return {
        group: (row[COL.count_group - 1] || 'Unsorted').toString(),
        name: (row[COL.product_name - 1] || '').toString(),
        barcode: (row[COL.barcode - 1] || '').toString(),
        key: normBarcode_(row[COL.barcode - 1]),
        price: Number(row[COL.price - 1]) || 0,
        priority: (row[COL.priority - 1] || 'B').toString(),
        stock: numOrBlank_(row[COL.stock - 1]),
        min: numOrBlank_(row[COL.min - 1]),
        max: numOrBlank_(row[COL.max - 1])
      };
    });

  return {ok: true, products: roster, serverTime: Date.now(), needsCode: !!accessCode_()};
}

// ── RPC: submit counts ─────────────────────────────────────

/**
 * Takes a batch of {barcode, stock, min, max, at, by} and writes it.
 *
 * The batch is re-read inside the lock rather than written from a
 * snapshot taken earlier, so min/max someone filled in by dragging down
 * a column in the sheet is not clobbered by a phone that loaded the
 * roster before they did.
 *
 * Resubmitting a batch that already landed is a no-op, which is what
 * makes it safe for the device to retry a batch whose response it never
 * saw.
 */
function rpcSubmit(code, entries) {
  checkAccess_(code);
  if (!entries || !entries.length) return {applied: 0, unmatched: [], serverTime: Date.now()};

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) throw new Error('BUSY');

  try {
    const sh = sheet_();
    const rows = readRows_(sh);

    const rowByKey = {};
    for (let i = 0; i < rows.length; i++) {
      const key = normBarcode_(rows[i][COL.barcode - 1]);
      if (key && !(key in rowByKey)) rowByKey[key] = i;
    }

    const touched = {};
    const unmatched = [];

    entries.forEach(function (entry) {
      const key = normBarcode_(entry.barcode);
      if (!(key in rowByKey)) { unmatched.push(entry.barcode); return; }

      const i = rowByKey[key];
      const row = rows[i];
      row[COL.stock - 1] = numOrBlank_(entry.stock);
      row[COL.min - 1] = numOrBlank_(entry.min);
      row[COL.max - 1] = numOrBlank_(entry.max);
      row[COL.counted_by - 1] = safeText_(entry.by);
      row[COL.counted_at - 1] = entry.at ? new Date(entry.at) : new Date();
      touched[i] = true;
    });

    const indexes = Object.keys(touched).map(Number).sort(function (a, b) { return a - b; });

    if (indexes.length > BULK_WRITE_THRESHOLD) {
      const block = rows.map(function (row) { return row.slice(WRITE_FIRST - 1, WRITE_LAST); });
      sh.getRange(DATA_START_ROW, WRITE_FIRST, block.length, WRITE_WIDTH).setValues(block);
    } else {
      indexes.forEach(function (i) {
        sh.getRange(DATA_START_ROW + i, WRITE_FIRST, 1, WRITE_WIDTH)
          .setValues([rows[i].slice(WRITE_FIRST - 1, WRITE_LAST)]);
      });
    }

    return {applied: indexes.length, unmatched: unmatched, serverTime: Date.now()};
  } finally {
    lock.releaseLock();
  }
}

// ── Menu ───────────────────────────────────────────────────

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('📦 Shelf Count')
    .addItem('Set access code…', 'promptAccessCode')
    .addItem('Clear all counts…', 'promptClearCounts')
    .addSeparator()
    .addItem('Counting progress', 'showProgress')
    .addToUi();
}

function promptAccessCode() {
  const ui = SpreadsheetApp.getUi();
  const res = ui.prompt(
    'Access code',
    'Staff type this to open the count. Leave blank to turn the gate off.',
    ui.ButtonSet.OK_CANCEL
  );
  if (res.getSelectedButton() !== ui.Button.OK) return;

  const code = res.getResponseText().trim();
  const props = PropertiesService.getScriptProperties();
  if (code) {
    props.setProperty('ACCESS_CODE', code);
    ui.alert('Access code set to "' + code + '".');
  } else {
    props.deleteProperty('ACCESS_CODE');
    ui.alert('Access code removed — anyone with the link can count.');
  }
}

function promptClearCounts() {
  const ui = SpreadsheetApp.getUi();
  const res = ui.alert(
    'Clear all counts?',
    'Empties stock, min, max, counted by and counted at for every product. ' +
    'The product list itself is kept. This cannot be undone.',
    ui.ButtonSet.YES_NO
  );
  if (res !== ui.Button.YES) return;

  const sh = sheet_();
  const last = sh.getLastRow();
  if (last >= DATA_START_ROW) {
    sh.getRange(DATA_START_ROW, COL.stock, last - DATA_START_ROW + 1, COL.counted_at - COL.stock + 1)
      .clearContent();
  }
  ui.alert('Counts cleared.');
}

function showProgress() {
  const rows = readRows_(sheet_());
  const byGroup = {};
  const order = [];

  rows.forEach(function (row) {
    if (!(row[COL.product_name - 1] || '').toString().trim()) return;
    const group = (row[COL.count_group - 1] || 'Unsorted').toString();
    if (!(group in byGroup)) { byGroup[group] = {done: 0, total: 0}; order.push(group); }
    byGroup[group].total++;
    if (row[COL.stock - 1] !== '' && row[COL.stock - 1] !== null) byGroup[group].done++;
  });

  let done = 0, total = 0;
  const lines = order.map(function (group) {
    const g = byGroup[group];
    done += g.done; total += g.total;
    return '  ' + group + ' — ' + g.done + ' of ' + g.total;
  });

  SpreadsheetApp.getUi().alert(
    'Counting progress',
    done + ' of ' + total + ' products counted\n\n' + lines.join('\n'),
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}
