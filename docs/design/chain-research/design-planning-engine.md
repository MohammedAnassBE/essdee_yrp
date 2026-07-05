# Commonized Fabric Chain — Planning-Engine-First Design

Bench: /home/anas/frappe-16 · App: essdee_yrp (base: yrp) · Date: 2026-07-04
Companion docs: `constraints.md` (hardcode map), `cases.md` (case catalogue + invariants I1–I9).
Angle: design the requirement→greige BACKWARD SOLVER first; let its determinism
needs dictate the minimal data model. Everything else (matrix generation, popup,
ledger) is derived from what the solver consumes and produces.

---

## 0. The solver is the spec

The owner's sentence — *"if we want this many kilos in Red colour 18 dia, the
IPD Process Matrix will generate how much greige yarn I should give in knitting,
in what dia, and the receivables — similarly in compacting and dyeing"* — is one
function:

```
requirement {(dia, colour): kg of FINISHED cloth}          (Lot data)
        │  walk chain steps LAST → FIRST,
        │  scaling through each step's IPD Process Matrix   (per-unit rules)
        ▼
per-step plan: expected OUTPUT kgs + expected INPUT kgs per step
        + yarn kg (conversion step input) / greige procurement kgs (bought greige)
        + knitting-program suggestion (dia → kg)            (Lot data)
```

For that walk to be **deterministic**, the solver needs exactly four things:

| Solver need | What provides it | Status today |
|---|---|---|
| S1. An ordered step list per IPD | new `fabric_steps` child table | missing (3 fixed tabs, order implicit) |
| S2. One matrix per step, resolvable by (ipd, process_name) | `sync_fabric_process_matrices` | exists; builders are tab-bound |
| S3. Fully-expanded matrix groups whose OUTPUT attrs are exact-matchable | `_build_value_swap_matrix` + wildcard expansion | exists; passthrough derivation is chain-order-hardcoded |
| S4. Reverse-unambiguous mappings: per step, no two groups share the same (output attrs) key | new invariant I2 (injectivity per pin) | not validated today (explicitly legal forward) |

Everything in sections 1–8 exists to supply S1–S4 and to store/consume the
solver's output. No quantity math ever lives outside matrix combos
(owner requirement 2, invariant I3).

---

## 1. The backward solver — `essdee_yrp/essdee_yrp/fabric_plan.py` (new file)

### 1.1 Core pure function

```python
def solve_chain_backward(ipd_doc, requirement):
    """requirement: {frozenset({(attr, value), ...}): kg} keyed by FINISHED-cloth
    output attrs (Dia always; Colour when the cloth has it).

    Returns (step_plans, unreachable):
      step_plans: list, FIRST→LAST, one per chain step:
        {"process_name", "position", "shape",
         "outputs": {attrs_frozenset: kg},   # what this step must produce
         "inputs":  {attrs_frozenset: kg}}   # what must be fed to it
        Conversion-step inputs use the input item's (attr-less) key: frozenset().
      unreachable: [{"position", "process_name", "attrs", "kg"}] — demanded
        combos with no matching matrix group (caller decides warn vs block).
    Quantities come ONLY from matrix combos (in_qty/out_qty/wastage_pct)."""
```

Algorithm (junior-readable, ~60 lines):

```python
steps = get_fabric_steps(ipd_doc)                 # S1, section 3
demand = dict(requirement)                        # demand entering "after last step"
unreachable, step_plans = [], []
for step in reversed(steps):
    groups = _load_groups(ipd_doc.name, step.process_name)   # S2
    # index groups by their OUTPUT attrs — exact match (S3):
    by_out = {frozenset(g["output"][0]["attrs"].items()): g for g in groups}
    out_attr_names = _matrix_output_attribute_names(step)     # e.g. {"Dia","Colour"}
    outputs, inputs, next_demand = {}, {}, {}
    for combo, kg in demand.items():
        # project the demand combo onto the attrs this matrix declares —
        # identity for swap/identity steps (fully stamped), narrows to {Dia}
        # at the conversion step (yarn side is attr-less, merging is additive)
        key = frozenset((a, v) for a, v in combo if a in out_attr_names)
        group = by_out.get(key)
        if not group:
            unreachable.append({...}); continue
        out_qty = flt(group["output"][0]["qty"])              # e.g. cloth_per_kg_yarn
        scale = kg / out_qty
        outputs[combo] = outputs.get(combo, 0) + kg           # keep demand granularity
        for inp in group["input"]:
            in_kg = flt(inp["qty"]) * scale * (1 + flt(inp["wastage_pct"]) / 100.0)
            in_key = frozenset((inp["attrs"] or {}).items())
            inputs[in_key] = inputs.get(in_key, 0) + in_kg
            next_demand[in_key] = next_demand.get(in_key, 0) + in_kg
    step_plans.append({...})
    demand = next_demand
return list(reversed(step_plans)), unreachable
```

Properties, stated as code comments in the file:

- **Same scale rule as the popup**: `in_kg = out_kg × in_qty/out_qty × (1+wastage)`
  is byte-identical to `calculate_fabric_deliverables` (api/work_order.py:412–416).
  Wastage v2 is a data change, zero solver change (Case 9).
- **Exact output match is safe** because matrices are fully expanded at build time
  (wildcards → concrete groups, passthrough stamped on both sides) — the same
  property `_matrix_qty_rows` already relies on. This is the user's
  "combination": stage k's output attr-set == stage k+1's input attr-set,
  connected per dia AND colour.
