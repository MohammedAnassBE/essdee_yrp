# F15 `production_api` → F16 `essdee_yrp` processing parity gate

Date: 2026-08-20
F15 reference: `/home/anas/frappe-15`, app `production_api`, site `mrp3.site:8002`
F16 target: `/home/anas/frappe-16`, app `essdee_yrp` branch `MRP`, site `essdee_yrp.site:8003`

## Purpose and completion rule

This is the single completion gate for the migrated Desk workflow. It compares
what F15 does with what F16 does, at the UI, controller, lifecycle, linked
document, stock, and cut-bundle-ledger levels.

The audit is complete only when every row below is either:

- `[x] Parity verified` — exercised against live migrated records and backed by
  a screenshot and/or a rollback-safe lifecycle test; or
- `[x] Intentional F16 difference verified` — the F16 implementation is
  deliberately different, the business result is equivalent or stronger, and
  the reason/evidence is recorded.

`[ ]` means unresolved or not yet independently reverified. Existing audit
claims and passing tests are useful evidence, but they do not close a row by
themselves. No partial section is a declaration that the whole migration is
finished.

## Application boundary

- All Essdee-specific behavior and fixes in this gate belong to `essdee_yrp`.
- Base `yrp` is read-only for this pass. The only previously authorized base
  change was the generic Work Order Supplier Address / Delivery Address filter.
- This gate covers Frappe Desk. It does not authorize changes to `/web`.
- Live migrated documents are evidence and must not be rewritten merely to make
  a test pass.
- No migrate, restore, reinstall, destructive data operation, commit, or push.

## End-to-end oracle chain

Primary migrated chain:

`PPO-00081 → C0326-28 → EE-36221 SHORTS SET HALF SLEEVE (CORD)-3 →
WO-2526-02637-2 → CP-2603-00030 → CM-2603-00135 → CLS-2603-00251 →
DC-2526-07291 → GRN-2526-12944 → WO-2627-00005 → CPM-2603-00364 /
STE-2026-05590 → CPM-2604-00015 / DC-2627-00057 → CPM-2604-00036 /
GRN-2627-00183 → Cut Bundle Movement Ledger`

Additional state oracles:

- IPD: `CS-34820 Heavy Tee-1`
- Cutting Plan: `CP-2608-00012`, `CP-2608-00006`, `CP-2608-00005`,
  `CP-2605-00019`
- Cutting Marker: `CM-2608-00028`, `CM-2608-00036`
- Cutting LaySheet: `CLS-2608-00093`, `CLS-2606-00294`,
  `CLS-2607-00276`, `CLS-2608-00109`, `CLS-2608-00066`
- Delivery Challan: `DC-2627-03557`, `DC-2627-01677`, `DC-2627-03405`
- Goods Received Note: `GRN-2627-04745`
- Stock Entry: `STE-2026-13931`, `STE-2026-12654`
- Cut Panel Movement: `CPM-2608-00187`, `CPM-2606-00482`,
  `CPM-2608-00220`, conflicts `CPM-2608-00052`, `CPM-2608-00222`
- Ledger: `v42mbob5ds`, `i9is4s7f5f`, `80094ttgma`, `8t7f1kbeqo`,
  `fg5kutdge1`

## Evidence columns

Each row will finish with all applicable evidence:

- **Source** — exact F15 JS/Python behavior and condition.
- **Target** — exact F16 JS/Python behavior and condition.
- **Desk** — rendered form/button/dialog/tab plus console result.
- **Lifecycle** — save/submit/cancel/return/revert and linked effects.
- **Data** — live oracle links, totals, statuses, and no unintended mutation.
- **Test** — focused rollback-safe test name/result.

## Freeze and owner-led UAT boundary

Engineering verification uses source comparison, read-only migrated records,
rendered Desk screenshots, and rollback-safe tests. It does not silently save,
submit, cancel, return, print, or rewrite the owner's live business documents.

After this gate is resolved, the implementation is frozen for owner-led UAT.
The owner will then request one operation at a time in Telegram, for example:

1. create a Work Order and leave it in Draft;
2. send the Draft screenshot;
3. open and send the calculated SKU popup;
4. submit only after an explicit instruction;
5. create a Stock Reconciliation in Draft; and
6. send the item row after the stock-dimension fields are entered.

Each later screenshot must show the exact requested state. No following action
is implied by the previous request, and **Submit** is never implied by
**Create**, **open**, **calculate**, or **send a screenshot**.

## F15 source to F16 target processing map

