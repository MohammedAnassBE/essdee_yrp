# Cutting Workspaces Design

## Objective

Complete the Cutting area inside the existing `/web` Vue application so cutting-room users can create and operate Cutting Plans, Cutting Orders, Cutting Bulk LaySheets, and Cutting LaySheet Planner records without visiting Desk. Preserve the current Reports workspace and the established enterprise visual system.

The completed Cutting landing page has five permission-aware destinations:

1. Cutting Plans
2. Cutting Orders
3. Bulk LaySheets
4. LaySheet Planner
5. Reports

## Existing-system findings

The required business workflows already exist in Frappe 16 under `essdee_yrp`:

- `SD YRP Cutting Plan` owns Lot-based item planning, cloth generation and receipt, LaySheet calculation, completion, recut, print-panel, transfer, approval, Marker and LaySheet relationships, and Cutting Plan print formats.
- `SD YRP Cutting Order Detail` defines the item, colours, sizes, set-item combinations, panel structure, and order-planning inputs used by Cutting Orders.
- `SD YRP Cutting Order` owns the quantity matrix, submission lifecycle, LaySheet calculation, completed/incomplete summaries, planned-versus-actual summary, Markers, LaySheets, and Cutting Order print formats.
- `SD YRP Cutting Bulk Lay Sheets` owns main-stock-lot setup, split-lot validation, LaySheet creation, active LaySheet cloth/accessory editing, bundle generation, shared or per-lot Lot Transfers, Delivery Challans, grammage approval, label printing, and aggregate workflow status.
- `SD YRP Cutting Laysheet Planner` owns optimizer input validation, asynchronous long-worker execution, status polling, strategy comparison, strategy selection, lay details, totals, and per-size deviation.

The `/web` application currently exposes the Cutting Plan list and existing-record workspace, but it does not expose Cutting Plan creation. The other three workspaces are not yet exposed in `/web`.

## Project constraints

- Preserve Vue 3, PrimeVue, Vite, Frappe RPC/REST, PrimeIcons, and the existing enterprise CSS tokens.
- Do not introduce another component library or design system.
- Keep current Frappe/YRP/Essdee document controllers authoritative. Vue must not duplicate stock, cutting, quantity, status, or optimizer calculations.
- Do not redirect to Desk during normal work. Lists, creation, editing, document actions, related-document viewing, and print selection remain inside `/web`.
- Use record-level Frappe permissions and document state as the security boundary. Button visibility is presentation only; the server repeats every check.
- Preserve the current Cutting Plan and Reports behavior unless this specification explicitly extends it.
- Preserve the dirty worktree and keep the implementation uncommitted unless the user later requests a commit.

## Information architecture and routes

### Landing page

`/web/cutting` shows five compact workspace cards. A card is rendered only when the user can read its primary DocType or report capability. If none is available, show one intentional permission-empty state.

### Routes

- `/web/cutting/plans`: Cutting Plan list.
- `/web/cutting/plans/new`: new Cutting Plan editor.
- `/web/cutting/plans/:cuttingPlanId`: existing Cutting Plan workspace and Draft editor.
- `/web/cutting/orders`: Cutting Order list.
- `/web/cutting/orders/new`: new Cutting Order editor.
- `/web/cutting/orders/:cuttingOrderId`: existing Cutting Order workspace and Draft editor.
- `/web/cutting/bulk-lay-sheets`: Bulk LaySheets list.
- `/web/cutting/bulk-lay-sheets/new`: new Bulk LaySheets editor.
- `/web/cutting/bulk-lay-sheets/:bulkLaySheetId`: Bulk LaySheets workspace.
- `/web/cutting/lay-sheet-planner`: LaySheet Planner list.
- `/web/cutting/lay-sheet-planner/new`: new planner editor.
- `/web/cutting/lay-sheet-planner/:plannerId`: existing planner workspace.
- `/web/cutting/reports`: existing Cutting Reports workspace.

