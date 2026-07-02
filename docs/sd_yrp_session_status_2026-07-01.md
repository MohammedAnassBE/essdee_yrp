# SD YRP — Session Status & Handoff (2026-07-01)

- **Owner:** Mohammed Anas (anas@essdee.fit)
- **Site:** `essdee_yrp.site` (F16, frappe + yrp + essdee_yrp), serves on `:8003`
- **Source:** `mrp3.site` (F15 `production_api`), Kafka broker `localhost:29092`, topic `sd_yrp_master`
- **Resume:** Tomorrow morning (2026-07-02)

---

## 1. DONE today ✅ (all UI-verified in the browser)

### Master sync — full round-trip PASSED
- Deleted the previously-synced business data, re-ran `production_api.sd_yrp_sync.trigger_all_initial_sync`, and verified **all 28 doctypes** match source (Item 4305, **Item Variant 71713**, IIAM 6552, Supplier 3154, Address 2880, IPD 403, Production Order 162, Lot 1767, all masters/mappings). **0 unresolved failures.**
- **Bug fixed (consumer):** `filter_doc_fields` in `essdee_yrp/sd_yrp_sync.py` now drops `no_value_fields` (HTML etc.) — fixes `Unknown column 'address_html'` on the supplier→Warehouse update.
- Perf note: the two-stage pipeline syncs ~20–30 rec/s; 71k variants ≈ ~1 hr. Ordering (variants before PO/Lot) is required — use the built-in sequential `trigger_all_initial_sync`, do NOT hand-roll a parallel drain (collides with the F15 publish cron → `TimestampMismatchError`).

### MRP Settings (Lot dependency)
- Created **`MRP Settings`** (Single) in `essdee_yrp` (`essdee_yrp/essdee_yrp/doctype/mrp_settings/`) — 39 resolvable fields, dropped the 5 child-tables + AQL/sewing/sticker links that don't exist here.
- Wired into the sync: consumer `upsert_mrp_settings` (uses `set_single_value`), added to `SYNC_DOCTYPES` + consumer config; F15 producer `SD_YRP_*` lists + hooks + Single handling in `_ordered_initial_docnames`. Patch `patches/setup_sd_yrp_mrp_settings.py`. Data synced (`enable_production_order=1`, roles). Fixes the Lot "asks for MRP Settings" error.

### Lot form
- `get_ocr_details` (`lot.py`) crashed with `Unknown column 'includes_packing'` (yrp GRN lacks it). Fixed: **early-return empty when the lot has no Work Orders** + feature-detect GRN columns. (Matches your intent — no transaction/OCR load needed until the full production_api transaction flow is implemented.)
- **Hid the OCR Detail + Alternative Detail tabs** (`hidden:1` on the tab breaks in `lot.json`) — only the Details tab shows now. Reversible (unset `hidden` when transactions are implemented).

### Item Production Detail (IPD) form
- **"Not Saved" on open** → fixed: the 4 combination widgets (`Item_Po_detail/CuttingItemDetail.vue`, `ClothAccessory.vue`, `ClothAccessoryCombination.vue`, `CombinationItemDetail.vue`) wired `cur_frm.dirty()` before the async `set_value` settled. Now deferred with `Promise.resolve(set_value).then(...)`.
- **Cutting / Cloth-Accessory tabs showed blank attribute cells** → fixed: read-only attribute cells were Links that couldn't async-resolve a title here → now rendered as **Data** so the stored value shows (Part "Top"/"Bottom" etc.). Applied in CuttingItemDetail + ClothAccessory + CombinationItemDetail.
- **Save-time data loss** → fixed: `item_production_detail.js` `validate` no longer wipes `*_json` to `{}` when a widget didn't render (preserves synced cutting/cloth data).

---

## 2. TODO tomorrow (2026-07-02) — the work to perform

### A. Production Order — customize + extend the sync  ⬅ main item

