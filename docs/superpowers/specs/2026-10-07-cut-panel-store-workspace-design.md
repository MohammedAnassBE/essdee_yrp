# Cut Panel Store Workspace Design

## Objective

Build the Cut Panel Store inside the existing `/web` Vue application so store users can manage cut-panel movements, their linked stock documents, Work Orders, bundle corrections, label printing, and cut-panel reports without visiting Desk.

The workspace must follow the same product and engineering rules already approved for Cutting and Fabric Store: compact premium presentation, permission-aware actions, server-authoritative business logic, in-app dialogs, clear errors, minimal navigation, and complete automated browser coverage.

The Cut Panel Store landing page contains exactly six permission-aware cards:

1. Cut Panel Movement
2. Work Orders
3. Cut Bundle Edit
4. Box Sticker Print
5. Excel Sticker Print
6. Reports

Raw Sticker Print is intentionally excluded. Excel Sticker Print is its replacement in this workspace.

## Existing-system findings

The required business behavior already exists across Frappe 16 and the migrated `essdee_yrp` application:

- `SD YRP Cut Panel Movement` owns lot, source, posting controls, selected exact bundles, collapsed quantities, accessory quantities, submission, cancellation, and bundle-ledger side effects.
- `essdee_yrp.cutting.movement` already converts a submitted movement into authoritative YRP Stock Entry, Delivery Challan, and Goods Received Note rows and protects one active root transaction per movement.
- `essdee_yrp.cutting.web_workspace` already exposes the plan-scoped movement editor, movement matrix, stock editor, transaction detail dialog, lifecycle controls, and related-document projection.
- Fabric Store already provides the complete Work Order, Delivery Challan, and Goods Received Note workspaces, including embedded dialogs, matrices, lifecycle actions, printing, errors, and parent refresh.
- `SD YRP Cut Bundle Edit` owns bundle transformation and label-generation behavior.
- `SD YRP Box Sticker Print` owns FG-item size rows, MRP, printed quantity, excess rules, ZPL generation, preview, and rollback when printing fails.
- `YRP Excel Sticker Print` owns Excel upload parsing, first-row ZPL preview, multi-row quantity rendering, and resolution-specific output.
- the shared QZ client already discovers printers and sends raw ZPL.
- the shared Stock Balance report and `SD YRP Cut Bundle Balance` report already provide the required report data.

The Frappe 15 `production_api` Desk UI is a behavioral reference for Cut Panel Movement, Cut Bundle Edit, Box Sticker Print, and Excel Sticker Print. It is not a visual or architectural dependency. The Frappe 16 controllers and migrated YRP doctypes remain authoritative.

## Product rules inherited from Cutting and Fabric Store

- Preserve Vue 3, PrimeVue, Vite, Frappe REST/RPC, PrimeIcons, and the existing enterprise design tokens.
- Do not introduce a second component library or a separate Cut Panel Store theme.
- Keep all normal workflows inside `/web`; do not redirect to Desk.
- Use the finalized common launcher, list, filter, form, document-shell, confirmation, error-dialog, printing, and report patterns.
- Lists use Frappe record permissions and user-selected filters. They do not silently apply warehouse, supplier, process, item, or department filters.
- Browser payloads never own stock availability, bundle identity, transaction ownership, pricing, status, or lifecycle eligibility.
- The server reloads and validates authoritative records for every mutation.
- Unauthorized actions are absent. Hiding a button is not security; endpoints repeat permission and state checks.
- Destructive actions use the application confirmation dialog. Browser-native confirmation is forbidden.
- Operational errors use the shared application error popup and preserve entered values.
- New and editable forms use one clear primary action with secondary actions grouped consistently with Frappe.
- Keep page-level scrolling small. Long matrices, activity lists, previews, and reports own their overflow.
- Preserve Cutting, Fabric Store, Stock Transfer, and existing report behavior unless this specification explicitly shares a component with them.

