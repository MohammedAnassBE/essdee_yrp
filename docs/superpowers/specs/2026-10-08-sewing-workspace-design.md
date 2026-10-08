# Sewing Workspace Design

## Objective

Build the Sewing department inside the existing `/web` Vue application so sewing-unit users can operate Sewing Plans, review sewing reports, and open the attendance strength report without using the legacy Frappe 15 Desk page.

The Frappe 15 `production_api` Sewing Details page is a behavioral and API reference only. The implementation must use the current polished `/web` design system, the migrated Frappe 16 domain services, Frappe permissions, and server-authoritative validation.

The Sewing landing page contains exactly three cards:

1. Sewing Plan
2. Reports
3. Attendance Report

The workspace selector called `Warehouse` in the legacy page is actually a Supplier filtered by `is_company_location = 1`. The new UI labels it Sewing Unit while preserving the Supplier value and `supplier` API contract.

## Approved scope

### Sewing Plan

The Sewing Plan card contains exactly five operational tabs:

1. Dashboard
2. Data Entry
3. Entries
4. Consumption
5. Closed Work Order GRN

### Reports

The Reports card contains exactly five supplier-scoped reports:

1. Status Summary
2. DPR
3. SCR
4. Monthly Summary
5. Item Summary

### Attendance Report

The Attendance Report card contains the Strength Report as a standalone reusable component. It is global because the installed HR endpoint has no Supplier or Sewing Unit mapping. It uses only the existing report inputs and output needed for the Strength Report. No new HR department, HR location, designation, employee, or Supplier-mapping feature is introduced in this scope.

The legacy Status Summary, DPR, SCR, Monthly Summary, Item Summary, Data Entry, Entries, Consumption, and Closed Work Order GRN behaviors are reference requirements. FI Updates, Input/Output, Input Pending, and other legacy tabs are intentionally excluded.

## Existing-system findings

The required business logic is substantially migrated in Frappe 16:

- `essdee_yrp/sewing/read_models.py` owns dashboard, Status Summary, SCR, Entries, daily DPR, Monthly Summary, Item Summary, and consumption read models.
- `essdee_yrp/sewing/entry.py` owns Data Entry loading, entry creation, inspection updates, and entry cancellation with stronger server validation than Frappe 15.
- `essdee_yrp/sewing/closed_work_order.py` owns the privileged Closed Work Order GRN flow and normalizes browser quantities against authoritative Work Order rows.
- `essdee_yrp/sewing/strength.py` owns the external HR Strength Report integration.
- `essdee_yrp/sewing/plan.py` and `config.py` own Work Order integration and stage-sequence configuration.
- `essdee_yrp/essdee_yrp/doctype/sd_yrp_sewing_plan/sd_yrp_sewing_plan.py` exposes the migrated endpoints.
- `frontend/src/departments/Sewing.vue` is currently a placeholder.
- the legacy Frappe 16 components under `essdee_yrp/public/js/SewingPlan/` remain a behavioral reference, not a component dependency.

Material gaps that must be resolved:

- the Frappe 16 Status Summary intentionally omits several derived legacy values;
- date-range DPR summary is present in the current Frappe 15 reference but not in the Frappe 16 read model;
- entry cancellation needs a server-side previous-entry-day eligibility guard rather than UI-only gating;
- report and operational permissions need an explicit `/web` capability contract;
- the existing `/web` catalog does not yet expose the Sewing Plan capability;
- slow or stale responses must not overwrite newer Supplier/filter selections.

## Product and engineering rules

- Reuse Vue 3, PrimeVue, Vite, Frappe RPC, PrimeIcons, and the existing `--erp-*` enterprise design tokens.
- Do not copy the old Frappe 15 theme, global Desk dependencies, jQuery workflow, or broad `ignore_permissions` behavior.
- Keep all normal operations inside `/web`; do not redirect to Desk.
- Use the same premium, compact, responsive workspace, card, tab, filter, table, dialog, confirmation, error, and empty-state patterns already established for Cutting, Fabric Store, Accessory Store, and Cut Panel Store.
- The selected Sewing Unit must scope every Sewing Plan and Reports request on the server.
- Attendance Report remains explicitly global and does not present a misleading Sewing Unit filter.
- Load only the active tab. Changing Sewing Unit cancels or invalidates stale requests and reloads only the active view.
- Preserve active tab and filters while navigating within a card. Never trigger every report simultaneously.
- Errors use the shared application popup and preserve entered values. Browser alerts and raw traceback messages are forbidden.
- Browser payloads never own remaining quantities, allowances, Work Order ownership, variant identity, received-type eligibility, or GRN lifecycle state.
- Every mutation reloads authoritative state and rechecks permission, document state, Supplier ownership, and concurrency-sensitive quantities.

