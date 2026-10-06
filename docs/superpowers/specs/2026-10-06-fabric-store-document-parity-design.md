# Fabric Store PO, WO, DC, and GRN Parity Design

## Goal

Provide complete operational parity in `/web` for Purchase Orders, Work Orders, Delivery Challans, and Goods Received Notes while reducing operator dwell time. The implementation must combine base YRP behavior with every applicable `essdee_yrp` customization and keep the existing controllers, hooks, calculations, and permissions authoritative.

Operators working from a Work Order or Purchase Order must be able to complete related DC and GRN work without leaving the parent workspace. The same DC and GRN workspace must also work as a routed page when opened directly.

This specification supersedes the Fabric Store portions of the earlier workspace-alignment specifications wherever they retained reduced DC/GRN popups or described PO/GRN behavior as unchanged.

## Success criteria

- PO, WO, DC, and GRN creation, editing, viewing, document lifecycle, custom actions, matrices, and calculations are available in `/web` wherever the user has permission.
- DC and GRN open as complete maximizable workspaces inside WO and PO rather than reduced quick-entry dialogs.
- The embedded and routed versions use the same Vue components and server commands.
- Server responses determine which fields and actions are available. An action for which the user lacks permission is absent, not disabled.
- Existing YRP and Essdee controllers and services perform business calculations and validation. Vue does not reimplement them.
- GRN Calculate preserves received-type splits and all other authoritative rows across calculate, save, reload, and submit.
- After a related document changes, its parent WO or PO refreshes quantities, status, totals, and activity without navigation.
- Existing Desk behavior remains functional.

## Scope

### Purchase Order

- Create, view, edit, save draft, submit, cancel, amend, and print.
- Supplier, contact, address, delivery destination, dates, currency, warehouse, terms, comments, and effective YRP fields.
- Item composition with stock dimensions, UOM conversion, supplier pricing, discounts, taxes, row totals, and document totals.
- YRP fulfillment state, close, reopen, and refresh status.
- Essdee approval request, approve, and reject behavior.
- Linked-lot management and its audit reason.
- Create GRN and Create Delivery Challan entry points where eligible.

### Work Order

- Create, view, edit, save draft, submit, cancel, amend, and print.
- Process, lot, item, production detail, supplier, delivery location, dates, addresses, terms, and dynamic stock dimensions.
- Server-driven process/lot/item eligibility.
- Garment item calculation and fabric deliverable calculation.
- Deliverable and receivable matrices, pending quantities, process costs, and summary tracking.
- Close request, close approval, close details, and debit creation/approval behavior exposed by the existing services.
- Rework creation and source allocation.
- Material Issue, Cutting Plan, recut, sewing-plan, change-item, change-delivery-date, and piece-calculation actions when eligible.
- Related DC and GRN activity with in-place creation and management.

### Delivery Challan

- Create, view, edit, save draft, submit, cancel, amend, and print.
- Authoritative Work Order defaults and optional Purchase Order traceability.
- Posting controls, movement parties, addresses, warehouses, logistics, supplier document data, and comments.
- Deliverable and correction matrices with pending quantities, secondary quantities, stock dimensions, and stock-availability validation.
- Delivered quantity, stock value, total value, and additional goods value.
- Internal-unit transfer progress and Complete Transfer.
- Return creation, including Essdee whole-bundle and cut-panel movement variants.
- Packing, finishing, bulk laysheet, loose-piece, and cut-panel movement behavior when prepared by their source workflows.
- SMS and WhatsApp actions when their existing eligibility and integration requirements are satisfied.

### Goods Received Note