## Information architecture and routes

### Landing page

`/web/cut-panel-store` renders the six cards in the shared workspace launcher. A card is visible only when its primary DocType or report capability is readable. If none is readable, the page shows one permission-empty state.

### Routes

- `/web/cut-panel-store/movements`: Cut Panel Movement list.
- `/web/cut-panel-store/work-orders`: Work Order list.
- `/web/cut-panel-store/work-orders/new`: shared Work Order editor.
- `/web/cut-panel-store/work-orders/:workOrderId`: shared Work Order workspace.
- `/web/cut-panel-store/work-orders/:workOrderId/edit`: shared Work Order editor.
- `/web/cut-panel-store/cut-bundle-edits`: Cut Bundle Edit list.
- `/web/cut-panel-store/box-sticker-prints`: Box Sticker Print list.
- `/web/cut-panel-store/excel-sticker-prints`: Excel Sticker Print list.
- `/web/cut-panel-store/reports`: Stock Balance and Cut Bundle Balance.

Cut Panel Movement, Cut Bundle Edit, Box Sticker Print, and Excel Sticker Print records open in maximizable dialogs over their lists. Their open record may be reflected in the URL query for refresh/back-button restoration, but they do not require separate full-page forms.

Work Orders use the same domain components as Fabric Store. The shared Work Order pages accept a section context so back navigation and nested routes remain inside Cut Panel Store without cloning the workspace.

## Shared list contract

All five document lists use the common `ListView` behavior:

- search, refresh, sorting, pagination, quick filters, advanced filters, clear filters, and user-selected columns;
- field-aware Link, Select, Check, Date, Time, Datetime, number, and text filters;
- newest modified records first by default;
- permission-controlled create and bulk lifecycle actions where the DocType supports them;
- explicit loading, empty, filtered-empty, permission, and error states;
- compact desktop density and responsive containment;
- no duplicated page title, implementation helper text, or record-count headline.

Default columns:

- Cut Panel Movement: ID, Lot, Item, From Warehouse, Against, Against ID, Movement Date, status.
- Work Order: the same default columns and statuses as Fabric Store.
- Cut Bundle Edit: ID, Lot, Item, Warehouse, Posting Date, Printed Time, status.
- Box Sticker Print: ID, Lot, Item, Print Format, status.
- Excel Sticker Print: ID, Excel File, Print Format, status, modified time.

## Cut Panel Movement workspace

### List and creation

The movement list shows every `SD YRP Cut Panel Movement` record the user can read. It is not limited to movements created from a Cutting Plan.

Create Movement opens the same bundle-selection experience already used in Cutting. For a store-created movement the operator selects:

- Lot;
- From Warehouse/Supplier;
- Posting Date and Time, protected by Edit Posting Date and Time;
- available exact bundles, individual panels, collapsed quantities, and accessory quantities.

The server derives Item from Lot, regenerates availability immediately before save, and rejects stale, forged, mixed, overdrawn, or duplicate selections. Store-created movements set `movement_from_cutting = 0` and do not invent a Cutting Plan.

### Movement popup

Selecting a row opens a maximizable popup with a sticky identity/action header. Desktop content uses an approximately 80/20 split:

- the main 80% shows posting/source details, selection summary, exact-bundle matrices, collapsed rows, and accessory quantities;
- the right 20% shows linked Stock Entries, Delivery Challans, and Goods Received Notes created from the movement.

The rail is independently scrollable, sorts newest first, and shows document ID, status, posting date/time, and compact source context. Selecting a related row opens the existing complete transaction/document dialog without leaving the movement.

At narrower widths the rail moves below the movement content. No action or linked record is removed.

### Movement lifecycle and linked creation

Available actions are returned by the server and may include:

- Save Draft;
- Submit;
- Cancel;
- Amend;
- Duplicate where supported safely;
- Print;
- Create Stock Entry;
- Create Delivery Challan;
- Create Goods Received Note.