| DocType | F15 `production_api` processing | F16 processing and deliberate differences | Verification basis |
| --- | --- | --- | --- |
| Production Order | Own DocType/controller supplied quantity/ratio entry, price/date/status actions, approval, transfer, and Lot creation/linking. | Base schema is supplied by `yrp`; `essdee_yrp.production_order_workflow` and its Desk editor are authoritative for Essdee ratios. Conflicting base quantity presentation is hidden. Frappe datetime formatting replaces the raw timestamp presentation. Mutations are authenticated and status/approval guarded server-side. | PPO ratio/new/update dialogs on `PPO-00257` and `PPO-00081`; 12 Production Order business tests and 2 schema/customization tests. |
| Lot | Lot controller calculated order rows, cloth requirements/programs, and Time & Action. | Essdee owns the same business layer. Lot consumes the exact PPO ratio. Cloth programs are deterministic/idempotent, validate yarn recipes/routes before writing, and version changed cloth IPDs. Order-item recalculation is locked after Time & Action exists. | `C0326-28` screenshots; 50 cloth-program tests, Lot tests, Lot packing-boundary tests, and Time & Action regression. |
| Item Production Detail | Monolithic JS/Python owned all tabs, combinations, BOM mappings, panel consumption, approval, revert, and duplicate. | Schema remains in base `yrp`; all Essdee editors and rules remain in `essdee_yrp`. F16 adds an explicit **Generate / Regenerate IPD Process Matrix** recovery action for migrated IPDs and a stronger approved-document lock across native grids, Vue editors, bulk/BOM APIs, and direct save. Generation is derived-only and preserves the IPD `modified` value. | Eight-tab approved/editable captures; Heavy Tee generation result; 11 panel-consumption tests, 4 terminal/IPD regressions, garment-matrix tests, and cloth-program suite. |
| Work Order | One garment SKU calculation dialog plus fabric calculation, operational Create/actions, incremental **Calculate Pieces**, close/rework/recut logic, and address filters. | Essdee explicitly routes cloth processes to **Calculate Fabric Deliverables** and all other saved garment drafts to **Calculate Items**. The garment popup exposes the same colour/size SKU matrix as F15. **Calculate Pieces** is now a deterministic replay of submitted DC/GRN sources, making submit/cancel/retry idempotent. New WO Recut opens a zero-quantity SKU matrix. The owner-authorized generic Supplier/Delivery Address filters are the only task change in base `yrp`. | `YRP-WO-2026-00038` SKU dialog, submitted action captures, Recut matrix, closed **Calculate Pieces** capture; 4 garment tests, 17 fabric API tests, 3 piece-replay tests, close tests. |
| Cutting Plan | Buttons and controller handled Generate, received cloth, LaySheet optimization, completion, recut/print-panel, grammage, transfer, and state rollup. | Functional port is retained in Essdee with F16 stock dimensions and a common Cutting Plan/Cutting Order parent adapter. F16 additionally removes all mutation actions from cancelled plans and every endpoint rechecks submitted/non-cancelled state. | `CP-2603-00030` and Planned/In Progress/Partial/Cancelled state sets; 16 cutting lifecycle tests and terminal-state regressions. |
| Cutting Marker | Vue ratio editor and controller handled plan/order context, sizes, panels, group markers, validation, and saved JSON. | Near line-for-line functional port with namespace changes, explicit read-permission checks, F16 parent adapter, and a fixed draft mount/load sequence. No new business action is added. | `CM-2603-00135`, draft `CM-2608-00028`, cancelled `CM-2608-00036`; source diff plus runtime endpoint/form verification. |
| Cutting LaySheet | Generate, label printing, grammage approval, print outputs, revert labels, status change, cancellation, GRN/bundle/ledger effects. | Same Desk vocabulary and processing are retained. Essdee print formats replace legacy format ownership. Approval, bundle generation, GRN creation, label transition, reversion, and cancellation now reload/lock the saved LaySheet and reject browser-supplied terminal-state mutations. | Primary chain plus Started/Completed/Bundles Generated/Approval Pending/Label Printed/Cancelled captures; cutting lifecycle and terminal-state tests; print-format render tests. |
| Delivery Challan | Draft **Calculate** staged items; Complete Transfer, Return and custom Cancel; controller updated Work Order, stock, and bundle state incrementally. | Base `yrp` owns the reactive matrix, pending-quantity and stock transaction engine, so a separate staging **Calculate** button is intentionally unnecessary. Complete Transfer and Return remain. Standard Frappe supplies Cancel. Essdee hooks add CPM ownership, bundle ledger, and deterministic Work Order piece replay. | Cutting/printing/draft/cancelled/wide-matrix screenshots; CPM→DC→GRN and cancel tests; customization and permission tests. |
| Goods Received Note | Draft **Calculate**, Complete Transfer, **Create YRP Stock Entry**, custom Cancel, and controller-side Work Order/stock updates. | Base `yrp` reactive matrix removes the separate staging Calculate step. Complete Transfer and Inspection actions remain; standard Frappe supplies Cancel. The old cross-bench **Create YRP Stock Entry** RPC is intentionally excluded: F16 posts through the installed base stock engine and Essdee hooks. | Cutting/printing/draft screenshots; migrated LaySheet→GRN, CPM→GRN, return, received-type, packing and cancel tests; customization tests. |
| Stock Entry | `production_api.mrp_stock` owned stock dimensions, transit, ledgers, and custom item editor. | Base `yrp` owns stock posting, valuation, transit, inspections, and normal Stock Entry behavior. Essdee contributes only its custom fields, packing/dimension normalization, CPM ownership, and cut-bundle hooks. Completion Stock Entries remain distinct from CPM root entries. | Submitted/draft/cancelled/wide-matrix captures; CPM→SE submit/cancel, unrelated SE, recut, FG receipt, conversion, UOM and dimension tests. |
| Cut Panel Movement | Fetched available panels, serialized movement JSON, then used `sessionStorage` to seed an SE/DC/GRN. Root ownership was normally known only after submit. | Same Fetch/Create flow is retained, but F16 prepares one SPA-safe local document and server defaults. Work Orders are same-Lot, submitted and open. A locked server check permits only one active Draft/Submitted SE/DC/GRN root; existing historical conflicts are displayed rather than rewritten. | Primary three CPM links, draft/cancelled/unlinked/conflict captures; one-root, closed-WO, collapsed-bundle and all three transaction lifecycle tests. |
| Cut Bundle Movement Ledger | LaySheet, SE, DC, GRN and Cut Bundle Edit wrote/reposted signed bundle movements. | Controller semantics are retained in Essdee; F16 stock hooks carry configured dimensions and active-root ownership. Backdated posting, cancellation, collapse, non-bundle and transform routes preserve identity and quantity. Ledger remains read-only audit evidence. | LaySheet/SE/DC/GRN-origin screenshots; transform/cancel, collapse/non-bundle and full CPM round-trip tests. |

