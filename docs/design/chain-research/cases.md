# Generalized Fabric Chain — Case Catalogue

Grounded in (read 2026-07-04):
- `apps/essdee_yrp/essdee_yrp/fabric_ipd.py` (matrix generation, wildcard expansion, shapes)
- `apps/essdee_yrp/essdee_yrp/fabric_program.py` (Lot program + colour ledger)
- `apps/essdee_yrp/essdee_yrp/fabric_tracking.py` (GRN tracking, balance queries)
- `apps/essdee_yrp/essdee_yrp/api/work_order.py` (Calculate popup, matrix consumption)
- `apps/essdee_yrp/essdee_yrp/ipd_validations.py`, `ipd_ui.py` (cloth validation, approval flow)
- Child doctypes: `lot_fabric_detail`, `lot_fabric_program`, `lot_fabric_colour_program`,
  `ipd_knitting_dia_detail`, `ipd_dyeing_colour_detail`, `ipd_compacting_dia_detail`

## Vocabulary used below

- **Chain**: an ORDERED list of fabric steps on the cloth IPD, replacing the three
  hardcoded fields (`knitting_process` / `dyeing_process` / `compacting_process`).
  Proposed model: one child table `fabric_chain_steps` (idx = order, process link,
  shape read from the Process master) + one generic mapping child table
  `fabric_chain_mappings` (step ref, passthrough_value, from_value, to_value) —
  Frappe can't nest child tables, so mappings reference their step by idx/name.
  A step's SHAPE comes from the Process master exactly as today
  (`get_process_shape`): **conversion** (item change, knitting), **swap(attr)**
  (Colour or Dia value change), **identity** (no change).
- **State at position k**: the set of (Dia, Colour) combos that exist after step k,
  computed by pushing the knitting dias (or the IPD's Dia mapping for bought
  greige) forward through steps 1..k. This replaces today's hardcoded
  `derive_passthrough_values` ("dyeing needs knitting dias; compacting needs
  dyeing to-colours") with one generic rule: *a step's wildcard expansion and
  validation always use the incoming state, i.e. the cumulative output of the
  previous step*.
- **Matrix per occurrence**: `sync_fabric_process_matrices` generalizes to one
  IPD Process Matrix per chain STEP (not per fixed tab). Owner rule holds:
  matrices stay auto-generated, per-unit, never per-lot, never hand-authored.
- **Plan**: the back-computed per-lot expected quantities (requirement pushed
  backwards through the matrices). Lives on the Lot (demand never in matrices).

---

## Case 1 — Standard chain: knit → dye → compact (baseline, must not regress)

**Scenario.** Yarn → greige cloth per dia (ratio `cloth_per_kg_yarn`), Colour swap
per (dia?, from, to), Dia swap per (colour?, from, to). Exactly today's three tabs.

**What the model must do.**
- Represent it as chain rows: [conversion(knitting), swap-Colour(dyeing),
  swap-Dia(compacting)]. The three current builders (`_build_knitting_matrix`,
  `_build_value_swap_matrix` × 2) become two generic builders keyed on shape;
  outputs must be byte-identical matrices for this configuration.
- WO resolution: `get_fabric_process_kind(ipd, wo.process_name)` becomes
  `get_chain_step(ipd, wo.process_name)` returning the step row (with its idx
  and shape). Popup, tracking (`fabric_tracking.TRACKED_KINDS`) and program
  columns must keep working unchanged for this shape sequence.
- Migration: existing IPDs with the three fields/tables must load into chain rows
  (patch or on-load shim). Existing matrices regenerate on first save.

**Ambiguities / recommended rules.**
- *Where does `cloth_per_kg_yarn` + the dia list live?* On the conversion STEP
  (ratio field on the step row; dias as mapping rows with from_value = NULL),
  not as top-level IPD fields — otherwise a second conversion step could never
  exist. Keep the top-level fields as read-only aliases during migration.
- *Tab UI:* tabs are rendered FROM the chain rows (one tab per step, editor
  chosen by shape). Adding a step = appending a row; no new code. Preserve
  checkbox-mode fast entry per the standing rule.

---

## Case 2 — Re-compacting: knit → dye → compact(D22→D20) → compact(D20→D18)

**Scenario.** The owner's driving example. Cloth is compacted, then compacted
again. Two swap(Dia) steps in one chain; step 3 maps D22→D20, step 4 maps
D20→D18. "There may be another process too" — the model must take N occurrences.

**What the model must do.**
- Allow the same SHAPE twice; each occurrence is its own step row with its OWN
  mapping rows and its OWN matrix.
- Chain-order validation: step 4's from_dias must be ⊆ step 3's output state
  (D20 comes out of step 3, so D20→D18 is legal). Violation = save-time error
  naming the step and the unreachable from-value.
- Forward WO flow: availability for step k's input combo v =
  received(step k−1, v) − consumed(step k, v). This is exactly today's
  dyeing/compacting logic (`_add_planning_data`) stated once, generically.
- Ledger: today `Lot Fabric Colour Program` has TWO hardcoded columns
  (received_weight = dyed, compacted_weight = compacted). With N steps this
  breaks. Replace with a generic per-step ledger: `Lot Fabric Step Ledger`
  (cloth_item, process_name [unique per IPD, see below], dia, colour,
  planned_weight, received_weight) — server-owned, GRN-driven, rework-excluded,
  same atomic-increment write path as `_bump_program_rows`. Migrate the two old
  columns into rows for the dyeing/compacting steps.

**Ambiguities / recommended rules.**
- *Same Process master twice, or a distinct "Re-Compacting" master?* **Require a
  DISTINCT Process master per occurrence.** Three reasons already in the code:
  (a) `validate_cloth_ipd` forbids duplicates because the engine resolves
  matrices per process_name with subset attr matching — two steps sharing a
  master would cross-match groups; (b) the WO carries only `process_name`, so
  WO→step resolution must be unique per IPD; (c) the ledger and balance queries
  key on process_name. The owner's own language ("re-compacting" as a NEW
  process) matches this. The master carries the same shape (swap Dia); creating
  it is a one-time 30-second master entry, which respects "no rebuild per new
  process".
