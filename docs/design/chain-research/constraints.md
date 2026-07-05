# Fabric chain commonization — exhaustive constraint map

Bench: /home/anas/frappe-16 · App: essdee_yrp (+ base yrp) · Date: 2026-07-04
Scope: every place the three hardcoded fabric stages (knitting / dyeing / compacting)
are baked in, what each hardcodes, and what a generic chain model (N stages,
e.g. + re-compacting) must supply instead. Plus the IPD approval flow the
chain back-computation function will hook.

All paths relative to `/home/anas/frappe-16/apps/` unless absolute.

---

## 0. The one sentence version

The stage list lives in exactly ONE server constant —
`FABRIC_PROCESS_FIELDS` in `essdee_yrp/essdee_yrp/fabric_ipd.py:12` — but its
three *kinds* leak everywhere as string literals (`"knitting"|"dyeing"|"compacting"`),
as three fixed IPD Link fields + three fixed child tables (fixtures), as an
implicit chain ORDER (knit feeds dye feeds compact) wired into wildcard
expansion, availability math, UI seeding, and the Lot ledger's two fixed
columns (`received_weight` = dyed, `compacted_weight` = compacted). A generic
model must replace "three named tabs" with an ordered list of stage rows
(process + stage-shape + mapping rows), and replace "previous stage by name"
with "previous row in the chain".

---

## 1. Data model — IPD custom fields (fixtures) [THE root hardcode]

File: `essdee_yrp/essdee_yrp/fixtures/custom_field.json` (dt = Item Production Detail)

| fieldname | type | hardcodes |
|---|---|---|
| `is_cloth_item` | Check (after `item`) | cloth-IPD discriminator (fine, keep) |
| `fabric_knitting_tab` | Tab Break, depends `is_cloth_item` | fixed tab #1 |
| `knitting_process` | Link Process | fixed stage-1 process slot |
| `yarn_item` | Link Item | stage-1 input item slot (conversion input) |
| `knitting_dia_details` | Table → IPD Knitting Dia Detail | stage-1 value rows (dia list) |
| `cloth_per_kg_yarn` | Float | stage-1 conversion ratio (1 in → N out) |
| `fabric_dyeing_tab` | Tab Break | fixed tab #2 |
| `dyeing_process` | Link Process | fixed stage-2 process slot |
| `dia_wise_colour_change` | Check | stage-2 "entry mode" flag (pin-wise widget) |
| `dyeing_colour_matrix_html` | HTML | stage-2 swap-widget mount |
| `dyeing_colour_details` | Table → IPD Dyeing Colour Detail | stage-2 mapping rows |
| `fabric_compacting_tab` | Tab Break | fixed tab #3 |
| `compacting_process` | Link Process | fixed stage-3 process slot |
| `colour_wise_dia_change` | Check | stage-3 entry mode flag |
| `compacting_dia_matrix_html` | HTML | stage-3 swap-widget mount |
| `compacting_dia_details` | Table → IPD Compacting Dia Detail | stage-3 mapping rows |

Child doctypes (essdee_yrp/essdee_yrp/essdee_yrp/doctype/):
- `IPD Knitting Dia Detail` = {dia: Link IAV} — one column.
- `IPD Dyeing Colour Detail` = {dia?: Link IAV (pin), from_colour, to_colour}.
- `IPD Compacting Dia Detail` = {colour?: Link IAV (pin), from_dia, to_dia}.

Also `Process.is_cloth_process` Check custom field (same fixtures file) — routes WO
item filtering + WO validation; stays as-is in a generic model.

**Generic replacement needs:** ONE ordered child table on the IPD, e.g.
`IPD Fabric Stage` rows: {idx = chain position, process: Link Process,
(shape read from Process master: conversion vs swap(attribute)),
conversion fields (input_item, output_per_input) when conversion,
mapping rows}. Mapping rows need a stage-generic shape: {pin_value?, from_value,
to_value} where the swap attribute comes from the Process master and the pin
attribute is "the other" chain attribute — or, fully general, {pin_attribute,
pin_value, from_value, to_value}. The three per-stage child tables and the
six per-tab scalar fields all collapse into this. Tab Breaks/HTML mounts become
one "Fabric Chain" tab with a repeating widget per stage row. Entry-mode
checkboxes become per-stage-row flags (or always-on widget).
Re-compacting then = a second stage row pointing at a *different* Process master
with the same swap attribute (Dia) — note constraint in §4 (distinct Process per
stage because matrices are keyed (ipd, process_name)).