The create actions are visible only for a submitted movement that is eligible under the existing active-root-transaction rule. The server remains the final authority when existing or concurrent transactions make an action unavailable.

Stock Entry creation uses the existing movement-to-stock adapter and complete stock-entry editor. Delivery Challan and Goods Received Note creation first select a submitted Work Order belonging to the movement Lot. The server validates the Work Order again and builds all document defaults and item matrices through `essdee_yrp.cutting.movement` plus the existing Fabric Store DC/GRN services.

DC and GRN open in the same complete embedded workspace used by Fabric Store. Save, Submit, Cancel, Amend, Print, transfer, inspection, return, and other valid actions behave identically. Successful changes refresh both the movement and the linked-document rail.

## Work Order workspace

The Work Orders card reuses the approved Fabric Store list, editor, record workspace, Delivery Challan popup, Goods Received Note popup, action panels, totals, and related-document rail.

There is no reduced Cut Panel Store version of a Work Order. Field behavior, matrices, pending quantities, calculations, actions, popup errors, lifecycle confirmations, duplicate handling, and printing remain identical to Fabric Store. Only navigation context changes:

- back returns to `/web/cut-panel-store/work-orders`;
- create/edit/view routes remain under `/web/cut-panel-store`;
- nested DC/GRN work remains inside the Work Order.

## Cut Bundle Edit workspace

### Editor

Create and existing Draft records open a maximizable popup. The compact header fields are Lot, derived Item, Warehouse, Posting Date, Posting Time, Printed Time, and status.

After selecting Lot and Warehouse, the server loads the same authoritative input/output bundle structure used by the Desk controller. The editor presents bundle transformations in compact grouped tables, preserves stable bundle identity, and shows a before/after summary. The browser may edit only the quantities and selections permitted by the controller.

Saving or submitting reloads current bundle state, validates available quantities, rejects stale or browser-invented rows, and calls the normal document lifecycle.

### Label printing

Submitted eligible records expose Print Labels. The application discovers QZ printers, uses a single-select printer popup, requests server-rendered raw output, prints, and records Printed Time only after success. Printing failure preserves the submitted document and displays the shared error popup.

## Box Sticker Print workspace

Create and Draft records open a maximizable editor with:

- Lot;
- FG Item;
- optional Size;
- Use Item Name;
- Print Format;
- size rows containing MRP, total quantity, printed quantity, excess controls, and requested print quantity;
- label preview.

FG Item and Lot changes reload authoritative size/MRP rows. The browser does not calculate allowed quantities or mutate printed totals directly.

Submitted eligible records expose Print Labels. The flow is:

1. discover and filter configured QZ printers;
2. choose one printer and resolution;
3. enter positive print quantities per size;
4. request locked server-generated ZPL;
5. print through QZ;
6. reload printed totals after success;
7. invoke the existing rollback endpoint if QZ printing fails after quantities were reserved.

Preview uses server-generated ZPL and a contained image preview. Preview failure is non-destructive and does not block document viewing.

## Excel Sticker Print workspace

Create and Draft records open a compact maximizable editor with:

- Excel file upload;
- YRP ZPL Raw Print Format;
- status and lifecycle actions;
- first-row preview after submission;
- parsed row count and a safe, compact preview of uploaded columns/rows where permitted.

File upload uses Frappe's authenticated upload endpoint and attaches the resulting File URL to the draft. Submission calls the existing `YRP Excel Sticker Print` controller, which parses and serializes the workbook.

Submitted records expose Print. The operator chooses one detected QZ printer and 200/300 dpi, the server renders all positive `print_quantity` rows, and the client sends the returned ZPL to QZ. Empty workbooks, missing formats, missing quantities, unavailable QZ, and print failures use clear application errors.

## Reports workspace

The Reports card contains exactly two tabs:

1. Stock Balance
2. Cut Bundle Balance