- *Does every D20 have to pass through step 4?* Yes — **totality rule**: every
  (dia, colour) combo entering a step must match exactly one mapping row.
  A combo that should pass through unchanged gets an explicit identity mapping
  row (from = to), pre-seeded by the UI. Silent skipping is forbidden: it makes
  the plan ambiguous and hides a physical step. (See Case 6 for the merge
  consequence of this rule.)
- *Matrix key:* keep (ipd, process_name) as the resolution key (unique by the
  distinct-master rule) but stamp the step idx on the matrix for readability
  and ordering.

---

## Case 3 — Re-dyeing / topping: second Colour swap

**Scenario.** knit → dye(Ecru→Rose) → dye2/topping(Rose→Maroon) → compact; or
topping AFTER compacting. Some colours topped, others sold as first-dyed.

**What the model must do.**
- Identical mechanics to Case 2 with attr = Colour: dye2's from-colours must be
  ⊆ dye1's output state; untopped colours get identity rows (Rose→Rose absent ⇒
  Rose demand cannot pass dye2 — totality forces the explicit row).
- Position sensitivity: if dye2 sits after compacting, its dia-passthrough
  expansion uses POST-compacting dias; before compacting, pre-compacting dias.
  The cumulative-state rule (Vocabulary) handles both with no special code.
- Greige colour options for the knitting popup (`_knit_colour_options`) must
  read the FIRST colour-swap step's from-colours, not "the dyeing tab".

**Ambiguities / recommended rules.**
- *Is topping a different Process master than dyeing?* Yes, same rule as Case 2.
- *Chemical reality (topping consumes dye recipes etc.)* — out of scope; the
  chain models cloth variants and kgs only, v1 stays 1:1.

---

## Case 4 — Identity process mid-chain (washing between dyeing and compacting)

**Scenario.** knit → dye → wash → compact. Washing changes no attribute and no
item; deliverable = receivable.