## Information architecture and routes

### Landing page

`/web/sewing` shows a compact Sewing Unit selector followed by the three permission-aware cards. The selector searches Supplier with `is_company_location = 1`.

Sewing Plan and Reports require a Sewing Unit. Until one is selected, their cards remain visible with a clear selection requirement and do not issue data requests. Attendance Report is immediately available because it is global.

The selected Supplier is stored in the route query as `supplier`. It survives refresh, browser navigation, and card changes without creating a second global store.

### Routes

- `/web/sewing`: launcher and Sewing Unit selection.
- `/web/sewing/plans`: five-tab operational workspace.
- `/web/sewing/reports`: five-tab reporting workspace.
- `/web/sewing/attendance`: standalone Strength Report.

The `supplier` query is preserved on the first two routes. A direct plan/report URL without a Supplier shows the shared Sewing Unit selection state instead of running an unscoped query.

## Shared Sewing context

A focused route-backed composable owns:

- selected Supplier name;
- Supplier display label;
- current tab;
- Supplier link filters;
- route query synchronization;
- a request generation token or abort mechanism for stale-response protection;
- a common missing-selection state.

The context does not cache business records or duplicate server calculations. Individual tab components own their own filter state and results.

## Sewing Plan workspace

The workspace uses a compact sticky context header containing back navigation, Sewing Unit, refresh, and the tab selector. Desktop uses horizontal tabs; narrow layouts use the shared responsive selector. Only the active tab is mounted.

### Dashboard

Dashboard calls the migrated `get_dashboard_data(supplier)` service and shows open-Work-Order quantities grouped by configured input type.

The presentation uses a small metric row plus a compact stage distribution table or chart only when the data benefits from it. Empty configuration, no open orders, permission errors, and load failures have distinct states. The UI does not invent delivered, pending, or balance values that the endpoint does not return.

### Data Entry

Data Entry uses the Frappe 16 trusted-row contract from `entry.py`, not the browser-trusting Frappe 15 payload.

The page provides:

- optional Lot filtering within the selected Supplier;
- grouped Lot and Sewing Plan sections;
- date, time, work station, input type, and received type controls;
- compact colour/size matrices with ordered, previous-stage, entered, remaining, and allowance context;
- one clear primary save action;
- inspection update/revert only when supported by the migrated contract.

The server rebuilds and validates row identity, stage ordering, allowance, remaining quantity, positive quantities, permissions, and current data under a lock before saving. Concurrent or stale quantities return a clear popup and refresh the affected matrix after acknowledgement.

### Entries

Entries provides Work Station, Input Type, and Lot filters and groups results by entry date. Each entry displays the posting context and a compact colour/size quantity matrix.

Cancel is shown only when the entry is eligible under `MRP Settings.previous_day_entries` and the user has delete permission. The endpoint repeats the same date-window check before deletion so a crafted request cannot bypass the UI. Cancellation uses the shared confirmation dialog, then refreshes the current filtered result.

### Consumption

Consumption offers only Lots belonging to the selected Supplier. It loads the Item Production Detail, BOM-derived sections, attribute mappings, and cloth accessory consumption through the migrated Frappe 16 service.

The UI uses compact editable sections with clear UOM and authoritative BOM quantity context. Save replaces only the intended consumption rows for plans matching the selected Supplier and Lot. Supplier is passed explicitly through read, save, and print flows; no arbitrary Supplier is inferred from a Lot.

### Closed Work Order GRN

The Work Order search returns only submitted, closed Sewing Work Orders belonging to the selected Supplier and readable by the user.

Selecting a Work Order loads server-normalized receivables into the current `/web` grouped-item GRN editor. The form collects the required naming series, posting date/time, delivery date, supplier document details, vehicle number, DC number, comments, received type, and quantities supported by the Frappe 16 contract.