## Evidence ledger

- **Desk evidence:** 237 form-state screenshots in
  `/home/anas/frappe-16/screenshots/mrp-functional-audit/`, plus the 2026-08-20
  root follow-ups for the SKU popup, Production Order ratio editor, IPD locks,
  Work Order action dialogs, WO Recut matrix, Calculate Pieces, and Lot cloth
  program.
- **Focused rerun:** 145/145 passed: 37 cutting/stock/runtime/replay tests and
  108 Production Order/Lot/IPD/Work Order/DC/GRN/Stock Entry tests.
- **Full app rerun:** 441/441 passed: 12 unit, 263 integration, 80
  old-Frappe-category, and 86 remaining-category tests.
- **Primary-chain read-only baseline:** all 16 parent records retained their
  migrated `docstatus` and `modified` timestamps after the rollback-safe test
  runs. The exact timestamp list is recorded in the final data-integrity
  section below.

## 1. Production Order

F15 owner: `production_api` Production Order custom workflow.
F16 owner: `essdee_yrp/public/js/production_order_workflow.js`,
`essdee_yrp/production_order_workflow.py`, and
`essdee_yrp/production_order_alternative.py`.

- [x] PPO-01 Desk uses the Essdee quantity/ratio editor as the authoritative
  entry surface; conflicting base quantity UI is hidden.
- [x] PPO-02 Update Quantity & Ratio loads, validates, persists, and reopens the
  exact colour/size ratio without flattening it.
- [x] PPO-03 Total quantity, size quantity, price, and ratio validations match
  the F15 business result.
- [x] PPO-04 Update Price, Change Dates, Change Status, approval request,
  approval/rejection, and role visibility match their F15 conditions.
- [x] PPO-05 Transfer Quantity and approval preserve source/target quantities
  and audit history.
- [x] PPO-06 Create Lot and Link Lot use the stored Essdee ratio and reject
  invalid/duplicate linkage.
- [x] PPO-07 Non-processed/approval status messages render dates through Frappe
  formatting and do not show an unexplained raw timestamp.
- [x] PPO-08 Submitted/cancelled/unauthorized states have no browser-only
  mutation path; server checks remain authoritative.

## 2. Lot

