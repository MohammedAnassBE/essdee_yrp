# Sales Production Orders Design

## Goal

Replace the Sales placeholder in `/web` with a compact, permission-aware workspace containing exactly two destinations: Production Orders and Reports. Production Orders must expose the complete current F16 workflow in the polished visual language already used by Fabric Store and Sewing. Reports initially contains only PPO Report.

## Approved navigation

- `/web/sales`: two launcher cards, `Production Orders` and `Reports`.
- `/web/sales/production-orders`: compact searchable list with status segmentation.
- `/web/sales/production-orders/new`: create editor.
- `/web/sales/production-orders/:productionOrderId`: document workspace.
- `/web/sales/production-orders/:productionOrderId/edit`: draft editor.
- `/web/sales/reports`: report workspace containing PPO Report only.

## Production Order experience

The list follows the Fabric Store Work Orders density and interaction pattern. The default columns prioritize PPO, item, delivery date, total quantity, operational status, and price approval. Status quick filters cover Draft, PPO Request, Open, Pending Request, Item Changed, Not Processed, Closed, and Cancelled without replacing normal list search and filters.

The document workspace uses a compact header, action strip, order summary, size/quantity/ratio/price matrix, lot allocation, and activity/history areas. It must preserve the current F16 behaviors:

- Create, edit, submit, cancel, amend, print.
- Request PPO approval, approve and submit, or request changes.
- Update quantity and ratio and approve the request.
- Update MRP, retail price, and wholesale price through the existing price workflow.
- Change delivery dates with reason tracking.
- Change operational status and approve pending status changes.
- Transfer quantities and approve incoming transfers.
- Create or link lots and show ordered quantities.
- Reopen eligible closed Production Orders.

The browser never decides whether an operation is allowed. The server returns explicit capabilities based on effective permissions, document state, configured workflow roles, linked lots, ordered quantities, pending requests, and transfer state. Invalid or stale actions return the existing domain error in the standard `/web` error dialog.

## Editor

The editor keeps the current data model: naming series, item, production detail, production term, delivery date, don't-deliver-after date, comments, skip-box-sticker option, and the complete variant matrix. The matrix exposes the configured primary/dependent attributes plus quantity, ratio, MRP, retail price, wholesale price, and Production Order MRP where available. A draft can be saved or sent into the PPO approval workflow; submitted data is changed only through the existing workflow commands.

## PPO Report

The report ports the frappe-15 behavior into the current `/web` theme:

- Filters: status, product category, from date, and to date.
- Summary: total orders, total quantity, and size groups.
- Compact matrix: PPO, item, fabric, dia, GSM, posting/delivery/don't-deliver-after dates, lead time, operational status, size quantities, total, and comments.
- Expandable dispatch summary per PPO.
- Totals row and Excel export.
- Dates render as `DD-MM-YYYY`.

The F16 implementation targets `YRP Production Order`, current item variants and `SD YRP Lot`; it must not call the old frappe-15 `Production Order` schema directly.

## Architecture

Create `essdee_yrp.sales.web_workspace` as the permission-safe adapter for capabilities, document projections, editor context, saving, commands, and PPO report data. It delegates mutations to `essdee_yrp.production_order_workflow` and the YRP DocType controller so domain validation remains single-sourced. Frontend requests live in `frontend/src/api/sales.js`; Sales-specific Vue components remain under `frontend/src/departments/sales/` and reuse shared launcher, list, document, dialog, field, and report primitives.

## Quality requirements

- Match the existing `/web` typography, spacing, surfaces, badges, dialogs, and responsive behavior.
- Avoid nested scroll regions for ordinary lists and matrices; use normal page flow with horizontal overflow only for genuinely wide matrices.
- Preserve the current dirty worktree and stage only Sales-owned changes.
- Test permissions, state-driven capabilities, stale writes, malformed payloads, workflow delegation, report grouping/totals, route behavior, responsive geometry, dialogs, and production build.
