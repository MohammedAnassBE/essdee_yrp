# Fabric Chain Commonization — Plan

> **2026-07-05 REVERSAL — user-added extra steps REMOVED.** The user found the
> chain-table tab (add arbitrary processes like Re-Compacting / Dye-Compact)
> confusing and of no use on the floor: "just remove the Item Production Detail
> tab itself… we will only manage knitting, dyeing, and compacting. If anything
> else arises we can work on it later." So the `fabric_chain_tab` custom field,
> the `fabric_steps` + `fabric_step_mappings` tables, and the `IPD Fabric Step` /
> `IPD Fabric Step Mapping` doctypes are DELETED. `get_fabric_steps()` now yields
> only the three tab steps; the multi_swap/identity matrix builders and chain
> mapping validation are gone. Everything ELSE the plan below built and still
> stands: the backward solver (`fabric_plan.py`), the Lot Fabric Requirement +
> Step Ledger, GRN tracking, matrix-driven WO popups, per-process template
> validation (`validate_fabric_process_shapes`). The chain is now fixed at
> knitting → dyeing → compacting, but still fully matrix/template-driven.

Date: 2026-07-04 · App: essdee_yrp (+ tiny base-yrp reads) · Status: **EXECUTED, then extra-steps feature removed 2026-07-05**
(P0+P1 core shipped: requirement entry, backward solver, approval trigger, step ledger,
chain-table extra steps incl. multi-attribute swaps; fresh-agent review fixes applied.
Deviation from plan: the three classic tabs stay VISIBLE (extra steps append after them via
the chain table) — full tab retirement deferred. Amendment: `multi_swap` shape added
(Dye-Compact: one process changing Colour AND Dia; mapping rows carry both From/To pairs).)
Research: `chain-research/` (constraint map, case catalogue, 3 competing designs, 2 critiques).
Chosen: **planning-engine design** (won the product critique), with the feasibility critic's
fixes and minimal-delta's phasing grafted in.

## What the user asked (2026-07-04 voice)

1. Commonize the IPD's FABRIC side (knitting→compacting) into a template/chain model —
   new processes (e.g. **re-compacting**) must be user-addable, no code. Garment side untouched.
2. ALL quantity math flows through **IPD Process Matrix** — no side calculation functions.
3. The Lot's fabric entry = TWO things: the **knitting program** (dia+kg, as today) AND the
   **final requirement** (colour + dia + kg of finished cloth).
4. On **IPD approval**, a **common function** back-computes the chain from the requirement
   via the matrices ("Red 18-dia N kg → how much greige, what dia, how much yarn").
5. Matrices combine stage-to-stage per dia/colour ("greige in 18 dia → dyed in 18 dia").
6. The current WO popup / program balances / GRN ledger flow keeps working.

## Target model

### IPD (replaces the three fabric tabs — one release of coexistence)

- **`IPD Fabric Step`** (ordered child table, one row per chain step):
  `process` (Link Process, distinct master per step — "Re-Compacting" is its own Process),
  shape read live from the Process master (`is_item_conversion` / `value_change_attributes`),
  conversion fields `input_item` + `output_per_input` (kg cloth per kg yarn) on conversion rows,
  `pin_wise_entry` Check (dia-wise / colour-wise mode).
- **`IPD Fabric Step Mapping`** (one generic table for every swap step):
  `process`, server-stamped `pin_attribute`, `pin_value`, `from_value`, `to_value`.
  Passthrough is explicit (from = to), rendered as ONE PRE-TICKED CHECKBOX per incoming
  value ("passes through unchanged") — checkbox-mode entry, no typing.
- The existing `FabricSwapDetail` widget is reused per step (already config-driven); step
  headers in plain words: *"Step 4 — Re-Compacting (changes Dia), after Compacting"*.
- **Chain state walker** `fabric_chain.py`: `combos_entering(step)`, `values_entering(step,
  attribute)`, `final_combos(ipd)` — ONE primitive replacing all six chain-order hardcodes
  found in the constraint map (passthrough derivation, availability's "previous stage",
  widget seeding, identity unions, knit colour options, program dias).

### Matrix generation (unchanged doctype, one loop)

`sync_fabric_process_matrices` becomes: for each step, dispatch by shape —
`_build_conversion_matrix` / `_build_swap_matrix` (today's already-generic builder, pin
values fed from the state walker) / `_build_identity_matrix` (new, 1:1, for in-chain
washing — "in the chain iff you GRN it"; ad-hoc `ipd_processes` identity stays for services).
Pin stamping from actual upstream state IS the user's "combination": dyed Red@D18 groups
only exist fed by greige@D18.

