# Multi-Fabric Lot + Fabric-Process Work Orders — Design Spec

- **Date:** 2026-07-02 · **Owner:** Mohammed Anas (anas@essdee.fit)
- **App:** everything in `essdee_yrp` (base `yrp` untouched)
- **Site:** `essdee_yrp.site`
- **Status:** user-approved design (this doc = the spec for the implementation plan)

## 1. Why

Work Orders today manage only **cutting → packing**. The pre-cutting fabric
processes — **knitting, dyeing, compacting** — are unmanaged anywhere (F15
production_api only has manual cost fields; its old "Cloth Production Detail"
doctype is dead code). Managing them is the reason SD YRP data is migrated
into this app.

A Lot today binds ONE garment `item` + ONE `production_detail` (IPD). The new
requirement: a Lot may use **1..N fabrics** (e.g. rib + cotton — count
undefined per lot), each fabric declared on the Lot with its own IPD, and
fabric-process Work Orders calculated from that.

## 2. Locked decisions (user-confirmed 2026-07-02)

1. **Manual fabric table on Lot — never derived/auto-seeded from the garment
   IPD's `cloth_detail`.** Fabric production is planned FIRST; `cloth_detail`
   is managed only after cloth production completes.
2. Fabric row columns: **`yarn_item` + `cloth_item` + the cloth's IPD**.
   **No quantities on the Lot** ("just a detail for managing the work_order";
   qty maybe future).
3. Only **three processes** are managed: **Knitting, Dyeing, Compacting**.
4. **Cloth items have NO dependent attribute** → no `in_stage`/`out_stage`
   bookkeeping for fabric processes. Do not re-introduce stages for cloth.
5. Attribute semantics: **Dyeing changes ONLY Colour** (Dia unchanged);
   **Compacting changes ONLY Dia** (Colour unchanged); **Knitting converts
   yarn → dia-wise cloth** (that's why `yarn_item` sits on the Lot row).
6. **User enters DELIVERABLES in a popup** (variant + weight in kg); the
   receivable is computed. **v1 is strictly 1:1** (100 kg in → 100 kg out).
   Wastage/excess percentage math comes later, "after the implementation,
   based on the user needs".
7. **IPD Process Matrix records are AUTO-CREATED from the IPD via an API** —
   never hand-authored (standing 2026-06-25 rule).
8. **`Item.is_cloth_item`** checkbox gates IPD behaviour: cloth IPDs
   show fabric-process tabs and hide garment tabs.
9. Custom Fields deploy **via fixtures only** (no create_custom_fields
   patches) — standing 2026-07-02 workflow.

## 3. Data model changes (all essdee_yrp)

### 3.1 Item
- `is_cloth_item` (Check, Custom Field, fixtures) — marks fabric items.

### 3.2 Lot (native change — Lot is essdee_yrp's own doctype)
- New child doctype **`Lot Fabric Detail`** (`istable`):
  - `yarn_item` — Link → Item
  - `cloth_item` — Link → Item (JS query: `is_cloth_item = 1`)
  - `production_detail` — Link → Item Production Detail (JS query:
    `item = cloth_item`, mirroring the existing lot item→IPD filter pattern)
- New Lot field `lot_fabric_details` — Table → Lot Fabric Detail, in its own
  section on the Lot form.
- The existing garment `item` + `production_detail` stay exactly as-is.
- **Sync safety:** Lots replicate from F15 via `upsert_filtered_doc`, which
  only rebuilds child tables PRESENT in the payload — F15 payloads never
  contain `lot_fabric_details`, so locally-entered fabric rows survive
  every re-sync. (Verified against `sd_yrp_sync.py` filter logic.)

### 3.3 IPD — cloth-mode tabs (Custom Fields, fixtures)
Visibility driven by the IPD item's `is_cloth_item` (fetched into a hidden
check on the IPD, used in `depends_on`):
- **Cloth item IPD → show** three new tabs, **hide** the garment tabs
  (Packing / Set Item / Stiching / Emblishment / Cutting / Cloth Accessory /
  Advance Settings).
- New tabs + child tables (new child doctypes in essdee_yrp):
  - **Knitting tab** — `knitting_dia_details` (Table): rows of
    `dia` (Link → Item Attribute Value, of the Dia attribute).
    *v1 assumption (flagged for review): a plain list of the Dia values this
    cloth is knitted in. Columns like GSM or per-dia yarn override can be
    added when real usage demands.*
  - **Dyeing tab** — `dyeing_colour_details` (Table): `from_colour` →
    `to_colour` (both Link → Item Attribute Value, Colour attribute).
  - **Compacting tab** — `compacting_dia_details` (Table): `from_dia` →
    `to_dia` (both Link → Item Attribute Value, Dia attribute).

### 3.4 Auto-matrix API
- essdee_yrp server module (e.g. `essdee_yrp/fabric_ipd.py`):
  `sync_fabric_process_matrices(ipd)` — regenerates the **IPD Process
  Matrix** docs for the cloth IPD's three processes from the tab data,
  on IPD `on_update` (hook) — idempotent (delete+recreate or upsert by
  `{ipd, process_name}`).
- Matrix content per process:
  - **Knitting:** output combos = cloth × each `dia` row. The INPUT side
    (yarn) is resolved at Work-Order-calculation time from the Lot fabric
    row's `yarn_item` (a matrix is IPD-scoped and cannot know the
    lot-specific yarn; the calc API stamps it).
  - **Dyeing:** input combo colour = `from_colour` → output combo colour =
    `to_colour` (Dia untouched).
  - **Compacting:** input `from_dia` → output `to_dia` (Colour untouched).

