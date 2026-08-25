# MRP DocType functional audit — 2026-08-20

Site: `essdee_yrp.site:8003`
Essdee app/branch: `apps/essdee_yrp` / `MRP`
Base app/branch: `apps/yrp` / `develop`
Read-only F15 reference: `mrp3.site:8002` / `production_api`

## Scope and boundary

This is the screenshot-led functional audit requested for the migrated MRP
workflow, not a smoke test. It covers the rendered forms and state-dependent
actions, the server endpoints behind them, permissions, lifecycle transitions,
and the cross-document stock/bundle effects.

The owner-set application boundary was preserved:

- Only Supplier Address and Delivery Address filtering was changed in base
  `yrp`, because that behavior is generic Work Order functionality.
- Production Order, Lot/IPD behavior, Essdee Work Order fabric behavior,
  Cutting Plan/Marker/LaySheet, Delivery Challan/GRN integration, Stock Entry,
  Cut Panel Movement, and bundle-ledger behavior remain in `essdee_yrp`.
- No `bench migrate`, restore, reinstall, data deletion, commit, or push was
  performed during this audit.

## Workflow exercised

`Production Order → Lot → Item Production Detail → cutting Work Order → Cutting
Plan → Cutting Marker → Cutting LaySheet → cutting Delivery Challan → label/GRN
→ printing Work Order → Cut Panel Movement/Stock Entry → printing Delivery
Challan → printing GRN → Cut Bundle Movement Ledger`

## Rendered UI and state coverage

The original evidence set contains 237 screenshots in
`/home/anas/frappe-16/screenshots/mrp-functional-audit/`, plus four root-level
follow-up screenshots for the Work Order/IPD calculation correction. Each
normal form audit captured top, middle, bottom, and a runtime-state image;
tabbed records were captured tab by tab.