**What the model must do.**
- Allow identity-shape steps IN the chain at a position. Because the owner's
  rule is "ALL quantity calculations flow through IPD Process Matrix", an
  in-chain identity step gets an AUTO-GENERATED matrix too: one group per
  incoming (dia, colour) combo, input attrs = output attrs, qty 1:1. The common
  back-compute and the popup then treat every step uniformly (no `identity:`
  special key, no union derivation for in-chain steps).
- Its combos come from the exact state at its position — narrower and more
  correct than today's UNION derivation in `_identity_qty_rows` (which offers
  every dia/colour the IPD has ever mentioned because it has no position).
- It participates in the ledger and in availability gating: compact's available
  = washed received − compact consumed.

**Ambiguities / recommended rules.**
- *Do today's out-of-chain identity processes (`ipd_processes` rows, e.g. a
  yarn-doubling service) survive?* Yes — keep both flavours: **in-chain
  identity** (positioned, matrix-backed, tracked) and **off-chain identity**
  (today's `get_identity_process_row` behaviour: union combos, no matrix, no
  tracking) for ad-hoc services on the cloth or yarn. Validation: a process may
  appear in only one of the two places.
- *Should washing receipts gate compacting?* Physically yes; recommend yes for
  in-chain steps (uniformity is simpler than a per-step "gates next step"
  flag). If the mill doesn't GRN washing, the owner simply doesn't put washing
  in the chain. This is the deciding heuristic to give users: *in the chain iff
  you GRN it per lot.*

---

## Case 5 — Bought greige (no knitting step)