Successful first saves replace the `/new` route with the saved record route. Existing Draft records reopen in edit mode when permitted. Submitted records open read-only except for explicit controller actions.

## Shared list contract

All four document lists reuse the finalized `ListView` and `ListviewFilters` behavior:

- one-second quick-filter debounce;
- field-aware Link, Select, Check, Date, Time, Datetime, numeric, and text filter controls;
- search, advanced filters, clear filters, sorting, pagination, refresh, and customizable drag-and-drop columns;
- Frappe-style bulk selection, edit, submit, and cancel where supported and permitted;
- `modified desc` as the initial order;
- no record-count headline, technical helper copy, or duplicated page heading;
- explicit loading, empty, filtered-empty, error, and permission-denied states.

Each list has a permission-aware Create action. The list does not embed implicit business filters. Record-level Frappe read permission remains authoritative.

### Default list presentations

- Cutting Plans: ID, Lot, Item, status, number of colours, completed colours.
- Cutting Orders: ID, Cutting Order Detail, Item, status, Lay number, cutting location.
- Bulk LaySheets: ID, main stock Lot, stock location, posting date, status.
- LaySheet Planner: ID, description, Lot, Item, optimization status, selected strategy, modified time.

Users may change these columns through the existing column customizer.

## Cutting Plan creation and Draft editing

The Cutting Plan list adds Create Cutting Plan when the user has create permission. Creation uses a full routed editor rather than a small dialog because the item quantity matrix is primary content.

The editor exposes the meaningful Desk fields in their existing logical order:

- Is Manual Entry;
- Lot;
- Maximum No of Plys;
- Maximum Allow Percent;
- Cutting Location;
- Work Order when the field is permitted and applicable;
- the Lot-derived colour/size item quantity matrix.

Selecting a Lot calls the existing authoritative `get_items` service and refreshes the matrix. Item, production detail, status, counters, dates, and other derived fields are not browser-controlled. The server reloads the Lot and validates all submitted matrix rows.

Available actions depend on permission and state:

- Save Draft requires create for a new record or write for an existing Draft.
- Save & Submit additionally requires submit permission.
- Cancel and Amend follow Frappe lifecycle permissions.
- Closing a dirty editor requires confirmation.

After saving, the user remains in `/web` and the page becomes the normal Cutting Plan workspace. Existing Draft Cutting Plans expose Edit in the same workspace and use the same editor component.

## Cutting Order workspace

### List and creation

The Cutting Order list uses the common list contract and opens a full routed workspace. Create Cutting Order opens the routed editor.

The editor includes:

- Cutting Order Detail;
- Item derived from the selected detail;
- Cutting Location;
- Maximum No of Plys;
- Maximum Allow Percent;
- colour/size quantities, including part-aware rows for set items.

Selecting a Cutting Order Detail uses `get_cutting_order_detail_data` to load authoritative item, colour, size, part, and combination data. Derived Item and set-item state are read-only.

### Cutting Order Detail inside Cutting

The Cutting Order Detail Link control supports Select Existing, Create New, and Edit Selected without leaving the Cutting section. Create and Edit open a maximizable nested dialog using the authoritative Cutting Order Detail schema and controllers.

The nested editor preserves the Desk business model:

- parent Item and relevant item-production context;
- packing and primary attributes;
- set-item attribute and combinations where applicable;
- colours, sizes, panel definitions, and other existing detail inputs;
- Save Draft or permitted lifecycle action supported by the DocType.

After save, the dialog closes, the new or updated detail is selected, and the Cutting Order quantity matrix reloads. The server controls derived combinations and rejects stale or incompatible detail data.

### Existing record view

The record header contains back navigation, title, ID, status, Edit, Print, and the compact action toolbar. The desktop body uses the established 80/20 split.

The main 80% contains fixed tabs with independently scrolling content:

1. Details
2. Summary
3. Planned Detail

