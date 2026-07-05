# Fabric Chain Commonization — MINIMAL-DELTA design

Date: 2026-07-04 · Bench: /home/anas/frappe-16 · App: essdee_yrp (base yrp untouched)
Angle: keep the three existing tabs (knitting / dyeing / compacting) working EXACTLY
as-is for every existing IPD; ADD a generic chain mechanism behind and after them.
Optimize for zero migration risk, smallest diff, ship in days.

Companion files: `constraints.md` (hardcode map), `cases.md` (case catalogue) — same folder.

---

## 0. The design in one paragraph

The three tabs stay the canonical editors for the first three stages. A new
server-side **normalizer** — `get_fabric_chain(ipd_doc)` in a new module
`essdee_yrp/fabric_chain.py` — reads the tabs PLUS a new generic child table
(`IPD Fabric Stage` + one flat mapping table `IPD Fabric Stage Mapping`) and returns
ONE ordered list of stage descriptors. Every chain-order hardcode
(`derive_passthrough_values`, `_add_planning_data` gating, widget seeding, identity
value unions, knit colour options) becomes a call to two helpers on that list:
`get_chain_stage(ipd, process)` and `state_at(chain, position, attribute)`. Matrices
for extra stages are built by the ALREADY-generic `_build_value_swap_matrix`. New
stages' receipts and the new back-computed plan land in one new per-row ledger
(`Lot Fabric Stage Ledger`); the existing program table and colour ledger keep
their exact roles. The requirement (colour + dia + kg) is a new Lot child table;
`build_fabric_plan()` walks the matrices last→first on IPD approval and on Lot
requirement save. Adding "re-compacting" = create one Process master (30 seconds,
declares swap-Dia shape) + one stage row + mapping rows on the IPD. Zero code.

