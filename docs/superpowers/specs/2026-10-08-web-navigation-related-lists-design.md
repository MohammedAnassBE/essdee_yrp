# Web Navigation and Related Lists Design

**Date:** 2026-10-08

**Status:** Approved for implementation

## Purpose

Make the `/web` workspaces faster to move through without changing document creation. The separate back-navigation row currently consumes vertical space, list filters are lost when opening a record, and high-volume related records are constrained to narrow side rails. The new design puts navigation beside the visible page title, preserves list context for deterministic Previous/Next movement, and provides full list dialogs for the related records that can grow large.

## Scope

### Included

- Replace the separate back row with a compact arrow beside the primary visible heading on non-creation pages in:
  - Cutting
  - Fabric Store
  - Cut Panel Store
  - Accessory Store
- Apply the inline back treatment to workspace launchers, section/list pages, reports, and saved document views where those areas use the current `/web` shell.
- Add filter-aware Previous/Next navigation to routed saved documents opened from a `ListView`:
  - Cutting Plan
  - Cutting Order
  - Cutting Bulk LaySheet
  - Fabric, Cut Panel, and Accessory Work Orders
  - Fabric and Accessory Purchase Orders
- Restore the same list search, advanced filters, quick filters, status, sort, page, and page size when returning from a document.
- Add expanded related-record lists for:
  - Cutting Plan and Cutting Order Markers
  - Cutting Plan and Cutting Order Lay Sheets
  - Fabric, Cut Panel, and Accessory Work Order Delivery Challans
  - Fabric, Cut Panel, and Accessory Work Order Goods Received Notes
- Retain existing permissions, create actions, filters, record dialogs, and document actions.

### Explicitly excluded

- All creation and editor UI redesign.
- Sewing workspace code or behavior.
- Cutting LaySheet Planner list, editor, and saved view.
- Expanded Purchase Order GRN lists; the existing Purchase Order related display remains sufficient.
- Optional expansion for Stock Entry or other transaction dialogs.

## Design Principles

1. Navigation is shared infrastructure, not repeated page-specific state.
2. Previous/Next must never guess and open the wrong document.
3. The applied list query is authoritative; text still waiting for debounce is not.
4. Existing creation, validation, permissions, and document workflows must remain unchanged.
5. Expanded lists use server pagination and cannot silently inherit the 500-row workspace payload limit.
6. All new controls remain keyboard accessible and usable on touch screens.

## Inline Page Navigation

`DepartmentPage` will gain an opt-in inline-navigation mode. Its existing standalone navigation row remains the default, protecting excluded pages and any routes not migrated in this change. In inline mode it provides the static back destination and label to descendants and suppresses only the old standalone row.

A shared inline navigation control will render:

- a RouterLink back arrow labelled `Back to {destination}`;
- Previous and Next buttons when a valid list-navigation context exists;
- stable control positions, with unavailable Previous/Next controls disabled rather than removed.

The control will be consumed by the shared heading owners already present in the application:

- `WorkspaceLauncher` for department landing pages;
- `ListView` for list pages;
- report headers/shells for report pages;
- `FormView` for the Cutting Plan saved view;
- `FabricDocumentWorkspace` for full-page Work Order, Purchase Order, Delivery Challan, and GRN views;
- the custom saved-view headers for Cutting Order and Cutting Bulk LaySheet.

Creation/editor wrappers will not opt into inline navigation. Full-page Delivery Challan and GRN views may show Back, but their embedded dialog presentation must never show page-level navigation.

## Capturing List Navigation State

`ListView` will create a serializable state snapshot when a row is opened. The snapshot contains only values already used by the live query:

- source route name and full path;
- DocType;
- normalized base filters;
- applied advanced filters;
- applied quick filters;
- applied status and search;
- deterministic order;
- current page offset and page size;
- clicked record's global index;
- last known total;
- target route name and target parameter name.

The snapshot must use `allFilters()` and the applied search/quick-filter values. Draft text waiting for its debounce must not leak into navigation.

The full state is versioned and stored in `sessionStorage`, keyed by source route plus DocType. Only the state key, current index, and current document name travel in browser history state. This avoids large duplicated history entries and allows a list to restore its controls after returning or refreshing.

Every list query uses a deterministic secondary `name` sort in the same direction as the selected primary sort. Existing rows with equal primary values therefore retain stable order.

`ListView` will emit `(row, navigationSnapshot)` for both desktop and mobile activation. A shared route helper will enrich the snapshot with the destination route and parameter, persist it, and navigate with browser state. List pages will not manually reimplement this behavior.

## Previous and Next Resolution

The shared document navigation control reads the small browser-state reference, loads the corresponding session state, and validates all of the following:

- the context version is supported;
- the current route matches the recorded destination route;
- the DocType and current name match;
- the stored source route is still available.