Details shows the relevant Cutting Order fields and quantity matrix without duplicate identifiers or hidden implementation fields. Summary shows completed and incomplete structures using the same production components as Cutting Plan. Planned Detail uses the existing `get_cutting_order_planned_vs_actual` service and grouped analytical table.

The action toolbar exposes controller-backed actions only when permitted and valid for the current state:

- Calculate LaySheets;
- Get Completed, including Copy;
- Update Completed;
- standard Save, Submit, Cancel, Amend, Edit, and Print actions.

The toolbar uses the same compact action-button vocabulary as Cutting Plan. It must not resemble navigation headings.

### Marker and LaySheet rail

The right 20% is split into equal-height, independently scrolling Marker and LaySheet sections. Records sort by modified time descending.

- Marker cards show marker name, ID, length, width, required piece weight, panels, and status.
- LaySheet cards show Lay number, Marker name, Marker panels, bundle-generated date, printed time, and status.
- Filter controls use the shared field-aware filter component.
- Create New appears only with create permission and valid parent state.
- Selecting or creating a Marker/LaySheet opens the shared in-page dialogs parameterized with `cutting_order` instead of `cutting_plan`.
- Marker and LaySheet Save, Submit, Cancel, Amend, Print, bundle, grammage, and label actions remain in their dialogs and call existing authoritative controllers.

## Bulk LaySheets workspace

### Setup and structure

The Bulk LaySheets list opens a routed 80/20 workspace.

The main 80% holds:

- setup fields: Main Stock Lot, Stock Location, Posting Date, Cutting Spreader, and Cutter;
- the split-lot entry table;
- the active LaySheet cloth editor;
- the active LaySheet accessory editor;
- generated bundle details;
- a compact action bar containing only actions valid for the selected split lot or the whole bulk record.

The right 20% shows one independently scrollable workflow card per split lot. Each card displays:

- split Lot;
- Cutting Plan;
- Cutting Marker;
- Cutting LaySheet;
- Lot Transfer;
- Delivery Challan;
- current workflow status.

Selecting a card saves permitted dirty editor values, switches the authoritative active LaySheet, and refreshes the main editor without navigation.

### Creation and locking

Create Bulk LaySheets opens the routed setup editor. Users enter the setup fields and split-lot rows. Each split-lot row chooses Lot, its submitted non-completed Cutting Plan, and a submitted Marker belonging to that plan.

The server preserves the existing validations:

- the split Lot differs from the main Lot;
- duplicate or incompatible split rows are rejected;
- the Cutting Plan belongs to the split Lot and has a Work Order;
- the Marker belongs to the selected Cutting Plan;
- setup and source fields lock when downstream LaySheets or stock documents exist;
- created split rows cannot be removed or silently retargeted.

### Workflow actions

The `/web` workspace exposes all existing controller-backed operations without Desk redirects:

- Create Lay Sheets;
- select and edit the active LaySheet cloth/accessory details;
- Generate Bundles;
- Create, Submit, and view a per-lot Lot Transfer;
- Create, Submit, and view a shared Bulk Lot Transfer;
- Create, Submit, and view a per-lot Delivery Challan;
- Create and submit pending Delivery Challans in bulk;
- approve LaySheet grammage when required;
- choose printer and print bundle labels;
- view related generated bundles and Goods Received Note references;
- open related documents in common in-page dialogs.

Action availability is derived from the authoritative row status and effective permissions. Stock sufficiency, transferred/DC stock, grammage tolerance, and print prerequisites are always revalidated on the server.

Long data areas scroll inside their panels. Header, action bar, and split-lot selector remain available while users work through the active lot.

## LaySheet Planner workspace

### Inputs tab

Create Planner opens the routed editor. The Inputs tab contains:

- Description;
- optional Lot and Item;
- Maximum Plies;
- Maximum Pieces Per Marker;
- Tolerance %;
- Maximum Lays;
- Tubular Fabric;
- editable size-wise Order Details.

The input editor enforces the existing rules: unique non-empty sizes, non-negative integers, at least one positive quantity, positive limits, tolerance within range, and even accepted ply counts for tubular fabric.