- **Determinism needs S4**: two groups with identical output attrs (D22→D18 and
  D20→D18 unpinned; White→Black and Ecru→Black at one dia) make `by_out`
  collide. Validated away at approval (section 3.4). Forward flow stays
  permissive per bench rule — only the PLAN demands invertibility.
- **Conversion step**: demand entering it carries (dia, greige-colour) —
  produced by reversing the first Colour swap. Projection onto {Dia} merges the
  colours per dia for group lookup; `outputs` keeps the (dia, colour) split for
  display (Case 13); yarn = `inputs[frozenset()]` (attr-less, one figure per
  cloth). The knitting-program suggestion = per-dia sums of `outputs`.
- **Zero steps** (fully bought finished cloth): loop runs zero times; caller
  copies the requirement into procurement rows (Case 5 degenerate).
- Rounding: `flt(x, 3)` applied only when WRITING rows, division last — no
  mid-chain drift.

### 1.2 Orchestration functions (same file)

```python
class FabricPlanError(frappe.ValidationError): ...

def build_fabric_plan(lot_doc, fabric_row, raise_on_unreachable=True):
    """Requirement rows of one (lot, cloth) → solver → write plan rows.
    Called from Lot save (fast path) and rebuild_fabric_plans_for_ipd."""

def rebuild_fabric_plans_for_ipd(ipd_doc):
    """IPD approval hook: rebuild the plan of every open Lot whose
    lot_fabric_details references this IPD and that has requirement rows.
    Per-lot try/except — one lot's bad requirement never blocks approval or
    the other lots; failures aggregated into ONE msgprint listing lots."""

def on_ipd_update(doc, method=None):
    """hooks.py on_update, listed AFTER sync_fabric_process_matrices, so the
    matrices the solver reads are the ones just rebuilt in this same save.
    Gate: is_cloth_ipd(doc) and doc.approval_status == "Approved"."""
```

Storage of results: section 6. Error handling: section 6.3.

---

## 2. What the solver dictates for matrices (S2/S3) — matrix generation

File: `essdee_yrp/essdee_yrp/fabric_ipd.py` (rewritten in place; module keeps
its name and hook signature).

### 2.1 One generic sync

```python
def sync_fabric_process_matrices(doc, method=None):   # hook name UNCHANGED
    if not is_cloth_ipd(doc):
        return
    _delete_all_matrices(doc.name)                    # unchanged wipe-rebuild
    uom = frappe.db.get_value("Item", doc.item, "default_unit_of_measure")
    for step in get_fabric_steps(doc):
        builder = {
            "conversion": _build_conversion_matrix,
            "swap":       _build_value_swap_matrix,
            "identity":   _build_identity_matrix,
        }[step.shape]
        matrix = builder(doc, step, uom)
        if matrix:
            matrix.insert(ignore_permissions=True)
```

The matrix DOC format (base yrp `IPD Process Matrix`) needs **zero changes** —
`get_combinations_grouped()`, `_resolve_matrix_group`, and `get_process_io`
already work for N matrices. Matrices stay auto-generated, per-unit, draft.

### 2.2 The three builders (one per shape, not per stage name)

- `_build_conversion_matrix(doc, step, uom)` — today's `_build_knitting_matrix`
  reparametrized: dia list = the step's mapping rows (`to_value` column, section
  3.2), input item = `step.input_item`, output qty = `step.output_per_input`.
  Output attribute = Dia. One group per dia, input combo attr-less. Identical
  output for the migrated data (Phase-1 gate: byte-identical matrices).
- `_build_value_swap_matrix(doc, step, uom)` — the existing function survives
  almost untouched (it is already fully parametrised); the wrapper dispatch
  (`_build_dyeing_matrix` / `_build_compacting_matrix`) dies. Parameters come
  from the step: `attribute = step.swap_attribute` (from the Process master),
  `passthrough_attribute = step.pin_attribute` (= the *other* fabric attribute,
  Dia↔Colour), rows = the step's mapping rows with generic field names
  (`pin_value`, `from_value`, `to_value`).
- `_build_identity_matrix(doc, step, uom)` — NEW (Case 4, invariant I3): one
  group per combo in `state_at(doc, step.position)`; input attrs == output
  attrs, qty 1:1. In-chain identity steps (washing) thereby flow through the
  same solver/popup/ledger code with no `identity:` special key. The existing
  OFF-chain identity flavour (`ipd_processes` rows, `_identity_qty_rows`)
  survives unchanged for ad-hoc services; a process may appear in only one of
  the two places (validation). User heuristic, documented in the field
  description: *put a process in the chain iff you GRN it per lot.*

### 2.3 The chain-walk primitive (kills all six order-hardcodes)

File: `essdee_yrp/essdee_yrp/fabric_chain.py` (new; pure helpers, no writes):

