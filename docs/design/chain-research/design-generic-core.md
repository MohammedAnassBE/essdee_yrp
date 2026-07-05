# Commonized Fabric Chain — Design Proposal (Clean-Generic-Core angle)

Bench: /home/anas/frappe-16 · App: essdee_yrp (on base yrp) · Date: 2026-07-04
Inputs: constraints.md + cases.md (same folder), current code as of today.

**Design stance.** An ordered `IPD Fabric Step` child table on the IPD **is** the
model. One row = one position in the physical chain, pointing at a Process
master whose SHAPE (conversion / swap-on-attribute / identity) is already
declared there. All value mappings for all steps live in ONE generic mapping
table. The current three tabs become three pre-seeded rows. Adding
"re-compacting" = one new Process master (30 seconds) + one appended step row +
its mapping rows. Zero code, zero fixtures, zero new doctypes per new process.

---

## 0. The one primitive everything hangs off

Every hardcode found in constraints.md §10 reduces to one missing function:
**"what (Dia, Colour) combos flow into position k of the chain."** We build
that once (`fabric_chain.combos_entering`) and derive from it:

- wildcard pin expansion per step (replaces `derive_passthrough_values`),
- in-chain identity matrices (replaces the UNION hack in `_identity_qty_rows`),
- totality/injectivity validation (invariants I1/I2),
- the final-state set that validates the Lot requirement (Case 7/15),
- pin seeding for the swap widgets (replaces IPD JS 1159–1166),
- program dia list / target colours (`_ipd_dias`, `_ipd_target_colours`),
- greige colour options (`_knit_colour_options` → "next swap's from-values").

