# Cutting and Fabric Store Workspace UI Alignment

## Goal

Apply the finalized Cutting Plan interaction strategy to Cutting Orders, Bulk LaySheets, LaySheet Planner, and Fabric Store without changing their business logic.

## Reference principles

- Keep work inside `/web`; do not redirect normal workflows to Desk.
- Minimize dwell time by placing record identity, status, and primary context in the header.
- Avoid duplicate headings, repeated context, technical helper text, and separate action strips.
- Keep lists compact, filterable, permission-aware, and consistent with Cutting Plans.
- Keep primary work in the main area and related workflow records in the existing 80/20 rail where applicable.
- Put contextual commands in the record header. One primary action may remain visible; secondary commands belong in `More Actions`.
- Preserve Frappe permissions and repeat every mutation check on the server.
- Reuse the existing emerald enterprise tokens, common list/filter components, popup workflows, and responsive rules.
- Preserve all current calculations, document fields, lifecycle actions, reports, and stock workflows.
- Keep all work uncommitted.

## Required changes

### Cutting Orders

- Keep the common list and make Create Cutting Order visually primary.
- Show status, Cutting Order Detail, and Item in the record header.
- Remove duplicated Detail and Item cells from the Details tab.
- Move Calculate LaySheets, Get Completed, and Update Completed into a header `More Actions` menu.
- Keep Print, Cancel, and Amend permission-driven in the header.
- Preserve Details, Summary, Planned Detail, Marker, and LaySheet functionality.

### Bulk LaySheets

- Keep the common list and make Create Bulk LaySheets visually primary.
- Show status, Main Stock Lot, and Stock Location in the record header.
- Remove those duplicated facts from the setup summary; retain Posting Date, Cutting Spreader, and Cutter.
- Move bulk-wide commands into a header `More Actions` menu.
- Preserve row-specific actions inside the workflow rail and all current dialogs.

### LaySheet Planner

- Keep the common list and make Create LaySheet Plan visually primary.
- Show status, Lot, and Item in the record header.
- Keep Optimize/Re-optimize as the one visible primary action, using a conventional calculation icon rather than decorative AI styling.
- Preserve Inputs, Strategies, Lay Plan, polling, selection, retry, and validation behavior.

### Fabric Store

- Replace the four top-level tabs with the same permission-aware card launcher used by Cutting.
- Cards: Work Orders, Purchase Orders, Stock Transfers, Reports.
- Route each card to a focused full-width page with back navigation to Fabric Store.
- Keep Work Order records as routed 80/20 workspaces.
- Keep Purchase Order viewing/GRN creation, stock-transfer popups, and Stock Balance reports unchanged inside their focused pages.
- Change the Work Order record back link to the Work Orders list.

## Verification

- Browser tests assert card launchers, focused Fabric Store routes, compact header actions, visible primary Create buttons, and the absence of obsolete command bars.
- Existing workflow tests remain green.
- No body overflow and no text below 11px at 1600, 1280, 900, and 390 pixel widths.
- Production frontend build passes.