---

## 2. Matrix generation — `essdee_yrp/essdee_yrp/fabric_ipd.py`

| line | what it hardcodes | generic need |
|---|---|---|
| 8–9 | `FABRIC_DIA_ATTRIBUTE="Dia"`, `FABRIC_COLOUR_ATTRIBUTE="Colour"` | keep as site constants OR derive from Process.value_change_attributes per stage; the *pair* (swap attr + passthrough attr) must come from the stage row, not module constants |
| 12–16 | `FABRIC_PROCESS_FIELDS` = the 3 (fieldname, kind) pairs | iterate IPD Fabric Stage rows instead |
| 23–27 | `FABRIC_KIND_SHAPES` kind→expected Process shape | shape comes from Process master directly (`get_process_shape`), kind string dies |
| 30–37 | `get_fabric_process_kind(ipd, process)` — resolves WO process → kind by comparing the 3 link fields | `get_fabric_stage(ipd, process)` → the stage ROW (carries position, shape, mapping table); every caller below depends on this |
| 40–52 | `get_process_shape` — already generic (reads is_item_conversion / value_change_attributes) but takes only `swaps[0]` | keep; decide multi-swap policy explicitly |
| 55–79 | `validate_fabric_process_shapes` iterates the 3 fields, expects kind-specific shape | validate each stage row's process declares *a* shape; the IPD stage row stores which |
| 82–95 | `get_identity_process_row` — "not one of the three conversion tabs" ⇒ identity | "not any chain stage row" ⇒ identity |
| 98–121 | `ensure_cloth_item_attributes` — knitting/compacting⇒Dia, dyeing⇒Colour, plus dia_wise/colour_wise flags | per stage row: add its swap attribute + its pin/passthrough attribute to `item_attributes` |
| 125–154 | `sync_fabric_process_matrices` — builder dict keyed by the 3 kind strings | one loop over stage rows: `conversion → _build_conversion_matrix`, `swap → _build_value_swap_matrix`; wipe-and-rebuild (137–141) stays |
| 171–201 | `_build_knitting_matrix` — reads `knitting_dia_details`, `yarn_item`, `cloth_per_kg_yarn`; output attr = Dia; input combo attr-less (yarn variant chosen per WO) | `_build_conversion_matrix(stage)`: value rows, input item, ratio from the stage row; output attribute = the stage's declared out attribute |
| 204–247 | `_build_value_swap_matrix` — ALREADY generic (attribute, from/to fields, passthrough attr/field parametrised) | keep; call with stage-row params. Passthrough stamping both sides (242–246) is the "combination" the user asked for — it already connects stages per dia/colour |
| 250–270 | `_expand_wildcard_rows` — generic | keep |
| 273–287 | `derive_passthrough_values` — **CHAIN ORDER HARDCODE**: dia values := knitting tab dias (else Dia mapping); colour values := dyeing to_colours (else Colour mapping) | "values of attribute A available at my chain position" = walk PRECEDING stage rows: last stage whose swap/out attribute is A contributes its to-values / dia rows; fallback to IPD attribute mapping. This is the core chain-walk function and should be THE shared helper (also used by §3 identity rows, §5 Lot dias/colours) |
| 290–303 | `_build_dyeing_matrix` / `_build_compacting_matrix` — bind the tab's table + field names | die; replaced by generic call with stage mapping rows |

**Key insight:** the matrix DOC format is already stage-agnostic. Only the
*builders' inputs* (which table, which fields, which passthrough values) are
tab-bound. A chain of N swap matrices whose passthrough values are derived from
the previous stage's to-values already "combines" per dia/colour exactly as
requirement 5 demands — for the 2-attribute (Dia, Colour) world. A third
attribute would need pin→set-of-pins generalisation.

---

## 3. WO popup context + calculate — `essdee_yrp/essdee_yrp/api/work_order.py`