```python
def get_fabric_steps(ipd_doc) -> list[frappe._dict]:
    """Ordered steps. Each: {position, process_name, shape, swap_attribute,
    pin_attribute, input_item, output_per_input, mapping_rows}. Shape resolved
    once via get_process_shape(process) — Process master owns the SHAPE
    (2026-06-25 rule), the IPD supplies the values."""

def get_fabric_step(ipd_doc, process_name):
    """Step row for a WO's process, or None. Replaces get_fabric_process_kind.
    Cloth IPDs only (garment IPDs never enter the fabric path, I7)."""

def state_at(ipd_doc, position) -> list[dict]:
    """The (Dia[, Colour]) combos ENTERING the step at `position`:
    position 0  -> initial state: conversion step's dias (greige colour left
                   open) or, bought greige, the IPD's Dia×Colour mapping values;
    position k  -> push state through steps 0..k-1's mapping rows
                   (pin-aware: a row rewrites only combos matching its pin)."""

def values_entering(ipd_doc, position, attribute) -> list[str]:
    """Distinct values of one attribute in state_at() — the ONE helper that
    replaces derive_passthrough_values, _identity_attr_values, _ipd_dias,
    _ipd_target_colours and the swap-widget pin seeding (invariant I9)."""
```

`_expand_wildcard_rows` keeps its logic but its `values` argument becomes
`values_entering(doc, step.position, step.pin_attribute)` — passthrough values
are now *positional*, so a swap step after re-compacting expands against
POST-re-compacting dias automatically. `derive_passthrough_values` is deleted.

`ensure_cloth_item_attributes` becomes: for each step, append its
`swap_attribute` and (when any mapping row pins) its `pin_attribute`; the
conversion step appends Dia. Same before_validate hook.

### 2.4 The "combination" (owner requirement 5), restated precisely

A stage k matrix group's INPUT combo (from-value + stamped pin values) is
exactly a stage k−1 OUTPUT combo, because (a) wildcard expansion enumerates
pins from `state_at(k)` = stage k−1's outputs, and (b) pins are stamped on both
sides. So the chain is connected per (dia, colour) BY CONSTRUCTION — "I should
give greige in 18 dia, only then I get 18 dia" falls out of the data, and the
solver's exact-match walk is the proof that the combination is complete
(any gap = an `unreachable` entry, section 6.3).

---

## 3. IPD data model (S1) — the minimal change

All in essdee_yrp (fixtures + new child doctypes). Base yrp untouched.

### 3.1 `IPD Fabric Step` (new child doctype, `essdee_yrp/essdee_yrp/doctype/ipd_fabric_step/`)

| field | type | notes |
|---|---|---|
| `process` | Link Process, reqd, in_list_view | distinct per IPD (I4); order = row idx |
| `shape_summary` | Data, read_only | display: "Conversion (Yarn → Cloth)" / "Swap Colour" / "Identity" — stamped server-side from `get_process_shape` on validate, so the grid is self-explaining |
| `input_item` | Link Item | conversion steps only (was IPD `yarn_item`) |
| `output_per_input` | Float | conversion steps only (was `cloth_per_kg_yarn`); reqd > 0 when conversion |
| `pin_wise_entry` | Check | swap steps: per-pin widget mode (was `dia_wise_colour_change` / `colour_wise_dia_change`) |

Parent field on IPD (Custom Field, fixtures): `fabric_chain_tab` (Tab Break,
depends_on `is_cloth_item`) → `fabric_steps` (Table) → `fabric_chain_html`
(HTML, the per-step editor mount) → `fabric_step_mappings` (Table, hidden —
edited only through the widgets).

### 3.2 `IPD Fabric Step Mapping` (new child doctype) — ONE table for all steps

| field | type | notes |
|---|---|---|
| `process` | Link Process, reqd | which step the row belongs to (unique per IPD by I4 — survives row reordering, unlike an idx pointer) |
| `pin_value` | Link Item Attribute Value | blank = applies to every pin value (wildcard) |
| `from_value` | Link Item Attribute Value | blank on CONVERSION rows |
| `to_value` | Link Item Attribute Value, reqd | swap: the to-value; conversion: the output dia |

Row semantics by the owning step's shape:
- conversion: `{to_value: dia}` — one row per knitted dia (replaces
  `knitting_dia_details`).
- swap: `{pin_value?, from_value, to_value}` (replaces `dyeing_colour_details` /
  `compacting_dia_details`; pin = the other attribute's value).
- identity: no rows (matrix generated from `state_at`).

Frappe cannot nest child tables — the flat mapping table keyed by `process` is
the standard workaround and keeps ONE generic save/validate path.

### 3.3 What dies (after migration, section 7)

The nine per-tab Custom Fields (`knitting_process`, `yarn_item`,
`cloth_per_kg_yarn`, `knitting_dia_details`, `dyeing_process`,
`dia_wise_colour_change`, `dyeing_colour_details`, `compacting_process`,
`colour_wise_dia_change`, `compacting_dia_details`, 3 Tab Breaks, 2 HTML
mounts) and the three one-off child doctypes. `is_cloth_item` and
`Process.is_cloth_process` stay.

### 3.4 Chain validation — `fabric_chain.validate_fabric_chain(doc)` (called from `validate_cloth_ipd`)

Save-time HARD errors (data would be self-contradictory):
- duplicate Process across steps (I4 — generalizes ipd_validations.py:63; this
  is exactly why "Re-Compacting" is a NEW 30-second Process master, not
  Compacting twice);
- a step's Process declares no shape → hard error now (today's warn) because
  the builder dispatch needs it; message: "tick Item Conversion or add a Value
  Change Attribute on the Process master";
- conversion step without `input_item`/`output_per_input > 0`/dia rows;
- swap row missing from/to; duplicate (pin, from) per step (today's
  `validate_swap_rows`, now one loop over steps);