> **ALSO DONE 2026-07-02 — "Lotwise Ordered Detail" view (F15 parity).** Sync gap fixed: F15 `production_ordered_details.lot` now maps to base yrp's generic `reference_doctype="Lot"`/`reference_name` (new `map_production_ordered_rows`; Lot NOT existence-validated — Lot syncs after PO). Backfilled via on_update re-sync: 808/808 rows identical to F15. View: Custom Field `lot_ordered_html` (fixtures) + `essdee_yrp/production_order.py::get_lot_ordered_details` + `public/js/production_order.js` (doctype_js) + `ProductionOrder/LotOrderedDetail.vue` (read-only — F15's inputs never persisted). UI-verified on PPO-00038 (7 lots).

> **DONE 2026-07-02.** 10 custom fields via FIXTURES (no patch — owner wants the fixtures-sync-on-every-migrate workflow; `hooks.py` or_filters + `fixtures/custom_field.json`), mapper copies the 5 child fields, re-synced 162 POs with `event="on_update"`. Exhaustive diff F15↔F16: 162/162 parents, 1033/1033 child rows, 0 mismatches. UI verified (PPO-00012).
F15 PO business fields are dropped on F16. Plan (from the field-gap analysis):
- **Custom fields via `essdee_yrp`** (new idempotent patch `patches/setup_sd_yrp_production_order_custom_fields.py` + `fixtures/custom_field.json`, mirror `setup_sd_yrp_process_custom_fields.py`):
  - **`Production Order Detail`** (child — the price/ratio data): `ratio` (Float), `mrp` (Currency), `production_order_mrp` (Currency, hidden), `retail_price` (Currency), `wholesale_price` (Currency)
  - **`Production Order`** (parent): `gsm` (Float), `fabric` (Data), `dia` (Link → Item Attribute Value), `skip_box_sticker_print` (Check), `price_approval_status` (Select)
  - Do NOT add a parent `item` field — F16 PO is intentionally multi-item; the mapper stamps `item` per row.
- **Mapper** (`essdee_yrp/sd_yrp_sync.py`):
  - Parent scalars need **no code change** — once the custom fields exist, `filter_doc_fields` retains `gsm/fabric/dia/skip_box_sticker_print/price_approval_status` from the payload.
  - `map_production_order_item_rows` (~line 491): copy the 5 child fields onto each mapped row (`ratio/mrp/production_order_mrp/retail_price/wholesale_price`).
  - Custom fields MUST be migrated before the mapper writes them (else `_db_insert_child_rows` → Unknown column).
- Then re-trigger Production Order sync and verify ratio/prices land.

> **UPDATE (end of 2026-07-01) — items B and C below are now DONE / resolved. Production Order (§A) is the ONLY remaining work for tomorrow.**
> - **Sync now preserves source `creation` / `modified` / `owner` (created-by) / `modified_by`** — consumer keeps them and re-applies via `_apply_source_timestamps` (`set_value(update_modified=False)`) in `upsert_filtered_doc` (26/28 doctypes) + `upsert_user`. Verified (Brand test). **Logic only — existing records not backfilled** (owner will re-sync/manage the existing data).
> - **Lot `items` (LotOrder) table = NON-ISSUE** — it renders fine; both Lot tables just live inside the collapsible "Order Details" section (`section_break_yquv`, collapsed by default). No fix needed.

---

## 3. Uncommitted changes (commit on `develop` per the standing preference)
- **`apps/essdee_yrp`** (branch `develop`): new `MRP Settings` doctype + `patches/setup_sd_yrp_mrp_settings.py` + `patches.txt`; `sd_yrp_sync.py` (MRP Settings mapper); `lot.py` (get_ocr_details), `lot.js`, `lot.json` (tab hidden); `item_production_detail.js` + `Item_Po_detail/*.vue` (IPD fixes); rebuilt `essdee_yrp.bundle`.
- **`apps/production_api` on F15 (`/home/anas/frappe-15`)**: `sd_yrp_sync.py` (MRP Settings in SYNC lists + Single handling) + `hooks.py` (MRP Settings doc-events). NOT committed here (F15 daily-driver); commit in frappe-15 separately if wanted. F15 bench needs a restart for the new MRP Settings realtime hook to load.

## 4. Ops notes
- `eventdispatcher` (Kafka→Message Log) is NOT in the Procfile — start manually to consume; consumer cron was left as-is. Both were torn down after the sync test.
- After committing + restarting the bench, re-enable anything needed for realtime; the old-code bench worker won't have the Supplier fix until restarted.