- Create, view, edit, save draft, submit, cancel, amend, and print for WO and YRP-managed PO sources.
- Authoritative source defaults, delivery-challan selection, posting controls, movement parties, addresses, warehouses, logistics, freight, and comments.
- Receivable and correction matrices with stock dimensions, pending limits, excess allowances, received types, and valuation.
- Total received quantity, total value, freight allocation, tax/grand totals where applicable, and transfer progress.
- Essdee Calculate using the saved Work Order calculation, received-type selection, quantity matrix, source availability, row/column/grand totals, and stale-document protection.
- Inspection Entry creation/view and Complete Transfer when eligible.
- Return, rework, packing, finishing, cutting laysheet, cut-panel movement, closed-sewing, fabric, and additional-GRN behavior when prepared by the owning workflow.
- SMS and WhatsApp actions when eligible.

## Explicit non-goals

- Reimplementing Frappe's complete metadata form engine in Vue.
- Copying valuation, pending-quantity, price, tax, garment, fabric, packing, or stock calculations into the browser.
- Exposing hidden bookkeeping fields as manual controls.
- Turning source-owned modes such as packing, cut-panel movement, return, or additional GRN into user-selectable checkboxes.
- Changing the underlying Desk workflows or controller semantics.
- Redesigning stock-transfer and report workflows unrelated to the four documents.

## Sources of truth

The implementation must reconcile these layers rather than treating any single file as complete:

1. Effective DocType metadata: base JSON, ERPNext Purchase Order metadata, YRP custom fields, Essdee custom fields, property setters, permissions, and installed stock dimensions.
2. Base YRP client behavior in the PO, WO, DC, and GRN JavaScript files.
3. Essdee client behavior in `public/js/purchase_order.js`, `work_order.js`, `delivery_challan.js`, and `goods_received_note.js`.
4. Base controllers and all Essdee controller overrides and document hooks.
5. Existing domain services such as Work Order actions, garment/fabric calculation, purchase approval, purchase-order lots, returns, inspections, and internal transfer.

The server controller and hook chain is authoritative when client metadata and business rules overlap.

## Architecture

### Shared document workspace

A shared document shell owns:

- Identity, status, source context, and compact header facts.
- Permission-aware action placement.
- Loading, errors, stale-document handling, and unsaved-change protection.
- Print, save, submit, cancel, and amend controls.
- Embedded-popup and routed-page presentation modes.
- Reload and parent-refresh events.

PO, WO, DC, and GRN each use a domain workspace inside that shell. Domain components own their specialized fields, matrices, totals, and action panels. They do not become configurations inside one universal metadata form.

### Popup and routed-page reuse

The DC and GRN domain workspace accepts a presentation mode:

- `embedded`: rendered inside a maximizable popup over a WO or PO.
- `page`: rendered directly from its list or URL.

Both modes call identical APIs and render identical document content. The popup host supplies parent context and listens for document changes. No separate quick-entry implementation is retained.

Small WO actions such as calculation, close, rework selection, change date, and change item use focused in-page panels or dialogs. A complete DC or GRN always uses its full workspace.

### Routes

- `/fabric-store/work-orders/new`
- `/fabric-store/work-orders/:name`
- `/fabric-store/work-orders/:name/edit`
- `/fabric-store/purchase-orders/new`
- `/fabric-store/purchase-orders/:name`
- `/fabric-store/purchase-orders/:name/edit`
- `/fabric-store/delivery-challans/new`
- `/fabric-store/delivery-challans/:name`
- `/fabric-store/delivery-challans/:name/edit`
- `/fabric-store/goods-received-notes/new`
- `/fabric-store/goods-received-notes/:name`
- `/fabric-store/goods-received-notes/:name/edit`

New-document routes accept explicit source context in query parameters, such as `work_order`, `purchase_order`, and `delivery_challan`. The server validates every supplied source instead of trusting route state.

### Server services

The current Fabric Store service is split into focused modules for shared document behavior, PO, WO, DC, and GRN. The exact module names may follow existing package conventions, but the boundaries are mandatory:

