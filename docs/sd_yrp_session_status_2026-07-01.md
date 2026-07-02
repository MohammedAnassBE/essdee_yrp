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
- ~~`eventdispatcher` (Kafka→Message Log) is NOT in the Procfile~~ **RESOLVED 2026-07-02:** `eventdispatcher` added to the frappe-16 Procfile (logs to `logs/eventdispatcher.log`); bench restarted with fresh worker code. Continuous F15→F16 sync is LIVE and user-verified (Lot edit on mrp3 landed automatically).
- After committing + restarting the bench, re-enable anything needed for realtime; the old-code bench worker won't have the Supplier fix until restarted.

---

## 5. Multi-fabric Lot feature — acceptance gate PASSED (2026-07-02, Task 7)

Full spec: `docs/multi_fabric_lot_design_2026-07-02.md`. Implementation plan:
`docs/plans/2026-07-02-multi-fabric-lot.md`. Per-task briefs/reports:
`.superpowers/sdd/task-{1..7}-{brief,report}.md` (Task 7 = this acceptance gate,
`.superpowers/sdd/task-7-report.md` has the full step-by-step evidence).

### What was built (maps to design-doc §s)

| Spec § | What | Where |
|---|---|---|
| §3.1 | `Item.is_cloth_item` (Check, fixtures) | `fixtures/custom_field.json` |
| §3.2 | `Lot.lot_fabric_details` → new child `Lot Fabric Detail` (`yarn_item`, `cloth_item`, `production_detail`); pickers filtered (`is_cloth_item=1`, `item=cloth_item`) | `doctype/lot_fabric_detail/`, `doctype/lot/lot.js` |
| §3.3 | IPD cloth-mode tabs: Knitting (`knitting_process` + `knitting_dia_details`), Dyeing (`dyeing_process` + `dyeing_colour_details`: from/to Colour), Compacting (`compacting_process` + `compacting_dia_details`: from/to Dia); garment tabs hidden in cloth mode | fixtures custom fields + new child doctypes `ipd_knitting_dia_detail`, `ipd_dyeing_colour_detail`, `ipd_compacting_dia_detail` |
| §3.4 | Auto-matrix generation on IPD save (`before_validate`/`on_update` hooks), idempotent delete+rebuild | `essdee_yrp/fabric_ipd.py` |
| §3.5 | WO `lot` field — confirmed already provided by base yrp's stock-dimension engine, no new field needed | (verification only, no code) |
| §4 | Calculate context + calculate endpoints; "Calculate Fabric Deliverables" popup (kind-conditional fields: knitting = yarn attrs + Cloth Dia + non-Dia cloth attrs; dyeing = Colour restricted to `colour_from_options`; compacting = Dia restricted to `dia_from_options`); idempotent rewrite of deliverables/receivables (1:1) | `essdee_yrp/api/work_order.py`, `public/js/work_order.js` |
| — | Pre-existing bug fix (found in Task 5, unrelated to this feature): `Lot.py` `add/delete_ppo_lot_qty` now use `reference_doctype`/`reference_name` on `Production Ordered Detail` instead of a nonexistent `lot` column | `doctype/lot/lot.py` |

### Task 7 acceptance-gate result: **DONE**, one real bug found + fixed

Active-driving E2E (headless Playwright, real fill/click/select + literal DOM/DB reads, not
screenshots-only) exercised every flow in the brief:
- IPD form: added a Dia row (new IAV `FT-D34`) via the grid UI, saved, confirmed the Knitting
  matrix regenerated 2→3 output combos.
- Lot form: confirmed the `cloth_item` picker is filtered to `is_cloth_item=1` (typed "FT",
  dropdown showed only `FT-CLOTH`, not `FT-YARN`); added + saved + deleted a second fabric row
  via the grid pickers.
- WO Calculate popup driven end-to-end on all three fabric WOs (WO-00003 Knitting, WO-00004
  Dyeing, WO-00005 Compacting) — filled real values, clicked Calculate, read the resulting
  deliverables/receivables from both the DOM and the DB. Re-ran Knitting at a different weight
  (100 → 80) and confirmed rows are REPLACED, not duplicated.
- `bench migrate` clean; sync-safety assert passed (fabric rows survive an F15-style re-sync
  payload that omits `lot_fabric_details`); Error Log clean of any fabric-feature-related entries.