### 3.5 Work Order — NO new field needed
- The WO header **already has a mandatory `lot` Link → Lot on this site**,
  provided by base yrp's stock-dimension system: `Lot` is the configured
  production-group stock dimension and `Work Order` is in the dimension
  engine's `OPERATIONAL_DOCTYPES` (`yrp/stock/dimensions.py:42`). Verified on
  `essdee_yrp.site` (`tabWork Order` has the `lot` column; dimension config =
  `{Lot, fieldname: lot, mandatory, in_valuation, is_production_group}`).
- Downstream lot-wise stock tracking also already flows: DC Item / GRN Item /
  Stock Entry Detail etc. are dimension `STOCK_DOCTYPES`.
- The fabric calc endpoints simply read `wo.lot`.
- Mechanism (for reference): dimension fields are auto-created by
  `yrp.stock.dimensions.create_dimension_fields()` — runs on every
  `YRP Stock Settings` save (`yrp/hooks.py:171`); config = the
  `YRP Stock Dimension` child rows. Any future doctype needing dimension
  fields gets added to `STOCK_DOCTYPES`/`OPERATIONAL_DOCTYPES` in base yrp —
  never a hand-made `lot`/`received_type` field.

## 4. Work Order Calculate flow (fabric processes)

UX pattern: **MGK's Calculate popup** (`mgk_clothing_yrp/public/js/work_order_mgk.js`)
— dynamic per-row sections, attribute Selects, weight Float.
Server pattern: **yrp_essdee's `calculate_deliverables`**
(`yrp_essdee/api/work_order.py:29`) — permission-checked, draft-only,
idempotent rewrite of deliverables/receivables, grouped-JSON cleared before
save. (MGK's matrix branch is a throwing stub — do NOT copy it.)

Flow when `WO.process_name` ∈ {Knitting, Dyeing, Compacting}:
1. **Calculate** button (essdee_yrp `doctype_js` on Work Order) → whitelisted
   `get_fabric_deliverable_context(work_order)`: requires `wo.lot`; returns
   one section per **Lot Fabric Detail** row (yarn/cloth/IPD + the relevant
   attribute options from the matrix/tabs).
2. User enters, per fabric row they're sending: deliverable variant
   attribute values + **weight (kg)**. Rows left empty are skipped.
3. Confirm → whitelisted `calculate_fabric_deliverables(work_order, rows)`:

| Process | Deliverable (user-entered) | Receivable (computed, qty = weight, 1:1) |
|---|---|---|
| Knitting | yarn variant (from lot row's `yarn_item`) + weight | cloth variant at the chosen Dia + the popup-collected remaining cloth attributes (e.g. greige Colour) — `create_variant` requires every template attribute |
| Dyeing | cloth variant (input colour) + weight | same cloth, colour swapped per `from→to` mapping |
| Compacting | cloth variant + weight | same cloth, dia swapped per `from→to` mapping |

4. Variants resolved via base yrp `get_or_create_variant`; rows written to
   `deliverables`/`receivables` (received_type "Accepted", `is_calculated=1`),
   prior calculated rows dropped on re-run; `deliverable_details`/
   `receivable_details` JSON cleared; `wo.save()`.
5. Garment processes (cutting→packing) keep today's behavior untouched.

## 5. Out of scope (v1)

- Wastage/excess percentage math (Process `default_wastage`/`default_excess`
  stay unused here for now; `wo_excess_allowed_percentage` continues to work
  at GRN as today).
- Quantities on the Lot fabric rows.
- Any processes beyond the three named.
- Deriving fabric rows from the garment IPD `cloth_detail`.
- Stage/dependent-attribute mechanics for cloth items.
- Syncing any of this config to/from F15 (it is F16-native, created fresh).

## 6. Implementation surface (planning aid)

- `essdee_yrp/fixtures/custom_field.json` + `hooks.py` fixtures filter:
  Item (`is_cloth_item`), IPD (tab fields + hidden is_cloth fetch).
  (WO needs nothing — `lot` comes from the stock-dimension engine, §3.5.)
- New child doctypes: `lot_fabric_detail`, `ipd_knitting_dia_detail`,
  `ipd_dyeing_colour_detail`, `ipd_compacting_dia_detail` (names indicative).
- Lot doctype JSON + `lot.js` (queries for the fabric table).
- `essdee_yrp/fabric_ipd.py` (auto-matrix) + hook on IPD `on_update`.
- `essdee_yrp/api/work_order.py` (context + calculate endpoints).
- `public/js/work_order.js` (doctype_js: Calculate button + popup) — follow
  MGK dialog UX; register in `hooks.py`.
- Verification per `docs/claude/validation.md`: migrate, fixtures export,
  build, then a UI-driven end-to-end on `essdee_yrp.site` (create cloth item
  → cloth IPD → lot fabric rows → knitting/dyeing/compacting WOs → Calculate
  → verify deliverables/receivables in the form + DB).

### 3.6 Cloth IPD prerequisite (found in plan review)
Base `IPDProcessMatrix.validate_attributes_belong_to_ipd` requires every
matrix attribute to appear in the IPD's `item_attributes` child table.
Cloth-mode auto-ensures those rows server-side (`ensure_cloth_item_attributes`
on before_validate) — the garment UI does this via client JS, console/API
paths would otherwise break.

## 7. Open items flagged at review

- **Knitting tab columns** (§3.3): v1 = plain Dia list. Confirm or extend.
- Whether the knitting popup also needs a Dia picker per row when the IPD
  lists multiple Dia values (v1: yes — user picks the target Dia per entry).
- **v1 limitation (recorded):** one (dia, weight) entry per fabric row per
  knitting WO; multiple Dias in one go = multiple Work Orders. Re-running
  Calculate REPLACES calculated rows, it does not accumulate.