- mapping row whose `process` matches no step; from-value not an
  `swap_attribute` value; process in both chain and `ipd_processes`.

Save-time WARN, approval-time HARD (chain may legitimately be half-built while
editing):
- **I1 totality**: every combo in `state_at(k)` matches ≥1 mapping row of step
  k (pass-through = explicit from==to row, pre-seeded by the widget). Message
  lists the uncovered combos per step.
- **I2 injectivity per (step, pin)**: duplicate `to_value` for one `pin_value`
  → the solver cannot reverse. Message names the colliding rows and the three
  fixes: pin them to different values, chain them as two steps, or remove one.
  Genuinely non-invertible flows (knitted D20 and D22 both ending D18 — Case 6)
  get the extended message: "split into two cloths/IPDs or drop one source dia".

Approval-time checks run inside `approve_ipd` via a new
`fabric_chain.assert_chain_approvable(doc)` call (before `doc.save()`), so a
broken chain can never reach "Approved" and the solver never sees S4 violated.

### 3.5 Approval lifecycle (closes today's gaps)

- **Un-approve on chain edit**: in `validate`, compare
  `chain_fingerprint(doc)` (sha1 of steps + mapping rows, order-sensitive)
  against the stored doc's; if different and `approval_status == "Approved"`,
  set it to "Not Approved" + msgprint "chain changed — re-approve to rebuild
  lot plans". The `approve_ipd` save itself doesn't touch the chain, so it
  stays Approved and `on_ipd_update` fires the plan rebuild.
- **Form lock**: extend the Approved lock in `item_production_detail.js`
  (345–351) to `fabric_steps` + `fabric_step_mappings` + widget `locked` flag
  (today only the swap widgets honour it — the plain grids are editable after
  approval, a live bug).
- **Revert** (`revert_ipd_approval`): plans are KEPT (they document the last
  approved state) but every affected `Lot Fabric Detail.plan_status` is set to
  "Stale" (section 6.2) — cheap and honest.
- "Cutting Approved" is hidden for cloth IPDs (garment concept).

---

## 4. Lot requirement entry (owner requirement 3)

### 4.1 `Lot Fabric Requirement` (new child doctype on Lot, parentfield `lot_fabric_requirements`, hidden table)

| field | type | notes |
|---|---|---|
| `cloth_item` | Link Item, reqd | one of `lot_fabric_details` cloths |
| `dia` | Link Item Attribute Value, reqd | finished dia |
| `colour` | Link Item Attribute Value | reqd iff the cloth has Colour |
| `weight` | Float, reqd > 0 | kg of FINISHED cloth |

User-edited through the FabricProgram Vue island (`public/js/Lot/FabricProgram.vue`):
a third grid **"Final Requirement (finished cloth)"** above the knitting program
grid — columns Colour | Dia | Kg, add-row, colour column hidden for colourless
cloths. Options for the selects come from the server payload:
`entry.final_dias` / `entry.final_colours` = `values_entering(ipd, len(steps))`
(the chain's FINAL state — only reachable values are offered, which is the
fast-entry rule applied to the requirement).

### 4.2 Save path (mirrors the program's transient-JSON pattern exactly)

`fabric_program.save_fabric_requirement_details(lot_doc)` — before_validate,
fed by island JSON `fabric_requirement_details`:
- validate dia/colour attribute membership (`_validate_attribute_value`),
  duplicates per (cloth, dia, colour), negative weight; zero-weight rows drop;
- **reachability check**: each row's (dia, colour) must be in the final state
  set — unreachable rows HARD-BLOCK the save with the aggregated Case-7 message
  ("No chain path produces Colour=Purple / Dia=D16 for cloth X — add mapping
  rows on IPD Y or correct the requirement"). Data error ⇒ block; the warn-only
  doctrine is for balances only (I6).
- then, per fabric row: IPD approved → `build_fabric_plan(lot_doc, fabric_row)`
  (plan rows land in the same save); not approved → `plan_status =
  "Pending Approval"`, requirement saves fine (never gate data entry).

The knitting program table (`Lot Fabric Program` {dia, weight, received}) is
UNCHANGED and stays the WO driver (owner requirement 6). Relationship: the plan
SUGGESTS the program (section 6.4); the user owns it.

---

## 5. Where the plan lives — `Lot Fabric Step Ledger`

### 5.1 One generic table replaces `Lot Fabric Colour Program`

New child doctype on Lot, parentfield `lot_fabric_step_ledger`, hidden; rows
server-owned end to end (client JSON can never write it — same guard as today's
colour ledger):

| field | type | owner |
|---|---|---|
| `cloth_item` | Link Item, reqd | — |
| `process_name` | Link Process, reqd | which chain step |
| `side` | Select `Output`/`Input`, default Output | Output = the step produces it; Input = the step consumes it |
| `dia` | Link Item Attribute Value | blank on the yarn Input row |
| `colour` | Link Item Attribute Value | blank when the combo has no colour |
| `planned_weight` | Float, read_only | written ONLY by `build_fabric_plan` |
| `received_weight` | Float, read_only | written ONLY by fabric_tracking GRN hooks (Output rows only) |

Row population:
- `build_fabric_plan` writes `planned_weight` on **Output rows per step**
  (solver `outputs`) and **Input rows for the FIRST step only** — yarn
  (dia/colour blank, the "how much greige yarn" figure) or, bought greige, the
  per-(dia, colour) procurement kgs (Case 5: the first step's back-computed
  input IS the purchase figure; no pseudo-step needed, it's just side=Input on
  step 1).
- GRN tracking writes `received_weight` on Output rows keyed by the received
  variant's (dia, colour) — rows created at planned 0 when missing (no receipt
  silently dropped), exactly `_bump_program_rows` semantics: atomic SQL
  increment, per-lot `for_update` lock, direct row writes (never `lot.save()`
  inside GRN submit), rework GRNs skipped.

