# Fabric Store Workspace Design

## Objective

Build a Fabric Store workspace inside the existing `/web` Vue application so store users can inspect Work Orders and Purchase Orders, complete stock-transfer workflows, and run Stock Balance without leaving the web UI.

The workspace is common. It must show every document the signed-in user can read. It must not add fabric-process, warehouse, item-type, or department-specific filtering beyond filters the user deliberately applies.

## Existing-system constraints

- Preserve the existing Vue 3, PrimeVue, Vite, Frappe REST/RPC, and enterprise token stack.
- Match the Cutting workspace's compact desktop-first presentation and interaction quality.
- Keep the current Frappe/YRP document controllers and business methods authoritative.
- Do not route users to Desk for normal Fabric Store work.
- Keep all create, view, submit, cancel, amend, and print actions inside this web workspace.
- Use Frappe DocType permissions as the security boundary. Hidden buttons are presentation only; every server mutation must recheck permission and document state.
- Preserve all current dirty-worktree changes and do not commit this feature unless the user later asks.

## Information architecture

`/web/fabric-store` is the Fabric Store landing workspace. It has four persistent tabs:

1. Work Orders
2. Purchase Orders
3. Stock Transfers
4. Reports

The tab strip stays fixed while only the active tab content scrolls. Tabs that the user cannot read are omitted. If no Fabric Store feature is readable, show one intentional permission-empty state.

### Routes

- `/web/fabric-store`: Fabric Store tab workspace.
- `/web/fabric-store/work-orders/:workOrderId`: full Work Order workspace.

Work Order rows navigate to the full Work Order route. Purchase Order and stock-transfer rows never navigate; they open dialogs.

## Common list behavior

Work Orders, Purchase Orders, and each stock-transfer type use the existing shared `ListView` and `ListviewFilters` behavior:

- search, refresh, columns, advanced filters, clear filters, pagination, sorting, and one-second quick-filter debounce;
- field-aware filter value controls for Link, Select, Check, Date, Time, Datetime, number, and text fields;
- user column preferences and Frappe-style bulk operations where the user has the corresponding DocType permission;
- newest modified documents first unless the user changes the sort;
- no record-count text in the page header and no implementation-facing helper copy;
- loading, empty, filtered-empty, permission, and error states.

The lists have no implicit business filter. Frappe's record-level read permission remains in force.

## Work Order workspace

### Navigation and frame

Selecting a Work Order opens a dedicated full-page workspace patterned after the Cutting Plan view. The header contains:

- back navigation to Fabric Store;
- Work Order title and ID;
- visible document status and open status;
- permission-controlled Print action.

The body uses the same 80/20 desktop split as Cutting Plan:

- 80% main Work Order content;
- 20% persistent activity rail.

At narrower widths the rail moves below the main content without creating page-level horizontal overflow.

### Main 80% content

The main content has fixed tabs with independently scrollable content:

1. Details
2. Summary

Details displays the Work Order fields and values in the same logical order as the Desk form, using a balanced two-column read-only layout. It does not expose internal HTML fields or duplicate the document ID/status already shown in the header.

Deliverables and Receivables use the existing YRP grouped item model. Each parent item is rendered as a compact attribute matrix with variant attributes as identifying columns, primary-attribute values such as sizes as quantity columns, and aligned total columns. The UI must not flatten the matrix into raw child-table rows.

Summary uses the existing Work Order summary calculation and presents:

- Planned
- Delivered
- Received
- Pending

Each logical SKU row and total row follows the `production_api` Work Order summary contract. Additional deliverables are shown when the source data contains them. Numeric cells use tabular figures and tables remain horizontally scrollable inside their own containers.

### Right 20% activity rail

The rail is split into equal-height sections:

- Delivery Challans in the upper section;
- Goods Received Notes in the lower section.

Each section has its own scrolling list, filter action, and permission-controlled Create New action. Records sort by modified time descending. Compact cards show document ID, status, posting date/time, and the most useful quantity or reference summary available from the document.

Selecting an existing DC or GRN opens a detail dialog. Creating a DC or GRN opens its editor dialog using authoritative defaults from the selected Work Order. The page URL remains the Work Order route.

