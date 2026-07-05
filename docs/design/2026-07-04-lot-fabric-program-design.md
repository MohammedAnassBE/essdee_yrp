# Lot Fabric Program — dia-wise program quantity + per-process received tracking

Date: 2026-07-04 · App: essdee_yrp (site essdee_yrp.site) · Status: user-approved design, executing

## Problem

Fabric demand (kgs) is currently typed ad-hoc into the Work Order "Calculate Fabric
Deliverables" popup on every WO — nothing is planned on the Lot and nothing tracks what
each fabric process actually received. The garment side already has this (Lot Order
Detail: `quantity` → `cut_qty` → `stich_qty` → `pack_qty`, GRN-driven); the fabric chain
(knitting → dyeing → compacting) needs its analogue.

User decisions (2026-07-04, voice):

- The Lot is the demand source. Program quantity = **dia + weight (kg)** only.
- The final product has colour too → a **second table** holds the colour-wise split.
- Knitted cloth has a **default colour (greige)** → knitting output variant = (Dia, Greige),
  so dia-level tracking is variant-exact.
- Track received kgs for **knitting and dyeing** on the Lot (GRN submit/cancel updates).
- WO popups pre-fill the remaining **balance** and stay editable (partial / split WOs
  across suppliers allowed). One dyeing WO may split one dia's greige into several
  target colours (one popup row per to-colour matrix group).
- IPD Process Matrix is **unchanged**: it stays the auto-generated per-unit rule
  (`sync_fabric_process_matrices`); the Lot supplies demand, the engine multiplies.
- UI on the Lot is a **Vue island** like LotOrder / CutPlanItems, not a plain child grid.

## Data model (all essdee_yrp, module "Essdee YRP")

### New child doctype `Lot Fabric Program` (istable)

| field | type | notes |
|---|---|---|
| cloth_item | Link Item, reqd | which Lot fabric this row belongs to |
| dia | Link Item Attribute Value, reqd | Dia value |
| weight | Float (precision 3), reqd | program kg (what knitting must produce) |
| received_weight | Float (precision 3), read_only | knitting received kg — server-owned |

### New child doctype `Lot Fabric Colour Program` (istable)

| field | type | notes |
|---|---|---|
| cloth_item | Link Item, reqd | |
| dia | Link Item Attribute Value, reqd | |
| colour | Link Item Attribute Value, reqd | target (dyed) colour |
| weight | Float (precision 3), reqd | planned kg of this (dia, colour) |
| received_weight | Float (precision 3), read_only | dyeing received kg — server-owned |

### Lot (lot.json) additions — inside the existing Fabric Details section

- `fabric_program_html` HTML — Vue mount point (after `lot_fabric_details`)
- `lot_fabric_programs` Table → Lot Fabric Program, hidden
- `lot_colour_programs` Table → Lot Fabric Colour Program, hidden

`received_weight` is never accepted from the client: the save path preserves the stored
value keyed by (cloth_item, dia[, colour]).

New validation on Lot: `cloth_item` must be unique across `lot_fabric_details` rows
(program rows are keyed by cloth_item).

## Lot UI — Vue island `FabricProgram.vue`

Pattern (b) from the bench's established island flow (LotOrder/CutPlanItems):

1. `Lot.onload` → `set_onload("fabric_program_details", fetch_fabric_program_details(self))`:
   one entry per `lot_fabric_details` row →
   `{cloth_item, production_detail, dias, colours, greige_colour, program: [...], colour_program: [...]}`.
   `dias` = IPD `knitting_dia_details` (fallback: IPD Dia mapping values);
   `colours` = IPD `dyeing_colour_details` distinct `to_colour` (fallback: Colour mapping);
   `greige_colour` = distinct `from_colour` when exactly one, else null.
2. `lot.js` `refresh` mounts `frappe.production.ui.FabricProgram` at `fabric_program_html`,
   `load_data(__onload.fabric_program_details)`.
3. Component (essdee_yrp `public/js/Lot/FabricProgram.vue`, registered in
   essdee_yrp `vue_plugins.js`): one card per cloth —
   - **Program grid**: row per dia → weight input, received (RO). Add-dia picker from `dias`.
   - **Colour grid**: row per (dia, colour) → weight input, received (RO). Add-row pickers.
   - Per-dia hint when Σ colour weights ≠ program weight (visual only, non-blocking).
   - Edits call `cur_frm.dirty()`. Inputs disabled when status ≠ Open.
4. `lot.js` `validate` → `frm.doc.fabric_program_details = JSON.stringify(get_data())`.
5. `Lot.before_validate` → `save_fabric_program_details()`: parse, validate
   (cloth ∈ lot_fabric_details; dia/colour are IAVs of Dia/Colour), rebuild the two child
   tables, carry `received_weight` forward from existing rows by key.

## Tracking — GRN writes back to the Lot

New module `essdee_yrp/fabric_tracking.py`; hooks:
`doc_events["Goods Received Note"]["on_submit" | "on_cancel"]` (sign +1 / −1).

Flow per GRN: only when the GRN is against a Work Order → WO gives `lot`, `process_name`.
For each Lot fabric row: `kind = get_fabric_process_kind(ipd, wo.process_name)`.