- Shared service: supported doctypes, serialization, permissions, printing, lifecycle commands, stale checks, and action-capability helpers.
- PO service: workspace/editor projection, item schema/pricing coordination, approval, lots, close/reopen, and related-document preparation.
- WO service: workspace/editor projection, selection context, calculations, summary, close/debit/rework, and related-action capabilities.
- DC service: source defaults, editable projection, item/correction merge, return, transfer, and special-mode capabilities.
- GRN service: source defaults, editable projection, safe item/correction merge, Calculate, inspection, transfer, and special-mode capabilities.

These services coordinate existing controllers and domain functions. They do not replace their validations or side effects.

## Server response contract

Each document workspace returns:

- `record`: identity, status, document state, modified timestamp, and compact header facts.
- `fields`: permitted domain fields with effective label, type, options, required/read-only state, dependencies, and current values.
- `matrices`: domain-specific grouped item, correction, deliverable, receivable, or calculation data.
- `totals`: explicit labeled quantities, values, and transfer progress.
- `permissions`: create, read, write, submit, cancel, amend, print, and domain permissions.
- `capabilities`: named actions with eligibility and any required preparation data.
- `related`: document links and activity needed by the parent workspace.
- `print_formats`: permitted formats.

Capabilities are returned only after checking document state, domain eligibility, and user permission. The client does not infer action eligibility from status alone.

## Permission and action visibility

- An unauthorized action is not rendered.
- No submit permission means no Submit action.
- No cancel permission means no Cancel action.
- No amend permission means no Amend action.
- No create permission for a target doctype means no Make DC, Make GRN, Return, Rework, Inspection, or similar creation action.
- No print permission means no Print action.
- PO Send Request follows its request permission rules. Approve and Reject appear only for the configured approver authority.
- Every command repeats permission and eligibility checks on the server even when the client did not render the action.

## Data flow

### Load

1. The client requests a new or existing document workspace with explicit source context.
2. The server checks permission and source ownership.
3. For an existing document, the controller `onload` behavior produces authoritative grouped data.
4. The service combines effective metadata, values, matrices, totals, capabilities, and modified timestamp.

### Source changes

Changes to WO, PO, delivery challan, process, lot, item, or another authoritative source call a server preview. If applying the response would replace entered quantities, the client asks for confirmation. The accepted response replaces all source-derived fields and rows as one unit.

### Save

1. The client sends editable header values, grouped matrices, document name when present, and expected modified timestamp.
2. The server reloads the source document and current target document.
3. It validates stable row identities and merges user-entered quantities into authoritative rows.
4. For an existing GRN, the merge starts from the saved document and preserves calculated received-type splits and special rows not targeted by the edit. It must not reconstruct the document solely from fresh default rows.
5. The normal controller and hook chain validates and saves or submits the document.
6. The endpoint returns a freshly loaded workspace.

### GRN Calculate

1. Calculate is available only when the server reports the saved draft as eligible.
2. The client requests `get_grn_calculation_context` using the GRN name.
3. The internal Calculate panel displays Received Type, saved WO calculated rows, per-cell availability, row toggles, select/unselect controls, and row/column/grand totals.
4. The client submits selected source rows, received type, and expected modified timestamp to `calculate_grn_receivables`.
5. The service replaces only the selected received-type split, preserves all other splits, saves the draft, and returns the reloaded GRN workspace.
6. Any later ordinary save preserves these calculated rows.

### Commands

Submit, cancel, amend, close, reopen, approve, reject, return, transfer, inspection, rework, calculation, and other mutations use named commands rather than a generic unrestricted update endpoint. Each command checks permission, document state, source ownership, and modified timestamp where applicable, then returns refreshed state.

## Interaction design

### Parent WO and PO workspaces

- Keep the parent visible while related DC or GRN work is open.
- Opening a related row and creating a related document use the same embedded workspace host.
- After a successful related mutation, refresh the parent header, matrices/totals, status, and activity feed.
- Do not repeat parent identity fields inside the form body when they are already fixed and visible in the popup header.

### DC and GRN workspace layout