Saving changed inputs invalidates prior results. Inputs are locked while the optimizer is Queued or Running.

### Strategies tab

Optimize and Re-optimize call the existing asynchronous service. The browser never runs optimization logic. The UI displays explicit Not Started, Queued, Running, Completed, and Failed states and polls the lightweight status endpoint only while active.

Completed results show each accepted Pareto strategy in a comparable, compact result selector. The user can inspect and select a strategy. Selection calls the existing `select_strategy` endpoint, refreshes the saved summary and lay details, and stays on the current route.

Failed, invalid, dominated, duplicate, infeasible, and timed-out outcomes are shown separately from successful strategies without exposing raw server tracebacks.

### Lay Plan tab

The selected strategy view contains:

- total lays;
- total order quantity;
- total cut quantity;
- overcut and percentage;
- undercut and percentage;
- lay rows with ratio and ply information;
- per-size ordered, cut, deviation, and percentage values.

Numeric cells use tabular figures. Wide strategy and size matrices scroll inside their containers without page-level overflow.

### Planner lifecycle

- Save Draft and editing follow create/write permission.
- Optimize requires write permission and a saved valid record.
- Active jobs cannot be duplicated.
- Retry is available after Failed when the user can write.
- Delete follows DocType permission and is unavailable while work is active.
- Print is shown only if a registered print format exists and the user has print permission.

## Shared components and modularity

The implementation extends existing components instead of creating page-specific copies:

- `ListView`, `ListviewFilters`, quick filters, and column customizer remain common.
- one common document lifecycle/print dialog handles related documents.
- Marker and LaySheet dialogs accept an explicit parent contract (`cutting_plan` or `cutting_order`).
- completion, grouped item, stock item, and analytical table components are reused.
- focused editors own Cutting Plan, Cutting Order, Cutting Order Detail, Bulk LaySheets, and Planner state independently.
- large routed pages are composed from focused tab, rail, editor, and action components so no single file becomes an unreadable workflow monolith.

## Backend boundary

Focused web modules under `essdee_yrp.cutting` own browser contracts. They may call the installed DocType controllers but must not copy their business logic.

The backend provides explicit endpoints for:

- expanded Cutting capabilities for all five landing destinations;
- Cutting Plan create/edit defaults, Lot item matrix loading, validated save, and lifecycle actions;
- Cutting Order create/edit defaults, Detail-derived matrix loading, validated save, view payload, actions, Markers, and LaySheets;
- Cutting Order Detail load/create/edit within the nested workflow;
- Bulk LaySheets load/create/edit, workflow projection, active-lot switching, and every existing bulk action;
- Planner load/create/edit, optimization initiation, status, strategy selection, and result projection;
- related-document dialog data and print registry data.

Endpoints must:

- whitelist supported DocTypes, fields, and operations;
- call `check_permission` or `frappe.has_permission` for every read and mutation;
- reload authoritative source documents immediately before mutation;
- accept expected `modified` for edits and report stale-document conflicts;
- preserve child-row identity when editing tables;
- reject unknown, removed, duplicate, incompatible, or browser-invented rows;
- call standard insert, save, submit, cancel, and amend behavior;
- call existing Cutting Order, Bulk LaySheets, LaySheet, Marker, and Planner services for specialized actions;
- return user-safe validation messages and never raw tracebacks.

## Permissions

UI capabilities are derived from Frappe DocType permissions plus current record state:

- read controls destination, list, tab, rail, and related-document visibility;
- create controls New/Create actions;
- write controls existing Draft editing and optimizer initiation;
- submit controls Submit and Save & Submit;
- cancel controls cancellation of submitted documents;
- amend controls amendment of cancelled documents;
- delete controls eligible Draft deletion;
- print controls print actions and format selection.