Stock Balance reuses the shared report component used by Fabric Store and Cutting.

Cut Bundle Balance uses the shared report shell and the existing `SD YRP Cut Bundle Balance` report. Filters are Lot and Supplier. Results show Name, Lot, Supplier, Supplier Name, Item, Lay No, Bundle No, Size, Colour, Shade, Panel, and Quantity. The report includes compact result metrics, loading/empty/error states, sticky headers, and contained horizontal overflow.

Both reports remain permission-aware and execute server report logic. Vue performs formatting and totals only; it does not reproduce ledger queries.

## Shared component design

The implementation extends existing components instead of creating workflow copies:

- `WorkspaceLauncher`, `ListView`, filters, and column settings remain common.
- Fabric Work Order pages accept configurable base routes/back context.
- the existing full DC/GRN embedded workspaces are reused unchanged for movement transactions.
- movement bundle matrices are extracted or parameterized so Cutting Plan and Cut Panel Store share one renderer and selection model.
- document action, print, confirmation, error-dialog, time/date, Link, and report components remain common.
- QZ discovery and printing stay in the shared printer API.
- focused Cut Panel Store components own launcher, section routing, movement rail, bundle edit, box sticker, Excel sticker, and report orchestration.

No single Vue file should own all six workspaces. Backend modules are similarly divided by domain.

## Backend boundary

A focused package under `essdee_yrp.cut_panel_store` provides browser contracts while delegating business behavior to installed controllers and existing services.

It exposes explicit endpoints for:

- Cut Panel Store capabilities;
- global movement load/create/edit, availability generation, save, lifecycle, print, and linked-document projection;
- movement Work Order choices and Stock Entry/DC/GRN preparation;
- Cut Bundle Edit load/create/edit, bundle projection, lifecycle, and printing;
- Box Sticker load/create/edit, authoritative FG rows, lifecycle, preview, printer filtering, printing, and rollback orchestration;
- Excel Sticker load/create/edit, attachment validation, lifecycle, preview, and printing;
- Cut Bundle Balance report execution.

Endpoints must:

- whitelist supported DocTypes, fields, commands, and report names;
- call `check_permission` or `frappe.has_permission` for every read and mutation;
- validate document state and action eligibility;
- accept and enforce expected `modified` timestamps for editable existing records;
- reload authoritative Lot, Work Order, bundle, printer-format, and stock state before mutation;
- preserve child-row identity and reject unknown, missing, duplicate, or forged rows;
- use normal insert, save, submit, cancel, and amend methods;
- use named commands rather than a generic unrestricted update endpoint;
- return user-safe validation messages and never expose raw tracebacks.

## Error handling and concurrency

- Failed loads show an intentional page or popup error state.
- Failed saves keep all unsaved client values and open the shared error popup with the meaningful server message.
- Every existing editable document uses optimistic concurrency through `modified`.
- Stale data explains that the record changed and provides Reload; it never overwrites silently.
- Cancel, amend, discard, and source changes that replace entered matrices use application confirmations.
- A linked transaction created concurrently causes a clear movement ownership error followed by authoritative reload.
- QZ and preview errors distinguish unavailable printer software, printer rejection, server rendering failure, and remote preview failure.
- Successful mutations reload the authoritative record, linked rail, list row, totals, and statuses.

## Visual and interaction requirements

- Use the same bright neutral canvas, green accent, type scale, borders, radii, shadows, and density as the polished Cutting and Fabric Store pages.
- Keep headers compact and sticky where content scrolls.
- Show identity values once in the most useful place.
- Use an 80/20 desktop split only where the linked-document rail adds value.
- Avoid cards inside cards, oversized empty areas, redundant section labels, and browser-level page overflow.
- Tables use normal document flow unless a bounded working matrix genuinely needs contained scrolling.
- Primary actions remain visible without excessive scrolling.
- Focus, keyboard dismissal, active, hover, loading, empty, permission, error, and disabled states are complete.
- Desktop verification covers 1600 and 1280 pixels; responsive verification covers 900 and 390 pixels.

