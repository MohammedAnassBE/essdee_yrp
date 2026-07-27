# SD Lot → Cloth Production Detail (CPD) Auto-Builder — Architecture & Plan

**Feature (2026-07-21):** a button on the SD Lot opens a popup that lists the garment's cloth items, asks which yarn produces each, then auto-creates each cloth's Item Production Detail ("CPD"), auto-calculates knitting + dyeing, and pre-fills the per-colour quantity split from the Lot's order quantity — so users stop hand-authoring the cloth IPD and the colour/qty split.

> Source: analysis workflow `cpd-from-lot-analysis` (run wf_41d0ff81-7a3), 9 agents. Grounded in a full read of the essdee_yrp fabric chain + base yrp + production_api reference.

---

## 1. Verdict — will it be correct this way?

**Mostly yes, with two clearly-bounded exceptions.** The whole downstream engine you'd rely on already exists and is proven; the feature is an *orchestration layer* plus one ported calculation plus a small data-capture decision.

| Step | Feasibility | Notes |
|---|---|---|
| 1. Button on SD Lot | Yes, as-is | Clone `add_custom_button` (Desk) / `moreMenuModel` (web). |
| 2. Popup lists cloth items | Yes, as-is | Source = garment IPD `cloth_detail[].cloth`; filter `is_cloth_item=1`. |
| 3. Popup asks which yarn | Yes, as-is (input) | Yarn = a non-cloth Item; no `is_yarn` flag today. |
| 4. Auto-calc knitting + dyeing from yarn | Partial — needs data | Matrix build is **free** once the CPD tabs are filled, but the *process/ratio/greige are not derivable from the yarn* — nothing maps yarn→process. |
| 5. Per-colour qty pre-fill from order qty | Net-new + precondition | Requires porting `calculate_cloth`; depends on the garment IPD Cutting tab being populated. |
| 6. Fully auto, no manual entry | Achievable after 4+5 | Becomes "derive from garment IPD + a yarn profile", not "from a bare yarn pick". |

### Why steps 4 and the tail of 5 are free once fed
Verified in code:
- **Knitting/dyeing auto-calc:** `fabric_ipd.synthesize_fabric_processes_from_tabs` (fabric_ipd.py:337) + `sync_fabric_process_matrices` (fabric_ipd.py:524) rebuild the `IPD Process Matrix` docs on **every** cloth-IPD save, from `yarn_item` + `cloth_per_kg_yarn` + `knitting_dia_details` + `dyeing_colour_details`. Knitting = a conversion row (input=`yarn_item`, ratio=`cloth_per_kg_yarn`, Introduce Dia per dia row); Dyeing = Colour Change + Dia Pin. **This is the "auto-calculate knitting and dyeing" the user wants — it needs no new code, only correctly-populated child rows.**
- **Qty back-solve:** `fabric_plan.solve_chain_backward` / `build_fabric_plan` (fabric_plan.py) walk the matrices backward from `lot_fabric_requirements` (dia, colour, kg) down to yarn kg, then `_preseed_knitting_program` seeds the per-dia knitting program. Runs automatically on `Lot.on_update → rebuild_plans_after_save`, **only when the CPD `approval_status == "Approved"`**.

---

## 2. Where the auto-derivation breaks down (precisely)

### Break point A — `yarn_item → (knitting_process, dyeing_process, compacting_process, cloth_per_kg_yarn, greige_colour)`
**This mapping does not exist.** Confirmed: `Item` has only `is_cloth_item` (fixtures/custom_field.json:668) and `product_category`; there is **no** `is_yarn` flag and **no** yarn-side process/ratio field anywhere. The relationship is stored **inverted** — the cloth IPD holds `yarn_item` + `knitting_process`/`dyeing_process`/`compacting_process` + `cloth_per_kg_yarn`, pointing *back* at the yarn. `validate_cloth_ipd` (ipd_validations.py:90) even *requires* `cloth_per_kg_yarn > 0` for knitting, but nothing supplies it from the yarn.

Consequence: **"auto-calculate the knitting/dyeing process from the selected yarn item" is impossible from the yarn alone today.** The yarn only ever fixes the knitting *input item*; the process identities, the conversion ratio, and the greige colour must come from somewhere.