Related Marker, LaySheet, Cutting Order Detail, Lot Transfer, Delivery Challan, and Goods Received Note actions use their own DocType permissions. Permission for the parent does not imply permission for the child. Direct endpoint calls receive the same checks as the visible UI.

## Visual and interaction system

Use the current PrimeVue enterprise system:

- off-white/mint canvas, white surfaces, restrained emerald accent;
- 8px controls, 12px panels, thin neutral borders, and subtle tinted depth;
- existing `Segoe UI Variable` stack;
- 11px minimum supporting text, readable 13px values, and tabular numeric cells;
- one consistent radius, spacing, and colour vocabulary;
- compact action buttons with clear icons, labels, keyboard focus, hover, pressed, and disabled states;
- no gradients, glass effects, oversized headings, repeated explanatory copy, decorative labels, or card nesting without hierarchy;
- sticky record tabs and action areas where content scrolls beneath them;
- skeletons matching final layouts;
- accessible contrast and no page-level horizontal overflow at 1600px, 1280px, 900px, or 390px widths.

Dialogs are maximizable and dismissable by mask when no dirty state would be lost. Dirty editors require discard confirmation. Nested dialogs preserve their parent context. Dialog content scrolls independently while headers and footers remain visible.

## Error and state handling

- Lists distinguish initial loading, no records, no filtered matches, permission denial, and server failure.
- Editors show field-level validation and one contextual server error region.
- Save buttons remain disabled during active requests and duplicate submissions are prevented.
- Stale-record errors ask the user to reload rather than overwriting newer values.
- Background optimizer failure preserves inputs and provides Retry.
- Bulk workflow failures preserve the active split-lot selection and refresh authoritative status.
- Successful mutations refresh affected list rows, summaries, rails, and related documents without a full page redirect.

## Testing and verification

### Server tests

- capability visibility and record-level permissions for all new destinations;
- Cutting Plan Lot matrix loading, Draft creation, Submit, edit, stale conflict, Cancel, and Amend;
- Cutting Order Detail nested creation/editing and authoritative derived combinations;
- Cutting Order matrix loading, lifecycle, view projection, summaries, actions, Marker/LaySheet relationships, and print formats;
- Bulk LaySheets setup validation, row locking, LaySheet creation, active editor save, bundles, transfer, DC, approval, print context, and status rollup;
- Planner input validation, result invalidation, queue deduplication, status projection, failure, retry, and strategy selection;
- unsupported DocTypes, fields, rows, states, and operations are rejected;
- every action rejects missing permission even when called directly.

### Browser tests

- five permission-aware Cutting landing cards;
- four lists with common controls, typed filters, columns, bulk actions, Create, and row navigation;
- Cutting Plan create, Lot matrix, Draft reopen, Save & Submit, and transition to the existing workspace;
- Cutting Order create plus nested Cutting Order Detail workflow;
- Cutting Order 80/20 layout, fixed tabs, summaries, action toolbar, Marker/LaySheet rail, filters, and dialogs;
- Bulk LaySheets create and complete split-lot workflow without Desk navigation;
- Planner Inputs, Strategies, and Lay Plan tabs across Not Started, Queued, Running, Completed, Failed, Retry, and strategy selection;
- permission-controlled Create, Edit, Save, Submit, Cancel, Amend, Delete, Print, and specialized workflow actions;
- dirty-close confirmation, dismissable clean dialogs, loading, empty, error, stale, and permission states;
- keyboard focus, minimum text size, compact alignment, responsive collapse, and contained wide tables.

### Regression and deployment verification

- focused Python suites for all Cutting web contracts;
- existing Cutting Plan, Reports, permission, sidebar-filter, and stock-workflow browser suites;
- Fabric Store backend and browser regressions because shared document components are reused;
- frontend production build;
- site migration when hooks, schema, fixtures, or DocTypes change;
- `git diff --check` across the dirty worktree.

No workspace is complete until its real controller-backed happy path and failure path have been exercised in `/web`, no action redirects to Desk, and existing Cutting Plan and Fabric Store regressions remain green.