It then requests a small server window around the saved global index using the captured filters and deterministic order. The current name must appear at the expected location before either adjacent record becomes available.

If the current record moved, disappeared from the filter, or the list otherwise changed, both controls become disabled and an accessible `List changed — return to list` explanation is shown. The system does not guess using a stale index.

Moving Previous or Next uses `router.replace`, not `router.push`, and carries the updated browser state. Consequently, browser Back returns to the source list instead of stepping through every visited document. The inline back arrow always routes to the captured source list when valid, otherwise to the page's static fallback.

Previous/Next is hidden while a document is in edit mode and blocked whenever the host reports unsaved changes. Existing route-leave confirmation remains authoritative. Any save-time `router.replace` must preserve the current navigation state.

Direct deep links have no list context. They show only the static Back arrow and no Previous/Next controls.

## Expanded Related Lists

A reusable `RelatedRecordsDialog` will wrap the existing server-backed `ListView`. It receives:

- title and DocType;
- parent/base filters;
- default columns and labels;
- status field/options when applicable;
- initial advanced filters owned by the rail;
- row-open behavior.

Because the dialog queries the DocType directly, normal server pagination, search, advanced filters, quick filters, sorting, metadata, and permission checks continue to work beyond the 500-row cap of the parent workspace payload.

The dialog disables bulk actions and page-level Back/Previous/Next controls. Applying advanced filters in the dialog updates the rail's filter model, so reopening either surface shows a consistent selection.

### Cutting Plan and Cutting Order

The shared Cutting sidebar already serves both parent types. Each Markers and Lay Sheets heading gains an icon-only Expand button immediately to the left of its existing Filters button.

- Marker base filter: `cutting_plan = current parent` or `cutting_order = current parent`.
- Lay Sheet base filter: the same resolved parent field.
- Existing Marker and Lay Sheet dialogs remain the record views.

Selecting a row closes the expanded list, opens the existing record dialog, and records that it came from the expanded list. Closing the record dialog reopens the expanded list at its retained filter/page position.

### Work Orders

Each Delivery Challans and Goods Received Notes heading gains the same Expand placement before its current filter/search action.

- Delivery Challan base filter: `work_order = current Work Order`.
- GRN base filters: `against = "YRP Work Order"` and `against_id = current Work Order`.
- The existing `RelatedDocumentWorkspaceDialog` remains the record view.

The behavior applies automatically to Fabric, Cut Panel, and Accessory Work Orders because they share `FabricWorkOrder` and `WorkOrderActivityRail`.

## Accessibility and Responsive Behavior

- Back is a real link with an accessible destination label.
- Previous and Next announce the document type and expose disabled state without shifting layout.
- Expand buttons use `aria-haspopup="dialog"`, `aria-expanded`, visible tooltips, and labels such as `Expand Lay Sheets`.
- New icon controls keep a minimum 44 by 44 pixel touch target on coarse pointers and mobile sizes.
- Dialogs use the existing maximized mobile surface and named keyboard-scroll regions.
- Focus returns to the triggering Expand button when an expanded dialog closes.
- After Previous/Next navigation, focus moves to the new document title.

## Failure Handling

- Missing or invalid session state degrades to Back-only navigation.
- Adjacent-query failures leave the current document open and expose a concise navigation error.
- Changed lists disable Previous/Next rather than selecting an unverified neighbor.
- Permission failures use the existing `ListView` and document error treatment.
- Empty expanded lists retain filters and show the standard deliberate empty state.

## Verification Strategy

Implementation follows test-driven development. Automated coverage must include:

1. Inline Back replaces the standalone row on each migrated page type.
2. Creation pages retain their current behavior.
3. Sewing and all Cutting LaySheet Planner source files remain unchanged.
4. Desktop and mobile row activation emit the same applied navigation snapshot.
5. Returning restores search, filters, status, sorting, page, and page size.
6. Previous/Next crosses a pagination boundary using deterministic ordering.
7. A direct deep link renders Back only.
8. The first and last result expose the correct disabled control.
9. A saved or externally changed record produces `List changed` rather than a wrong neighbor.
10. Editing and dirty-state navigation are blocked.
11. Expanded Marker, Lay Sheet, DC, and GRN lists receive exact parent filters.
12. An expanded list can page past 500 mocked records.
13. Dialog filters stay synchronized with their rail filters.
14. Opening and closing a related record restores the expanded list.
15. Keyboard labels, focus return, mobile touch targets, and overflow remain valid.

Existing Cutting, Cutting Order, Bulk LaySheet, Fabric Store, Work Order, Purchase Order, DC, and GRN regression suites must remain green, followed by a production frontend build and an independent code review.

## Rollout Boundary

This change is frontend-only unless an existing Frappe list API proves unable to express one of the required parent filters. No migration, schema change, or existing data backfill is expected. The feature is opt-in per migrated page, allowing excluded pages to retain current behavior without conditional global CSS.