| line | what it hardcodes | generic need |
|---|---|---|
| 41–49 | kind = `get_fabric_process_kind` else identity | stage-row resolution (§2) |
| 60–62 | `_add_planning_data` gated on the 3 kind strings | run for every chain stage |
| 70 | `ratio = ipd.cloth_per_kg_yarn or 1` context field | ratio from the stage row (conversion stages only) |
| 72–78 | `greige_colour` / `colour_options` / `colour_mapping` **knitting-only** context | property of "first stage whose output lacks a value for attribute X that later stages will swap": generically = a conversion stage whose output attrs don't cover all item attributes ⇒ popup asks for the free attribute's value. Options = next swapping stage's from-values (see `_knit_colour_options`) |
| 85–162 | `_add_planning_data` — three explicit branches: knitting keyed {dia} vs `lot_fabric_programs`; dyeing availability = knit `received_weight` − `get_consumed_by_dia` (gated `has_knitting`, 128); compacting availability = colour-ledger `received_weight` − `get_consumed_by_dia_colour` keyed on INPUT attrs (147–162, gated `has_dyeing`) | generic rule per stage i: `ordered` = Σ receivables of other WOs of THIS process keyed by out-attrs; `available` = previous stage's received (from the generic ledger, §6) − Σ calculated deliverables of this process keyed by IN-attrs. "Previous stage" = chain row i−1 (None when i=0 or previous not managed → available=None, matching today's bought-greige behaviour). Prefill policy per stage kind (first stage: program balance; middle: 0 or available) should be data, not code |
| 101–107 | program keyed `r.dia` / colour rows keyed `(r.dia, r.colour)` | ledger keys become attr-dicts (§6) |
| 165–195 | `_matrix_qty_rows` — matrix-driven, generic except `_group_label(kind,…)` | keep; label from group_name or generic "{in}→{out}" formatter |
| 198–246 | `_identity_qty_rows` — Dia/Colour only (212–217); union of values from the 3 tab tables (249–261) | value union = chain-walk helper (§2 273–287 replacement) over all stage rows; attr whitelist = attrs the chain knows |
| 264–273 | `_group_label` — 3 label formats | one format: `[pins]: from → to` (already effectively that) |
| 276–293 | `_knit_colour_options` — dyeing from_colours, else Colour mapping, else all Colour IAVs | "from-values of the NEXT stage that swaps the free attribute" |
| 306–317 docstring | states the 3 kinds' entry semantics | doc only |
| 380–389 | knitting colour validation (`_require_ipd_yarn` 384, valid_colours 389) | conversion-stage free-attribute validation, options as above |
| 400–405 | colour required + must be valid greige — knitting-only | same |
| 414 | `input_item = matrix.input_item or ipd.item` | already generic |
| 422–424 | knitting stamps line colour into out_attrs | free-attribute stamping for conversion stages |
| 437–439 | yarn override valid only when 1 aggregated input | conversion-stage input override, same guard |
| 460–465 | `fc-` row_index stamping | generic, keep |
| 484–505 | `_resolve_matrix_group` — fully generic (key = matrix:group) | keep untouched |
| 525–529 | `_require_ipd_yarn` reads `ipd.yarn_item` | stage-row input_item |

**Requirement-4 hook (back-compute on approval):** the per-WO calculate at
306–481 is already matrix-group-keyed. The new "common function" that, at IPD
approval, walks REQUIREMENT → compacting⁻¹ → dyeing⁻¹ → knitting⁻¹ can reuse the
same group resolution but must walk matrices in REVERSE: given desired out-attrs
(colour+dia+kg), find the group whose OUTPUT matches, take its INPUT combo as the
previous stage's demand. Reverse matching by attrs (not by key) is safe iff a
stage never maps two different from-values to the same (out, pins) key — which
today's data allows (White→Black and Ecru→Black at same dia, see 313–317
comment). So the chain function needs a DISAMBIGUATION rule (e.g. split demand
across all matching groups, or refuse and ask) — flag this in the design.

---

## 4. IPD validation — `essdee_yrp/essdee_yrp/ipd_validations.py`