**Bug found and fixed during the gate** (`essdee_yrp/api/work_order.py`,
`get_fabric_deliverable_context`): for knitting rows, the popup's `attribute_options` dict was
built from the **yarn** item only, so the required non-Dia cloth attribute select (e.g. "Colour
(cloth)") rendered with zero options whenever the yarn item had no configured attributes —
impossible to submit. Never caught before because Task 6 explicitly did not exercise the full
submit flow. Fixed to merge yarn-item + cloth-item attribute options for knitting rows only
(cloth-only kinds unaffected). Full diagnosis + fix in `.superpowers/sdd/task-7-report.md` under
"Deviations, #2".

**Pre-existing, feature-unrelated site-data gap worked around** (not fixed in code): `Item
Production Detail.packing_attribute` has had `mandatory_depends_on: eval: !doc.__islocal` since
before this feature (custom field dated 2026-06-27) — unconditional on `is_cloth_item`, so any
already-saved IPD, garment or cloth, must carry a value to save via the UI. Filled the missing
value on the test IPD (`packing_attribute = "Colour"`); flagged as a follow-up for the feature
owner to make cloth-aware if it recurs. Full diagnosis in task-7-report.md, "Deviations, #1".

### FT- test masters (live on `essdee_yrp.site`, reusable)

- Items: `FT-YARN` (no attributes), `FT-CLOTH` (`is_cloth_item=1`, attributes Dia+Colour)
- Item Attribute Values: `FT-D30`, `FT-D32`, `FT-D34` (Dia); `FT-White`, `FT-Black` (Colour)
- IPD `FT-CLOTH-1`: Knitting (Dia rows FT-D30/FT-D32/FT-D34), Dyeing (FT-White→FT-Black),
  Compacting (FT-D32→FT-D30); 3 auto-generated `IPD Process Matrix` docs (draft, never
  hand-authored)
- Lot `TASK5-FABRIC-TEST`: 1 fabric row (`FT-YARN`/`FT-CLOTH`/`FT-CLOTH-1`)
- Work Orders (all draft, calculated): `WO-00003` Knitting (deliverable FT-YARN 80, receivable
  FT-CLOTH-FT-D30-FT-White 80 — last state after the weight-80 re-run test), `WO-00004` Dyeing
  (FT-CLOTH-FT-D30-FT-White 50 → FT-CLOTH-FT-D30-FT-Black 50), `WO-00005` Compacting
  (FT-CLOTH-FT-D32-FT-Black 50 → FT-CLOTH-FT-D30-FT-Black 50)
- Process Costs `PC-00001..6` (Approved, scoped to `TASK5-FABRIC-TEST`); Tax Slab `0`; Workflow
  States `Draft`/`Approval Pending`/`Expired` (were missing, created in Task 5)

### Evidence (screenshots, `apps/essdee_yrp` → `/home/anas/frappe-16/screenshots/`)

IPD write: `2026-07-02_11-53-44-step1-ipd-before.png`,
`2026-07-02_11-53-50-step1-ipd-row-added-presave.png`,
`2026-07-02_11-53-53-step1-ipd-after-save.png`. Lot picker filter: `explore-lot-cloth-suggest.png`.
Lot grid write/delete: `2026-07-02_12-01-35..12-02-23-step2*.png`. WO Calculate (all 3 fabric
processes + the weight-80 replace test): `2026-07-02_12-06-07..12-09-39-step{3,4,5}-wo{3,4,5}*.png`.
Full list + DOM/DB read values: `.superpowers/sdd/task-7-report.md`.

### Deferred (v1 scope, per design-doc §5 + §7)

- Wastage/excess percentage math — deliverable→receivable stays strictly 1:1 for now.
- Quantities on the Lot fabric rows (`lot_fabric_details` has no qty column).
- **v1 limitation (by design, recorded for the user):** one `(dia, weight)` entry per fabric row
  per Knitting Work Order — knitting the same fabric into multiple Dias in one go means multiple
  Work Orders, not multiple rows in one Calculate call. Re-running Calculate on the same WO
  REPLACES the calculated rows, it does not accumulate them (verified in Task 7).
- Deriving fabric rows from the garment IPD's `cloth_detail` — still manual-only, by design.
- Stage/dependent-attribute mechanics for cloth items — intentionally not reintroduced.
- Syncing any of this fabric config to/from F15 — it's F16-native, created fresh, not part of the
  Kafka master-sync pipeline.

### Multi-fabric backlog (final-review minors, 2026-07-02 — none block usage)
- Popup selects offer ALL global attribute values (~300 Dia/~450 Colour) — should resolve per-item Item Item Attribute Mapping first (M1).
- `default_unit_of_measure` None-guard in calc rows + fabric_ipd (M2).
- Deleting a cloth IPD hits LinkExistsError from its own auto-matrices — cloth-aware on_trash should delete them (M3).
- "Dia"/"Colour" hardcoded in JS (work_order.js, item_production_detail.js) vs Python constants — ship names in context payload (M4).
- lot.py delete SQL: move to parameterized %s (values are escaped today) (M5).
- Calculate button shows on garment WOs too (harmless msgprint roundtrip); `packing_attribute` unconditional mandatory needs cloth-aware follow-up (M6).
- Deferred by design: wastage/excess % math, Lot fabric quantities, multi-dia per knitting WO.

### TOMORROW (2026-07-03): IPD Process Matrix + Calculation review — user suspects the matrix is wrong
Verified state (bench execute dump, 2026-07-02 EOD): Dyeing/Compacting matrices = one group per mapping row with paired Input/Output combos (qty 1, correct from→to cattrs); Knitting matrix = output-only groups per Dia, `input_item=None`, empty input side (yarn is lot-specific by design). Two things to settle with the user:
1. **The WO fabric calc does NOT read the matrices** — `essdee_yrp/api/work_order.py` calculates from the IPD tab tables directly; matrices are generated as the declarative record only. If the intent was calculation THROUGH `calculate_major_deliverables`/`get_process_io` (like yrp_essdee's garment calc), the calc must be rewired and the knitting matrix input semantics decided (base engine treats `input_item=None` as "IPD's own item" → wrong for yarn).
2. Whether the base ProcessMatrixEditor UI renders these auto-created matrices acceptably (combination_html was never generated by the get_combination flow).