- Maximizable popup with a sticky compact header.
- Header contains document number, status, source, process, item, lot, and primary actions.
- Main column contains editable fields and matrices.
- Compact side rail contains prominent totals, stock value, transfer progress, and contextual actions.
- Sticky footer contains the current draft action set.
- Correction, packing, return, inspection, transfer, and other specialized regions render only when relevant.
- Save Draft keeps the popup open.
- Submit changes the same workspace to read-only state and keeps it open for print, transfer, or inspection actions.

Calculate, return selection, inspection preparation, and similar multi-step actions render as an internal panel within the workspace rather than stacking unrelated modal dialogs.

### Visual density

- Use the existing Fabric Store enterprise tokens and control sizing.
- Show Work Order, item, lot, supplier, and series once in the most useful location.
- Highlight total delivered/received quantity and monetary value.
- Avoid redundant titles, instructional paragraphs, and empty sections.
- At narrow widths, move the side rail below the main content without removing commands or matrix columns; matrices may scroll horizontally.

## Error handling and concurrency

- Every editable existing document uses its modified timestamp for optimistic concurrency.
- A stale response explains that the document changed and offers a reload; it never silently overwrites the newer document.
- Failed saves preserve client-side entries and show the server validation message.
- Destructive actions require confirmation.
- Source changes that replace entered quantities require confirmation.
- Successful mutations always reload authoritative state.
- Permission or eligibility changes between load and command return a server error and remove the action on reload.

## Testing strategy

### Server contract tests

- Effective fields honor base metadata, custom fields, property setters, field permissions, and document state.
- Capabilities honor both role permission and business eligibility.
- Unauthorized endpoints reject direct calls.
- Stale modifications are rejected.
- New and existing document projections return stable matrices and totals.

### Domain tests

- PO: pricing, taxes, totals, approval, linked lots, close/reopen, source preparation, lifecycle, and permission visibility.
- WO: selection context, garment calculation, fabric calculation, costs, close/debit, rework, related actions, lifecycle, and summaries.
- DC: defaults, item/correction merging, stock availability, totals, return variants, transfer, lifecycle, and special modes.
- GRN: WO/PO defaults, item/correction merging, Calculate eligibility, received-type replacement and preservation, stale calculation rejection, freight, valuation, inspection, transfer, lifecycle, and special modes.

### Frontend and contract verification

- Embedded and page modes render the same domain component.
- Parent workspace does not navigate away when opening or completing DC/GRN work.
- Parent state refreshes after mutations.
- Unauthorized action buttons are absent.
- Draft values survive server errors.
- Responsive checks cover 1600, 1280, 900, and 390 pixel widths.
- Production frontend build succeeds.
- A parity inventory maps every applicable base YRP and Essdee client action to a web component, server capability, command, and automated test.

## Rollout sequence

1. Introduce the shared server contract, named command layer, workspace shell, and embedded host.
2. Complete PO and WO field/action parity using their current routed pages as the starting point.
3. Replace the reduced DC editor with the complete reusable DC workspace.
4. Replace both WO and PO reduced GRN editors with the complete reusable GRN workspace, including Calculate.
5. Add cross-document refresh, direct routes, responsive behavior, messaging, and remaining special-mode projections.
6. Run the Desk-to-web parity inventory and regression suite.
7. Remove old reduced popup components and obsolete endpoints only after their replacement paths pass.

## Acceptance checklist

- All four document types can complete their permitted lifecycle in `/web`.
- WO and PO users can complete DC/GRN work without leaving the parent.
- Direct DC/GRN routes use the same component and commands as embedded mode.
- Every applicable action from base YRP and Essdee JavaScript is accounted for.
- Effective JSON/custom-field behavior is represented intentionally, including conditional, required, and read-only fields.
- Hidden automation fields remain protected.
- Permission-ineligible buttons are absent and endpoints remain protected.
- GRN Calculate and later saves preserve all received-type splits and authoritative rows.
- Parent activity, quantities, totals, and status refresh after related work.
- Existing Desk workflows, stock side effects, lifecycle hooks, printing, and messaging remain functional.
