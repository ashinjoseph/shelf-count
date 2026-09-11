# Setting up Shelf Count

Twenty minutes, once. This is a **separate** Apps Script project from StoreOps —
its own spreadsheet, its own script, its own deployment. Do not push it into the
StoreOps script.

## 1. Make the spreadsheet

Create a new Google Sheet called **Shelf Count**. Rename the first tab to
exactly `stock_count`.

### Set the barcode column to plain text *before* pasting anything

This is the step that breaks the upload if it is skipped. Most barcodes in this
catalog are zero-padded — `072890000224`. Sheets reads that as a number and
throws the leading zero away, and ePOS then matches the wrong product or none at
all.

1. Click the **C** column header.
2. **Format → Number → Plain text**.

Do this on an empty column, before the paste. Fixing it afterwards does not
bring the zeros back.

**Never open the CSV in Excel.** Excel strips leading zeros on open, without
warning, and saving over the file makes it permanent.

## 2. Load the products

1. **File → Import → Upload**, choose `stock_count_list.csv`.
2. Import location: **Replace current sheet**. Separator: **Comma**.
3. Turn **off** "Convert text to numbers, dates and formulas" — this is the
   second line of defence for the barcodes.

You should land on 906 rows: one header, 905 products. Spot-check that C2 still
reads `071610122741` and not `71610122741`.

## 3. Add the script

**Extensions → Apps Script**. In the editor:

1. Paste `src/Code.gs` over the default `Code.gs`.
2. **+ → HTML**, name it `Index` (no extension), paste `src/Index.html`.
3. **Project Settings → Show "appsscript.json"**, then paste `src/appsscript.json`.

Or, with clasp: `cp .clasp.json.example .clasp.json`, fill in the new script id,
and `npx clasp push` from this folder.

## 4. Deploy

**Deploy → New deployment → Web app**

| Setting | Value |
|---|---|
| Execute as | **Me** |
| Who has access | **Anyone** |

"Anyone" is needed because staff open this on personal phones with no Google
account. That is what the access code in the next step is for.

Copy the `/exec` URL. That is the link staff get.

## 5. Set an access code

Reload the spreadsheet, then **📦 Shelf Count → Set access code…** and pick
something short. Anyone with the link can otherwise open the count and write to
the sheet.

Leaving it blank turns the gate off, which is fine if the link never leaves a
group chat you control.

## 6. Hand it out

Send staff the `/exec` link. Tell them to **Add to Home Screen** — it opens
full-screen and, more usefully, is harder to close by accident than a tab.

They type their name once. After that the link opens straight into the count.

---

## Running the count

- Pick a section chip, walk that section, type the number in.
- Only **stock** is required. Min and max appear under a row once it has a
  count, and can be left empty — they are quicker to fill in the sheet
  afterwards by dragging a column down.
- The pill at the top right is the whole status story: **All sent**,
  **n waiting**, **Sending**, or **Offline**.
- **📦 Shelf Count → Counting progress** shows how far along each section is
  without opening the app.

### What happens when the phone loses signal or sleeps

Every number is written to the phone's own storage as it is typed, before
anything touches the network. Entries queue on the device and go up in batches —
on a 15-second timer, when the tab comes back to the foreground, when the
network returns, and on **Send now**.

So a counter can put the phone away for twenty minutes mid-aisle, walk into a
stockroom with no signal, or close the tab entirely; the count is still there.
The pill tells them whether anything is still waiting, and they should not end a
shift while it says **n waiting** and they have signal.

Starting the app with no signal works too, as long as that phone has opened it
once before — the product list is cached on the device.

## When the count is done

The counts are in the `stock_count` tab. The last step — turning that into a
file ePOS will accept on import — **is not built yet**, because ePOS Now does
not publish its Bulk Import column layout; it comes from the template the app
generates for you. Once that template is in hand it is a small script.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "Could not reach the sheet" on a phone that has never opened it | No signal on first run. The roster has to come down once before offline use works. |
| Counts stuck on "n waiting" | Deployment was redeployed and the URL changed, or the access code changed. Counts are safe on the device — reload and re-enter. |
| An item reports "not in the list" | Its barcode is not in the `stock_count` tab, usually because the zeros were stripped on import. Redo step 1. |
| Barcodes show as `7.28900002E11` | Column C was not set to plain text before the paste. Redo step 1. |