State representation (v1, two attributes): a list of attr-dicts, where an
attribute can be **absent = undetermined** (e.g. Colour before the first colour
swap — the value is chosen at the knitting WO, exactly today's semantics).

```
combos_entering(ipd, 0)          # before step 0
  conversion first step  -> not meaningful (input is yarn); state AFTER step 0
                            = [{Dia: d} for each conversion output row]
  swap first step (bought greige)
                         -> [{Dia: d} for d in IPD Dia mapping]  (Colour undetermined)
step k swap on attr A, rows (pin p, from f, to t):
  a combo C matches a row iff (C[pin_attr] == p or p is blank-expanded)
  and (C[A] == f, or C[A] undetermined — the row ASSIGNS f as the incoming value)
  -> output combo = C with [pin_attr]=p, [A]=t
step k identity: state unchanged
```

This is ~60 lines of pure-python and is THE thing to unit-test hardest.

---

## 1. Data model — IPD side (all in essdee_yrp)

### 1.1 New child doctypes

`essdee_yrp/essdee_yrp/doctype/ipd_fabric_step/` — **IPD Fabric Step**

| field | type | notes |
|---|---|---|
| `process` | Link Process, reqd, in_list_view | distinct per IPD (I4); WO→step key |
| `shape_label` | Data, read_only, in_list_view | display only, stamped server-side from `get_process_shape()`: "Conversion (item change)" / "Swap: Colour" / "Swap: Dia" |
| `input_item` | Link Item | conversion steps only (was `yarn_item`) |
| `output_per_input` | Float, precision 3 | conversion only (was `cloth_per_kg_yarn`), label "Output kg per 1 kg input" |
| `pin_wise_entry` | Check | replaces `dia_wise_colour_change` / `colour_wise_dia_change`; per-step widget mode |

Row order (`idx`) = chain order. No "kind" string anywhere — the shape is read
from the Process master at runtime (`get_process_shape`, unchanged).

`essdee_yrp/essdee_yrp/doctype/ipd_fabric_step_mapping/` — **IPD Fabric Step Mapping**

| field | type | notes |
|---|---|---|
| `process` | Link Process, reqd | which step the row belongs to (stable across step reorder; valid key because I4 forces distinct masters) |
| `pin_attribute` | Link Item Attribute, hidden | **server-stamped**, never typed: "the other chain attribute" of the step's swap attr; kept explicit so rows are self-describing and a 3rd attribute later is a data change |
| `pin_value` | Link Item Attribute Value | optional; blank = wildcard (expanded at matrix build, exactly today) |
| `from_value` | Link Item Attribute Value | blank on conversion rows |
| `to_value` | Link Item Attribute Value, reqd | conversion rows: the output value (dia); swap rows: the to-value |

One table holds every step's rows. The three per-tab child doctypes
(`IPD Knitting Dia Detail`, `IPD Dyeing Colour Detail`,
`IPD Compacting Dia Detail`) die after migration.

Frappe can't nest child tables, so mappings reference their step by `process` —
safe because `validate_cloth_ipd` (generalized) enforces one Process master per
step per IPD (I4). This is also exactly why **re-compacting must be its own
Process master**: matrices, WO resolution, and ledger rows all key on
`process_name`.

### 1.2 Custom Fields on Item Production Detail (fixtures/custom_field.json)

Keep: `is_cloth_item`. Add:

| fieldname | type | notes |
|---|---|---|
| `fabric_chain_tab` | Tab Break, depends_on `is_cloth_item` | ONE tab replaces three |
| `fabric_steps` | Table → IPD Fabric Step | visible grid, drag-order = chain order |
| `fabric_chain_html` | HTML | mount point for per-step editor widgets |
| `fabric_step_mappings` | Table → IPD Fabric Step Mapping, hidden | written by the widgets; hidden grid keeps the data in the doc (same pattern as today's swap tables) |

Remove (in the same release, after the migration patch): the 3 tab breaks,
`knitting_process`, `yarn_item`, `knitting_dia_details`, `cloth_per_kg_yarn`,
`dyeing_process`, `dia_wise_colour_change`, `dyeing_colour_matrix_html`,
`dyeing_colour_details`, `compacting_process`, `colour_wise_dia_change`,
`compacting_dia_matrix_html`, `compacting_dia_details`.

`Process.is_cloth_process`, `Process.is_item_conversion`,
`Process.value_change_attributes` — unchanged (base yrp already generic).

### 1.3 New chain module — `essdee_yrp/essdee_yrp/fabric_chain.py` (NEW)

The single home of chain semantics. Junior-readable, no frappe writes.

```python
CHAIN_ATTRIBUTES = (FABRIC_DIA_ATTRIBUTE, FABRIC_COLOUR_ATTRIBUTE)  # v1 pair

def get_chain_steps(ipd_doc) -> list[frappe._dict]
    # ordered; each: position, process_name, shape ("conversion"|"swap"|"identity"),
    # swap_attribute, pin_attribute, input_item, output_per_input,
    # pin_wise_entry, mappings (that step's rows from fabric_step_mappings)

def get_chain_step(ipd_doc, process_name) -> frappe._dict | None
    # replaces get_fabric_process_kind; None => try off-chain identity

def combos_entering(ipd_doc, position) -> list[dict]   # state BEFORE step
def combos_after(ipd_doc, position) -> list[dict]      # state AFTER step
def final_combos(ipd_doc) -> list[dict]                # requirement validation set
def values_entering(ipd_doc, position, attribute) -> list[str]
    # projection; replaces derive_passthrough_values / _ipd_dias / _ipd_target_colours

def free_attribute(ipd_doc, step) -> str | None
    # conversion step whose output combos miss a cloth attribute (Colour today)
def free_attribute_options(ipd_doc, step) -> list[str]
    # from-values of the NEXT step that swaps the free attribute
    # (replaces _knit_colour_options); fallback: IPD mapping, then all IAVs

def validate_chain(ipd_doc, strict=False) -> list[str]
    # I1 totality + I2 injectivity + reachability of every mapping row's
    # (pin, from) against combos_entering. strict=False -> return warnings
    # (msgprinted on save); strict=True -> frappe.throw (approval time).

def chain_fingerprint(ipd_doc) -> str
    # sha1 over ordered (process, input_item, ratio, mapping rows) — used to
    # auto-revert approval on chain edits (§6) and to stamp plan staleness (§7)

def get_fabric_chain_ui(ipd_doc) -> dict
    # onload payload for the Desk widgets: per step -> shape, labels,
    # pin_options (= values_entering), from/to value queries, locked flag
```

Constants `FABRIC_DIA_ATTRIBUTE` / `FABRIC_COLOUR_ATTRIBUTE` move here (fabric_ipd
re-exports for compatibility). They are the ONLY remaining site-level
assumption; a third attribute is a future data-change on `pin_attribute` +
this tuple, and nothing downstream hardcodes the pair anymore.

---

## 2. Matrix generation — `fabric_ipd.py` rewrite

`sync_fabric_process_matrices(doc, method=None)` keeps its name, hook position
(on_update), wipe-and-rebuild idempotency, and the matrix DOC format
(untouched base doctype). New body:

```python
def sync_fabric_process_matrices(doc, method=None):
    if not is_cloth_ipd(doc):
        return
    uom = frappe.db.get_value("Item", doc.item, "default_unit_of_measure")
    _delete_all_matrices(doc.name)
    for step in get_chain_steps(doc):
        builder = {
            "conversion": _build_conversion_matrix,
            "swap":       _build_swap_matrix,
            "identity":   _build_identity_matrix,
        }[step.shape]
        matrix = builder(doc, step, uom)
        if matrix:
            matrix.insert(ignore_permissions=True)
```

- `_build_conversion_matrix(doc, step, uom)` = today's `_build_knitting_matrix`
  with `rows = [m for m in step.mappings if not m.from_value]`,
  `input_item = step.input_item`, `output_qty = step.output_per_input or 1`,
  output attribute = the conversion output attribute (Dia, v1 constant).
- `_build_swap_matrix(doc, step, uom)` = today's `_build_value_swap_matrix`
  (already fully parametrised) called with `attribute=step.swap_attribute`,
  `pin=step.pin_attribute`, `rows=step.mappings`, and — the key change —
  wildcard pin values from `values_entering(doc, step.position, step.pin_attribute)`
  instead of the hardcoded knit-dias/dye-colours. `_expand_wildcard_rows`
  gains a `pin_values` parameter and loses its internal derivation.
- `_build_identity_matrix(doc, step, uom)` (NEW, Case 4): one group per combo
  in `combos_entering(doc, step.position)`, input attrs = output attrs,
  qty 1:1. Honors owner requirement 2 — even washing flows through a matrix.
  **v1 restriction:** an in-chain identity step is only legal at a position
  where every cloth attribute is determined (validation error otherwise,
  message: "move it after the first Colour step or declare it in IPD
  Processes instead") — keeps variant creation unambiguous without inventing
  a free-attribute picker for identity steps.

**This is requirement 5 ("combination") mechanically:** pins are stamped on
BOTH sides of every group (existing behaviour, lines 242–246), and pin values
now come from the *actual upstream state*, so an 18-dia greige can only enter
the dyeing groups pinned to Dia 18, whose outputs only enter compacting groups
whose from-dia is 18. Stages connect per dia/colour by construction, for any N.

`ensure_cloth_item_attributes` becomes: add `step.swap_attribute` +
`step.pin_attribute` (when any mapping pins) + the conversion output attribute
for every chain step — same before_validate hook.

`get_identity_process_row` keeps today's semantics for **off-chain** identity
(`ipd_processes` rows): union combos, no matrix, no tracking. New validation:
a process may appear in `fabric_steps` OR `ipd_processes`, never both
(Case 4 heuristic for users: *in the chain iff you GRN it per lot*).

No changes to base yrp: IPD Process Matrix doctype, `get_combinations_grouped`,
`ipd_engine.get_process_io`, Process master — all verified untouched-safe.

---

## 3. Lot data model — requirement + generic step ledger

### 3.1 New child doctypes (essdee_yrp, fields added directly to lot.json)

`Lot Fabric Requirement` (requirement 3b — user-entered, NEW):

| field | type | notes |
|---|---|---|
| `cloth_item` | Link Item, reqd | |
| `dia` | Link Item Attribute Value, reqd | |
| `colour` | Link Item Attribute Value | blank when the cloth has no Colour attribute |
| `weight` | Float, precision 3 | kg of FINISHED cloth |

Parent field `lot_fabric_requirements` (hidden Table on Lot), edited via the
FabricProgram island. Validation on save (in `fabric_program.py`): attribute
membership (`_validate_attribute_value`, reused), no duplicate (cloth, dia,
colour), no negative weight, zero rows dropped, **combo ∈ `final_combos(ipd)`**
(Case 7 — hard block, aggregated message).

`Lot Fabric Step Ledger` (replaces `Lot Fabric Colour Program`):

| field | type | notes |
|---|---|---|
| `cloth_item` | Link Item, reqd | |
| `process` | Link Process | **blank = "Chain Input"** — the procurement/yarn pseudo-step (Case 5) |
| `dia` | Link Item Attribute Value | optional (yarn row has neither) |
| `colour` | Link Item Attribute Value | optional |
| `planned_weight` | Float, read_only | written ONLY by `build_fabric_plan` |
| `received_weight` | Float, read_only | written ONLY by `fabric_tracking` (GRNs) |

Parent field `lot_fabric_step_ledger` (hidden Table). One long-format table
serves plan AND actuals for N steps — re-compacting lands rows with
`process = "Re-Compacting"`; nothing to add anywhere. Semantics: each row is
the planned/received **output** of that step for that variant; the blank-process
row is the planned input of step 0 (yarn kg, or greige kg per dia/colour for
bought-greige chains).

`Lot Fabric Program` (knitting program) — **unchanged** (requirement 6). It
stays user-edited, dia-keyed, and the knitting-WO driver. `received_weight`
stays on it as the program grid's mirror (also written into the ledger row for
uniform availability math — one GRN pass writes both, `rebuild_fabric_tracking`
zeroes both).

`Lot Fabric Detail` gains two hidden read-only fields for plan staleness:
`plan_built_on` (Datetime) and `plan_fingerprint` (Data — `chain_fingerprint`
at build time). Popup and island show "plan stale — re-approve IPD" when the
IPD's current fingerprint differs or `approval_status != "Approved"`.

### 3.2 `fabric_program.py` changes

- `fetch_fabric_program_details`: entry gains
  `requirement: [...]`, `steps: [{process, label}]` (ordered, from the chain),
  `ledger: [{process, dia, colour, planned_weight, received_weight}]`
  (zero-noise rows filtered as today), `plan_stale: bool`;
  `dias`/`colours`/`greige_colour` now come from `fabric_chain` helpers.
- `save_fabric_program_details`: also parses the requirement grid out of the
  island JSON (same transient `fabric_program_details` field), validates as
  §3.1, resurrection rule for rows the plan/receipts depend on mirrors the
  program-row rule. Then: if the IPD is Approved → `rebuild_lot_plans` for the
  touched cloths; else msgprint "requirement saved — plan pending IPD approval".
- `_warn_program_below_ordered` generalizes to first-conversion-step lookup via
  `get_chain_steps`, and gains two more warn-only checks (Case 16):
  "program below plan" and "plan below ordered".

---

## 4. The common back-computation — `essdee_yrp/essdee_yrp/fabric_plan.py` (NEW)

Requirement 4's "common function". ~150 lines, matrices are the ONLY math
source (requirement 2 / I3) — the chain rows give ordering and step→matrix
lookup, never quantities.

```python
def build_fabric_plan(lot_doc, fabric_row) -> dict
    """Back-compute per-step planned outputs from the Lot's requirement.

    Returns {"steps": {process_name: {combo_key: kg}},
             "chain_input": {combo_key: kg},        # yarn / greige procurement
             "program_suggestion": {dia: kg}}       # conversion step outputs
    Raises frappe.ValidationError listing ALL unreachable combos at once."""

def rebuild_lot_plans(lot_doc, cloth_items=None)     # loops fabric rows, per-cloth try/except (Case 8)
def rebuild_plans_for_ipd(ipd_name)                  # called from approve_ipd (§6)
def _write_plan_rows(lot_doc, cloth_item, plan)      # delete-and-rewrite planned_weight only
def _seed_knitting_program(lot_doc, cloth_item, plan)
```

Algorithm (Case 6), walking `get_chain_steps(ipd)` LAST → FIRST:

1. `demand = {frozenset(combo.items()): kg}` from the requirement rows
   (validated ⊆ `final_combos` — Case 7 already blocked bad combos at entry;
   re-checked here because IPD edits can strand old requirements).
2. Per step: load its matrix, index groups by `frozenset(out_attrs.items())`.
   Injectivity (I2, enforced at approval, §6) guarantees the index is unique.
   For each demanded combo: exact-match the group; record
   `plan[step][combo] = out_kg`; accumulate upstream demand per input combo:
   `in_kg += out_kg * in_qty/out_qty * (1 + wastage_pct/100)` — the same scale
   rule as `calculate_fabric_deliverables`, so v2 wastage is a data change.
   Unmatched combos are collected (not thrown one-by-one).
3. Conversion step: inputs are attr-less → `chain_input` = one yarn figure
   (division happens through the matrix quantities, NEVER `output_per_input`
   read directly). Its OUTPUT demand per dia = `program_suggestion` — the
   owner's "how much greige in knitting, in what dia".
   Swap-first chains (bought greige, Case 5): after the loop, the remaining
   demand IS `chain_input` — greige procurement per (dia, greige-colour).
4. Any collected unreachable combos → one aggregated `frappe.throw`:
   "No chain path produces Dia 16 · Purple for <cloth> — add mapping rows on
   IPD <name> or correct the requirement." (I6: data error ⇒ hard block.)
5. `_write_plan_rows`: zero all `planned_weight` for the cloth, write plan rows
   (create missing rows at received 0 — same insert pattern as
   `_bump_program_rows`), stamp `plan_built_on` + `plan_fingerprint` on the
   fabric row. Received values are never touched.
6. `_seed_knitting_program` (Case 10 rule): a program row is auto-filled/
   refreshed ONLY when its weight is 0 or equals the previous plan's suggestion
   (i.e. the user never touched it); otherwise warn-only drift msgprint.
   The program remains the WO driver (requirement 6) — the plan never
   overwrites a human decision silently.

Free-attribute note (Case 13): when the demand entering the conversion step
carries a colour (multi-greige chains), the knit group matches on its OUT
attrs as a SUBSET (dia) and the plan row keeps the full (dia, colour) key —
the greige-colour split is advisory data the popup shows; program stays
dia-total; knit RECEIVED stays dia-keyed. Plan rows and received rows may
therefore differ in key granularity; the ledger view groups them.

---

## 5. WO popup — shape-driven, plan-aware

### 5.1 Server (`api/work_order.py`)

`get_fabric_deliverable_context` — per fabric row:
`step = get_chain_step(ipd, wo.process_name)`; fallback off-chain identity as
today. The row payload becomes stage-neutral:

```python
{
  "fabric_row": ..., "cloth_item": ..., "treated_item": ..., "production_detail": ...,
  "step": {"position": k, "process_name": ..., "shape": "conversion|swap|identity",
           "is_first": k == 0, "free_attribute": "Colour" | None},
  "input_item": step.input_item,            # was yarn_item
  "ratio": step.output_per_input or 1,      # conversion only
  "free_attr_options": free_attribute_options(ipd, step),   # was colour_options
  "has_colour": ..., "colour_mapping": ...,  # unchanged mechanics
  "qty_rows": [...],
}
```

`_matrix_qty_rows` unchanged except labels: `_group_label` collapses to one
format `[pins]: from → to` (conversion: just the out value) — kind param dies.
Each qty row additionally carries two server-computed strings so BOTH clients
stop branching:

- `planning_label` — e.g. "Program 500 · Ordered 200 · Balance 300" /
  "Plan 480 · Available from Dyeing 350" (client renders verbatim),
- `overshoot_key` — the row's input combo projected onto the previous step's
  tracked attributes; the client groups rows by it for the overshoot warning
  (replaces the 3-branch `warn_balance_overshoot` in Desk JS and /web).

`_add_planning_data(qty_rows, step, lot, wo, fabric, ipd)` — ONE body:

```
plan      = ledger planned_weight for the row's out-attrs (this step's process)
ordered   = get_wo_totals(..., side="receivables", attrs=tracked_out_attrs)
available =
    step 0, conversion : program.weight − ordered   (a.k.a. balance — unchanged)
    step 0, swap       : None                        (bought greige — unchanged)
    step k > 0         : ledger_received(prev step process, in-attrs projected
                         to prev step's tracked attrs)
                         − get_wo_totals(this process, side="deliverables",
                           attrs=same key)           (today's dye/compact rule, once)
prefill   =
    step 0 conversion  : max(program − ordered, 0)               (unchanged, req 6)
    plan exists        : clamp(min(plan − ordered, available), ≥ 0)
    no plan, input combo shared by 2+ groups : 0     (ambiguous split — today's dyeing)
    no plan, unique input combo              : max(available, 0)  (today's compacting)
```

"Tracked attrs" of a step = its matrix's `output_attributes` list — the same
rule tracking uses (§6), so popup math and ledger keys can never diverge.

`calculate_fabric_deliverables`: `kind` branches become shape branches.
Knitting-specific code becomes "conversion step with a free attribute":
`_require_ipd_yarn` → `_require_step_input_item(step)`; greige-colour
validation reads `free_attribute_options`; the free value is stamped into
`out_attrs` exactly as today; yarn override stays gated on "exactly one
aggregated input". **Payload contract, matrix-group keys, `fc-` row indexing,
and the idempotent rewrite are unchanged** — already-calculated WOs survive.

### 5.2 Clients

- `public/js/work_order.js`: delete `planning_description` + 3-branch
  overshoot; render `planning_label`; group by `overshoot_key`; colour
  picker/columns + yarn field gated on `row.step.free_attribute` /
  `row.step.shape === "conversion"` instead of `kind === "knitting"`.
  `MAX_COLOUR_COLUMNS` stays.
- `frontend/src/views/dynamic/FabricDeliverablesModal.vue`: identical 1:1
  mirror of the above (twin file, twin diff). `DocDetail.vue` untouched.

---

## 6. Tracking + validation + approval wiring

### 6.1 `fabric_tracking.py`

- `TRACKED_KINDS` dies. `_apply_grn`: `step = get_chain_step(ipd, wo.process_name)`;
  skip if None. `tracked_attrs = _tracked_attrs(step)` (matrix output_attributes,
  cached). `deltas = _grn_deltas_for_cloth(grn, cloth, tracked_attrs)`
  (parameterised, as is `_variant_attribute_map(variants, item, attributes)`).
  Bump `Lot Fabric Step Ledger` (cloth, process, attrs) `received_weight` —
  same atomic-increment SQL + create-at-zero pattern as `_bump_program_rows`.
  When `step.position == 0 and step.shape == "conversion"`: ALSO bump
  `Lot Fabric Program.received_weight` (the program-grid mirror).
- The four named wrappers (`get_produced_by_dia`, …) are replaced by ONE
  `get_wo_totals(lot, process_name, cloth_item, side, attributes, exclude_wo=None)`
  — `_sum_by_attributes` is already generic; `side="deliverables"` implies
  `calculated_only=True`. New `get_ledger_received(lot, cloth_item,
  process_name, attributes) -> {key: kg}` reads the ledger for availability.
- `rebuild_fabric_tracking(lot)`: zero program received + ALL ledger
  `received_weight` (planned untouched), replay GRNs; GRNs whose process no
  longer resolves to any chain step are summed into an **unmatched bucket**
  returned + msgprinted ("<n> kg on <process> not in any chain — receipts kept
  out of the ledger"), never silently dropped (Case 12).
- Rework-GRN exclusion, per-lot `for_update` locks, server-owned columns:
  all unchanged (standing rules). Guards extended so client payloads can't
  write `planned_weight` either (I5/Case 16).

### 6.2 `ipd_validations.validate_cloth_ipd` (rewrite of the fabric half)

1. Distinct Process master across `fabric_steps` rows (I4) — generalizes line 63.
2. Per-step shape sanity: conversion ⇒ `input_item` + `output_per_input > 0`
   + ≥1 output row; swap ⇒ Process declares the attribute
   (`validate_fabric_process_shapes` per step, still warn-only for shape
   metadata); mapping rows must reference a `fabric_steps` process.
3. `validate_swap_rows` per swap step (already field-generic: pin/from/to
   completeness + (pin, from) dedupe).
4. A process may not be in both `fabric_steps` and `ipd_processes`.
5. Identity `process_item` ∈ {doc.item} ∪ {conversion steps' input_item}.
6. In-chain identity position rule (§2). UOM sanity warn (Case 15).
7. `validate_chain(doc, strict=False)` — totality (I1: every entering combo
   matches a mapping row; pass-through must be an explicit from=to row, which
   the widgets pre-seed) and injectivity (I2: duplicate to-values per (step,
   pin) — the thing that makes the plan reversible) as **warnings on save**
   (forward flow stays permissive, matching today's legal White→Black +
   Ecru→Black), **hard errors at approval** (strict=True). Non-invertible
   flows get the Case 6 message suggesting pinning, chain-lengthening, or
   splitting the cloth into two IPDs.
8. **Auto-un-approve on chain edit**: if `approval_status == "Approved"` and
   `chain_fingerprint(doc) != fingerprint(db version)` → reset to
   "Not Approved" + msgprint "chain changed — re-approve to rebuild lot plans"
   (closes the audit gap: today fabric tables are editable after approval; the
   Desk lock in item_production_detail.js also adds `fabric_steps` +
   `fabric_step_mappings` + widget `locked` flags).

### 6.3 Approval hook (`ipd_ui.py`)

```python
def approve_ipd(doc_name, approval_type="Approved"):
    ...existing role check...
    doc.approval_status = approval_type; doc.approved_by = ...
    doc.save(...)            # rebuilds matrices in this save (hooks unchanged)
    if approval_type == "Approved" and is_cloth_ipd(doc):
        from essdee_yrp.fabric_plan import rebuild_plans_for_ipd
        rebuild_plans_for_ipd(doc.name)   # AFTER save => fresh matrices
    return {"status": "success"}
```

`rebuild_plans_for_ipd` finds non-closed Lots via `Lot Fabric Detail`
(`production_detail = ipd`), builds each lot's plan; `validate_chain(strict=True)`
runs first, and any lot whose requirement is now unreachable aborts the
approval with the aggregated lot list (I6 — approving a chain that strands
live requirements is a data error). "Cutting Approved" is hidden for cloth
IPDs (garment concept). `revert_ipd_approval`: plans are KEPT (they document
the last approved state); staleness shows via the fingerprint (§3.1).
Approval gates **plan generation only** — WOs, popups, GRNs, program entry
never blocked (I8); an unapproved IPD's popup just shows no plan figures plus
a one-line "plan pending IPD approval" note.

---

## 7. Desk + /web UI

- **IPD form** (`item_production_detail.js`): `FABRIC_SWAP_WIDGETS` dies. On
  refresh, read `doc.__onload.fabric_chain_ui` (built by
  `get_fabric_chain_ui`, attached in an onload hook) and mount one editor per
  step into `fabric_chain_html`: swap steps reuse **`FabricSwapDetail.vue`
  as-is** (it is already config-driven — pin/value labels, options, `locked`
  all passed in); conversion steps get a small sibling widget
  `FabricConversionDetail.vue` (input item + ratio + dia checklist —
  checkbox-mode against `values_entering` fallback/mapping values, preserving
  fast entry); identity steps render a static "1:1 pass-through" card.
  Write-back targets `fabric_step_mappings` rows filtered by the step's
  process. Pin seeds = server-sent `pin_options` (no client chain-walking).
  Approved lock covers the whole tab (gap fixed).
- **Lot island** (`FabricProgram.vue`): per cloth, three blocks —
  (1) NEW Requirement grid (dia | colour | kg, editable; colour column hidden
  when `!has_colour`); (2) Knitting Program grid unchanged + a read-only
  "Plan" hint column from `program_suggestion`; (3) Ledger grid goes
  long-format: Step | Dia | Colour | Planned | Received, rows grouped by the
  server-sent ordered `steps` list — N steps render naturally (re-compacting
  is just more rows). Dashed-border summary styling per the standing rule.
- **/web**: `FabricDeliverablesModal.vue` mirrors §5.2. The IPD /web view is
  meta-driven with an empty field config, so the new tab/table appear
  automatically; a rich /web chain editor is explicitly out of scope v1
  (none exists today to regress).

---

## 8. Migration from the three tabs

One release, three patches (`essdee_yrp/patches/v1_x/`), all reading old data
via raw table SQL (old child tables persist in DB even after doctype removal):

1. **`create_fabric_chain_schema`** — implicit via migrate (new doctypes +
   updated fixtures). Old Custom Fields removed from fixtures in this same
   release; their columns/tables linger harmlessly until cleanup.
2. **`migrate_fabric_tabs_to_chain`** — per cloth IPD (SQL over
   `tabItem Production Detail` old columns):
   append `fabric_steps` in fixed order [knitting_process?, dyeing_process?,
   compacting_process?]; conversion step gets `input_item = yarn_item`,
   `output_per_input = cloth_per_kg_yarn`; `pin_wise_entry` from
   `dia_wise_colour_change` / `colour_wise_dia_change`;
   `tabIPD Knitting Dia Detail` rows → mappings (process=knit, to_value=dia),
   `tabIPD Dyeing Colour Detail` → (process=dye, pin_attribute=Dia,
   pin_value=dia, from/to colour), `tabIPD Compacting Dia Detail` →
   (process=compact, pin_attribute=Colour, pin_value=colour, from/to dia).
   Then `doc.save()` per IPD → matrices regenerate through the new builders.
   **Acceptance gate: regenerated matrices are combination-identical to the
   pre-migration ones** (scripted diff over IPD Process Matrix children,
   ignoring group order/name; run on yrp3.site clone first). Approval status
   preserved; fingerprint stamped so the save doesn't un-approve.
3. **`migrate_colour_program_to_step_ledger`** — per Lot: each
   `tabLot Fabric Colour Program` row emits up to two ledger rows:
   (dye-process, dia, colour, received=received_weight) and
   (compact-process, dia, colour, received=compacted_weight); knitting mirror
   rows from `Lot Fabric Program.received_weight` → (knit-process, dia).
   Lots whose IPD had no dyeing/compacting process log to the patch output.
   Verification: `rebuild_fabric_tracking` on sampled lots must reproduce the
   migrated numbers exactly. Old table left in place read-only for one
   release, then dropped with the three IPD child doctypes.

Code ships fully cut over — no dual-read shims; the patches are the shim.

---

## 9. essdee_yrp vs base yrp

| Piece | App | Why |
|---|---|---|
| IPD Fabric Step / Step Mapping, Lot Fabric Requirement / Step Ledger, all Custom Fields | essdee_yrp | fabric = Essdee customization |
| fabric_chain.py, fabric_plan.py, rewritten fabric_ipd/tracking/program/api | essdee_yrp | same |
| All Desk JS + Vue widgets + /web modal | essdee_yrp (+ its frontend) | same |
| Process shape fields, IPD Process Matrix, ipd_engine, approval_status field | base yrp — **zero changes** | already the generic machinery |

Nothing moves down into yrp in v1. If a second industry app ever needs chains,
`fabric_chain.py`'s state walker is the candidate to promote — flagged in the
module docstring, not done now (no over-engineering).

---

## 10. Case walkthroughs (grounding)

- **Case 2 — Re-compacting (the driving example).** User creates Process
  "Re-Compacting" (Value Change Attributes = [Dia]) once, appends step row 4
  on the IPD, widget opens a Dia-swap editor whose pin options =
  `values_entering(ipd, 4, "Colour")` (post-dyeing colours) and whose from-dia
  options = post-compacting dias (D20 after D22→D20). Save → 4th matrix.
  Totality warns until every incoming dia has a row (pre-seeded from=to
  identity rows for untouched dias). WO on "Re-Compacting": popup rows from
  its matrix; available = ledger received of the FIRST compacting minus
  re-compacting consumption; GRNs land ledger rows process="Re-Compacting";
  plan back-computes through it like any step. Zero code was written.
- **Case 4 — Washing in-chain.** Step row with an identity-shape Process →
  auto 1:1 matrix per incoming combo (requirement 2 holds), ledger-tracked,
  gates compacting availability. Off-chain washing (not GRN'd) stays in
  `ipd_processes` untouched. Position rule (§2) rejects washing before dyeing
  on coloured cloth with a clear message.
- **Case 5 — Bought greige.** Chain [dye, compact]: initial state = IPD Dia
  mapping values; step-0 availability = None (today's behaviour); the plan's
  leftover demand becomes blank-process "Chain Input" ledger rows = the
  procurement figure per (dia, greige colour) the purchase team reads off the
  Lot. A no-chain cloth degenerates to requirement → chain-input copy.
- **Case 6/7 — Back-compute + unreachable combos.** As §4. Genuinely
  non-invertible flows (D22 and D20 both knitted, both ending D18) fail
  approval-time injectivity with the suggestion text; unreachable requirement
  combos hard-block requirement save and IPD approval with one aggregated list.
- **Case 13 — Two greige colours.** Dyeing rows Ecru→Navy, White→Black:
  reverse walk yields knit demand keyed (dia, greige colour); plan stores the
  split, program stays dia-total, popup free-colour options unchanged;
  operator picks the colour per knitting line exactly as today.
- **Case 12 — Mid-lot chain edit.** Matrices rebuild on save (popups already
  staleness-proof via key re-resolution); edit un-approves (fingerprint) so
  stale plans are flagged; removing a receipt-bearing step warns and keeps the
  ledger rows; `rebuild_fabric_tracking` reports the unmatched bucket.
- **Cases 8/14/16** fall out structurally: everything keys (lot, cloth_item)
  with per-fabric-row try/except; step resolution is per fabric row so one
  master can be step 3 for cloth A and off-chain for cloth B; over-plan /
  over-program stays warn-only, plan/received columns server-owned.

---

## 11. Build sequence (phases; each ends with bench validation + code review)

- **P1 — Chain core + data model + migration (server only).**
  `fabric_chain.py` (state walker unit-tested hard: pins, undetermined colour,
  wildcards, identity), new IPD doctypes/fixtures, `fabric_ipd.py` builders,
  `ipd_validations` rewrite, patch 2 with the matrix-identity acceptance gate.
  Desk renders the raw step/mapping grids (usable, ugly). Exit: existing WOs /
  popups / tracking still green on migrated data (they still resolve by
  process_name against identical matrices).
- **P2 — Tracking + ledger + Lot island.** `Lot Fabric Step Ledger`, tracking
  rewrite, `get_wo_totals`/`get_ledger_received`, patch 3, popup
  `_add_planning_data` generic (no plan column yet), FabricProgram.vue
  long-format ledger. Exit: rebuild reproduces migrated numbers; dye/compact
  availability identical to today; re-compacting demo works end-to-end.
- **P3 — Requirement + plan + approval.** `Lot Fabric Requirement`,
  `fabric_plan.py`, approval/un-approve/fingerprint wiring, program seeding,
  strict chain validation at approval. Exit: owner's scenario — enter
  requirement, approve IPD, read yarn/greige/step plan off the Lot.
- **P4 — Popup polish + widgets.** Plan-aware prefills, `planning_label` /
  `overshoot_key` served, Desk dialog + /web modal de-branched,
  FabricSwapDetail per-step mounting + FabricConversionDetail, Approved lock
  gap closed.
- **P5 — Hardening.** Unmatched-bucket UX, staleness badges, lessons-learned +
  `docs/design/` spec update, UI-driven test pass (Playwright active driving,
  not screenshots), cleanup patch dropping the dead tables.

**Non-goals (v1, explicit):** wastage entry (math already reads it), per-dia
knitting ratio (matrix format supports it later), >2 chain attributes
(pin_attribute column future-proofs it), (dia, colour)-keyed knitting program,
/web chain editor, stock-level availability for bought greige.

**Trade-offs accepted:** mappings reference steps by Process link (relies on
I4, in exchange for reorder-stable, human-readable rows); knitting received
mirrored in two tables (program grid stays untouched at the cost of one
dual-write in one function); totality/injectivity are save-time warnings not
errors (today's permissive forward flow preserved; the plan alone demands
strictness, at approval); plan rows and received rows can differ in key
granularity for multi-greige chains (display groups them).