### Work Order document actions

- A DC editor is populated from the current submitted/open Work Order through the existing Work Order defaults service.
- A GRN editor is populated from the current Work Order and, when selected, a submitted Delivery Challan through the existing GRN defaults service.
- Grouped item matrices retain child-row references so controllers can update pending quantities safely.
- Save Draft and Save & Submit are shown only when allowed.
- Existing Draft documents may be submitted; Submitted documents may be cancelled; Cancelled documents may be amended only when the user has the relevant permission and the controller permits the transition.
- Print is shown only when the document is printable and the user has print permission.
- Every mutation reloads the Work Order workspace so summary quantities and rail records cannot remain stale.

## Purchase Orders

The Purchase Orders tab shows the common Purchase Order list. Selecting a row opens a maximizable, dismissable detail dialog rather than changing routes.

The dialog shows:

- Purchase Order ID and status;
- supplier, transaction date, schedule date, delivery location/warehouse, linked lots, and totals that exist on the document;
- the YRP grouped item matrix rather than the raw ERPNext child-table layout;
- Print when permitted;
- Create GRN only when the Purchase Order is submitted, open, YRP-managed, and the user can create a YRP Goods Received Note.

Create GRN opens a second editor dialog populated by the existing Purchase Order GRN defaults service. Users complete the editable receipt fields and grouped quantities, then Save Draft or Save & Submit. Closing the child dialog returns to the Purchase Order dialog and refreshes its pending/received data.

The Fabric Store does not add Purchase Order creation. The list and details are read-oriented apart from creating the linked GRN and permitted document lifecycle actions.

## Stock Transfers

The Stock Transfers tab has four compact operation selectors above one active list:

1. Stock Entry
2. Stock Reconciliation
3. Stock Update
4. Lot Transfer

The selectors replace a second duplicate tab row. Each selector shows the operation name and readable-record count. Choosing one changes the `ListView` rendered below it. The active list retains the common list controls and filters for that operation's DocType.

### Existing records

Selecting a row opens a maximizable detail dialog containing:

- document ID, status, and modified/posting time;
- relevant document fields;
- grouped item/attribute matrix;
- permission-controlled Submit, Cancel, Amend, and Print actions.

No record redirects to Desk.

### Creating records

Each operation has a permission-controlled New action. The common stock editor is context-free and does not require a Cutting Plan. Users enter all fields required by the relevant document, including warehouses/locations, dynamic stock dimensions, item template, attributes, quantities, UOM information, received type, and operation-specific fields.

- Stock Entry exposes Purpose as a Select containing Material Issue, Material Consumed, and Send to Warehouse, then shows fields required by that purpose.
- Stock Reconciliation exposes the standard reconciliation purpose and current stock-dimension inputs.
- Stock Update exposes Add and Reduce, with neither forced as a Fabric Store default.
- Lot Transfer exposes source and target Lot values plus the stock dimensions required by the document.

The item workflow follows the existing Desk/YRP item editor:

1. Select the parent Item.
2. Load its attribute schema.
3. Enter attribute combinations and quantities in the split matrix.
4. Add the staged logical rows to the document matrix.
5. Save Draft or Save & Submit.

The existing Cutting stock composer should be generalized through injected API/context props rather than duplicated. Cutting keeps its locked Cutting Plan defaults; Fabric Store uses the same UI with freely entered document context.

## Reports

The Reports tab contains Stock Balance only.

Stock Balance becomes a common reusable report component under the shared component tree. Cutting Reports and Fabric Store both import the same component and share the same filter shell, report query, table rendering, loading state, empty state, and reset behavior. No copy of the report logic or CSS is permitted.

The report runs only after the user selects Generate. It retains the existing date, item, parent item, warehouse, lot, received type, zero-balance, attribute, ageing, and inward-split filters.

## Backend boundary

A dedicated `essdee_yrp.fabric_store.web_workspace` module owns Fabric Store web contracts. It may reuse existing YRP and Essdee services, but it must not depend on a Cutting Plan or write Cutting Plan stock-transfer references.