| line | what it hardcodes | generic need |
|---|---|---|
| 10–16 | `is_cloth_ipd` | keep |
| 63–65 | the 3 process fields must be DISTINCT masters (matrices keyed (ipd, process_name); base engine subset-matches across matrices of one process) | stage rows must each use a distinct Process master — this is what makes "re-compacting" a NEW Process ("Re-Compacting") rather than compacting twice; validation becomes "no duplicate process across stage rows" |
| 69–70 | `validate_fabric_process_shapes(doc)` | per-stage shape check (§2) |
| 72–79 | identity `process_item` ∈ {doc.item, yarn_item} | ∈ {doc.item} ∪ {conversion stages' input items} |
| 81–84 | `cloth_per_kg_yarn > 0` required when `knitting_process` set | ratio > 0 required on conversion stage rows |
| 86–95 | per-tab `validate_swap_rows` with tab-specific (table_label, pin, from, to) | one loop over swap stage rows; `validate_swap_rows` (98–110) is already field-generic |

## 4b. Base yrp pieces (already generic — the chain builds ON these)

- `yrp/yrp/yrp/doctype/ipd_process_matrix/ipd_process_matrix.{json,py}` — doc shape:
  ipd, process_name, input_item, output_item, input/output_attributes,
  combinations (group_index, group_name, side, combo_index, quantity, uom,
  wastage_pct), combination_attributes. `get_combinations_grouped()` py:74–92 is
  the read API. `validate_attributes_belong_to_ipd` py:21–63 forces every output
  attr into IPD `item_attributes` (why `ensure_cloth_item_attributes` exists).
  **No change needed for N stages.**
- `yrp/yrp/yrp/doctype/process/process.json` — `is_item_conversion` (l.37–43),
  `value_change_attributes` Table → Process Value Change {attribute} (l.117–129).
  The Process master already declares the reusable SHAPE. A "Re-Compacting"
  process = new Process doc with value_change_attributes=[Dia]. **No change.**
- `yrp/yrp/utils/ipd_engine.py:12 get_process_io` — generic demand→IO scaler,
  matches groups by attr subset across a process's matrices. The reverse chain
  walk (§3) can mirror its structure. **No change.**

---

## 5. Lot program + ledger — data + server

Lot doctype (`essdee_yrp/essdee_yrp/essdee_yrp/doctype/lot/`):
- `lot.json`: `fabric_details_section`, `lot_fabric_details` (Table → Lot Fabric
  Detail {cloth_item, production_detail}), `fabric_program_html` (island mount),
  `lot_fabric_programs` (hidden Table), `lot_colour_programs` (hidden Table).
- `lot.py:26–28` before-validate → `validate_unique_fabric_cloths` + `save_fabric_program_details`;
  `lot.py:126–127` onload → `fetch_fabric_program_details`.

Child tables:
- `Lot Fabric Program` {cloth_item, dia, weight, received_weight RO} —
  **hardcodes**: keyed by ONE attribute (dia); `weight` semantics = "what knitting
  must produce"; received = knitting GRNs only.
- `Lot Fabric Colour Program` {cloth_item, dia, colour, weight(unused),
  received_weight "Dyed (Kg)" RO, compacted_weight "Compacted (Kg)" RO} —
  **hardcodes**: exactly 2 stage-columns, labelled by stage name; adding
  re-compacting has NO column to land in. This is the loudest schema blocker.

`essdee_yrp/essdee_yrp/fabric_program.py`:

| line | hardcodes | generic need |
|---|---|---|
| 4–17 docstring | program = knitting demand; ledger cols = dyed/compacted | rewrite semantics |
| 40–42 | `dias` (63–67: knitting tab else Dia mapping), `colours` (70–74: dyeing to_colours else Colour mapping), `greige_colour` (77–83: single dyeing from_colour) | chain-walk helper per attribute (§2); greige = conversion stage's free-attr default |
| 49–58 | ledger payload row = {dia, colour, received_weight, compacted_weight} | per-stage received keyed by attr-dict |
| 86–116 | unique cloth per fabric row; removal blocked when `received_weight`/`compacted_weight` ≠ 0 (101–108) | same rule against the generic ledger |
| 119–180 | program rebuild keyed (cloth, dia); dia validated as Dia IAV (158, 222–226) | requirement 3 splits this: (a) knitting PROGRAM stays (dia, weight); (b) NEW final-REQUIREMENT table {colour, dia, kg of finished cloth} — does not exist anywhere yet; approval chain function consumes (b) |
| 203–219 | `_db_received` key = (cloth, dia) or (cloth, dia, colour) | key = (cloth, stage/process, attrs-json or normalized attr columns) |
| 229–262 | `_warn_program_below_ordered` — `ipd.knitting_process` only (243–245) | first-chain-stage generic |

**Generic ledger proposal implied by the code:** replace `Lot Fabric Colour
Program`'s fixed columns with per-(stage, variant-attrs) ROWS — e.g.
`Lot Fabric Stage Receipt` {cloth_item, process_name (or stage idx), dia, colour,
received_kg} — so any number of stages lands rows; the island renders columns
per stage dynamically. received columns stay server-owned (standing rule).

---

## 6. GRN tracking + balances — `essdee_yrp/essdee_yrp/fabric_tracking.py`

| line | hardcodes | generic need |
|---|---|---|
| 7–13 docstring | knitting→program.received; dyeing→colour.received; compacting→colour.compacted (keyed by OUTPUT variant) | receipts route by stage row: stage 0 → program received; stage i → ledger row (stage, out-attrs) |
| 29 | `TRACKED_KINDS = ("knitting","dyeing","compacting")` | "every chain stage row" |
| 56–68 | `_apply_grn` kind→(table, column) routing; `with_colour=(kind != "knitting")` | key attrs = union of stage's out attrs (from its matrix output_attributes) |
| 71–90 | `_grn_deltas_for_cloth` keys (dia,)/(dia,colour); requires Dia (80) and Colour when with_colour (82–84) | keys from stage's declared attrs; skip variants missing them |
| 93–112 | `_variant_attribute_map` SQL: `iva.attribute IN (Dia, Colour)` | attribute list parameterised |
| 115–152 | `_bump_program_rows` — two literal table names + two literal columns (127–129); row create sets dia/colour (146–148) | one ledger doctype, column = received_kg, row key includes stage |
| 155–188 | `rebuild_fabric_tracking` — replays all GRNs; zeroes the two fixed columns (166–170) | zero the generic ledger; replay unchanged |
| 195–226 | four wrappers: `get_produced_by_dia`, `get_produced_by_dia_colour`, `get_consumed_by_dia`, `get_consumed_by_dia_colour` — attribute tuples baked into names | ONE `get_wo_totals(lot, process, cloth, side, attributes, exclude_wo)`; `_sum_by_attributes` (229–277) is ALREADY generic given the attributes tuple — only the four named wrappers die |
| 246–251 | rework excluded, calculated_only for deliverables | keep (standing rules) |

---

## 7. Desk UI

### 7a. IPD form — `essdee_yrp/essdee_yrp/public/js/item_production_detail.js`

| line | hardcodes | generic need |
|---|---|---|
| 6–10 | set_query per tab child field (Dia/Colour attribute filters) | queries derived from stage rows' attributes |
| 1085–1102 | `FABRIC_SWAP_WIDGETS` — exactly two widget configs (dyeing, compacting) with field/attr names | one widget instance per swap stage row, config built from the row |
| 1104–1108 | setup set_query for pin fields | same |
| 1113–1123 | `apply_cloth_layout` — hides item_bom, relabels section | keep |
| 1124–1129 | per-checkbox re-render triggers (`dia_wise_colour_change`, `colour_wise_dia_change`) | per-stage-row flags |
| 1147–1175 | `fabric_swap_widget_data` — **CHAIN ORDER IN UI SEEDING** (1159–1166): dyeing seeds pins from `knitting_dia_details` dias; compacting seeds from dyeing `to_colour`s | seed pins = chain-walk "values of pin attribute available before this stage" (same helper as §2, exposed to client or computed server-side into onload) |
| 1172 | `locked` when `approval_status === "Approved"` (swap widgets only) | apply to all stage editors. NOTE GAP: the Approved lock lists (345–351) do NOT include `knitting_dia_details`/`dyeing_colour_details`/`compacting_dia_details` grids — plain-table fabric edits are NOT locked after approval today; the chain design must lock the whole stage table post-approval |
| 1177–1187 | write-back to cfg.table_field | write-back to the stage row's mapping rows |

`FabricSwapDetail.vue` (`public/js/Item_Po_detail/FabricSwapDetail.vue`, registered
`vue_plugins.js:165`) — fully config-driven (pin/value labels+attrs passed in);
**reusable as-is** per stage.

### 7b. Approval buttons (same file)

- 179–208: "Approve" button when `approval_status !== "Approved"` and user holds an
  approval role → `essdee_yrp.ipd_ui.approve_ipd(doc_name, "Approved")`.
- 209–227: "Revert Approval" (System Manager) → `revert_ipd_approval`.
- 325–376: Approved lock — garment-centric field lists only (see gap above).
- `item_production_detail_list.js`: list indicators for the 3 statuses.

### 7c. WO form + Calculate dialog — `essdee_yrp/essdee_yrp/public/js/work_order.js`

| line | hardcodes | generic need |
|---|---|---|
| 15 | "Calculate Fabric Deliverables" button (all draft WOs) | keep |
| 27–49 | `is_cloth_process` → item filtered to lot fabric cloths | keep |
| 80–95 | `planning_description(kind,…)` — 3 label branches ("Program/Ordered/Balance", "Greige available", "Dyed available") | server sends `planning_parts` or stage-neutral labels ("Available from <prev process>") so the client stops switching on kind |
| 100–134 | `warn_balance_overshoot` — knitting/dyeing sum per dia; compacting per row | rule = "sum per PREVIOUS-stage key"; server can send the grouping key per qty row |
| 140 | `MAX_COLOUR_COLUMNS = 6` | conversion-stage free-attr columns; keep |
| 142–311 | dialog: knitting-only colour picker/columns (167–222), yarn field (239–244), `recompute_yarn` (148–156), payload rows {fabric_row, colour, yarn_qty, entries[{key,out_attrs,qty,colour?}]} (252–303) | branches keyed on `row.kind === "knitting"` become `row.is_conversion` / `row.free_attribute`; payload contract can stay (key-based) |

`essdee_yrp/essdee_yrp/work_order_hooks.py:12–30` — cloth-process WO item must be a
lot fabric cloth. Generic already.

### 7d. Lot form — `lot.js` + `FabricProgram.vue`

- `doctype/lot/lot.js:21–27` fabric child queries (is_cloth_item / item=cloth);
  139–141 island mount; 188–190 get_data → `fabric_program_details`. Generic.
- `public/js/Lot/FabricProgram.vue` — **hardcodes** the two-grid layout:
  program grid (dia|weight|received, 24–74) and ledger grid with FIXED columns
  Dia|Colour|Dyed|Compacted (77–102, headers 84–85). `entry.dias/colours` come
  from the server (§5). Generic need: ledger columns rendered per chain stage
  (server sends stage list), or long-format rows (stage|dia|colour|kg). ALSO the
  place requirement 3's FINAL REQUIREMENT grid (colour+dia+kg) will live —
  currently absent.

---

## 8. /web (frontend SPA)

- `frontend/src/views/dynamic/FabricDeliverablesModal.vue` — line-for-line port of
  the Desk dialog. Same kind branches: knitting note+colour select (38–52),
  multi-colour grid (55–73), yarn field (92–104), `planningLine` 3-branch
  (196–210), `warnBalanceOvershoot` 3-branch (214–250), `MAX_COLOUR_COLUMNS`
  (252), payload (276–306). Whatever contract change §7c makes must be mirrored
  here 1:1.
- `frontend/src/views/dynamic/DocDetail.vue` — 113–124 Calculate button (draft WO);
  332–337 modal mount; 1242 import; 3156–3168 Lot fabric child link filters
  (cloth_item is_cloth_item, production_detail by cloth); 3521–3545 open/refresh
  handlers. Kind-agnostic already.
- `frontend/src/views/dynamic/IPDConfigView.vue` — approval badge only
  (49–50, 927+); no fabric tabs. `frontend/src/config/fields/item-production-detail.js`
  is an empty config: /web renders IPD Custom Fields META-DRIVEN — so replacing
  three tabs with one stage table shows up on /web automatically; a custom
  stage-chain widget for /web would be new work (currently none exists → no /web
  IPD fabric editor to migrate, only not to break).
- No /web Lot fabric-program editor exists (spec §out-of-scope) — nothing to port.

---

## 9. IPD approval flow today (the chain function's hook point)

- Field: base `yrp/yrp/yrp/doctype/item_production_detail/item_production_detail.json:36–37` —
  `approval_status` Select `Not Approved | Cutting Approved | Approved`
  (default "Not Approved", read_only) + `approved_by` Link User.
- `essdee_yrp/essdee_yrp/ipd_ui.py:90–102 get_approval_roles` — MRP Settings
  `senior_merch_role` / `merchandising_manager_role`, fallback ["System Manager"].
- `ipd_ui.py:105–118 approve_ipd(doc_name, approval_type)` — accepts only
  "Cutting Approved" / "Approved"; role check; sets `approval_status` +
  `approved_by`; **`doc.save(ignore_permissions=True)`** — this save re-runs the
  full hook chain (hooks.py:203–215): `before_validate` (ipd_validations +
  `ensure_cloth_item_attributes`) → `validate` → `on_update`
  (`sync_fabric_process_matrices`). So on approval the matrices are already
  freshly rebuilt IN THE SAME SAVE — the chain back-computation can run right
  after `sync_fabric_process_matrices` in on_update, gated on
  `doc.approval_status == "Approved"`, or be called explicitly from `approve_ipd`.
- `ipd_ui.py:121–130 revert_ipd_approval` — System Manager only → "Not Approved"
  (chain outputs may need invalidation on revert — currently nothing listens).
- Desk buttons §7b; list indicators `item_production_detail_list.js`; /web badge §8.
- IMPORTANT WRINKLE for requirement 4: the requirement (colour+dia+kg) lives on
  the LOT, but approval fires on the IPD (one IPD serves many Lots). The "common
  function" therefore needs (a) an on-approval part (freeze/validate the chain:
  every requirement-reachable (colour, dia) has a complete matrix path back to
  the conversion stage) and (b) a per-Lot part (expand a Lot's requirement kgs
  through the frozen matrices into per-stage receivable/deliverable plans) —
  triggered when the Lot references an APPROVED IPD (validated in Lot save or a
  Lot-side "Generate Plan" action). Nothing exists yet for either; there is also
  no guard today preventing a Lot from using a non-approved IPD.