F15 owner: `production_api` Lot workflow and cloth-program inputs.
F16 owner: `essdee_yrp/essdee_yrp/doctype/lot/lot.js/.py` and
`essdee_yrp/api/cloth_program.py`.

- [x] LOT-01 A Lot created/linked from PPO receives the exact colour/size
  quantity and ratio, not a recomputed approximation.
- [x] LOT-02 Item Production Detail linkage and item/variant rows match the PPO
  and IPD.
- [x] LOT-03 Cloth Program generation consumes the IPD cloth, colour, Dia,
  yarn-recipe, and process mappings with clear validation for missing setup.
- [x] LOT-04 Existing and regenerated cloth programs are idempotent and do not
  duplicate rows/documents.
- [x] LOT-05 Lot actions, Time and Action creation, and submitted/cancelled
  visibility match their conditions and permissions.
- [x] LOT-06 Lot quantity fields used by Work Order calculation are the same
  columns that the user maintained in the PPO/Lot flow.

## 3. Item Production Detail — primary checkpoint

F15 source:
`production_api/essdee_production/doctype/item_production_detail/` and its
combination/BOM APIs.
F16 target: base schema in `yrp`, with Essdee behavior in
`essdee_yrp/public/js/item_production_detail.js`, `essdee_yrp/ipd_ui.py`,
`essdee_yrp/ipd_validations.py`, and `essdee_yrp/garment_work_order.py`.

- [x] IPD-01 Item attributes, primary/dependent attributes, mappings, and
  allowed values load and filter as in F15.
- [x] IPD-02 Stitching, set-item, packing, cutting, cloth, accessory,
  embellishment, and bundle-group combinations load in every applicable tab.
- [x] IPD-03 BOM rows and BOM attribute mappings calculate the same inputs and
  outputs for garment IPDs.
- [x] IPD-04 Panel-wise consumption supports create/edit/read-only modes and
  preserves all panels, colours, Dias, and additional attributes.
- [x] IPD-05 Cloth IPD fabric processes, value mappings, fabric routes,
  colour-wise yarn recipes, dyeing swaps, compacting swaps, and compacting
  reference generation are internally consistent.
- [x] IPD-06 Duplicate IPD copies the intended scalar fields, child tables, JSON
  combinations, and mappings without sharing mutable owned mappings.
- [x] IPD-07 Approve/Revert Approval button visibility matches configured roles;
  direct server calls enforce the same roles.
- [x] IPD-08 Approved IPD is immutable in normal Desk fields, child grids, Vue
  editors, bulk/BOM paths, and direct saves.
- [x] IPD-09 Generate / Regenerate IPD Process Matrix is visible on saved IPDs,
  works for approved migrated IPDs, and does not alter authored IPD data or its
  `modified` timestamp.
- [x] IPD-10 Matrix generation covers every valid variant/process and reports
  every invalid/missing mapping explicitly; it never silently under-demands.
- [x] IPD-11 `EE-36221...-3` supports the primary cutting chain; `CS-34820
  Heavy Tee-1` regenerates its valid matrices and reports the source-missing
  Navy mapping without inventing it.
- [x] IPD-12 All tabs render without console/page errors, overflow, stale Vue
  mounts, duplicate controls, or editable controls while approved.

## 4. Work Order

F15 source:
`production_api/production_api/doctype/work_order/work_order.js/.py`.
F16 target: base `yrp` Work Order plus `essdee_yrp/public/js/work_order.js`,
`essdee_yrp/api/work_order.py`, and `essdee_yrp/garment_work_order.py`.

- [x] WO-01 Supplier Address is filtered by Supplier; Delivery Address is
  filtered by Delivery Location; primary-address/default display stays correct.
- [x] WO-02 Saved draft cloth-process Work Order shows only **Calculate Fabric
  Deliverables** and uses cloth recipe/process matrices.
- [x] WO-03 Saved draft non-cloth garment Work Order shows **Calculate Items**
  and never routes Cutting into the cloth-only error path.
- [x] WO-04 Cutting, Stitching, Packing, extra process, and grouped process
  calculations produce the correct deliverables and receivables from Lot/IPD.
- [x] WO-05 Wide calculation matrices remain inside the form and their saved
  rows reopen exactly.
- [x] WO-06 Submit validates quantities/costs/required fields and updates
  ordered/expected process data as in F15.
- [x] WO-07 Open submitted actions: Material Issue, Make Cutting Plan, Make DC,
  Make GRN, Change Delivery Date, Change Item, Close, rework, recut, Calculate
  Pieces, debit, and role-gated Sewing Plan are present only when applicable.