The module provides focused endpoints for:

- feature and DocType permission capabilities;
- Work Order workspace details, summary, related DCs, and related GRNs;
- Purchase Order dialog data and current GRN eligibility;
- common stock editor context and item schema;
- saving the four stock-transfer document types;
- loading document details;
- submit, cancel, and amend lifecycle actions;
- creating Work Order DC/GRN and Purchase Order GRN documents.

Server endpoints must:

- whitelist supported DocTypes and operations;
- reload authoritative source documents;
- call `check_permission`/`frappe.has_permission` for every read and mutation;
- validate docstatus transitions;
- preserve authoritative child-row references and recheck pending quantities at save time;
- use Frappe/YRP document insert, save, submit, cancel, and amend behavior instead of recreating controller calculations;
- reject unknown payload fields;
- accept an expected `modified` value for editing/lifecycle actions and report stale-document conflicts clearly.

## Permissions

UI capabilities derive from Frappe DocType permissions and the current document state:

- no read permission: omit the tab, rail section, or operation selector;
- create permission: show New/Create GRN/Create DC;
- write permission: allow saving an existing Draft;
- submit permission: show Submit or Save & Submit for Drafts;
- cancel permission: show Cancel for Submitted documents;
- amend permission: show Amend for Cancelled documents;
- print permission: show Print.

The server repeats every check. Direct endpoint calls cannot bypass the hidden controls.

## Visual system

Use the current shared enterprise tokens and PrimeVue components:

- off-white/mint canvas, white surfaces, emerald accent;
- 8px controls, 12px panels, thin neutral borders, restrained tinted shadows;
- `Segoe UI Variable` stack already established by the application;
- compact 11px minimum labels, readable 13px body values, tabular numbers;
- one accent color and no gradients, glass effects, oversized headers, decorative copy, or repeated explanatory headings;
- tactile hover/pressed states and visible keyboard focus;
- skeleton loaders shaped like the final content;
- intentional loading, empty, filtered-empty, permission, validation, conflict, and server-error states;
- no page-level horizontal overflow at 1600px, 1280px, 900px, or 390px widths.

## Dialog behavior

- Dialogs are maximizable and close when the user clicks the mask.
- Nested creation dialogs preserve the parent document dialog underneath.
- Long forms scroll only inside the dialog content; headers and footers remain visible.
- Closing a dirty editor requires confirmation.
- Successful saves refresh the originating list/workspace and keep the user in the Fabric Store context.
- Errors render inline in the active dialog. Do not use browser alerts for server or validation failures.

## Testing and verification

### Server tests

- permissions for every readable/creatable/actionable DocType;
- Work Order payload, production summary parity, related DC/GRN ordering, and no implicit Fabric Store filter;
- PO detail payload and GRN defaults;
- all four stock-transfer editors and Draft/Submit creation;
- submit, cancel, amend, and stale-document behavior;
- rejection of unsupported DocTypes, operations, fields, and invalid source relationships;
- child-row reference and pending-quantity integrity.

### Browser tests

- four top-level tabs and permission-based tab visibility;
- common list controls and field-aware filters on all lists;
- Work Order list navigation and full 80/20 workspace layout;
- fixed Work Order tabs with independently scrolling content;
- Work Order Details and production-summary matrices;
- separate DC and GRN rails, filters, sorting, dialogs, and create flows;
- PO dialog and nested Create GRN flow;
- four Stock Transfer selectors, active list switching, detail dialogs, and creation editors;
- permission-controlled Create, Save, Submit, Cancel, Amend, and Print buttons;
- shared Stock Balance behavior in both Cutting and Fabric Store;
- dialog dismissal, keyboard focus, loading/error/empty states, and responsive containment.

### Completion commands

- focused Python tests for the Fabric Store workspace;
- existing Cutting workspace Python/browser regressions;
- new Fabric Store browser suite;
- full frontend production build;
- site migration if schema, fixtures, or hooks change;
- `git diff --check` on every touched file.

No feature is complete until the browser behavior is verified against live migrated records and the existing Cutting workspace remains green.