| Surface | Records and states driven/inspected | Result |
| --- | --- | --- |
| Production Order | `PPO-00257`; quantity/ratio/price editor, Lotwise detail, request dates | Ratio entry is Essdee-owned and persisted; Lot consumes the stored ratio. The duplicate `Lot: null` presentation was removed. Request timestamps are normalized Frappe datetimes without microseconds. |
| Lot | Ratio propagation and cloth-program build contracts exercised through integration tests | Lot receives the Production Order ratio and composes the cloth-program/IPD inputs without duplicating the entry source. |
| Item Production Detail | `EE-36221 SHORTS SET HALF SLEEVE (CORD)-3`, `CS-34820 Heavy Tee-1`; all eight tabs before/after Approved lock and generated-matrix backfill | Approved records expose no Save, Add Row, inline edit, bulk edit, or BOM mutation path. Server saves are rejected until role-gated Revert Approval. The explicit **Generate / Regenerate IPD Process Matrix** action may rebuild derived matrix documents from an approved migrated IPD without modifying that IPD's authored fields or `modified` timestamp; invalid variants are listed instead of silently under-demanding them. |
| Work Order | `YRP-WO-2026-00038`, `WO-2627-00666`, `WO-2627-00644`, `WO-2627-00735`, `WO-2627-00855`, plus submitted/cancelled records; Cutting, Stitching, Packing, extra-process, grouped-process and wide-matrix paths | Supplier Address is filtered by Supplier and Delivery Address by Delivery Location. Every saved draft non-rework garment Work Order exposes the F15-compatible **Calculate Items** action; an explicitly cloth-marked Process exposes **Calculate Fabric Deliverables** instead. The garment dialog reads the applicable Lot quantity column and calculates deliverables/receivables for core, extra, and grouped processes. Cutting reports the exact variants missing generated IPD matrices. Wide matrices scroll inside the form. |
| Cutting Plan | `CP-2603-00030`, `CP-2608-00012`, `CP-2608-00006`, `CP-2608-00005`, `CP-2605-00019`; Planned, Cutting In Progress, Partially Completed, cancelled, all tabs | Cancelled plans expose only read/view behavior. Cloth fetch, lay calculation, grammage change, recut, and received-cloth mutation endpoints now require a submitted, non-cancelled plan server-side. |
| Cutting Marker | `CM-2603-00135`, `CM-2608-00028`, `CM-2608-00036`; submitted chain, draft, cancelled | Forms and state actions render without console errors; marker selection remains tied to its Cutting Plan/LaySheet flow. |
| Cutting LaySheet | `CLS-2603-00251`, `CLS-2608-00093`, `CLS-2606-00294`, `CLS-2607-00276`, `CLS-2608-00109`, `CLS-2608-00066`; Label Printed, Approval Pending, Bundles Generated, Completed, Started, cancelled | Approval Pending, Label Printed, and Cancelled are non-editable in Desk and its mounted cloth/accessory Vue editors. Bundle generation uses the saved marker/rows, label printing uses saved bundles/lay numbers, GRN creation is allowed only from Bundles Generated, and terminal-state mutation APIs fail server-side. |
| Delivery Challan | `DC-2526-07291`, `DC-2627-00057`, `DC-2627-03557`, `DC-2627-01677`, `DC-2627-03405`; cutting, printing, draft, cancelled, CPM-linked | Work Order context is enforced server-side. Large item matrices are contained horizontally. The authenticated `/web` list, existing detail, and new-document form also pass with no console/page errors. |
| Stock Entry | `STE-2026-05590`, `STE-2026-13931`, `STE-2026-12654`; submitted, draft CPM-linked, cancelled CPM-linked | Large matrices are contained. CPM ownership is validated on save/submit; normal unrelated Stock Entries and completion Stock Entries remain unaffected. Submit/cancel bundle effects are symmetric in integration tests. |
| Cut Panel Movement | `CPM-2603-00364`, `CPM-2604-00015`, `CPM-2604-00036`, `CPM-2608-00187`, `CPM-2606-00482`, `CPM-2608-00220`, plus anomalous `CPM-2608-00052` and `CPM-2608-00222` | Stock move, printing DC, printing GRN, draft, submitted, cancelled, unlinked, closed-WO rejection, and collapsed-bundle paths were exercised. One CPM may now own only one active root transaction across Stock Entry/DC/GRN, enforced with a locked server check. Existing conflicts show linked warnings and no additional Create actions. |
| Cut Bundle Movement Ledger | `v42mbob5ds`, `i9is4s7f5f`, `80094ttgma`, `8t7f1kbeqo`, `fg5kutdge1`; chain plus LaySheet/Stock Entry/DC/GRN origins | All source transaction types render and the complete cut-bundle edit/transform/submit/cancel lifecycle passes. Collapsed-bundle and non-bundle routes are covered. |

Representative evidence:

- Production ratio editor: `after-production-order-ratio-editor-production-order-PPO-00257-top.png`
- Approved IPD tabs: `after-approved-lock-item-production-detail-...-tab-1..8-*.png`
- Work Order address results: `verified-address-filter-results-work-order-YRP-WO-2026-00038-actual.png`
- Work Order garment button/dialog:
  `2026-08-20_09-49-55-work-order-00038-calculate-button.png` and
  `2026-08-20_09-50-22-work-order-00038-calculate-dialog.png`
- Approved-IPD matrix backfill:
  `2026-08-20_09-50-43-ipd-heavy-tee-regenerate-button.png` and
  `2026-08-20_09-51-03-ipd-heavy-tee-regenerate-result.png`
- Cancelled Cutting Plan guard: `after-cancelled-guard-cutting-plan-CP-2605-00019-top.png`
- Final LaySheet locks: `final-approval-pending-authority-...` and
  `final-label-printed-authority-...`
- CPM ownership warnings: `after-active-draft-warning-...` and
  `after-multiple-active-warning-...`

## Defects corrected by this audit