- [x] WO-08 Close/Approve Close summaries, shortages, recuts, stock updates,
  comments, and status transitions match F15 business results.
- [x] WO-09 Cancel and linked-document restrictions are symmetric and enforced
  server-side.
- [x] WO-10 `YRP-WO-2026-00038` can calculate through the restored garment path
  without unintended document mutation until the user saves.

## 5. Cutting Plan

F15 source: `production_api/production_api/doctype/cutting_plan/`.
F16 target: `essdee_yrp/essdee_yrp/doctype/cutting_plan/`.

- [x] CP-01 Work Order/Lot/IPD filters and initial item, cloth, accessory, panel,
  maximum-ply, tolerance, and cutting-location defaults match F15.
- [x] CP-02 **Generate** builds planned item/cloth structures correctly.
- [x] CP-03 **Fetch Received Cloth** respects warehouse, received type, Lot,
  posting cutoff, and excludes unavailable stock.
- [x] CP-04 **Calculate LaySheets** handles normal, phantom-panel, manual, set
  item, and versioned plan structures.
- [x] CP-05 Summary/size/lay/CCR reports show the same quantities and remain
  within the rendered form/print layout.
- [x] CP-06 Get/Update Completed, recut, and print-panel actions update only the
  intended tracking JSON and counts.
- [x] CP-07 Change Approval Grammage is role-gated, logged, and only approves
  pending LaySheets that fall within the new tolerance.
- [x] CP-08 Lot Transfer uses actual remaining cloth, creates one valid transfer,
  and is permission/state gated.
- [x] CP-09 Submit derives the correct `cp_status`; linked Markers/LaySheets
  drive Planned → Cutting In Progress → Partially Completed → Completed.
- [x] CP-10 Cancelled plans expose no mutation actions; every mutation endpoint
  independently requires a submitted, non-cancelled plan.

## 6. Cutting Marker

F15 source: `production_api/production_api/doctype/cutting_marker/`.
F16 target: `essdee_yrp/essdee_yrp/doctype/cutting_marker/`.

- [x] CM-01 Cutting Plan/Order query and selection populate Lot, item, cutting
  attribute, panels, sizes, parts, and allowed marker groups.
- [x] CM-02 Ratio editor validates total plys, selected type, group parts,
  calculated parts, marker length/width, weight, and efficiency as in F15.
- [x] CM-03 Normal, group, set-item, manual, and V1/V2/V3 marker structures
  round-trip without data loss.
- [x] CM-04 Submit validates the saved ratio against the selected plan/order and
  exposes the Marker to eligible LaySheets.
- [x] CM-05 Draft is editable; submitted is read-only except allowed actions;
  cancelled Marker cannot create or mutate LaySheets.
- [x] CM-06 Submitted, draft, and cancelled forms render without console/page
  errors, duplicate mounts, or overflow.

## 7. Cutting LaySheet

F15 source: `production_api/production_api/doctype/cutting_laysheet/`.
F16 target: `essdee_yrp/essdee_yrp/doctype/cutting_laysheet/`.

- [x] CLS-01 Plan/Order and Marker filters load exact marker parts, ratios,
  cloth/accessory stock, select attributes, allowances, and next lay number.
- [x] CLS-02 Started → Completed calculation validates rolls/bits/weights/plys,
  ratio parts, manual items, set combinations, and required piece weight.
- [x] CLS-03 Grammage within tolerance proceeds; outside tolerance enters
  Approval Pending through a server-rechecked transition.
- [x] CLS-04 Approve is role-gated and records `approved_by`; unauthorized Desk
  and direct calls fail.
- [x] CLS-05 Bundle generation creates exact bundle rows and LaySheet-origin Cut
  Bundle Movement Ledger entries once, including collapsed/non-bundle policy.
- [x] CLS-06 GRN creation is available only from Bundles Generated and creates
  the cutting GRN with correct deliverables, consumed cloth/accessories, stock
  entries, and LaySheet link.
- [x] CLS-07 Print Labels uses saved bundles/lay numbers and moves to Label
  Printed only after successful print; retry leaves safe state.
- [x] CLS-08 Print LaySheet and Movement Chart use installed Essdee print
  formats and handle large part counts.
- [x] CLS-09 Revert Labels reverses GRN/stock/bundle effects exactly once and
  restores a valid pre-print state.
- [x] CLS-10 Cancel reverses bundle and cloth stock effects, updates plan dates
  and status, and is blocked when linked state makes reversal unsafe.
- [x] CLS-11 Approval Pending, Label Printed, and Cancelled are read-only in
  standard fields and mounted editors; terminal APIs recheck state server-side.