### Lot

- **`Lot Fabric Requirement`** (user-entered): cloth, dia, colour, kg — validated against
  `final_combos` (unreachable combos hard-block with one aggregated message; data error,
  not a balance). Grid gets per-colour + grand-total footer.
- **`Lot Fabric Step Ledger`** (long format, replaces the fossilized Dyed/Compacted columns):
  cloth, `process` (blank = chain input/procurement), dia, colour,
  `planned_weight` (solver-owned) + `received_weight` (GRN-tracking-owned) + Balance column.
  Migration maps today's two columns to step rows.
- **Knitting program stays user-edited and stays the WO driver** (user's req 6). The solver
  PRE-SEEDS untouched program rows and warns on drift — never overwrites user numbers.
- Plan badge on the island + popup, in words with a date: "Plan ready 04-07" /
  "Plan waiting for IPD approval" / "Plan outdated — IPD changed". Never a bare enum.

### The common function (the heart)

`solve_chain_backward(ipd, requirement)` in `essdee_yrp/fabric_plan.py`:
walk steps LAST→FIRST; match each demand combo to a matrix group by OUTPUT attrs;
`in_kg = out_kg × in_qty/out_qty` (same rule the popup engine uses — matrices are the only
quantity source, so wastage later = data change, zero code). Conversion step divides via the
matrix, ending in yarn kgs + per-dia greige (the knitting program suggestion).

Feasibility-critic fixes baked in:
- **Carry non-declared attrs** through steps whose matrix doesn't mention them (minimal-delta's
  walk spec — prevents false "unreachable" on unpinned mid-chain swaps).
- **Ambiguity detection IN the solver** (duplicate output projections → error listing the rows
  to pin), not only at approval — protects grandfathered Approved IPDs.
- Injectivity per (step, pin) enforced at approval for NEW approvals (pinning is the
  disambiguation tool); genuinely non-invertible flows error with "lengthen the chain or
  split cloths".
- Plan build triggered EXPLICITLY from `approve_ipd` (per-lot try/except — approval never
  fails because of someone else's lot; failures listed in one msgprint that also shows the
  computed figures: "Approved. FAB-0007: 102.04 kg yarn, D22 100 kg…") and from requirement
  save when the IPD is already Approved. IPD chain edits flip plans to Stale (status, never a
  save-block; rebuild only when requirement/fabric rows actually changed).
- WO/GRN/popup are NEVER blocked by plan state (warn-only doctrine).

### WO popup / tracking fit

- Popup shapes collapse to server-sent stage-neutral planning parts (Desk dialog + /web modal
  render the same payload — they literally cannot disagree).
- Prefills: knitting unchanged (program − ordered); other steps `min(plan − ordered,
  available)` clamped ≥0 — and dyeing keeps prefill = 0 **unless a plan row exists** (preserves
  the user's earlier decision until the plan feature supplies real numbers).
- `fabric_tracking` routes by step (process_name) into the long ledger; balance queries stay
  on the already-generic `_sum_by_attributes`.

## Build sequence

- **P0 (headline first, ~1 session):** `Lot Fabric Requirement` grid + `fabric_plan.py` solver
  + approval trigger, running over a NORMALIZER that reads the existing three tabs
  (`get_fabric_chain(ipd)` synthesizes steps from today's fields). User sees: approve IPD →
  yarn/greige figures on the Lot. Zero migration.
- **P1:** `IPD Fabric Step` + generic mapping table + state walker + generic matrix builders;
  three tabs auto-migrate to step rows, old tabs HIDDEN (not deleted) for one release;
  approvals not reset; plans build lazily. Re-compacting becomes user-addable here.
- **P2:** long-format `Lot Fabric Step Ledger` (migrating Dyed/Compacted columns), popup
  prefills from plan rows, stage-neutral popup payload, /web parity, remove hidden tabs.
- Each phase ends with the full browser drive (Lot → knit → dye → compact → re-compact WO
  chain with GRNs) + fresh-agent code review, per bench rules.

## Decisions taken on the user's behalf (flag if wrong)

1. Distinct Process master per chain occurrence (Re-Compacting ≠ Compacting) — required by
   matrix keying; also what makes WO process selection unambiguous on the floor.
2. Knitting program is never auto-overwritten — solver seeds/warns only.
3. In-chain identity steps get real matrices + ledger rows; off-chain identity services stay
   matrix-less.
4. Requirement colours are FINAL colours; greige colour split stays advisory (operator picks
   at knitting WO, as today).
5. Bought greige: chain starts at a swap; the first step's back-computed input becomes a
   procurement figure on the ledger (process blank).