---

## 10. Cross-cutting chain-order hardcodes (the hidden ones)

1. `derive_passthrough_values` (fabric_ipd.py:273–287) — dyeing pins from
   knitting, compacting pins from dyeing.
2. `_add_planning_data` (api/work_order.py:125–162) — dyeing available :=
   knitting received; compacting available := dyeing received; gates
   `has_knitting`/`has_dyeing` mean "is the previous stage managed here".
3. Swap-widget seeding (item_production_detail.js:1159–1166) — same order in UI.
4. Ledger columns (Lot Fabric Colour Program received=dyed, compacted=compacted)
   — order fossilised in the schema.
5. `_identity_attr_values` (api/work_order.py:249–261) and `_ipd_dias`/
   `_ipd_target_colours` (fabric_program.py:63–74) — value unions read the named
   tab tables.
6. `_knit_colour_options` (api/work_order.py:276–293) — knitting's free colour
   choices := dyeing from-colours (stage i's free attr constrained by stage i+1).
   Generic: "next stage that swaps attribute X".

All six are instances of ONE missing primitive: an ordered stage list with
"values of attribute A entering/leaving stage i". Build that helper once (server
side, on the IPD doc) and every site above becomes a call to it.

## 11. What stays untouched (verified)

- Garment side: ipd_validations garment branch, packing/stitching/cutting JS,
  ipd_ui combination machinery — all gated by `is_cloth_ipd` / `!is_cloth_item`.
- IPD Process Matrix doctype + `get_combinations_grouped` + `_resolve_matrix_group`
  key contract + `fc-` row indexing + idempotent WO rewrite (MGK pattern).
- GRN excess/rework rules, per-lot locking (fabric_tracking.py:50,
  fabric_program.py:136–137), `rebuild_fabric_tracking` replay shape.
- `Process` master shape fields; `is_cloth_process` routing; work_order_hooks.
- Spec baseline: `essdee_yrp/docs/design/2026-07-04-lot-fabric-program-design.md`
  (program = knitting demand; colour table = ledger; popup balance semantics).