**v1 scope guard (explicit):** extra stages are SWAP stages on Dia or Colour.
Conversion happens only in the knitting tab; identity processes stay off-chain
(today's `ipd_processes` behaviour). This covers re-compacting, re-dyeing/topping,
and any future dia- or colour-changing process — which is the owner's ask
("re-compacting… there may be another process too"). In-chain identity (washing)
and second conversions are a later, separately-shippable extension (§12 phase 6);
nothing in this design blocks them because everything keys on the chain list.

---

## 1. IPD data model — chain + per-process config

### 1.1 New child doctypes (essdee_yrp, module "Essdee YRP")

**`IPD Fabric Stage`** (`essdee_yrp/essdee_yrp/doctype/ipd_fabric_stage/`), istable:

| field | type | notes |
|---|---|---|
| `process` | Link Process, reqd | must be DISTINCT from the tab processes and from other stage rows (I4) |
| `position` | Select `After Knitting` / `After Dyeing` / `After Compacting`, default `After Compacting`, reqd | anchor into the tab prefix; rows sharing an anchor order by table idx |
| `swap_attribute` | Link Item Attribute, read_only | display only — auto-filled server-side from `get_process_shape(process)`; the Process master owns the shape (standing rule) |
| `pin_wise_entry` | Check | per-stage analogue of `dia_wise_colour_change` — turns on the FabricSwapDetail widget card for this stage |

`position` resolution: anchors that point at an absent tab collapse to the nearest
earlier active anchor (e.g. `After Compacting` on a dye-only IPD = after dyeing).
Junior rule stated in the field description: "where in the chain this process runs".

**`IPD Fabric Stage Mapping`** (`.../ipd_fabric_stage_mapping/`), istable — ONE flat
table for all extra stages (Frappe can't nest child tables; the stage's `process`
is the foreign key, safe because processes are unique per IPD by I4):

| field | type | notes |
|---|---|---|
| `process` | Link Process, reqd | which stage row this mapping belongs to |
| `pin_value` | Link Item Attribute Value | the OTHER attribute's value; blank = wildcard (applies to every value), exactly like today's `dia`/`colour` pin columns |
| `from_value` | Link Item Attribute Value, reqd | |
| `to_value` | Link Item Attribute Value, reqd | |

### 1.2 New IPD Custom Fields (fixtures/custom_field.json, dt = Item Production Detail)

All `depends_on: eval:doc.is_cloth_item`, inserted after `compacting_dia_details`:

| fieldname | type | notes |
|---|---|---|
| `fabric_more_stages_tab` | Tab Break "More Processes" | fourth fabric tab, holds ALL extra stages |
| `fabric_stages` | Table → IPD Fabric Stage | the ordered stage rows |
| `fabric_stage_editor_html` | HTML | mount point: one FabricSwapDetail card per `pin_wise_entry` stage |
| `fabric_stage_mappings` | Table → IPD Fabric Stage Mapping | plain-grid entry; `depends_on` stays visible (grid and widget edit the SAME rows, like today's dyeing table) |

Nothing about the three existing tabs changes: no field moved, renamed, or
re-parented. Existing IPD JSON round-trips byte-identical.

### 1.3 The normalizer — `essdee_yrp/fabric_chain.py` (new module, ~150 lines)

```python
# A FabricStage is a frappe._dict:
# {
#   "source":        "tab:knitting" | "tab:dyeing" | "tab:compacting" | "stage_row",
#   "position":      int,                  # 0-based chain order
#   "process_name":  str,
#   "shape":         "conversion" | "swap",
#   "swap_attribute": "Colour"|"Dia"|None, # swap stages
#   "pin_attribute":  "Dia"|"Colour"|None, # the OTHER of (Dia, Colour), v1 rule
#   "input_item":     yarn item or None,   # conversion only
#   "ratio":          cloth_per_kg_yarn,   # conversion only (display; math uses matrix)
#   "mapping_rows":  [ {"pin": v, "from": v, "to": v}, ... ],   # normalized dicts
#   "pin_wise_entry": bool,
# }

def get_fabric_chain(ipd_doc) -> list:      # ordered FabricStage list
def get_chain_stage(ipd_doc, process_name): # FabricStage or None (replaces get_fabric_process_kind
                                            # as the RESOLUTION entry point; the old function stays
                                            # and is called by this one for the tab prefix)
def state_at(ipd_doc, chain, position, attribute) -> list[str]:
    """Values of `attribute` ENTERING the stage at `position`:
    walk stages [0..position-1] backwards; the LAST stage that defines the
    attribute wins — a swap stage contributes its distinct to-values, the
    conversion stage contributes its dia list (for Dia). Nothing found ->
    the IPD's attribute-mapping values (bought greige / free knit colour).
    This is invariant I9 — the ONE helper that kills all six chain-order
    hardcodes (constraints §10)."""
def final_output_values(ipd_doc, chain, attribute) -> list[str]:
    """= state_at(len(chain), attribute): what leaves the chain — requirement
    validation + Lot island pickers."""
def chain_fingerprint(ipd_doc) -> str:
    """md5 of the normalized chain JSON (tabs + stage rows + mappings + yarn +
    ratio). Used to auto-revert approval on chain edits (§5.4)."""
```

`get_fabric_chain` builds the tab prefix (knitting → dyeing → compacting, skipping
unset tabs, mapping rows normalized from `knitting_dia_details` /
`dyeing_colour_details` / `compacting_dia_details`), then splices `fabric_stages`
rows at their anchors. For dyeing/compacting the returned mapping dicts use the
same normalized keys (`pin`/`from`/`to`), so downstream code never touches the
tab-specific fieldnames again.

### 1.4 Validation deltas (`ipd_validations.validate_cloth_ipd`)

- Distinct-master check (line 63) extends to `fabric_stages` rows:
  `[knitting, dyeing, compacting] + [r.process for r in fabric_stages]` must be
  all-distinct. Error message names the duplicate. (I4 — this is exactly why
  re-compacting is a NEW Process master, matching the owner's own wording.)
- Extra stage shape: `get_process_shape(row.process)` must be `("swap", attr)`
  with attr ∈ {Dia, Colour} — HARD error for stage rows (they are new data, no
  legacy leniency; the tabs keep today's warn-only `validate_fabric_process_shapes`).
- Every `fabric_stage_mappings.process` must match a `fabric_stages` row; reuse
  `validate_swap_rows(rows, "Fabric Stage Mapping", "pin_value", "from_value",
  "to_value")` per stage for completeness + forward-dedupe (already field-generic).
- Reachability (I1-lite) at save, WARN only: each stage's from_values should be
  ⊆ `state_at(stage.position, swap_attribute)` — orange msgprint naming stage and
  value ("D20→D18 on Re-Compacting: D20 never comes out of Compacting").
  Hard enforcement happens at plan build/approval (§5.3) so legacy saves never break.
- Injectivity (I2) at save, WARN only (same reason: White→Black + Ecru→Black at
  one pin is legal in today's data); HARD at plan build/approval.
- `ensure_cloth_item_attributes` (fabric_ipd.py:98): add each stage row's
  `swap_attribute` and, when any of its mapping rows carries a pin (or state pins
  will be stamped by expansion), its `pin_attribute`. Concretely: append both
  attributes for every stage row — extra rows are harmless and the base matrix
  validator requires them.
- `get_identity_process_row` (fabric_ipd.py:82): the "is it a chain process?"
  test becomes `get_chain_stage(ipd_doc, process_name)` so an extra-stage process
  can never double as an off-chain identity row (Case 4/14 guard).

### 1.5 Desk IPD UI (item_production_detail.js)

- `render_fabric_swap_widgets` grows one loop: for each `fabric_stages` row with
  `pin_wise_entry`, mount a `FabricSwapDetail` (component reused AS-IS — it is
  already config-driven) into `fabric_stage_editor_html`, config built from the
  stage row (`pin_label/pin_attribute` = pin_attribute, `value_attribute` =
  swap_attribute), write-back filtered to that process's rows in
  `fabric_stage_mappings`.
- Pin seeding for empty stages comes from a new onload payload
  (`ipd_ui.onload` → `set_onload("fabric_chain_info", ...)`) carrying per-stage
  `{process, swap_attribute, pin_attribute, pin_seeds (= state_at pins),
  from_options (= state_at swap values)}` — server-computed with the same helper,
  so the UI seeding hardcode (constraints §10.3) dies. (Limitation, acceptable:
  seeds reflect the last-saved doc; same as approving semantics today.)
- `set_query` on `fabric_stage_mappings.pin_value/from_value/to_value` filters by
  the owning stage's attributes (from `fabric_chain_info`).
- **Approval-lock gap fix** (constraints §7a note): add
  `knitting_dia_details, dyeing_colour_details, compacting_dia_details,
  fabric_stages, fabric_stage_mappings` to the read-only table list and
  `knitting_process, yarn_item, cloth_per_kg_yarn, dyeing_process,
  compacting_process` to the read-only field list in the Approved lock block
  (JS ~line 345); pass `locked` to the new widgets exactly like line 1172 does.
  Server-side enforcement is §5.4 (auto-un-approve), so the JS is UX, not security.
- /web: IPD renders Custom Fields meta-driven (empty field config) — the new tab,
  stage table and mapping grid appear automatically; no /web work in v1.

---

## 2. Matrix generation — one generic builder, stages connected per dia/colour

File: `essdee_yrp/fabric_ipd.py`. The matrix DOC format, `_resolve_matrix_group`,
and the engine need **zero changes** (constraints §4b).

### 2.1 `sync_fabric_process_matrices` delta (~10 lines)

After the existing three-tab loop (unchanged), add:

```python
chain = get_fabric_chain(doc)
for stage in chain:
    if stage.source != "stage_row":
        continue  # tabs already built above, byte-identical to today
    matrix = _build_value_swap_matrix(
        doc, stage.process_name, uom, stage.mapping_rows,
        attribute=stage.swap_attribute, from_field="from", to_field="to",
        passthrough_attribute=stage.pin_attribute, passthrough_field="pin",
        passthrough_values=state_at(doc, chain, stage.position, stage.pin_attribute),
    )
    if matrix:
        matrix.insert(ignore_permissions=True)
```

`_build_value_swap_matrix` (fabric_ipd.py:204) is already fully parametrised; it
gains one optional kwarg `passthrough_values` that `_expand_wildcard_rows` uses
instead of calling `derive_passthrough_values`. The two legacy builders pass
`passthrough_values=None` → fall back to `derive_passthrough_values` →
**byte-identical matrices for every existing IPD** (regression guarantee; the
fallback itself is reimplemented as `state_at` with position of the tab stage —
provably equal outputs, and phase 1 keeps the old function as the wrapper).

### 2.2 How stages stay CONNECTED per dia/colour (the owner's "combination")

The connection is the pin stamping that already exists: a swap matrix's groups
carry the passthrough attribute on BOTH sides (fabric_ipd.py:242-246). The generic
change is only WHERE the pin values come from: `state_at(position, pin_attribute)`
= the previous defining stage's to-values. So:

- Re-compacting (after compacting): its wildcard Dia rows expand per COLOUR from
  the dyeing stage's to-colours; its from-dias validate against compacting's
  to-dias. `D20→D18` exists only for colours that actually reach re-compacting —
  exactly "I should give greige in 18 dia, only then I will get this in 18 dia".
- Topping (after dyeing, before compacting): pins = post-knitting dias; and
  compacting's own colour expansion now reads TOPPING's to-colours because
  `state_at` finds topping as the last colour-defining stage before compacting.
  (Note: this is the one behaviour change legacy code paths can see, and it is
  the CORRECT one — today compacting would wrongly expand on dyeing's colours.)

### 2.3 Identity qty rows + program value unions

`_identity_attr_values` (api/work_order.py:249) and `_ipd_dias` /
`_ipd_target_colours` (fabric_program.py:63-74) re-route through
`final_output_values` / `state_at` unions over the chain (so an IPD whose only
colour stage is a topping stage row still yields colours). Small mechanical edits,
same outputs for tab-only IPDs.

---

## 3. Lot requirement entry — colour + dia + kg beside the program

### 3.1 New child doctype `Lot Fabric Requirement` (istable)

| field | type | notes |
|---|---|---|
| `cloth_item` | Link Item, reqd | |
| `dia` | Link Item Attribute Value, reqd | finished dia |
| `colour` | Link Item Attribute Value | finished colour; blank allowed when the cloth has no Colour attribute |
| `weight` | Float precision 3, reqd | kg of finished cloth |

Lot (lot.json): `lot_fabric_requirements` Table → Lot Fabric Requirement, hidden,
after `lot_colour_programs`. Plus `fabric_plan_meta` JSON hidden (per-cloth plan
status, §5.5).

### 3.2 Entry + save path (mirrors the program flow exactly)

- `fetch_fabric_program_details` (fabric_program.py) adds per-entry keys:
  `requirement: [...]`, `plan: [...]` (§6.3), `plan_meta`,
  `final_dias` / `final_colours` (from `final_output_values`) for the pickers.
- `FabricProgram.vue` gains a third grid **"Final Requirement (finished cloth)"**:
  rows dia | colour | kg, add-row pickers from `final_dias`/`final_colours`,
  colour column hidden when `has_colour` is false. Edits go into the same
  transient `fabric_program_details` JSON the island already posts.
- New `save_fabric_requirements(lot_doc)` in fabric_program.py, called from
  `Lot.before_validate` right after `save_fabric_program_details`:
  validates dia/colour via the existing `_validate_attribute_value`, rejects
  duplicates `(cloth, dia, colour)` and negative weights, drops zero rows,
  rebuilds `lot_fabric_requirements` (no server-owned columns to carry — it is
  pure user data).
- Then `rebuild_lot_plans(lot_doc)` (§5) runs: per cloth, if the IPD is Approved
  → build the plan (HARD error on unreachable combos, so the user gets instant
  feedback while typing); if not approved → skip and set
  `plan_meta[cloth] = {"status": "pending-approval"}` (warn line in the island,
  never a block — I8).

The knitting program grid, its semantics, and its GRN tracking are untouched
(owner req 6): the program stays the user-edited WO driver; the requirement is a
NEW planning input alongside it.

---

## 4. Storage — `Lot Fabric Stage Ledger` (plan for all stages, receipts for new ones)

New child doctype **`Lot Fabric Stage Ledger`** (istable), Lot field
`lot_fabric_stage_ledger` Table hidden:

| field | type | notes |
|---|---|---|
| `cloth_item` | Link Item, reqd | |
| `process_name` | Link Process | blank = Procurement pseudo-row (bought greige, Case 5) |
| `side` | Select `Output` / `Input`, default Output | Input rows = the stage's demand on what FEEDS it: yarn kg (knitting), greige kg per dia (procurement) |
| `dia` | Link Item Attribute Value | |
| `colour` | Link Item Attribute Value | |
| `planned_weight` | Float 3, read_only | written ONLY by `build_fabric_plan` (I5) |
| `received_weight` | Float 3, read_only | written ONLY by fabric_tracking; **used only for extra stages in v1** — dyeing/compacting receipts stay in `Lot Fabric Colour Program` exactly as today |

Zero-migration split of responsibilities (the honest trade-off of this design):

| stage | plan lives in | received lives in |
|---|---|---|
| knitting | stage ledger (`planned_weight`, per dia [+ greige colour, Case 13]) + Input row for yarn | `Lot Fabric Program.received_weight` (unchanged) |
| dyeing | stage ledger | `Lot Fabric Colour Program.received_weight` (unchanged) |
| compacting | stage ledger | `Lot Fabric Colour Program.compacted_weight` (unchanged) |
| extra stages | stage ledger | stage ledger `received_weight` |
| procurement (bought greige) | stage ledger Input rows, process blank | — (available stays None, as today) |

One routing helper hides the seam from every consumer:

```python
# fabric_chain.py
def get_stage_received(lot_doc, cloth_item, stage) -> dict:
    """{(dia,)| (dia, colour): kg} received for `stage`, whichever table owns it.
    tab:knitting -> lot_fabric_programs.received_weight (dia,)
    tab:dyeing   -> lot_colour_programs.received_weight (dia, colour)
    tab:compacting -> lot_colour_programs.compacted_weight (dia, colour)
    stage_row    -> lot_fabric_stage_ledger.received_weight keyed by its attrs"""
```

Phase 6 (optional, later) consolidates the two legacy columns into stage-ledger
rows with a patch that simply calls `rebuild_fabric_tracking` per lot (GRNs are
the source of truth — the "migration" is a replay, not a data transform). Until
then there is nothing to migrate and nothing to break.

`validate_unique_fabric_cloths` extends its removal guard: a cloth with nonzero
`received_weight` in the stage ledger also cannot be removed; plan-only rows
(received 0) die with the cloth like today's zero-noise rows.

---

## 5. The common back-computation — `essdee_yrp/fabric_plan.py` (new module)

### 5.1 Signatures

```python
def build_fabric_plan(lot_doc, fabric_row, ipd_doc) -> dict:
    """The owner's 'common function'. Reads lot_fabric_requirements for this
    cloth, walks the chain LAST -> FIRST through the IPD Process Matrix docs
    (matrices are the ONLY quantity source — owner req 2), and rewrites this
    cloth's stage-ledger PLAN rows idempotently (received carried, planned
    replaced — same carry-forward pattern as save_fabric_program_details).
    Returns {"rows": [...], "yarn_kg": float, "warnings": [...]}.
    Raises FabricPlanError (frappe.ValidationError) listing ALL unreachable /
    ambiguous combos in one message (I6)."""

def rebuild_lot_plans(lot_doc):
    """Lot.before_validate (after requirement save): per fabric row, build if
    the IPD is Approved, else stamp plan_meta 'pending-approval'. One cloth's
    hard error blocks the LOT SAVE (fast feedback); per-cloth isolation only
    applies on the approval path below (Case 8)."""

@frappe.whitelist()
def build_plans_for_ipd(ipd_name) -> list[dict]:
    """Called by approve_ipd after the save. Finds non-closed Lots whose
    lot_fabric_details reference this IPD AND have requirement rows; runs
    build_fabric_plan per (lot, cloth) each in its own try/except (one bad lot
    never blocks approval — mirror of get_fabric_deliverable_context's
    per-fabric isolation). Returns [{lot, cloth, status, error?}]; approve_ipd
    msgprints the summary (red rows for failures)."""
```

### 5.2 The walk (mechanics, grounded in existing code)

```
demand = {frozenset({Dia: d, Colour: c}.items()): kg}   # from requirement rows
plan_rows, input_rows = [], []
for stage in reversed(chain):
    groups = index of the stage's matrix groups BY their OUTPUT-attr projection
             (matrix.get_combinations_grouped(); matrices are fully expanded,
              so projections are concrete — same trick _matrix_qty_rows uses)
    ambiguous = output projections appearing in >1 group  -> collect I2 errors
    next_demand = {}
    for combo, kg in demand.items():
        proj = {a: v for a, v in combo if a in stage_output_attributes}
        group = groups.get(frozenset(proj.items()))  -> missing = I1/Case-7 error
        plan_rows.append(stage, out_attrs=combo, planned=kg)      # side=Output
        for inp in group["input"]:
            in_kg = kg * (inp.qty / out.qty) * (1 + inp.wastage_pct/100)
            # identical scale rule to calculate_fabric_deliverables:412-416,
            # so wastage v2 is a data change (Case 9)
            carried = {a: v for a, v in combo if a not in stage_output_attributes}
            next_demand[frozenset({**inp.attrs, **carried}.items())] += in_kg
    demand = next_demand
# after the FIRST stage:
#   conversion first stage: demand is the attr-less yarn -> yarn_kg (one Input
#     row, process=knitting, dia/colour blank). The conversion stage's OUTPUT
#     plan rows per (dia[, greige colour]) are ALSO the suggested knitting
#     program (Case 13: colour split is advisory; program table stays dia-only).
#   swap first stage (bought greige): demand = procurement per (dia, colour) ->
#     Input rows with process_name blank (Case 5).
```

Attr carrying rule (the subtle line): attributes the stage's matrix does NOT
declare ride through unchanged (e.g. a chain with no colour swap carries the
requirement colour untouched down to knitting, where it becomes the greige
colour split — Case 13 falls out for free).

Rounding: `flt(kg, 3)` on write only; divisions happen on unrounded floats.

### 5.3 Error handling (I6 — data errors block, balances warn)

Collected across the WHOLE walk, thrown as ONE aggregated message:

- **Unreachable combo** (Case 7): "No chain path produces Colour=Purple ·
  Dia=D16 for cloth X — add mapping rows on IPD Y (stage Z) or correct the
  requirement." Includes mid-chain stranding (a pinned mapping can orphan a
  combo two stages up).
- **Non-invertible mapping** (Case 6 / I2): "D18 is produced by both D22→D18 and
  D20→D18 (Colour Red) on Compacting — pin the rows to different colours, chain
  them as two compacting steps, or split the cloths." Forward WO flow stays
  permissive (warn-only doctrine untouched); only the PLAN demands invertibility.
- Raised on Lot save (hard block) and surfaced per-lot on approval (approval
  itself succeeds; failing lots are listed red and stamped `status: "error"`).

### 5.4 Approval wiring (`essdee_yrp/ipd_ui.py`)

```python
# approve_ipd (line 105) — after doc.save():
if approval_type == "Approved" and is_cloth_ipd(doc):
    results = fabric_plan.build_plans_for_ipd(doc.name)
    -> msgprint summary ("Plans rebuilt for 3 lot(s); 1 failed: ...")
# the save ALREADY rebuilt matrices in the same transaction
# (hooks: on_update -> sync_fabric_process_matrices), so plans read fresh data.
```

Chain-edit freeze (Case 11 / I8), server-side in `validate_cloth_ipd`:

```python
if not doc.is_new() and doc.approval_status == "Approved":
    previous = frappe.get_doc("Item Production Detail", doc.name)  # DB copy
    if chain_fingerprint(doc) != chain_fingerprint(previous):
        doc.approval_status = "Not Approved"; doc.approved_by = None
        msgprint("Fabric chain changed — approval reverted; re-approve to rebuild lot plans.")
```

`revert_ipd_approval` (line 121): no data deletion — plan rows stay (they document
the last approved plan); `plan_meta.status` flips to `"stale"` lazily (§5.5).

### 5.5 Staleness stamp — `Lot.fabric_plan_meta` (JSON, hidden, server-owned)

`{cloth_item: {"ipd": name, "ipd_modified": ts, "built_on": ts, "status":
"ok"|"stale"|"pending-approval"|"error", "error": str?}}` — written by
build/rebuild paths. The popup and the island compare `ipd_modified` with the
live IPD and show "plan stale — re-approve IPD" (cheap and honest, Case 11).

---

## 6. WO popup integration

### 6.1 Server (`api/work_order.py`)

Resolution in `get_fabric_deliverable_context` AND `calculate_fabric_deliverables`
(both loops, same 3 lines):

```python
stage = get_chain_stage(ipd, wo.process_name)     # tabs + stage rows
row_kind = stage.kind if stage else None          # "knitting"|"dyeing"|"compacting"|"swap"
# kind for tab stages keeps TODAY'S strings -> Desk JS + /web modal untouched
# for them; stage rows get kind="swap".
```

- qty rows for `kind == "swap"`: `_matrix_qty_rows(ipd, process, "swap")` —
  works as-is; `_group_label` gains a final generic branch (identical format to
  dyeing/compacting: `pin: from → to` using the stage's attributes).
- `_add_planning_data` gains the generic branch (and this is the SPEC for what
  the three legacy branches converge to in phase 6, not a rewrite of them now):

```python
if kind == "swap":  # generic stage k
    prev = chain[stage.position - 1] if stage.position else None
    consumed = get_consumed(lot, wo.process_name, cloth, attrs=stage.in_attrs, exclude_wo=wo.name)
    ordered  = get_produced(lot, wo.process_name, cloth, attrs=stage.out_attrs, exclude_wo=wo.name)
    plan     = planned_weight by out-combo from the stage ledger
    for qr in qty_rows:
        available = (get_stage_received(lot, cloth, prev)[in_key] - consumed[in_key]) if prev else None
        prefill   = clamp(min(plan - ordered, available if available is not None else inf), >= 0) if plan else max(available or 0, 0)
        qr.update({plan, ordered, available, prefill, "prev_label": prev.process_name if prev else None})
```

  `get_consumed` / `get_produced` are one-line wrappers over the ALREADY-generic
  `_sum_by_attributes` (fabric_tracking.py:229) with the attribute tuple taken
  from the stage's matrix in/out attributes — the four named wrappers stay for
  the legacy branches.
- Plan enrichment on the legacy branches (additive, small): knitting keeps
  `prefill = program − ordered` (req 6 — the program remains the driver) but the
  context row gains `plan` per dia for display; dyeing/compacting prefill
  upgrades to `clamp(min(plan − ordered, available), ≥0)` WHEN a plan row exists,
  else exactly today's values. No plan → no behaviour change.
- `calculate_fabric_deliverables`: the swap branch is the same code path as
  dyeing/compacting already (matrix-group-keyed, `fc-` rows, idempotent rewrite
  — constraints verified it survives N stages unchanged). Only the kind
  resolution above changes. Knitting-only guards (colour validation, yarn
  override) stay keyed on `kind == "knitting"`.

### 6.2 Clients — Desk `work_order.js` + /web `FabricDeliverablesModal.vue`

Template rendering per shape, minimal additive branches (mirrored 1:1 in both):

- `planning_description` / `planningLine`: add the generic case — if
  `row.kind === "swap"`, render `Plan / Ordered / <prev_label> available /
  prefill` from server fields (`prev_label` makes the label stage-neutral:
  "Compacting available: 120 kg"). The three legacy branches untouched.
- `warn_balance_overshoot`: server now sends `overshoot_key` per qty row (the
  in-attrs tuple as a string) for swap rows; generic case groups by it. Legacy
  branches untouched.
- Row layout for swap = the compacting layout (label + qty input) — no colour
  columns, no yarn field (`kind === "knitting"` guards both already).
- Both files also render the `plan` figure and the "plan pending approval /
  stale" note when `plan_meta` says so (one line each).

### 6.3 Lot island (`FabricProgram.vue`)

- Grid 3: Final Requirement (editable, §3).
- Grid 4 **"Process plan & receipts"** (read-only): long-format rows —
  Process | Dia | Colour | Planned | Received — from the stage-ledger payload,
  `received` merged server-side by `fetch_fabric_program_details` from whichever
  table owns it (get_stage_received), plus a Yarn / Procurement summary line
  (Input rows). Long format = no per-stage column schema, so N stages render
  with zero grid changes (kills the fixed Dyed/Compacted column problem for new
  stages without touching the existing ledger grid, which stays as-is).

---

## 7. Tracking / ledger fit (`fabric_tracking.py`)

- `_apply_grn`: after the existing `TRACKED_KINDS` routing (untouched), add:

```python
stage = get_chain_stage(ipd, wo.process_name)
if stage and stage.source == "stage_row":
    attrs = [a for a in (DIA, COLOUR) if a in cloth_attributes]   # variant identity
    deltas = _grn_deltas_for_cloth(grn, fabric.cloth_item, attributes=tuple(attrs))
    _bump_stage_ledger(lot, fabric.cloth_item, stage.process_name, deltas, sign)
```

  `_grn_deltas_for_cloth` gets an `attributes` tuple param; the existing
  `with_colour` bool becomes a two-line wrapper (zero behaviour change).
  `_bump_stage_ledger` copies `_bump_program_rows`' exact pattern: per-lot
  `for_update` lock is already taken by `_apply_grn`; atomic
  `UPDATE ... SET received_weight = ROUND(IFNULL(...)+%s,3)` on existing rows
  keyed (cloth, process, dia, colour, side=Output); missing rows inserted with
  `planned_weight` untouched (0) — no receipt silently dropped. Rework GRNs are
  already excluded upstream (line 48); excess allowance / over-receipt unchanged.
- `rebuild_fabric_tracking`: additionally zero stage-ledger `received_weight`
  (NEVER `planned_weight` — plan is plan-function-owned, I5) before the replay;
  replay routes through the same `_apply_grn`. GRNs whose process no longer
  resolves to any chain stage are counted and returned as
  `{"unmatched": [{grn, process, kg}]}`; the island shows one warning line
  (Case 12's visible bucket, cheap v1 form).

---

## 8. Migration from the current three tabs + existing data

**There is none — that is the point of this design.**

- IPD: tabs, tables, fields untouched; matrices for tab stages byte-identical
  (§2.1 fallback proof). Existing IPDs need no re-save; new fixtures land via
  the normal `bench migrate` fixture sync (new doctypes + new Custom Fields only).
- Lot: `Lot Fabric Program` / `Lot Fabric Colour Program` keep their exact roles
  and writers. New tables start empty. No patch file required for v1.
- Approval: existing statuses keep meaning; the first chain edit after this
  ships triggers the fingerprint revert only if the IPD was already Approved and
  the chain actually changed (correct by definition).
- Phase 6 (deliberately later, independent): consolidate the colour-program
  columns into stage-ledger rows. Patch = per lot, `rebuild_fabric_tracking`
  into the new home + drop the two columns + FabricProgram.vue reads grid 4 only.
  Rollback-safe because GRNs remain the source of truth.

---

## 9. essdee_yrp vs base yrp

| piece | app |
|---|---|
| EVERYTHING in this design: fabric_chain.py, fabric_plan.py, 3 new child doctypes, Custom Fields, fabric_ipd/fabric_program/fabric_tracking/api.work_order/ipd_ui deltas, both JS clients, Vue island | **essdee_yrp** (fabric is the Essdee customization layer) |
| IPD Process Matrix doctype, `get_combinations_grouped`, ipd_engine, Process master (`is_item_conversion`, `value_change_attributes`), `approval_status` field | **base yrp — ZERO changes** |

The Process master already declares the reusable shape (2026-06-25 rule);
"Re-Compacting" is one new Process document with `value_change_attributes = [Dia]`
— a 30-second master entry, not a build.

---

## 10. Case walkthroughs (catalogue-grounded)

### 10.1 Re-compacting (Case 2 — the owner's driving example)

Setup: Process master "Re-Compacting" (swap Dia). IPD: tabs as today; More
Processes tab → stage row {process: Re-Compacting, position: After Compacting,
pin_wise_entry: 1}; widget seeds one card per colour (state_at pins = dyeing
to-colours), user enters D20→D18 rows. Save → fourth matrix generated, groups
`Red: D20 → D18`, … Validation warns if D20 never leaves compacting.
Lot: requirement (Red, D18, 100 kg). On IPD approve → plan: re-compact 100 in
(Red,D20); compact 100 (Red,D22→D20); dye 100 (Ecru→Red@D22); knit 100 D22 →
yarn 100/ratio. WO on Re-Compacting: popup rows from the matrix, available =
compacted_weight(Red,D20) − consumed, prefill clamped to plan. GRN → stage-ledger
received. **Zero code written by anyone.** Totality note: dias that skip
re-compacting need explicit `D18→D18`-style identity mapping rows (widget
pre-seeds them) — otherwise their requirement combos correctly fail Case-7
validation instead of silently skipping a physical step.

### 10.2 Topping / re-dyeing (Case 3)

Stage row {Topping, position: After Dyeing}, mapping Rose→Maroon per dia; untopped
colours entered as Rose→Rose identity rows. `state_at` gives compacting the
topping to-colours automatically (§2.2). Knit colour options still read the FIRST
colour-defining swap (the dyeing tab) — `_knit_colour_options` reroutes through
the chain but resolves identically here.

### 10.3 Bought greige (Case 5)

IPD with no knitting tab: chain = [dyeing, compacting, …]. `state_at(0, Dia)` =
IPD Dia mapping (today's fallback, unchanged). Plan's first-stage input demand
lands as Procurement Input rows (process blank) — the purchase figure per
(dia, greige colour) readable on the Lot island. First-stage `available` stays
None (today's behaviour). A no-chain cloth degenerates to requirement →
procurement copy (zero extra code: the walk loop runs zero times).

### 10.4 Unreachable requirement (Case 7)

Requirement (Purple, D16) with no producing path: `build_fabric_plan` collects
every stranded combo (including mid-chain stranding via pins) and throws ONE
aggregated message; Lot save blocks (data error, I6). At approval the same error
is reported per lot without blocking the approval (§5.1/§5.3).

### 10.5 Non-invertible merge (Case 6)

Compacting has D22→D18 and D20→D18 for the same colour: plan build hard-errors
naming both rows and the three fixes (pin differently / chain as two stages /
split cloths). Forward Calculate on the WO still accepts both groups (keys are
matrix-group-based, warn-only doctrine untouched).

### 10.6 Multiple greige colours (Case 13)

Requirement Black(from White) + Navy(from Ecru): the reverse dye step splits
knitting demand per (dia, greige colour); plan rows carry the split; the
user-edited program table stays dia-only; the knitting popup keeps its colour
columns and program−ordered prefill. Advisory split visible in grid 4.

### 10.7 Mid-lot chain edit (Case 12)

Adding re-compacting after knitting GRNs exist: matrices wipe+rebuild on save
(existing behaviour, popups staleness-proof); approval auto-reverts via
fingerprint; re-approve rebuilds plans; new stage's ledger rows appear via GRNs.
Removing a receipt-bearing stage: warn on save (extension of the removal guard),
ledger rows kept as historical fact; `rebuild_fabric_tracking` reports them in
the unmatched bucket.

### 10.8 No plan yet / plan after WOs (Cases 11, 16)

Unapproved IPD: WOs, popups, GRNs all work exactly as today; popup shows "plan
pending IPD approval". Requirement raised after WOs exist: plan build lands
mid-way; `ordered` nets out; prefills clamp ≥0; over-plan entry warns, never
blocks. Received/planned columns stay server-owned against client payloads
(existing guard pattern extended to the two new columns).

---

## 11. Invariants honoured (from cases.md)

I1 totality (approve-hard/save-warn) · I2 injectivity (plan/approve-hard,
save-warn — softened from the catalogue's save-hard to protect legacy saves) ·
I3 matrices-only math (plan + popup + builders) · I4 distinct master per
occurrence · I5 plan is Lot data, server-owned columns · I6 block data errors,
warn balances · I7 per-fabric-row resolution, garment IPDs excluded · I8 approval
gates plan only · I9 `state_at` as the single derivation primitive.

---

## 12. Build sequence (phases, each independently shippable + testable)

1. **Chain core + matrices** (~1 day): fabric_chain.py, 2 IPD child doctypes,
   Custom Fields, sync/validation deltas, IPD JS widgets + lock fix, fixture
   export. Test: re-compacting IPD generates a correct 4th matrix; existing IPD
   save produces byte-identical matrices (assert in a test by diffing matrix
   docs before/after).
2. **WO flow for extra stages** (~1 day): popup/calculate resolution via
   `get_chain_stage`, generic swap branch server+Desk+/web, `Lot Fabric Stage
   Ledger` doctype, GRN tracking + rebuild. Test: full WO→DC→GRN drive on a
   re-compacting stage (active UI driving per bench rule).
3. **Requirement entry** (~0.5 day): `Lot Fabric Requirement`, island grid 3,
   save/validation. Test: entry, duplicates, invalid IAVs, final-state check.
4. **Plan** (~1–1.5 days): fabric_plan.py, approve/revert wiring, fingerprint
   revert, plan_meta, island grid 4, popup plan/prefill enrichment. Test: Case 6
   walkthrough numbers end-to-end; unreachable + ambiguous error texts.
5. **Hardening** (~0.5 day): rebuild unmatched bucket, removal guards, code
   review (>50 lines rule), docs/design spec update in
   `apps/essdee_yrp/docs/design/`.
6. **Later, optional**: colour-program → stage-ledger consolidation (replay
   patch); in-chain identity stages; free reordering; wastage %; /web Lot island.

---

## 13. Trade-offs accepted (say them out loud)

1. **Two ledger homes** for received kgs until phase 6 — hidden behind
   `get_stage_received`; bought with zero migration.
2. **Tabs ≠ rows seam**: the first three stages are edited in tabs, later ones
   in the stage table. One normalizer removes the seam from all logic, but the
   UI shows two idioms until a (later) optional tab-to-row consolidation.
3. **Anchored positions** instead of free ordering — covers every named case
   (re-compacting, topping, second compacting) with a dropdown; full reorder
   deferred.
4. **Swap-only extra stages (Dia/Colour)** in v1 — matches every process the
   owner named; conversion/identity-in-chain deferred with a clear extension
   path (the chain list and matrix builders are already shape-keyed).
5. **Injectivity/totality soft at save, hard at plan** — protects existing IPD
   saves; the catalogue's stricter save-time stance can be tightened later once
   data is clean.