1. Work Order supplier/delivery address fields returned unrelated Addresses.
2. The cloth-only Calculate action was incorrectly used as the whole Work
   Order calculation path. Non-cloth Cutting then either showed a fabric-only
   action that failed or, after hiding it, had no Calculate action at all. The
   final routing has separate cloth and garment actions and restores the F15
   garment calculation flow.
3. Wide ratio/item matrices escaped Work Order, Delivery Challan, and Stock
   Entry form bounds.
4. Approved Item Production Details remained editable through multiple Desk,
   `/web`, bulk-edit, BOM, and direct-save paths.
5. Cutting Plan and Cutting LaySheet mutation endpoints trusted UI state or
   browser-provided rows after a record became terminal. Direct saves could
   also spoof entry into Approval Pending, Label Printed, or Cancelled. Those
   transitions now use locked server actions that recheck grammage and the
   LaySheet's submitted GRN.
6. Cut Panel Movement could acquire several draft/submitted root transactions
   because ownership was claimed only on submit.
7. Production Order showed a duplicate incomplete Lotwise card despite the
   Essdee ratio editor already being authoritative.
8. The Approved-IPD lock initially caught the legitimate generated-cloth
   rebuild too; the final implementation grants only the internal builder a
   scoped, document-specific save capability.
9. Migrated garment IPDs could predate `IPD Process Matrix`. Approved legacy
   records now have an explicit derived-matrix backfill action. For
   `CS-34820 Heavy Tee-1`, 24 Cutting matrices generate successfully; its eight
   Navy variants are reported as skipped because the source IPD has no Navy
   stitching/panel-colour combination, rather than inventing a consumption.

## Automated verification

- Full `essdee_yrp` app: **434/434 passed** — 12 unit, 258 integration, 78
  old-Frappe-category, and 86 remaining-category tests.
- Cloth-program builder: **50/50 passed**, both focused and again inside the
  full app run.
- Cutting business logic: **16/16 passed** inside the full run, including CPM
  → DC → GRN and CPM → Stock Entry round trips, cancellation symmetry,
  collapsed bundles, migrated LaySheet GRN, and recut stock.
- Production Order business logic: **12/12 passed**; Production Order
  customization: **2/2 passed**.
- Work Order calculation/API: **20/20 passed**; Work Order customization:
  **2/2 passed**.
- Delivery Challan, GRN, and Stock Entry customization: **4/4 each passed**.
- `npm run build` in `apps/essdee_yrp/frontend`: passed, 505 modules
  transformed. The existing Vite large-chunk advisory is non-fatal.
- Authenticated `/web` verification: **6/6 screenshots**, zero console errors,
  page errors, or warnings; configuration validation has zero warnings/errors.
  Evidence: `/home/anas/frappe-16/screenshots/verify-ui/current-01..06-*.png`.
- Changed Python files compile and the app diff passes `git diff --check`.

## Known pre-existing validation limitations

- `verify-ui --full` completes all browser/server checks and all 305
  `yrp.yrp.api.test_ui_config` tests, but one of 19 base-YRP UI-metrics tests
  fails in its own setup assertion. The throwaway restricted user has no
  role-level Work Order read permission, so `frappe.get_list` returns `[]`
  before the metric under test executes. This is outside the owner-authorized
  base change and was not modified.
- The normal base-YRP Work Order test runner is blocked during global fixture
  preload by the unrelated missing live DocType `Stock Valuation Closing`.
  The address-filter source contract and rendered link results were verified
  directly. No migration was run to alter the site just to unblock that test.

## Existing live-data conflicts retained

No migrated business data was rewritten or deleted. Two historical CPM
conflicts remain visible for manual cleanup:

- `CPM-2608-00052`: simultaneous draft Delivery Challan `DC-2627-03405` and
  draft GRN `GRN-2627-04745`.
- `CPM-2608-00222`: draft Stock Entry `STE-2026-13931` plus submitted Delivery
  Challan `DC-2627-03570`.

The UI now lists these active links and prevents creating another root; the
server applies the same rule under a row lock for all new saves/submissions.