Create and Submit are a single intentional action only when both permissions are available. The server locks the Work Order, verifies Supplier ownership and Sewing Plan association, rebuilds item identity and pending quantities, rejects duplicates/negative/mismatched quantities, and invokes the migrated closed-WO lifecycle marker so materials are not consumed twice.

## Reports workspace

All five reports use the shared `ReportShell`, compact filter bar, metrics, sticky table headers, contained horizontal overflow, explicit Generate/Reset actions where appropriate, and copy/export behavior already supported by the application. They never mount or fetch until selected.

### Status Summary

Status Summary is scoped to open Work Orders for the selected Supplier. It restores the current reference contract needed by operations:

- order, delivered, and GRN quantities;
- configured input stages by received type;
- pre-final and final quantities;
- FI/input/last-output dates;
- readiness state, running days, line stock, checking stock, and GRN pending;
- Lot, Item, Colour, Part, and input-date filters;
- recomputed visible totals after client filters.

Derived values are calculated on the server from authoritative records. The UI formats and filters returned rows only.

### DPR

DPR supports:

- daily mode with date, optional Work Station, and optional Input Type;
- date-range summary mode with From Date, To Date, optional Work Station, and optional Input Type.

The missing Frappe 16 range endpoint is implemented in the Sewing read-model layer with permission and Supplier scoping. The whole-report pending-FI behavior from the reference must be made explicit in the response and UI; the user receives a clear list of blocking Lots instead of an unexplained empty report.

### SCR

SCR requires a Supplier-scoped Lot and supports Colour filtering. It displays the authoritative colour/size/input-stage matrix, ordered/delivered values, configured stage balances, received-type totals, and work-station lines. It does not claim to be a machine-capacity calculation.

### Monthly Summary

Monthly Summary uses Start Date, End Date, Input Type, and the installed GRN mode. Results retain the reference date rows, Item/Part columns, and grand total. The endpoint owns grouping and totals; Vue owns presentation and export only.

### Item Summary

Item Summary loads Supplier-scoped Lot and Item options. At least one Lot or Item is required. When both are selected, the endpoint applies their intersection. Results group Item/Lot rows by date, input type, work station, colour, part, size, and total.

## Attendance Report

`/web/sewing/attendance` renders a reusable Strength Report component under the normal Sewing department shell.

The component uses the installed `get_worker_strength_report(report_date, from_time, to_time)` service. It exposes only:

- report date;
- from time;
- to time;
- Generate and Reset;
- returned strength rows, punch context, shift context, and total row;
- the supported export action.

It does not add Supplier, Sewing Unit, HR department, HR location, designation, or employee-selection requirements. External HR failures, missing configuration, authentication failure, and timeout receive distinct, plain-language application errors. The component can be imported by another workspace later without coupling it to Sewing routes.

## Frontend component design

New focused components live under `frontend/src/departments/sewing/`:

- `SewingLauncher.vue`
- `SewingPlanWorkspace.vue`
- `SewingReportsWorkspace.vue`
- `SewingUnitPicker.vue`
- one component for each operational tab and report;
- shared sewing matrix/filter helpers where at least two views use the same contract.

The reusable Strength Report component lives under the shared report tree rather than inside a Sewing-only folder.

`frontend/src/api/sewing.js` owns method paths and thin request functions. Components do not embed long dotted Frappe method names or business calculations.

Existing shared components remain authoritative for layout, Link fields, dates/times, responsive tabs, report shells, tables, dialogs, errors, confirmations, loading, and empty states. No second component library or Sewing-only theme is introduced.

## Backend boundary

The installed modules under `essdee_yrp/sewing/` remain business owners. A small web-capability module may expose permission-aware card and action capabilities, but it must delegate domain work rather than duplicate it.

Backend changes are limited to:

- explicit Sewing `/web` capabilities;
- missing Status Summary parity fields;
- date-range DPR summary;
- server-side cancellation date eligibility;
- any small adapters needed to provide stable browser contracts over existing domain functions;
- focused query/performance improvements proven necessary by tests.

