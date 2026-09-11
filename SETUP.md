# Setting up Shelf Count

Twenty minutes, once. This is a **separate** Apps Script project from StoreOps —
its own spreadsheet, its own script, its own deployment. Do not push it into the
StoreOps script.

## 1. Upload the spreadsheet

Upload **`Shelf Count.xlsx`** to Google Drive, then open it and choose
**File → Save as Google Sheets**.

That is the whole step. The workbook stores every barcode as a typed text cell,
so the zero-padded ones — `072890000224`, 640 of them — come through intact with
nothing to format and nothing to remember.

It arrives with two tabs: `readme` (a legend; delete it if you like) and
`stock_count`, holding one header row and 905 products. The script reads that
tab **by name**, so leave `stock_count` spelled exactly as it is.

Spot-check `C2` — it should read `071610122741`, not `71610122741`.

### Do not route this through Excel or CSV

The list also ships as `stock_count_list.csv`, for rebuilding the workbook and
for diffing against a future POS export. Do not use it to load the sheet.

CSV carries no type information, so Sheets and Excel both guess "number" on a
zero-padded barcode and drop the leading zero — silently, and permanently once
saved. ePOS then matches the wrong product, or none, and you would not find out
until after the count was finished. Opening the xlsx in Excel and re-saving does
the same damage.

Regenerating the workbook after a new POS export:

```bash
python build_stock_count_list.py <ProductList*.csv> -o .
python build_stock_count_sheet.py
```

## 2. Add the script

The project already exists:
<https://script.google.com/u/0/home/projects/1cADgF2xVT_ZTA8Ga-QTJwbl2Pb8NIa2Hn1dh6h1BdxU9wqdvEAOsMV5C/edit>

It is a **standalone** project — created at script.google.com rather than from
inside the spreadsheet — so it has no active spreadsheet of its own and has to
be told which one to use. Step 2c does that.

### 2a. Push the code

```bash
npm install
npx clasp login            # opens a browser; one time only
cp .clasp.json.example .clasp.json
npx clasp push
```

`clasp login` needs a browser, so run this on your own machine.

Pushing replaces whatever is in the project with `src/` — `Code.gs`,
`Index.html` and `appsscript.json`. If `clasp push` complains about the
manifest, answer yes; `appsscript.json` is meant to be overwritten.

Prefer to paste by hand? In the editor: `Code.gs` over the default file, then
**+ → HTML** named `Index` (no extension), then **Project Settings → Show
"appsscript.json"** and paste that too.

### 2b. Point it at the spreadsheet

Copy the spreadsheet's id from its URL — the part between `/d/` and `/edit`.

In the editor, open `Code.gs`, paste that id into `SPREADSHEET_ID` inside
`setSpreadsheetId()`, pick that function from the dropdown and **Run**. Approve
the permissions prompt when it appears.

The log should print the sheet's name. If it throws, the id is wrong or the
account running the script cannot open that sheet.

Equivalent, without editing code: **Project Settings → Script Properties → Add
property**, name `SPREADSHEET_ID`, value the id.

> A bound project — made with **Extensions → Apps Script** from the spreadsheet
> — skips this step entirely and gets the 📦 Shelf Count menu, which a
> standalone project does not have. Both work; bound is slightly more
> convenient.

## 3. Deploy

**Deploy → New deployment → Web app**

| Setting | Value |
|---|---|
| Execute as | **Me** |
| Who has access | **Anyone** |

"Anyone" is needed because staff open this on personal phones with no Google
account. That is what the access code in the next step is for.

Copy the `/exec` URL. That is the link staff get.

## 4. Set an access code

Reload the spreadsheet, then **📦 Shelf Count → Set access code…** and pick
something short. Anyone with the link can otherwise open the count and write to
the sheet.

Leaving it blank turns the gate off, which is fine if the link never leaves a
group chat you control.

## 5. Hand it out

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
| An item reports "not in the list" | Its barcode is not in the `stock_count` tab, usually because the zeros were stripped on import. Re-upload the workbook from step 1. |
| Barcodes show as `7.28900002E11` | The sheet was loaded from the CSV instead of the xlsx. Re-upload the workbook from step 1. |