- kind == knitting → for each GRN item row whose variant's parent item == cloth_item:
  read the variant's **Dia** attribute value; `received_weight += sign × qty` on the
  matching `Lot Fabric Program` row. No matching row → append one with `weight 0`
  (nothing is silently dropped).
- kind == dyeing → same, keyed (Dia, Colour) into `Lot Fabric Colour Program`.
- All received types count. Quantities are kgs (cloth default UOM).

Also whitelisted `rebuild_fabric_tracking(lot)`: zero both received columns, replay every
submitted GRN of the lot's fabric WOs (knitting/dyeing kinds), recompute. Exposed as a
button in the Vue panel ("Recalculate Received"). Mirrors production_api's
`calculate_completed_pieces` recovery pattern.

Write path: update child rows directly (db-level per-row set_value / insert with
parent linkage), NOT `lot.save()` — avoids re-triggering Lot's before_validate rebuild
machinery from inside GRN submit.

## WO popup upgrades (`api/work_order.py` + Desk dialog + /web modal)

`get_fabric_deliverable_context` gains per-qty-row planning data (all computed
server-side; both the Desk dialog and `FabricDeliverablesModal.vue` display it):

- knitting rows (per dia): `program`, `ordered` (Σ receivable qty of OTHER non-cancelled
  WOs of this lot + this process, per variant Dia, variant item == cloth),
  `balance = max(program − ordered, 0)` → **pre-fill = balance** (editable).
  Greige colour: pre-select `greige_colour` in the existing Cloth Colour picker when set.
- dyeing rows (per dia, from→to colour): `plan` (colour program row weight), `ordered`
  (other dyeing WOs per (dia, to_colour)), `available` (program row's knitting
  `received_weight` − Σ dyeing ordered on that dia) → pre-fill = max(plan − ordered, 0),
  row label shows `Available greige <dia>: X kg`.
- compacting rows (per colour, from→to dia): `available` = colour program
  `received_weight` for (from_dia, colour) − other compacting WOs' ordered on that key
  → pre-fill = balance.

Exceeding the balance warns (orange) but does not block — same stance as production_api
(its qty-limit validation is deliberately disabled) and knitting can legitimately
over-deliver.

Engine (`calculate_fabric_deliverables`) is unchanged.

## Amendments (2026-07-04, post-live-testing)

- **Multi-colour knitting (user request):** one knitting WO can produce several
  greige colours for the same supplier. The popup renders one COLUMN per greige
  colour (dyeing from-colours), an input per dia inside each; every (dia,
  colour) input posts its own entry line with a line-level `colour` (validated
  server-side). The greige column gets the balance pre-fills; per-dia overshoot
  warning sums across colours. More than 6 colour options falls back to the old
  single-colour picker. Desk dialog + /web modal.
- **Display collapse fix:** calculated rows now carry `table_index`/`row_index`
  (`fc-<n>`) — yrp's `group_items_for_ui` buckets logical rows by row_index and
  was rendering only the FIRST of the indexless calculated rows (and a manual
  form save then persisted the collapsed view, deleting the rest). Base yrp
  hardened too: indexless rows get a unique synthetic bucket instead of
  collapsing into one.

- **Dyeing split replaced by a production LEDGER (user request, same evening):**
  the Lot no longer plans a colour split. `Lot Fabric Colour Program` is now a
  read-only, fully server-owned ledger: rows appear as GRNs land —
  `received_weight` = dyed kgs, new `compacted_weight` = compacted kgs (keyed by
  the receipt's variant). Compacting is therefore TRACKED now (supersedes
  "knitting+dyeing only"). The island's second grid renders "Produced against
  program — from GRNs" (Dia | Colour | Dyed | Compacted, no entry controls);
  saves rebuild only the program table. Dyeing popup pre-fills nothing (colour
  decision happens in the popup); it still shows Ordered + Greige available.

## Out of scope (this round)

- /web Lot program entry panel (the /web WO modal still benefits from the enriched
  context; a dedicated LotFabricProgram /web editor is a follow-up).
- Wastage/excess percentage math in the popups (v1 stays 1:1 per the 2026-07-02 rule).
- Compacting received tracking (only knitting + dyeing tracked, per user).

## Acceptance drive (begin where the user begins)

1. Desk Lot: enter fabric program (32 dia: 500) + colour split (Red 200 / Blue 300),
   save, reload — persists; totals hint correct.
2. Fresh knitting WO created by hand (process → lot → item): popup pre-fills 500,
   greige auto-selected; Calculate writes yarn deliverable + greige receivables.
3. Second knitting WO: popup pre-fills remaining balance (program − first WO).
4. Submit WO → DC → GRN receive (incl. one receipt over program via excess allowance):
   Lot program `received_weight` updates; GRN cancel decrements.
5. Dyeing WO: popup shows greige available = knitting received; pre-fills colour plan;
   after dyeing GRN, colour program `received_weight` updates.
6. Compacting WO: popup shows dyed available per (dia, colour).
7. "Recalculate Received" reproduces identical numbers.