**Fix — capture it once, on the yarn (recommended):** add a small yarn PROFILE (custom fields on `Item`):
`is_yarn_item` (Check), `default_knitting_process` / `default_dyeing_process` / `default_compacting_process` (Link Process), `default_cloth_per_kg_yarn` (Float), `default_greige_colour` (Link Item Attribute Value). Then the popup reads these from the chosen yarn and "auto from yarn" is literally true, with a per-cloth override in the popup. (Alternative: capture in the popup every time, prefilling by reverse-querying any existing CPD whose `yarn_item` = the pick — but that's circular for a brand-new cloth.)

### Break point B — `total order qty → per-(cloth, dia, colour) KG`
The **piece-level colour/size split already exists**: `Lot.calculate_order → calculate_order_details` (lot.py:171) explodes `Lot.items` across the garment IPD `packing_attribute` + `packing_attribute_details` into `lot_order_details`. But that's **pieces**, not cloth **kg**.

The kg conversion — `calculate_cloth` / `get_cloth_combination` / `get_stitching_combination` — **exists only in `production_api`** (item_production_detail.py:660/779/808) and is **not ported** to yrp/essdee_yrp (grep: zero hits). It reads the garment IPD's Cutting tab: `cutting_items_json` (per-piece Dia+Weight), `cutting_cloths_json` (piece→cloth label), and the stitching combination (per-panel colour + panel count), and returns `{cloth_type, colour, dia, weight}` which `get_calculated_bom` aggregates into `cloth_details[(cloth Item, colour, Dia)] += weight` (item_production_detail.py:618-624).

**Fix — port it** into a new `essdee_yrp/fabric_requirement.py`, writing results to `lot_fabric_requirements` instead of a BOM. **Precondition:** the garment IPD Cutting tab must be populated (open question 5).

### The ordering trap (and how the design avoids it)
`save_fabric_requirement_details` (fabric_program.py:297) **hard-blocks** any requirement `(dia,colour)` not in `final_combos(ipd)`. So the CPD must exist, be saved (matrices built) and be *reachable* **before** requirements are written. **The plan runs the qty split first, then seeds the CPD's `knitting_dia_details`/`dyeing_colour_details` from exactly the demanded tuples, so reachability is guaranteed by construction.**

---

## 3. Recommended design (merge of A + B)

Take **Design A's minimal footprint** (one button, one popup, one whitelisted method, reuse the engine) and adopt **Design B's yarn profile** (so step 4 is real and multi-fabric works). Reuse everything downstream unchanged.

### 3.1 Data model
**New (small fixture) — yarn profile on `Item`:** `is_yarn_item`, `default_knitting_process`, `default_dyeing_process`, `default_compacting_process`, `default_cloth_per_kg_yarn`, `default_greige_colour`.

**Reused, no schema change:**
- Cloth list source: garment IPD `cloth_detail` → *Item Production Detail Cloth Detail* (`name1`, `cloth`, `is_bom_item`, `required_gsm`).
- The **CPD** = an `Item Production Detail` on the cloth item with existing custom fields: `is_cloth_item`, `yarn_item`, `cloth_per_kg_yarn`, `knitting_process`+`knitting_dia_details`, `dyeing_process`+`dyeing_colour_details`, `compacting_process`+`compacting_dia_details`.
- Lot attach point: `lot_fabric_details` → *Lot Fabric Detail* (`cloth_item`, `production_detail`, `plan_status`…). One row per cloth (enforced by `validate_unique_fabric_cloths`).
- Qty pre-fill target: `lot_fabric_requirements` → *Lot Fabric Requirement* (`cloth_item`, `dia`, `colour`, `weight`).
- Auto-populated downstream (untouched): `lot_fabric_programs`, `lot_colour_programs`, `lot_fabric_step_ledger`, `IPD Process Matrix`.

### 3.2 Server methods (net-new)
1. `essdee_yrp/fabric_requirement.py` — port of `calculate_cloth`/`get_cloth_combination`/`get_stitching_combination`. Entry: `compute_cloth_demand(lot_doc) -> {(cloth_item, dia, colour): kg}` over `lot_order_details` × garment IPD Cutting data.
2. `essdee_yrp/cloth_program.py::build_cloth_programs(lot, selections)` (whitelisted; also thin-wrapped in `lot.py` for the Desk convention `essdee_yrp.essdee_yrp.doctype.lot.lot.build_cloth_programs`). Pipeline:
   - **Phase 1 — split:** `demand = compute_cloth_demand(lot)`; gives each cloth its distinct dias and (dia→colours).
   - **Phase 2 — per selected cloth:** find-or-create CPD; stamp `yarn_item`, `cloth_per_kg_yarn`, `knitting_process`/`dyeing_process`/`compacting_process` from `selection` (defaulting to the yarn profile); build `knitting_dia_details` from the demanded dias and `dyeing_colour_details` `{dia, from_colour=greige, to_colour=colour}` from the demanded (dia,colour) tuples; `save()` (matrices auto-rebuild); set `approval_status="Approved"` (decision — open Q2).
   - **Phase 3 — attach:** append a `lot_fabric_details` row (cloth_item + CPD) if absent.
   - **Phase 4 — requirements:** set `lot_doc.fabric_requirement_details` JSON from Phase-1 demand and `lot.save()` → `before_validate.save_fabric_requirement_details` writes `lot_fabric_requirements` (reachability now guaranteed).
   - **Phase 5 — plan (existing):** `on_update.rebuild_plans_after_save` → `build_fabric_plan` → `solve_chain_backward` → step ledger + knitting-program pre-seed.
3. Small helpers: `get_cloth_program_context(lot)` (one row per garment cloth_type: `name1`, `cloth_item`, suggested yarn, defaults) to drive the popup.

### 3.3 UI flow
**Desk (lot.js `refresh`):** `frm.add_custom_button(__("Build Cloth Programs"), openDialog)`, gated `!is_new && production_detail && production_order`. Dialog = `frappe.ui.Dialog` (shape of the Duplicate-IPD dialog): one row per garment cloth — cloth label (read-only) + `yarn_item` Link (filter `is_yarn_item:1`, prefilled) + `cloth_per_kg_yarn` + a live derived-process preview. Primary action → `frappe.call(...build_cloth_programs, {lot, selections})`, `freeze:true`, callback `frm.reload_doc()`.

**/web (DocDetail.vue):** add one `moreMenuModel` isLot entry `{label:"Build Cloth Programs", command:()=>clothProgramOpen.value=true}` (beside "Calculate Order Items"); mount a `ClothProgramModal.vue` cloned from `FabricDeliverablesModal.vue` (`<Dialog @show=loadContext>` → `callMethod("...get_cloth_program_context")`, `LinkField` for yarn, footer primary → `callMethod("...build_cloth_programs")` → `emit("built")` → parent `reloadView()` + `hydrateLotForView()`).

**Result:** open Lot → *Build Cloth Programs* → confirm yarn per fabric → the Lot reloads showing Fabric Detail rows (plan_status **Built**) with auto-filled per-colour/dia requirement, per-dia knitting program, dyeing split, and yarn kg — repeatable across N fabrics (rib + cotton).

---

## 4. Phased plan

- **Phase 0 — decisions:** resolve open questions 1–7 (esp. yarn-profile vs popup, auto-approve, cutting-data availability). *Blocking.*
- **Phase 1 — data & split:** add the yarn-profile fixture on Item; port `calculate_cloth` into `fabric_requirement.py`; unit-test `compute_cloth_demand` against a live garment IPD with populated Cutting data.
- **Phase 2 — orchestrator:** `cloth_program.build_cloth_programs` + `get_cloth_program_context`; verify CPD save rebuilds matrices, requirement write passes reachability, and the plan/program/ledger populate. Idempotency: re-run re-splits and re-solves without duplicate CPDs or rows.
- **Phase 3 — Desk UI:** button + dialog in lot.js; drive a real Lot end-to-end (fill/click, read rendered rows, check Error Log).
- **Phase 4 — /web UI:** moreMenu entry + ClothProgramModal; verify parity via `pw-shot.mjs`.
- **Phase 5 — QA/review:** multi-fabric lot, thin-Cutting-data fallback, GRN writeback still tracks. **This exceeds 50 lines across the bench → invoke `superpowers:requesting-code-review` before claiming done (CLAUDE.md rule #6).**

---

## 5. Open questions (decision-shaped)
1. ~~**Yarn→process capture**~~ — **DECIDED 2026-07-21: capture in the Lot popup** (no yarn-profile fixture on Item). See §7.
2. **Auto-approve the CPD** (plan runs immediately, true zero-manual) vs leave **Pending Approval** for a human gate before it drives procurement?
3. **One CPD per cloth Item** (shared) vs per-(cloth,yarn)/per-Lot — can the same cloth ever use two different yarns? (If yes, yarn moves onto Lot Fabric Detail.)
4. **Piece-dyed vs yarn-dyed:** is there a greige→dye step (needs a greige from_colour) or is colour fixed at knitting (no dyeing rows)?
5. **Is the garment IPD Cutting tab populated** on essdee_yrp.site? The qty→kg split is impossible without it.
6. **Weight semantics:** is `cutting_items_json` Weight already kg/piece, or derived from `required_gsm` × area?
7. **Sign-off:** this reverses the **locked 2026-07-02 decision #1** ("manual fabric table — never auto-seeded from cloth_detail"). Confirm the reversal.

---

## 6. Risks
- Promising "processes fall out of the yarn" before the data-capture decision (Break point A) is made.
- Thin/absent garment IPD Cutting data silently breaking the kg split — must guard + fall back to manual.
- Auto-approve bypassing the human matrix gate.
- Shared-CPD dia/colour accretion across garments.
- >50-line change → mandatory code review.

---

## 7. Decisions log

- **2026-07-21 — Q1 (yarn→process capture): CAPTURE IN THE LOT POPUP** — not a yarn-profile fixture on Item. This resolves Break point A the Design-A way: the popup, per cloth, asks `yarn_item` + `knitting_process` + `dyeing_process` (+ `compacting_process`) + `cloth_per_kg_yarn` + greige `from_colour`, optionally prefilled by reverse-querying an existing CPD that uses the same yarn. **Drop the §3.1 yarn-profile custom fields** (`is_yarn_item`, `default_*`). Net effect: smaller footprint, but the operator supplies the process/ratio/greige each time (with prefill) rather than it being a one-time master.
- **2026-07-21 — Q2 (approval): AUTO-APPROVE.** The built CPD is set `approval_status="Approved"` so `solve_chain_backward` runs immediately (true zero-manual). No human gate.
- **2026-07-21 — Q3 (yarn↔cloth cardinality): 1:1.** One cloth is knitted from exactly one yarn. One CPD per cloth item with `yarn_item` on the cloth IPD is sufficient — **Design A confirmed; do NOT move yarn onto the Lot fabric row (Design B dropped).** The CPD is shared across Lots (dia/colour rows accrete by union).
- **2026-07-21 — Q4 (dyeing): PIECE-DYED.** Knitted greige cloth goes to dyeing, so `dyeing_colour_details` ARE built. Both the **colours and the dias come from the garment IPD Cutting tab**, and the **(dia × colour) combinations in the Cutting tab** define the dyeing rows: `from_colour = greige` (from the popup, Q1), `to_colour` = the cutting-tab colour, per dia. This is the same tuple set the qty→kg split produces, so the CPD's dyeing rows and the Lot requirements stay reachable by construction.
- **2026-07-21 — Q5 (Cutting tab populated): CONFIRMED (per user).** essdee_yrp.site syncs from F15; the Cutting tab IS populated. Example garment IPD: **`437765-LADIES NIGHT SET`** — Cutting tab shows **two cloth items** with their **dias**. **Refined data sourcing:** fetch **DIA from the Cutting tab**; fetch **panel-wise COLOURS from the Stitching tab combination** (NOT the packing tab — user corrected). So the port reads dia via `cutting_items_json`/`cutting_cloths_json` and colour via `get_stitching_combination` (per-panel colour + count). Verifying against the live record before building.
- **2026-07-21 — Q6 (weight semantics): RESOLVED.** On live record `437765-Ladies Night Set-1`, `cutting_items_json` Weight = 0.263 / 0.246 → **already KG per piece**, used directly by the split; `required_gsm` (150) is NOT needed for the qty→kg calc.
- **2026-07-21 — Scope confirmation:** the endgame is to **auto-calculate the Work Order AND the cloth IPD (CPD)** from this flow. The CPD build feeds the existing program/plan engine (`build_fabric_plan` → `solve_chain_backward` → `_preseed_knitting_program`) which drives WO deliverables/receivables — so "auto CPD" and "auto WO" are both in scope and both reuse the existing downstream engine (no new WO calc).
- **2026-07-21 — LIVE DATA VERIFIED on `437765-Ladies Night Set-1`** (garment IPD, essdee_yrp.site):
  - `cloth_detail` (2 rows) = the popup's cloth list: `{name1, cloth (Item), required_gsm, is_bom_item}` — e.g. `Main Fabric → Polyester Velour Fabric @150gsm`; `cutting_cloths_json.select_list = [Main Fabric, Piping Fabric]`.
  - `cutting_items_json.items[] = {Part, Dia, Weight}` — Dia per part (`Top/Bottom → 60 Dia`), Weight = kg/piece (see Q6).
  - `cutting_cloths_json.items[] = {Part, Cloth}` maps each cutting Part → cloth label (→ `cloth_detail.cloth` Item).
  - **Panel-wise COLOUR = `stiching_item_combination_details[].attribute_value`** (16 rows; `set_item_attribute_value` = panel, `major_attribute_value` = set colour) — confirms "colours from the stitching combination". This record is single-colour White.
  - Finished/dye colour also visible via `packing_attribute='Colour'` + `packing_assortment_json` (sizes × qty per colour box).
  - The cloth-mode CPD fields (`cloth_per_kg_yarn`, `knitting_dia_details`, `dyeing_colour_details`, `compacting_dia_details`, `dia_wise_colour_change`, `colour_wise_dia_change`) live on the SAME doctype — the CPD is a separate `Item Production Detail` on the cloth Item with `is_cloth_item=1`.
  - **Net — `compute_cloth_demand`:** for each ordered piece → for each cutting Part accumulate `(cloth Item [via cutting_cloths_json], Dia [via cutting_items_json], colour [via stitching combination]) += Weight(kg)`. All inputs confirmed present.
- **2026-07-21 — Q7: SIGNED OFF** (user proceeded to implementation planning).
- **2026-07-21 — MULTI-IPD VALIDATION (owner-mandated, after single-sample correction):** swept **all 417 garment IPDs / 10 shape families** on essdee_yrp.site, incl. all **33 Aishwarya IPDs** (Plain/Print/S-Box/O.E — family F4, ~10× larger than the 437765 family). F4 shape: cutting keyed **(Size, Panel)** — not Part; **dia varies by size AND by panel within a size** (13–20 Dia); **Pouch stitched ×2** (`stiching_item_details.quantity=2`); ONE cloth (`40's GL Dyed Fabric New`) across ~8 dias × 5 colours; 1 sibling (PRINT O.E-1) keys cloths by **(Colour)**. The generic `cutting_attributes`-driven port handles all families; per-full-cutting-key dia cardinality is 1 site-wide. **5 breaks found → 10 amendments applied to the plan:** (1) **shared-cloth CPD re-seed was destructive** — 50/81 cloth Items serve >1 garment (Lycra Rib: 24 garments; the Aishwarya cloth: 7) → seeding is now ADDITIVE union-merge; (2) 25 empty-draft IPDs (10 live Lots) crashed KeyError → `_validate_garment_ipd` clear-error guard; (3) unresolvable cloth labels silently dropped (UL-34807, Lot F0624-48) → now throw; (4) zero-demand popup cards (22 IPDs incl. 437765's Piping Fabric) + duplicate label→same-Item rows → popup filters to demanded cloths + dedupes; (5) gram-scale weights (EC Ryan Hoodie Weight=257) → non-blocking warning. Plus: accessory demand (66% of IPDs) recorded as IN scope (production_api parity), Aishwarya F4 fixtures/tests + mandatory Aishwarya E2E drive + empty-draft negative drive added; colour labels drift between sibling IPDs ('Military Green' vs 'M Green') → KeyError paths converted to clear errors.
- **Open owner questions (post-validation):** (1) accessory kg in v1 CPDs — default YES (parity); (2) shared-CPD scalars (yarn/processes/ratio/greige) are last-write-wins across lots — acceptable, or fill-only-when-blank?; (3) AISHWARYA PLAIN (S/Box)-2/-3 carry bad cutting rows (105cm Back 0.176; 110cm rows 0.52 @ '32 Dia') — fix before first live build.