## Testing strategy

### Server tests

- capability visibility for every card and action;
- record-level and command-level permission rejection;
- movement creation for non-Cutting sources and preservation of Cutting-created movements;
- authoritative bundle regeneration and stale/forged/overdrawn selection rejection;
- one-active-root transaction enforcement across Stock Entry, DC, and GRN;
- same-Lot submitted Work Order validation for DC/GRN;
- linked-document projection and lifecycle refresh;
- Cut Bundle Edit input/output validation and label generation;
- Box Sticker row generation, allowed quantities, ZPL, rollback, and permissions;
- Excel attachment validation, parsing, preview, ZPL output, and permissions;
- Stock Balance and Cut Bundle Balance permissions and report payloads;
- optimistic concurrency for every editable record.

### Frontend/browser tests

- six-card launcher and permission-hidden cards;
- each list's filters, search, columns, pagination, empty/error states, and Create action;
- movement create/edit/view, exact/collapsed/accessory matrices, 80/20 rail, and responsive collapse;
- linked Stock Entry/DC/GRN create, open, submit, cancel, error, and parent refresh flows;
- shared Work Order behavior from the Cut Panel Store route;
- Cut Bundle Edit save/submit/print states;
- Box Sticker preview, quantities, printer selection, success, rollback failure path, and lifecycle;
- Excel upload, submit, preview, resolution selection, printing, and failure states;
- both reports and their filters/results;
- no browser-native confirmation;
- all server failures shown through the shared error popup;
- keyboard and focus behavior for nested dialogs;
- production build and existing Cutting/Fabric Store browser regression suites.

### Completion gate

The feature is complete only when:

- focused backend tests pass;
- the Cut Panel Store browser suite passes against live migrated records;
- the full Cutting and Fabric Store browser suites remain green;
- the frontend production build succeeds;
- route and responsive audits pass;
- `git diff --check` is clean;
- an independent code review finds no unresolved Critical or Important issue.

## Rollout sequence

1. Add capabilities, routes, the six-card launcher, section shell, and failing browser contract tests.
2. Extract the reusable movement editor boundary and deliver the global Movement list/popup.
3. Add the linked 20% rail and Stock Entry/DC/GRN flows using existing document workspaces.
4. Parameterize and expose the shared Work Order pages under Cut Panel Store routes.
5. Deliver Cut Bundle Edit list/editor/printing.
6. Deliver Box Sticker list/editor/preview/printing.
7. Deliver Excel Sticker list/editor/upload/preview/printing.
8. Deliver the two-report workspace.
9. Complete responsive, accessibility, error-dialog, permission, and visual consistency audits.
10. Run all backend, browser, build, and cross-workspace regression gates before committing the completed implementation.

## Acceptance checklist

- The landing page shows exactly the six approved cards, subject only to permissions.
- Raw Sticker Print is absent.
- Movement records open in a popup with main content and an approximately 20% linked-document rail.
- Eligible users can create Stock Entry, DC, and GRN from a submitted movement without leaving `/web`.
- Movement DC/GRN Work Orders are submitted and belong to the same Lot.
- Work Orders behave exactly like the approved Fabric Store implementation while navigating within Cut Panel Store.
- Cut Bundle Edit matches the migrated Desk behavior and prints through QZ.
- Box Sticker Print supports authoritative quantities, preview, printer selection, printing, and rollback.
- Excel Sticker Print supports upload, preview, printer selection, and printing.
- Reports contains only Stock Balance and Cut Bundle Balance.
- All errors use application dialogs; no browser confirmation appears.
- UI density, theme, interaction quality, and responsive behavior match Cutting and Fabric Store.
- Existing Cutting, Fabric Store, Stock Transfer, and report workflows remain operational.