## 8. Delivery Challan

F15 source: `production_api/production_api/doctype/delivery_challan/`.
F16 target: base `yrp` transaction engine, extended through
`essdee_yrp/delivery_challan_hooks.py` and
`essdee_yrp/public/js/delivery_challan.js`.

- [x] DC-01 Work Order filter permits submitted/open orders only; source and
  destination supplier/warehouse filters are correct.
- [x] DC-02 Selecting Work Order loads process, Lot/IPD/item, suppliers,
  warehouses, deliverables, corrections, secondary quantities, and dimensions.
- [x] DC-03 Draft item matrix validates at least one delivery quantity and
  round-trips wide colour/size structures without overflow or data loss.
- [x] DC-04 Submit validates against Work Order pending quantities and available
  stock, updates delivered quantities, and writes stock ledger exactly once.
- [x] DC-05 Cutting DC `DC-2526-07291` and printing CPM DC `DC-2627-00057`
  retain the correct distinct ownership/linkage and business effects.
- [x] DC-06 CPM-linked DC validates that the CPM is submitted, unclaimed, same
  Lot/item/source, and claims only one active root transaction.
- [x] DC-07 Internal-unit Complete Transfer creates the correct Stock Entry and
  tracks transfer percentage/completion idempotently.
- [x] DC-08 Return shows only returnable quantities, supports ordinary and
  bundle returns, creates a valid return GRN, and prevents over-return.
- [x] DC-09 Cancel reverses Work Order quantities, stock, CPM ownership, and
  bundle-ledger entries symmetrically; cancelled form exposes no mutation UI.

## 9. Goods Received Note

F15 source: `production_api/production_api/doctype/goods_received_note/`.
F16 target: base `yrp` engine with
`essdee_yrp/overrides/goods_received_note.py` and
`essdee_yrp/public/js/goods_received_note.js`.

- [x] GRN-01 Against/Against ID and Delivery Challan filters permit valid open
  sources only; supplier, delivery location, and warehouse filters are correct.
- [x] GRN-02 Work Order source loads process, Lot/IPD/item, receivables,
  corrections, delivery context, dimensions, and secondary quantities.
- [x] GRN-03 Purchase Order source remains unaffected by Essdee cutting/CPM
  extensions.
- [x] GRN-04 Draft matrix validates at least one received quantity and enforces
  pending/tolerance rules without losing wide colour/size data.
- [x] GRN-05 Cutting label GRN `GRN-2526-12944` contains correct cutting outputs,
  cloth/accessory consumption, stock, LaySheet ownership, and ledger effects.
- [x] GRN-06 CPM printing GRN `GRN-2627-00183` validates movement ownership and
  records incoming bundle quantities at the intended location.
- [x] GRN-07 Collapsed bundle, ordinary bundle, non-bundle, incomplete, reject,
  and received-type routes update the correct quantities.
- [x] GRN-08 Internal-unit Complete Transfer is idempotent and creates the
  correct completion Stock Entry.
- [x] GRN-09 Return GRN validates original DC row identity and returnable
  quantities, reverses stock, and updates returned deliverables symmetrically.
- [x] GRN-10 Submit/cancel updates Work Order receivables, stock, CPM ownership,
  LaySheet linkage/status, and bundle ledger exactly once in both directions.
- [x] GRN-11 Inspection actions and cancelled/read-only behavior appear only in
  applicable states; form has no console/page errors or overflow.
- [x] GRN-12 Cutting GRNs preserve size-level transaction rows but render them
  with F15's logical SKU grouping: one Accepted/Rejected line per
  panel/colour/set combination, with every size quantity across that line.
  Verified on `YRP-GRN-2026-00021` through `YRP-GRN-2026-00026`; rendered totals
  exactly match the stored child-row totals in all six documents.

## 10. Stock Entry

F15 source: `production_api/mrp_stock/doctype/stock_entry/`.
F16 target: base `yrp` stock engine plus `essdee_yrp/stock_entry_hooks.py` and
`essdee_yrp/public/js/stock_entry.js`.

- [x] SE-01 Purpose toggles, required source/target warehouse, supplier filters,
  posting date/time, and transit fields match the selected stock operation.
- [x] SE-02 New CPM Stock Entry loads grouped movement rows from defaults and
  renders them in the item editor without requiring a refresh workaround.
- [x] SE-03 Draft validates non-empty quantities/dimensions and preserves Lot,
  received type, bundle identity, secondary UOM, and valuation data.