Why one table for plan + actuals: no join drift, one rebuild path, and
plan-vs-actual per step is a single table scan (the owner's daily question).
`rebuild_fabric_tracking` zeroes ONLY `received_weight`; plan rebuild rewrites
ONLY `planned_weight` (deleting planned-only rows that lost their plan,
keeping receipt-bearing rows at planned 0).

### 5.2 Plan status per (lot, cloth) — on `Lot Fabric Detail` (existing child table)

Add fields: `plan_status` Select `""|Built|Pending Approval|Stale|Error`
(read_only), `plan_error` Small Text, `plan_built_on` Datetime. `Stale` is
stamped by `revert_ipd_approval`; `Error` carries the aggregated solver message
when an IPD approval rebuild fails for this lot. The FabricProgram island and
the WO popup surface the status ("plan pending IPD approval" — warn, never
block, I8).

### 5.3 FabricProgram.vue ledger rendering

The fixed Dia|Colour|Dyed|Compacted grid (lines 77–102) becomes long-format:
one section per chain step (server sends the ordered step list with labels),
columns Dia | Colour | Planned | Received | Balance; the knitting step's
section shows the yarn Input row beneath it. Zero-value rows hidden as today.
`fetch_fabric_program_details` payload gains `steps: [{process_name, label,
rows: [...]}]`, `requirement: [...]`, `plan_status`.

---

## 6. The common function on approval — wiring, output, errors

### 6.1 Trigger topology (both paths call THE one function — no second code path)

```
approve_ipd(doc, "Approved")                    Lot save (requirement changed)
  └─ assert_chain_approvable(doc)  [3.4]           └─ save_fabric_requirement_details
  └─ doc.save() → hooks on_update:                     └─ per fabric row, if IPD approved:
       1. sync_fabric_process_matrices                       build_fabric_plan(lot, fabric_row)
       2. fabric_plan.on_ipd_update  (NEW hook, after #1)
            └─ rebuild_fabric_plans_for_ipd(doc)
                 └─ for each open referencing Lot: build_fabric_plan(...)
```

hooks.py change: append `"essdee_yrp.fabric_plan.on_ipd_update"` to the
Item Production Detail `on_update` list (order matters: matrices first).

### 6.2 `build_fabric_plan(lot_doc, fabric_row)` — inputs/outputs

- Inputs: the lot's `lot_fabric_requirements` rows for `fabric_row.cloth_item`;
  the IPD's steps + matrices (freshly synced). No requirement rows → clears
  planned weights, `plan_status = ""`, returns.
- Calls `solve_chain_backward`; writes ledger rows (5.1) via
  `_write_plan_rows(lot_name, cloth, step_plans)` — direct row-level writes
  with `update_modified=False`, per-lot `for_update` lock (same discipline as
  `_apply_grn`; an IPD-approval rebuild must not race a GRN submit).
- Pre-seeds the knitting program (6.4), stamps `plan_status/plan_built_on`.

### 6.3 Error handling for unreachable requirements

- **Lot-save path**: reachability already hard-blocked at requirement entry
  (4.2), so `build_fabric_plan` failures here are rare (mid-chain stranding via
  pins that final-state check can't see); they raise `FabricPlanError` and
  block the save with the aggregated per-combo message. Fast feedback while
  the merchandiser is typing.
- **Approval path**: per-lot try/except in `rebuild_fabric_plans_for_ipd`.
  Approval itself NEVER fails because of one lot's stale requirement (the IPD
  owner can't fix lot data); instead each failing lot gets
  `plan_status="Error"` + `plan_error`, and ONE msgprint lists them:
  "Approved. Plans built for 4 lots; FAILED for LOT-0007 (Purple/D16
  unreachable — fix the lot's requirement)". Chain-editing mistakes that would
  strand ALL lots are caught earlier by `assert_chain_approvable` (I1/I2).

### 6.4 Plan → knitting program pre-seed (requirement 6 kept intact)

After a successful solve, for each dia in the conversion step's output sums:
- program row missing, or its `weight` equals the PREVIOUS plan value or 0 →
  set `weight` to the new plan figure (pre-seed / refresh untouched rows);
- user-edited weight ≠ plan → leave it, add to a "program differs from plan"
  orange msgprint (extends `_warn_program_below_ordered`'s style; new checks:
  program < plan, plan < ordered — all warn-only, I6/Case 16).
The previous plan value is read from the ledger's conversion-step Output rows
before rewriting them — no extra column needed.

---

## 7. WO popup integration

### 7.1 Context becomes step-shaped (`get_fabric_deliverable_context`)

Per fabric row, `get_fabric_step(ipd, wo.process_name)` replaces the kind
resolver (off-chain identity fallback unchanged). Row payload changes:

```python
{
  "fabric_row", "cloth_item", "treated_item", "production_detail",
  "step": {"position": 2, "shape": "swap", "process_label": "Re-Compacting",
            "prev_process": "Compacting",          # None for first step
            "is_conversion": False},
  "plan_status": fabric.plan_status,
  # conversion-only (generic names replace knitting-only ones):
  "input_item": step.input_item, "ratio": step.output_per_input,
  "free_attribute": "Colour",                       # attr the output lacks (7.3)
  "free_attribute_options": [...],                  # from the NEXT swap step
  "qty_rows": [...],
}
```

`kind` is kept one release as a deprecated alias (`"knitting"` when
conversion+position 0, etc.) so /web and Desk migrate in the same PR but old
open tabs don't break mid-deploy.

### 7.2 `_add_planning_data` — one loop, no stage names

For step k, every qty row gets:

| figure | rule | source |
|---|---|---|
| `program` / `received` | conversion step only: program row per out-dia | `lot_fabric_programs` (unchanged) |
| `plan` | ledger Output row (step k, out combo).planned_weight | step ledger |
| `ordered` | Σ other WOs' RECEIVABLES of this process per out combo | `get_wo_totals(..., side="receivable")` |
| `available` | k=0: None (conversion; program drives) or None (bought greige). k>0: received(step k−1 Output, in-combo) − consumed(step k, in-combo) | ledger + `get_wo_totals(..., side="deliverable", calculated_only=True)` |
| `prefill` | conversion: `max(program − ordered, 0)` (UNCHANGED — program stays the driver). Other steps, plan present: `clamp(min(plan − ordered, available if not None), ≥ 0)`. Plan absent: `available` if the step doesn't split its input, else 0 (split = >1 matrix group sharing one input combo — the data-driven version of "dyeing prefills 0, compacting prefills available") |
| `balance_group`, `balance_limit`, `planning_line` | server-rendered label + overshoot grouping key ("sum per previous-stage combo ≤ limit") | replaces the client's 3-branch `planning_description`/`warn_balance_overshoot` |

This is the requirement-driven vision landing in the popup: once the IPD is
approved and the requirement entered, a dyeing/re-compacting popup opens
pre-filled with the plan figures, clamped to what upstream actually delivered.
Over-plan entry warns, never blocks (I6).

Availability matching is lenient on missing attrs: a ledger Output row lacking
`colour` (legacy knitting receipts, colourless cloth) matches any in-combo
colour — one documented loop, no silent zeroes on legacy data.

### 7.3 Free attribute (generalizes the greige-colour machinery)

A conversion step whose matrix output attrs don't cover the cloth's attributes
has a **free attribute** (Colour today). Options = from-values of the NEXT step
that swaps it (`_knit_colour_options` generalized to "next swap step of attr
X", falling back to the IPD mapping); the single-option case auto-fills
(`get_greige_colour` generalized). Server-side validation in
`calculate_fabric_deliverables` keeps the same guard with step-derived options.

### 7.4 Client changes

- Desk `work_order.js` + /web `FabricDeliverablesModal.vue` (twin UIs, change
  mirrored 1:1): delete the 3-branch `planning_description` /
  `warn_balance_overshoot` / `kind === "knitting"` switches; branch only on
  `step.is_conversion` (colour picker/columns, editable input-item qty) and
  render server-sent `planning_line` / group by `balance_group`.
  `MAX_COLOUR_COLUMNS`, payload contract `{fabric_row, colour?, yarn_qty?,
  entries:[{key, out_attrs, qty, colour?}]}`, `fc-` row stamping, idempotent
  rewrite — ALL unchanged (the matrix-group key contract survives, so
  `calculate_fabric_deliverables` needs only the resolver + free-attr rename).
- `calculate_fabric_deliverables`: replace `get_fabric_process_kind` with
  `get_fabric_step`; `_require_ipd_yarn` reads `step.input_item`; the
  "aggregated has exactly one input" yarn-override guard is already generic.

---

## 8. Tracking / ledger fit — `fabric_tracking.py`

- `TRACKED_KINDS` dies. `_apply_grn`: `step = get_fabric_step(ipd,
  wo.process_name)`; if step → bump the step ledger Output row keyed by the
  variant's (dia, colour) (attrs read as today via `_variant_attribute_map`,
  Dia/Colour only). Conversion step ADDITIONALLY mirrors into
  `Lot Fabric Program.received_weight` per dia (the program grid stays
  self-contained; one extra bump in the same loop — documented as "the ledger
  is the uniform source; the program's received column is a convenience
  mirror").
- The four named wrappers (`get_produced_by_dia`, ...) collapse into
  `get_wo_totals(lot, process_name, cloth_item, side, attributes,
  exclude_wo=None, calculated_only=False)` over the already-generic
  `_sum_by_attributes`; attribute JOINs become LEFT JOINs so colourless
  variants aren't dropped from (Dia, Colour) queries.
- `rebuild_fabric_tracking`: zero `received_weight` on program + step ledger,
  replay GRNs in posting order (unchanged shape). GRNs whose WO process no
  longer resolves to a chain step land in a visible **unmatched bucket**
  (msgprint listing WO/process/kgs) instead of vanishing (Case 12).
- Removal guards: `validate_unique_fabric_cloths` extends its
  received/tracked check to the step ledger; removing a chain STEP whose
  ledger rows carry receipts warns and keeps the orphan rows visible
  (receipts are historical fact); only removing the conversion step with
  program receipts hard-blocks.

---

## 9. Migration from the three tabs

One patch: `essdee_yrp/patches/v0/migrate_fabric_tabs_to_chain.py` (+
`patches.txt`), then a cleanup patch one release later.

1. **Steps**: per cloth IPD, insert `fabric_steps` rows in fixed order —
   knitting (conversion: `input_item = yarn_item`, `output_per_input =
   cloth_per_kg_yarn`), dyeing (`pin_wise_entry = dia_wise_colour_change`),
   compacting (`pin_wise_entry = colour_wise_dia_change`) — skipping unset
   process links (bought-greige IPDs start at dyeing naturally).
2. **Mappings**: `knitting_dia_details.dia` → `{process: knitting, to_value:
   dia}`; `dyeing_colour_details` → `{process: dyeing, pin_value: dia,
   from_value: from_colour, to_value: to_colour}`; `compacting_dia_details`
   likewise with `pin_value: colour`.
3. **Regenerate matrices** by calling `sync_fabric_process_matrices` per
   migrated IPD; assert group-count equality old-vs-new in the patch (cheap
   invariant; full byte-diff in tests).
4. **Ledger**: per `Lot Fabric Colour Program` row → step-ledger Output rows:
   `received_weight` → (dyeing process of that lot-cloth's IPD),
   `compacted_weight` → (compacting process). Rows with both split into two.
   `Lot Fabric Program` untouched.
5. **Old fields**: fixtures update hides the three tabs (`depends_on:
   "eval:false"`) but keeps fields + child doctypes readable for one release
   (rollback safety + the patch is re-runnable); cleanup patch then deletes
   the Custom Fields, the three IPD child doctypes, and
   `Lot Fabric Colour Program`.
6. **Approval statuses are NOT reset**: existing Approved cloth IPDs stay
   Approved (fingerprint is stamped, not compared, on first save); plans build
   lazily when requirements get entered — no site-wide rebuild storm.

Nothing garment-side is touched (all changes gated by `is_cloth_item` /
`is_cloth_ipd`, verified in the constraint map §11).

---

## 10. essdee_yrp vs base yrp

| Layer | App | Rationale |
|---|---|---|
| `Process.is_item_conversion` / `value_change_attributes`, `IPD Process Matrix` (+ `get_combinations_grouped`), `ipd_engine.get_process_io`, `approval_status` field | **base yrp — zero changes** | already generic machinery |
| Chain doctypes, fixtures, `fabric_chain.py`, `fabric_ipd.py` builders, `fabric_plan.py` solver, `fabric_program.py`, `fabric_tracking.py`, `api/work_order.py`, all JS/Vue, migration patches | **essdee_yrp** | fabric is an Essdee customization; Dia/Colour as the two chain attributes stays an essdee constant pair (module-level, one place) |

Promotion of the chain into base yrp is possible later (the solver only speaks
matrix language) but is explicitly NOT v1 — no speculative generality
(two-attribute worlds cover every case in the catalogue; a third attribute
would need pin→pin-set generalization, noted and deferred).

---

## 11. Cases, concretely

### 11.1 Re-compacting (Case 2 — the driving example)

Setup, zero code: create Process master **"Re-Compacting"** (30 seconds:
`value_change_attributes = [Dia]`); on the IPD append step row
`{process: Re-Compacting}` after Compacting; add mapping rows
`{process: Re-Compacting, from_value: D20, to_value: D18}` plus explicit
identity rows for dias that skip it (widget pre-seeds `from==to` from
`state_at(4)` — totality I1). Save → 4 matrices; approve → plans rebuild.
- Requirement (Red, D18, 100 kg) now reverses: D18 ←(re-compact)← D20
  ←(compact)← D22 ←(dye: Red←Ecru)← greige D22 ←(knit ratio 0.98)← 102.04 kg
  yarn. Each arrow is one matrix-group lookup, kgs scaled by that group.
- Popup for the Re-Compacting WO: `available` = compacting's ledger received
  per (D20, colour) − re-compacting's consumed; `prefill` = plan-clamped.
- GRNs land in the step ledger under process "Re-Compacting" — no schema
  change (this is what the old 2-column colour table could not do).
- Distinct-master rule (I4) is why it's "Re-Compacting" and not Compacting
  twice: WO→step resolution, matrix keying (ipd, process_name), and ledger
  keys all ride on process_name uniqueness — and it matches the owner's own
  vocabulary ("re-compacting" as a new process).

### 11.2 Re-dyeing / topping (Case 3)

Same mechanics, attr = Colour: step "Topping" after dyeing (or after
compacting — `state_at` makes pin expansion position-correct automatically).
Untopped colours need explicit `Rose→Rose` identity rows (I1) — the widget
pre-seeds them, one checkbox-style confirm. Knitting's greige options read the
FIRST Colour-swapping step's from-values (7.3), not "the dyeing tab".

### 11.3 Washing mid-chain (Case 4)

Step row `{process: Washing}`, no mapping rows → `_build_identity_matrix` from
`state_at(position)`: one 1:1 group per incoming combo. Solver passes demand
through it untouched (in=out); ledger tracks washed kgs; compacting's
`available` reads washing's received. Off-chain identity (yarn-doubling
service) keeps today's `_identity_qty_rows` path. Heuristic in the docs: *in
the chain iff you GRN it per lot.*

### 11.4 Bought greige (Case 5)

Chain = [dye, compact]. `state_at(0)` = IPD Dia×Colour mapping values (today's
fallback, now positional). Solver runs unchanged; the FIRST step's input
demand is written as side=Input ledger rows per (dia, greige colour) — the
**procurement figure** the purchase team reads off the Lot. No program rows;
first-step `available` stays None (stock-driven, warn-only) as today.

### 11.5 Backward chaining + ambiguity (Case 6)

Exact-output match + I2 give determinism. `Ecru→Black@D18, White→Black@D20`
is fine (injective per pin); unpinned `Ecru→Black` + `White→Black` blocks
approval with the pin/chain/remove fix list. Knitted D20+D22 both → D18 in one
compact step: totality+injectivity collide → approval error suggests chain-
lengthening or splitting cloths — genuinely non-invertible flows are refused,
never guessed.

### 11.6 Unreachable requirement (Case 7)

(Purple, D16) with no producing path: blocked at requirement save against the
final state set (4.2); mid-chain stranding (pin-created gaps) caught by the
solver and blocked (Lot path) or reported per-lot without failing approval
(6.3). Hard-block is correct: data error, not a balance (I6).

### 11.7 Multiple greige colours (Case 13)

Requirement Black(from White) + Navy(from Ecru): solver outputs conversion-step
Output rows per (dia, greige colour) — the split is visible in the plan ledger;
`Lot Fabric Program` stays dia-only (sum), operator picks the colour per
knitting WO line exactly as today. Advisory, not enforced — v1 decision
recorded so nobody "fixes" it into a program-key change.

(Cases 8, 12, 14, 16 are absorbed structurally: per-(lot,cloth) solve isolation
with try/except per fabric row; mid-lot chain edits = matrices rebuild + warn
on receipt-bearing step removal + unmatched replay bucket; per-fabric-row WO
resolution keeps a shared master at different positions in different IPDs;
warn-only doctrine on every balance figure.)

---

## 12. Build sequence

Each phase ends with the bench validation gates (docs/claude/validation.md:
tests + real-record UI drive via pw-shot; >50-line phases go through
requesting-code-review).

- **Phase 1 — Chain model + generic matrices (no behaviour change).**
  New doctypes (3.1/3.2), `fabric_chain.py` (steps/state_at/validate/
  fingerprint), rewrite `fabric_ipd.py` builders over steps, migration patch
  steps 1–3 + hidden old tabs, IPD step-editor UI (reuse FabricSwapDetail per
  swap step; conversion editor = dia checkboxes + input item + ratio).
  Gate: migrated IPDs regenerate byte-identical matrices; garment IPDs
  untouched; approval lock covers the new tables.
- **Phase 2 — Generic ledger + popup neutrality (still no solver).**
  `Lot Fabric Step Ledger` + tracking rewrite (8), colour-program migration
  (9.4), `get_wo_totals`, stage-neutral popup context + planning lines (7),
  Desk+/web dialog de-branching, FabricProgram.vue long-format ledger.
  Gate: knit→dye→compact flows byte-compatible (program balances, prefills,
  overshoot warnings); NEW: a re-compacting step works end-to-end (WO →
  Calculate → GRN → ledger row).
- **Phase 3 — Requirement + solver + approval wiring (the vision lands).**
  `Lot Fabric Requirement` + island grid (4), `fabric_plan.py` (1),
  `on_ipd_update` hook + `assert_chain_approvable` + un-approve fingerprint
  (3.4/3.5/6), plan columns + plan-clamped prefills + program pre-seed/drift
  warnings, plan_status surfacing.
  Gate: enter requirement → approve IPD → knitting program suggested, yarn
  figure shown, every popup pre-filled from the plan; unreachable combos
  blocked with the aggregated message; revert marks plans Stale.
- **Phase 4 — Cleanup + hardening.** Delete legacy fields/doctypes (9.5),
  `rebuild_fabric_tracking` unmatched bucket, docs (`docs/design/` +
  apps.md pointer), lessons-learned entries for the approval-lock gap.

Rough sizing: P1 ≈ P2 ≈ P3 in effort; P4 small. Each phase is independently
shippable; the mill keeps running on the program-driven flow throughout (I8).

---

## 13. Trade-offs accepted (explicit)

1. **Distinct Process master per occurrence** — one 30-second master per new
   physical process, in exchange for keeping WO/matrix/ledger keying on
   process_name (no schema surgery on WOs). Matches the owner's language.
2. **Injectivity required only at approval** — forward flow stays permissive;
   plans demand invertibility. Genuinely merging flows are refused with
   actionable fixes rather than heuristically split.
3. **Plan and actuals share one ledger table** — a planned column on the step
   ledger instead of a parallel plan table: one rebuild path, trivially
   reportable, at the cost of "plan rows at received 0" noise (hidden by the
   existing zero-row filter).
4. **Program stays user-owned and dia-keyed** — the solver only pre-seeds
   untouched rows and warns on drift; requirement-driven and program-driven
   flows coexist instead of a big-bang replacement (owner requirement 6).
5. **Two-attribute world (Dia, Colour) as an essdee constant** — no
   speculative N-attribute generality; the extension point (pin→pin-set) is
   named, not built.
6. **Conversion-step received mirrored into the program table** — small write
   duplication buys zero churn in the program grid and its balance semantics.