The current Frappe 15 implementation is never copied wholesale. In particular, new endpoints must not use broad `ignore_permissions`, trust browser variant metadata, allow unscoped Supplier reads, or perform permanent deletes without permission and eligibility checks.

## Permissions and security

- Launcher card visibility is capability-driven.
- Every read checks Sewing Plan read permission and applies the selected Supplier on the server.
- Data Entry and inspection writes check the relevant write/create permission and authoritative stage/row state.
- Entry cancellation checks delete permission and configured date eligibility.
- Consumption writes check write permission for every affected plan and limit changes to the selected Supplier and Lot.
- Closed Work Order GRN repeats Work Order read, GRN create/submit, closed status, Supplier ownership, Sewing Plan association, and pending-quantity validation under a lock.
- Strength Report checks the installed Sewing/Strength access rule but remains globally scoped by design.
- Unknown fields, unsupported received types, stale documents, invalid dates/times, and negative or excessive quantities are rejected server-side.

## Responsiveness and interaction quality

- Desktop density targets normal 1366–1920 px operational screens without oversized cards or empty vertical space.
- Filters stay compact and align in one or two rows before introducing horizontal scrolling.
- Matrices and reports own their overflow; the page itself must not horizontally scroll.
- Sticky identity/action/filter regions are used only where they reduce repeated scrolling.
- Mobile and narrow desktop keep every action and value, stacking controls and using contained table overflow instead of removing columns silently.
- Focus, keyboard navigation, labels, required states, disabled explanations, and contrast follow the shared accessibility rules.
- Loading never blanks an already useful screen; stale visible data is marked while refreshing, and mutation actions are locked against double submission.

## Error handling

All server and network failures pass through the shared error normalizer and application dialog. Expected validation errors use concise business wording and identify the relevant Lot, plan, Work Order, input stage, or field. Raw Python messages, HTML fragments, HTTP status-only text, and duplicated inline-plus-popup errors are forbidden.

External Strength Report failures distinguish missing configuration, upstream authentication, upstream timeout, and empty data. The rest of the Sewing workspace remains usable when HR is unavailable.

## Testing and acceptance

### Backend

- capability and permission tests for all three cards;
- Supplier scoping for every Sewing Plan and Reports read model;
- Data Entry allowance, stage sequence, trusted-row, positive-quantity, stale/concurrent, and permission tests;
- Entries cancellation permission and previous-entry-day eligibility tests;
- Consumption read/save Supplier+Lot isolation and permission tests;
- Closed Work Order GRN lifecycle, lock, ownership, normalization, duplicate, and double-consumption-bypass tests;
- Status Summary parity and totals tests;
- daily and date-range DPR tests, including pending-FI behavior;
- Strength Report configuration/error normalization tests.

### Frontend

- launcher renders exactly three permission-aware cards;
- Sewing Unit selection filters Supplier by `is_company_location = 1` and persists through route queries;
- Sewing Plan has exactly five tabs and Reports exactly five tabs;
- only the active tab fetches, stale Supplier responses are ignored, and filters survive tab changes;
- all read, empty, permission, loading, error, and refresh states;
- Data Entry save, inspection, Entries cancel confirmation, Consumption save, and Closed Work Order GRN creation;
- daily/range DPR and every report filter contract;
- Attendance Report has no Supplier or HR-department mapping controls;
- popup error rendering and value preservation;
- responsive desktop/tablet/mobile containment with no page-level horizontal overflow.

### Release verification

- run focused Python tests for the Sewing domain and web contracts;
- run the complete relevant frontend browser/mock suites;
- build the production frontend;
- manually verify all three cards and every included tab against representative Supplier data;
- verify direct URLs, refresh/back navigation, permission-restricted accounts, concurrent-entry rejection, and HR-unavailable behavior;
- inspect the final UI at normal laptop width and narrow width for premium consistency with the rest of `/web`.

## Out of scope

- creating or maintaining Sewing Plan masters outside existing Work Order behavior;
- FI Updates and Input Pending tabs;
- a new Supplier-to-HR department/location mapping;
- HR department, location, designation, or employee administration;
- changing the external HR report API;
- copying the Frappe 15 visual theme or exposing Desk as the normal workflow;
- redesigning unrelated Cutting, Fabric Store, Accessory Store, or Cut Panel Store behavior.