- [x] SE-04 CPM ownership validation requires submitted/unclaimed CPM with same
  movement context and allows only one active root transaction.
- [x] SE-05 Submit `STE-2026-05590` moves bundle and stock quantities from the
  cutting location to the cut-panel store and creates symmetric ledger entries.
- [x] SE-06 End Transit / Receive at Warehouse and Received Stock Entries match
  the base stock lifecycle without duplicating CPM effects.
- [x] SE-07 Completion Stock Entries for internal DC/GRN remain distinct from
  CPM Stock Entries and do not incorrectly claim a movement.
- [x] SE-08 Cancel reverses stock and Cut Bundle Movement Ledger entries and
  clears CPM ownership only when it owns that exact transaction.
- [x] SE-09 Draft, submitted, cancelled, wide matrix, and unrelated normal Stock
  Entry forms render without console/page errors or accidental hidden actions.

## 11. Cut Panel Movement

F15 source: `production_api/production_api/doctype/cut_panel_movement/`.
F16 target: `essdee_yrp/essdee_yrp/doctype/cut_panel_movement/`.

- [x] CPM-01 Lot/item/Cutting Plan/from-location filters and movement date/time
  cutoffs match F15.
- [x] CPM-02 Fetch Panels returns only currently available bundles at the source,
  with ordinary, collapsed, transformed, and non-bundle structures preserved.
- [x] CPM-03 Movement from Cutting validates the selected Cutting Plan and moves
  the plan's panels/accessories from the cutting location.
- [x] CPM-04 Draft editor round-trips movement JSON and totals; submitted and
  cancelled records are read-only.
- [x] CPM-05 Submit reserves/moves exact bundles and accessories once; cancel
  releases them symmetrically.
- [x] CPM-06 Submitted unclaimed CPM exposes Create Stock Entry, Delivery
  Challan, and Goods Received Note only to users with target create permission.
- [x] CPM-07 Work Order picker is restricted to same-Lot submitted/open orders;
  target defaults carry correct process, suppliers, warehouses, Lot/IPD/item,
  CPM link, and grouped items.
- [x] CPM-08 Creating a target uses one SPA-safe new document and does not leave
  duplicate locals/session payloads or lose the item matrix on refresh.
- [x] CPM-09 One CPM owns at most one active draft/submitted root SE/DC/GRN;
  client warning and locked server check agree under conflicts/concurrency.
- [x] CPM-10 Existing conflicts `CPM-2608-00052` and `CPM-2608-00222` are shown
  transparently and blocked from gaining another root without rewriting data.
- [x] CPM-11 Closed Work Orders, mismatched Lot/item/source, cancelled CPM, and
  already claimed CPM are rejected server-side.

## 12. Cut Bundle Movement Ledger

F15 source:
`production_api/production_api/doctype/cut_bundle_movement_ledger/`.
F16 target:
`essdee_yrp/essdee_yrp/doctype/cut_bundle_movement_ledger/`.

- [x] CBML-01 LaySheet bundle generation creates ledger identity keys from Lot,
  item, colour/size/lay/bundle/panel/shade/set combination consistently.
- [x] CBML-02 Stock Entry, Delivery Challan, and Goods Received Note each write
  the correct signed source/target entries with voucher type/no and supplier.
- [x] CBML-03 `quantity_after_transaction` is derived from the correct previous
  entry at posting date/time and future entries are reposted after backdating.
- [x] CBML-04 Cancel marks/reverses the exact voucher entries and reposts future
  balances without double reversal.
- [x] CBML-05 Collapsed bundle creation/consumption/cancel, non-stitch process,
  uncollapse, and intermediate entries preserve total quantity.
- [x] CBML-06 Transformed bundle origin and transformed flags remain traceable
  through Cut Bundle Edit and downstream movement.
- [x] CBML-07 Duplicate logical ledger entries are prevented/identified by the
  same key and voucher lifecycle rules as F15.
- [x] CBML-08 Ledger records from LaySheet, Stock Entry, DC, and GRN render as
  read-only audit evidence with working dynamic links and no console/page errors.

## Cross-document invariants

- [x] FLOW-01 Every target document links back to exactly the intended source;
  no duplicate active root claims.
- [x] FLOW-02 Total bundle quantity is conserved across LaySheet → cutting
  location → cut-panel store → printer → return, except explicit collapse,
  transform, rejection, or documented non-bundle routes.
- [x] FLOW-03 Stock ledger and Cut Bundle Movement Ledger agree at every
  submit/cancel boundary.
- [x] FLOW-04 Work Order delivered/received/pending quantities agree with DC and
  GRN totals after submit, return, cancel, rework, and recut.