**Scenario.** Chain = dye → compact (first step is a swap). Greige cloth is
purchased, not knitted. Already half-supported today (dias fall back to the
IPD's Dia mapping; dyeing `available` = None).

**What the model must do.**
- Chain may start with any shape; "state at position 0" = the IPD's Dia mapping
  values (today's fallback in `derive_passthrough_values` / `_ipd_dias`).
- Back-compute (Case 6) still runs: the FIRST step's back-computed INPUT demand
  becomes the **procurement figure** — "buy this many kg greige per dia (per
  greige colour)". Store it as plan rows with a pseudo-step "Procurement"
  (process_name NULL) so the purchase team reads it off the Lot.
- No `Lot Fabric Program` rows to enter (that table is the knitting program);
  first-step availability stays None (stock-driven, warn-only) as today.

**Ambiguities / recommended rules.**
- *Should first-step availability check actual purchased stock?* Not v1 —
  matches today's `available = None` for bought greige. Revisit when stock
  lookups per lot-dimension are wanted.
- *Cloth with NO chain at all* (fully bought finished cloth): requirement rows
  are pure procurement; back-compute degenerates to copying the requirement
  into procurement plan rows. Allow it — zero extra code if the loop just runs
  over zero steps.

---

## Case 6 — Backward chaining from the requirement (THE core computation)

**Scenario.** Lot requirement: finished cloth (Red, D18, 100 kg; Blue, D20,
50 kg). Chain: knit(D22,D24) → dye(Ecru→Red@*, Ecru→Blue@*) → compact
(D22→D18, D24→D20). Wanted output: greige kg per dia, yarn kg, and per-step
expected in/out — "the IPD Process Matrix will generate that automatically".

**What the model must do.**
- One common function, e.g. `build_fabric_plan(lot, cloth)`:
  1. Load requirement rows for the cloth: demand = {(dia, colour): kg} at the
     chain END.
  2. For each step from LAST to FIRST: for every demanded output combo, find
     the matrix group whose OUTPUT attrs equal the combo (matrices are fully
     expanded, so exact-match works — same trick `_matrix_qty_rows` relies on);
     accumulate input demand: `in_kg += out_kg × (in_qty / out_qty)` per group
     (exactly the scale rule `calculate_fabric_deliverables` uses — wastage_pct
     folds in automatically when it stops being 0). Record planned OUT kg per
     group as the step's plan rows.
  3. At the conversion step the input is the attr-less yarn:
     `yarn_kg = Σ greige_kg / cloth_per_kg_yarn`. The conversion step's OUTPUT
     demand per dia IS the suggested knitting program.
- It must read ONLY the matrices for quantities (owner requirement 2). The
  chain rows are used for ordering and step→matrix lookup, never for math.
- Runs per (lot, cloth); idempotent delete-and-rebuild of the plan rows
  (mirror `sync_fabric_process_matrices`'s idempotency style).

**Ambiguities / recommended rules.**
- **Merge ambiguity, Dia**: two rows in ONE step share a to-value
  (D22→D18 and D20→D18). Reversing 100 kg of D18 has no deterministic split.
  **Rule: injectivity per (step, passthrough value)** — at save/approval,
  duplicate to-values within a step for the same pin are a HARD ERROR with the
  fix spelled out ("D18 is produced by two rows; pin them to different colours,
  chain them as two compacting steps, or remove one"). Physical merges are
  still expressible as a LONGER chain (D22→D20 in step 3, D20→D18 in step 4 —
  outputs merge ACROSS steps, which reverses fine because each step stays
  injective... but note: totality then requires knitted D20 to also pass step 3,
  and D20→D20 would collide with D22→D20. If both D22 and D20 are knitted and
  both end at D18, that flow is genuinely non-invertible — the error message
  should suggest splitting into two cloths/IPDs or dropping one source dia).
- **Merge ambiguity, Colour**: Ecru→Black and White→Black at the same dia is
  explicitly legal in today's FORWARD flow (comment in
  `calculate_fabric_deliverables`). For back-compute it is the same hard error
  UNLESS the rows are pinned to different dias (Ecru→Black@D18, White→Black@D20
  is injective per pin and fine). Pinning is the disambiguation tool; forward
  flow stays permissive (warn, never block, per bench rule) but the PLAN
  requires invertibility at approval time.
- *Rounding*: plan kgs rounded to 3 decimals (matches tracking); division by
  ratio last to avoid drift.
- *Wastage later*: keep the math generic (read in_qty/out_qty/wastage_pct from
  combos) so v2 wastage is a data change, not a code change.

---

## Case 7 — Requirement combos with NO path (validation)

**Scenario.** Requirement asks for (Purple, D16) but no colour-swap row produces
Purple and/or no dia-swap row produces D16; or Purple exists only pinned to D18
while the requirement wants Purple@D16.

**What the model must do.**
- During back-compute, any demanded output combo with no matching final-step
  group (or any intermediate demand with no matching upstream group — pinning
  can strand a combo mid-chain) is collected and reported in ONE message:
  "No chain path produces Colour=Purple / Dia=D16 for cloth X — add mapping
  rows on IPD Y or correct the requirement."
- HARD BLOCK the requirement save / plan build (an unreachable requirement is a
  data error, not an operational over/under — the warn-only convention applies
  to balances, not to impossible routes).

**Ambiguities / recommended rules.**
- *Where is it raised?* Both places, same function: on Lot requirement save
  (fast feedback while typing) and on IPD approval (an IPD edit can strand an
  existing lot's requirement). Approval-time failure lists the affected lots.
- *Requirement stated mid-chain* (e.g. wanting greige-stage kgs as a
  deliverable): not v1. Requirement rows are always FINISHED-cloth terms —
  validate the combo against the final state set.

---

## Case 8 — Multiple cloths per lot

**Scenario.** A lot carries 2S Jersey and 1x1 Rib, each with its own IPD, chain,
requirement, and program.

**What the model must do.**
- Everything keys on (lot, cloth_item) exactly as today (`lot_fabric_details`
  is unique per cloth — keep `validate_unique_fabric_cloths`, extend its
  "cannot remove tracked cloth" check to the new step ledger and plan tables).
- Back-compute runs independently per fabric row; one cloth's validation
  failure must not block the other's plan (mirror the per-fabric try/except in
  `get_fabric_deliverable_context`).
- A WO's process may be step 2 for cloth A and off-chain identity for cloth B —
  per-fabric-row resolution (already the pattern) must survive generalization.

**Ambiguities / recommended rules.**
- *Shared yarn across cloths*: plan stays per-cloth; aggregate yarn demand is a
  display concern (sum plan rows), not a model concern.
- *One cloth, two lots*: independent by lot key — no change.
- *Mixed approval*: cloth A's IPD approved, B's not → plan exists for A only;
  B's popup shows "no plan" (Case 11), everything else works.

---

## Case 9 — Knitting ratio: the only non-1:1 step (v1)

**Scenario.** 1 kg yarn → 0.98 kg cloth (`cloth_per_kg_yarn`); every other step
1:1 until wastage arrives.

**What the model must do.**
- Keep the ratio ON the conversion step (Case 1) and IN the matrix (input qty 1,
  output qty = ratio per dia group — exactly `_build_knitting_matrix`). The
  back-compute must divide through the matrix quantities, never read the IPD
  field directly (owner requirement 2: matrices are the single quantity source).
- Yarn is attr-less in the matrix (variant chosen per WO) — the plan stores
  yarn as one figure per cloth (no dia on yarn); "in what dia" in the owner's
  words is answered by the greige CLOTH program per dia, which the plan yields.

**Ambiguities / recommended rules.**
- *Per-dia ratio?* Not v1 (one field today). The matrix format already supports
  it (output qty per dia group), so when needed it's a column on the knitting
  mapping rows + builder change — no consumer changes. Say so in the design doc
  to stop anyone hardcoding "the ratio" downstream.
- *Yarn override in the popup* (`yarn_qty`, valid only while the matrix has one
  input) must keep working; the plan's yarn figure is a suggestion, not a lock.

---

## Case 10 — Where the plan lives + how WO popups consume it

**Scenario.** The back-computed expected quantities must be visible per step and
drive popup prefills without breaking today's program-balance flow.

**What the model must do.**
- **Storage**: on the LOT (standing rule: demand on Lot/WO, matrices per-unit).
  Two server-owned pieces:
  1. `Lot Fabric Step Ledger` rows gain `planned_weight` (written only by
     `build_fabric_plan`), alongside GRN-owned `received_weight`. One table
     serves both plan and actuals per (cloth, process_name, dia, colour) —
     junior-readable and it makes the plan-vs-actual report a single table
     scan. Procurement/yarn figures are rows with process_name = NULL /
     "Procurement".
  2. `Lot Fabric Program` (knitting program) stays USER-EDITED — the owner
     explicitly keeps the program as the WO driver (req 6). The plan PRE-SEEDS
     it: on plan build, fill/refresh rows whose weight the user hasn't touched
     (weight == previous plan value or 0), and otherwise only WARN on drift
     (extend `_warn_program_below_ordered` with "program differs from plan").
     Never overwrite a user-entered figure silently.
- **Popup consumption** (`_add_planning_data`, generalized per step k):
  - `plan`      = planned_weight for the group's OUTPUT combo (new column).
  - `ordered`   = other WOs' receivables for this step (unchanged).
  - `available` = received(step k−1, input combo) − consumed(step k, input
    combo) (unchanged semantics, now uniform for all k>1; step 1 conversion
    uses the program table; bought-greige first step = None).
  - `prefill`   = knitting: program − ordered (UNCHANGED — program remains the
    driver); other steps: clamp(min(plan − ordered, available), ≥0) instead of
    today's plain `available` / 0. Over-plan entry warns, never blocks.

**Ambiguities / recommended rules.**
- *Why not a separate "Lot Fabric Plan" table?* One ledger table with a planned
  column beats two parallel keyed tables (no join drift, one rebuild path,
  `rebuild_fabric_tracking` zeroes only received columns). Rows created by the
  plan at received 0 are hidden from the read-only ledger view unless they have
  receipts or plan — the existing zero-row noise filter already does this.
- *Does the plan REPLACE program balances?* No. Program balance flow is
  untouched (req 6); the plan is an additional column + smarter prefill.

---

## Case 11 — What IPD approval gates exactly

**Scenario.** `approval_status` / `approve_ipd` exist (roles from MRP Settings);
today nothing fabric-side consumes them. Owner: "when the IPD is approved, a
common function back-computes the chain."

**What the model must do / recommended gates.**
- **Approval triggers plan builds**: on `approve_ipd`, run `build_fabric_plan`
  for every non-closed Lot whose fabric rows reference this IPD (and that has
  requirement rows). On Lot requirement save, build the plan only if the IPD is
  approved; otherwise save the requirement fine and show "plan pending IPD
  approval". Both paths call the ONE common function — no second code path.
- **Approval freezes the chain**: editing fabric chain rows / mappings of an
  Approved IPD flips `approval_status` back to Not Approved (server-side in
  validate, comparing chain fingerprint before/after) and msgprints that plans
  will rebuild on re-approval. Matrices still regenerate on every save (they
  must — they are derived data); the plan rebuilds only on re-approval so a
  half-edited IPD never emits a half-plan.
- **What approval does NOT gate** (keep the program-driven flow intact, req 6):
  WO creation, the Calculate popup, GRNs, program entry. An unapproved IPD
  simply shows no plan column / no prefill from plan. Warn ("IPD not approved —
  planning columns unavailable"), never block.

**Ambiguities / recommended rules.**
- *Cutting Approved vs Approved*: cloth IPDs only need the single "Approved"
  state; hide "Cutting Approved" for cloth IPDs (it is a garment concept).
- *Revert* (`revert_ipd_approval`): delete/zero the planned_weight rows of
  affected lots? Recommend: keep them (they document the last approved plan)
  but stamp the plan build with the IPD's modified timestamp; the popup shows
  "plan stale" when timestamps diverge. Cheap and honest.

---

## Case 12 — Editing the chain after production started (mid-lot IPD change)

**Scenario.** Knitting GRNs exist; the owner adds a re-compacting step, or
renames/removes a step, or changes a mapping row.

**What the model must do.**
- Matrices: wiped + rebuilt on save (today's behaviour). WO popups already
  defend against staleness (group keys re-resolved, "reopen the Calculate
  popup" errors). Already-calculated WOs keep concrete variant rows — safe.
- Ledger rows key on process_name: ADDING a step is clean (new rows appear via
  GRNs). REMOVING/REPLACING a step whose ledger rows carry receipts must warn
  (mirror the "cannot remove tracked cloth" rule — recommend warn + keep
  orphaned ledger rows visible, since receipts are historical fact; hard-block
  only removal of the conversion step when program receipts exist).
- `rebuild_fabric_tracking` must generalize: replay GRNs into whichever step
  each WO's process_name resolves to NOW; orphan receipts (process no longer in
  chain) land in a visible "unmatched" bucket rather than vanishing.

**Ambiguities / recommended rules.**
- *Reordering steps* with receipts on both: allowed (it's just data), but the
  availability math changes meaning; emit one loud msgprint listing steps with
  receipts. Plans rebuild on re-approval (Case 11).

---

## Case 13 — Colour introduced at knitting (multiple greige colours)

**Scenario.** Cloth has a Colour attribute; greige is knitted in Ecru AND White
(both are dye from-colours). Requirement: Black (from White), Navy (from Ecru).

**What the model must do.**
- Back-compute determines the greige COLOUR split per dia (reverse of the first
  colour-swap step). Plan rows for the conversion step therefore carry colour
  where the cloth has it: (dia, greige colour) → kg.
- `Lot Fabric Program` stays keyed by dia ONLY (today's table; the owner enters
  dia+weight). The per-greige-colour split is visible in the plan rows; at the
  knitting WO the colour is chosen per line exactly as today
  (`_knit_colour_options` = first swap step's from-colours). Program balance
  stays dia-total; the plan's colour split is advisory prefill data.

**Ambiguities / recommended rules.**
- *Should the program become (dia, colour)?* Not v1 — it would change the
  program table's key, the GRN bump path and the popup for a case the mill
  handles by operator choice today. The plan gives the numbers; revisit only if
  operators mis-split in practice.
- Knitting GRN tracking stays dia-keyed (`with_colour=False`) — unchanged.

---

## Case 14 — Two cloths, same Process master; process shared across IPD roles

**Scenario.** Cloth A's chain uses "Compacting" as step 3; cloth B's chain also
uses "Compacting"; a third garment IPD uses some process as an off-chain
embellishment. One WO (lot + process "Compacting") arrives.

**What the model must do.**
- Resolution is PER FABRIC ROW (today's loop in `get_fabric_deliverable_context`)
  — the same master may sit at different positions in different IPDs' chains.
  The distinct-master rule (Case 2) is per-IPD, not global.
- Garment IPDs must never enter the fabric path even when a Lot fabric row
  mis-points at them — keep the `is_cloth_ipd` guard from
  `get_identity_process_row` at the chain-resolution entry point.

**Ambiguities / recommended rules.**
- One WO covering the same process for BOTH cloths already works (one popup
  entry per fabric row); the plan columns are per (cloth, step) so no
  cross-talk. No new rules needed — just don't lose the per-row loop.

---

## Case 15 — Requirement entry: shape, validation, and its two-part nature

**Scenario.** Owner req 3: the Lot fabric entry = (a) knitting program (exists)
+ (b) final requirement: colour + dia + kg of finished cloth.

**What the model must do.**
- New child table `Lot Fabric Requirement`: cloth_item, dia, colour, weight —
  user-entered, part of the Vue island next to the program grid. Colour column
  hidden when the cloth has no Colour attribute.
- Validation on save: dia/colour must be values of the right attribute
  (reuse `_validate_attribute_value`); combo must be in the chain's FINAL state
  set (Case 7); duplicate (cloth, dia, colour) rows rejected; negative weight
  rejected; zero-weight rows dropped (mirror program-row handling).
- Requirement rows with downstream plan/receipts behave like program rows:
  removal warns/resurrects rather than silently orphaning the plan.

**Ambiguities / recommended rules.**
- *Units*: kg everywhere. Assert at IPD save that the cloth item's default UOM
  matches the yarn's stock UOM convention (both kg) — a mismatched UOM would
  silently corrupt every 1:1 step (matrix combos copy item UOMs today with no
  cross-check).
- *Requirement vs order quantities*: the requirement is fabric-side planning
  input only; no coupling to garment order tables in v1.

---

## Case 16 — Balances, over/under, and the warn-only doctrine applied to plans

**Scenario.** Program 500 kg, plan says 480; dyeing WO enters 520 against plan
480; GRN over-receives; requirement raised after WOs exist.

**What the model must do / rules.**
- Over-plan and over-program entry: WARN, never block (standing rule). The
  plan is a target, not a cap.
- Program < plan, program < already-ordered: extend the existing
  `_warn_program_below_ordered` pattern to "program below plan" and "plan below
  ordered" — same non-blocking msgprint style.
- Received columns stay server-owned; plan column stays plan-function-owned;
  user JSON payloads must never write either (extend the existing
  client-can't-touch guards to the new columns).
- Requirement raised late (WOs already exist): plan build simply lands mid-way;
  `ordered` already nets out, prefills clamp at ≥0. No special case needed —
  state it in tests.

---

## Cross-cutting invariants (the rules the design must enforce)

| # | Invariant | Where enforced |
|---|-----------|----------------|
| I1 | **Totality**: every combo entering a step matches ≥1 mapping row; pass-through is an explicit identity row (UI pre-seeds) | IPD save + approval |
| I2 | **Injectivity per (step, pin)**: no duplicate to-values for one passthrough value → chain reversible; pinning is the disambiguation tool | IPD save (extends `validate_swap_rows`) + approval |
| I3 | **Matrices are the only math**: every in-chain step (incl. identity) has an auto-matrix; all quantity code uses `in_qty/out_qty` (+wastage) scaling from matrix combos | builders + plan fn + popup |
| I4 | **Distinct Process master per chain occurrence** (per IPD) | `validate_cloth_ipd` generalized |
| I5 | **Plan is Lot data**: matrices per-unit rules; planned/received columns server-owned | plan fn + tracking guards |
| I6 | **Hard-block only data errors** (unreachable requirement, non-invertible mapping); balances warn only | Cases 6, 7, 16 |
| I7 | **Per-fabric-row WO→step resolution**; garment IPDs never enter the fabric path | chain resolution entry point |
| I8 | **Approval gates plan generation only**; chain edits un-approve; WO/GRN flow never gated | Case 11 |
| I9 | **State-at-position derivation** replaces all hardcoded "knitting dias / dyeing to-colours" lookups (wildcard expansion, identity combos, greige options, program dias) | one shared helper |