- [x] FLOW-05 Every button visibility condition has an equivalent server-side
  permission/state/link validation; UI hiding is never authorization.
- [x] FLOW-06 All exact migrated oracles retain their original `modified` value
  unless a test explicitly uses a rollback transaction.
- [x] FLOW-07 Every tested form state has a saved screenshot and zero unexplained
  console/page errors.

## Final independent observations

- F15 and F16 Cutting Marker JS/Python are functionally identical apart from
  namespace/Frappe compatibility changes and added permission checks. Draft,
  submitted and cancelled forms were rechecked after the draft mount fix.
- F16 Cutting Plan and LaySheet deliberately add stronger cancelled/terminal
  state guards and locked approval/label transitions. The rendered state sets
  and rollback-safe lifecycle suites agree.
- F16 DC/GRN/Stock Entry deliberately use the base YRP transaction engine
  rather than copying the monolithic F15 controllers. Equivalence was checked
  by resulting Work Order quantities, stock/bundle lifecycle effects, live
  source links, screenshots, and submit/cancel tests.
- The Work Order piece projection exactly matches the primary cutting Work
  Order (`0 delivered / 1456 received`) and printing Work Order (`728 delivered
  / 728 received`), including Accepted totals and all SKU rows. The newest 100
  historical source-bearing Work Orders have zero quantity mismatches. One
  legacy row differs only as `{\"Accepted\": 0}` versus `{}`.
- A read-only full historical replay found 2,928 exact Work Orders and 292 old
  incremental-data mismatches among 3,220 source-bearing submitted Work Orders.
  These are historical stored-data drift, not recent-flow code failures, and
  were deliberately not rewritten during this task.
- Historical conflicting CPM roots remain visible for `CPM-2608-00052` and
  `CPM-2608-00222`. The target prevents a new conflict but does not conceal or
  destructively repair migrated data.

## Primary-chain data-integrity snapshot

The exact read-only query was repeated after the 441-test run. Every value
below was unchanged from the pre-run value.

| Record | Docstatus | Modified |
| --- | ---: | --- |
| `PPO-00081` | 1 | `2026-04-28 17:26:46.654194` |
| `C0326-28` | 0 | `2026-08-04 17:07:49.403282` |
| `EE-36221 SHORTS SET HALF SLEEVE (CORD)-3` | 0 | `2026-05-06 12:01:46.653013` |
| `WO-2526-02637-2` | 1 | `2026-04-25 12:30:57.343759` |
| `CP-2603-00030` | 1 | `2026-04-04 09:44:41.026639` |
| `CM-2603-00135` | 1 | `2026-03-27 17:55:15.560543` |
| `CLS-2603-00251` | 0 | `2026-03-28 09:06:19.222106` |
| `DC-2526-07291` | 1 | `2026-03-28 09:01:51.107777` |
| `GRN-2526-12944` | 1 | `2026-03-28 09:06:00.894658` |
| `WO-2627-00005` | 1 | `2026-04-15 12:45:13.570623` |
| `CPM-2603-00364` | 1 | `2026-03-30 16:31:13.075648` |
| `STE-2026-05590` | 1 | `2026-03-30 16:30:54.095355` |
| `CPM-2604-00015` | 1 | `2026-04-02 15:35:01.290792` |
| `DC-2627-00057` | 1 | `2026-04-02 15:34:57.937891` |
| `CPM-2604-00036` | 1 | `2026-04-04 16:45:36.839518` |
| `GRN-2627-00183` | 1 | `2026-04-13 17:28:47.378853` |

Link checks also remained exact:

- Cutting Plan → Marker → LaySheet is
  `CP-2603-00030 → CM-2603-00135 → CLS-2603-00251`; the LaySheet retains
  `Label Printed` and the cutting GRN points back to that LaySheet.
- `CPM-2603-00364` owns `STE-2026-05590`.
- `CPM-2604-00015` owns `DC-2627-00057`.
- `CPM-2604-00036` owns `GRN-2627-00183`.
- Every one of those rows retains Lot `C0326-28` and the intended cutting or
  printing Work Order context.

## Final sign-off

- [x] Every row in this file is resolved.
- [x] Final screenshot directory and focused/full test outputs are recorded.
- [x] Independent task diff review found no `/web` change and no task-owned
  base-`yrp` change except the explicitly authorized generic Work Order address
  filters. Existing unrelated dirty worktree changes were preserved.
- [x] Exact primary-chain records were not unintentionally modified.
- [x] Owner receives one final completion report with remaining historical data
  issues clearly separated from code defects.
