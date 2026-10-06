# Cutting Workspace Implementation Plan

## Goal

Deliver one complete Cutting workspace in the `essdee_yrp` web frontend where users can:

- enter Cutting from a two-card landing page;
- manage Cutting Plans without leaving the custom web UI;
- create and complete Cutting-origin Cut Panel Movements from the Cutting Plan;
- create the related operational transactions from modal workflows;
- manually generate all Cutting reports from a dedicated Reports page; and
- see the same compact, premium enterprise visual system on every screen.

The Frappe 15 `production_api` behavior is the parity reference. New customization code and UI remain owned by `essdee_yrp`; base `yrp` services may be called through explicit Essdee adapters where they are already the migrated source of truth.

## Implementation status — completed 30-09-2026

- [x] Shared enterprise theme, two-card Cutting landing, new routes, and legacy route redirect.
- [x] Details, Summary, Planned Detail, CPM, and Stock Transfers tabs in the fixed Cutting Plan workspace.
- [x] Cutting-origin movement generation, selection, draft, submit, cancel, and permission-aware popup flows.
- [x] Stock Entry, Stock Reconciliation, Stock Update, Lot Transfer, and Delivery Challan activity tabs and dialogs.
- [x] Internal Cutting Plan transaction registry plus compatibility merge for historical CPM-native references.
- [x] Daily Production, Daily Cut Sheet, Multi CCR, Cutting Detail, and Stock Balance report tabs with explicit Generate behavior.
- [x] Two visual/browser review passes with migrated data, including populated Multi CCR and Stock Balance results.
- [x] Final production build, 10 CPM tests, 4 report parity tests, Python compile, and whitespace validation.
- [x] Full-resolution acceptance screenshots captured in `design-references/cutting-workspace-live/` for Telegram review.

## Confirmed information architecture

```text
Cutting
├── Cutting Plans
│   ├── list
│   └── Cutting Plan
│       ├── Details
│       ├── Summary
│       ├── Planned Detail
│       ├── CPM · Cut Panel Movement
│       └── Stock Transfers
│           ├── Stock Entry
│           ├── Stock Update
│           ├── Stock Reconciliation
│           ├── Lot Transfer
│           └── Delivery Challan
└── Reports
    ├── Daily Production Report
    ├── Daily Cut Sheet Report
    ├── Multi CCR
    ├── Cutting Detail Report
    └── Stock Balance Report
```

There is no Reports tab inside a Cutting Plan. Report generation is never automatic.

## Phase 1 — Shared visual system and navigation

- Add shared enterprise design tokens and reusable layout classes in one common CSS file.
- Use the same spacing, typography, cards, command bars, tabs, filters, tables, badges, empty states, dialogs, and responsive behavior across Cutting Plan and Reports.
- Change `/web/cutting` into a two-card landing page.
- Add `/web/cutting/plans` for the existing Cutting Plan list.
- Add `/web/cutting/reports` for the report workspace.
- Use `/web/cutting/plans/:cuttingPlanId` for Cutting Plan records and preserve `/web/cutting/:cuttingPlanId` as a compatibility redirect.
- Keep headers, tab bars, and modal action footers fixed; only their data regions scroll.

## Phase 2 — Cutting Plan CPM tab

### Data model

- Add the child DocType `SD YRP Cutting Plan Stock Transfer`.
- Required child fields:
  - `against` — target DocType;
  - `against_id` — Dynamic Link using `against`.
- Add the hidden, read-only `stock_transfers` table to `SD YRP Cutting Plan` as the append-only transaction registry.
- Do not add a new Cutting Plan reference field to Stock Entry, Stock Reconciliation, Stock Update, Lot Transfer, or Delivery Challan. Existing domain-required Cut Panel Movement links remain unchanged.
- Link rows are written server-side only after permission and ownership validation.

### CPM workspace

- Add `CPM · Cut Panel Movement` as the fourth fixed Cutting Plan tab.
- Show Cutting-origin CPM records for the current Cutting Plan, newest modified first.
- Display name, document status, movement date, source location, selection totals, linked transaction, and modified time.
- “Create Movement” opens a modal; it never redirects to Desk.
- Derive and hide Item, Lot, Cutting Plan, and `movement_from_cutting = 1` from the current plan.
- Source supplier, Item, Lot, Cutting Plan, Work Order, and `movement_from_cutting = 1` are derived server-side from the current plan. The user clicks Generate, selects exact bundles/panels or collapsed quantities, and enters accessory moved weights.
- Support Save Draft, Save & Submit, reopen Draft, Submit, and permission-aware Cancel.
- Clicking outside dismisses only when no unsaved change would be lost; dirty dialogs require an explicit discard confirmation.

### Stock Transfers primary tab

CPM remains movement-only. A separate fixed Cutting Plan tab contains compact activity tabs/cards for:

- Stock Entries;
- Stock Updates;
- Stock Reconciliations;
- Lot Transfers; and
- Delivery Challans.

Cut Panel Movements are queried directly through their native `cutting_plan` link and shown only in CPM. Stock Transfer lists are derived from `stock_transfers`, including compatible historical CPM-native links. Creation and editing happen in a modal with Save Draft / Save & Submit where the target DocType supports submission. Delivery Challan is prepared against the Cutting Plan Work Order and uses the existing Essdee same-location validation override, which retains item/quantity validation and posts balanced outgoing/incoming ledger legs.

Stock Entry and Stock Reconciliation use the same grouped item-entry contract as the YRP Desk stock editor. The popup shows configured stock dimensions, then Item, then an explicit Get Item action. Get Item loads dependent and normal attributes plus the primary-attribute quantity matrix; OK stages the logical item in a table with Item, dimensions, attributes, and primary values in separate columns. The Cutting Plan Lot and source Warehouse remain server-owned, Stock Entry rates are derived by the stock controller, and reconciliation accepts a counted target quantity including zero. Save Draft and Save & Submit persist the canonical grouped payload through the existing YRP variant/UOM/stock validation layer.

Stock Update and Lot Transfer continue to use revalidated live-balance selection because both operations act on existing stock identities. Movement-origin Stock Entry asks only for an eligible submitted movement and destination warehouse. Delivery Challan asks only for the movement; Work Order, lot, item, source/destination, supplier, quantities, posting values, and audit defaults are server-derived.

CPM-root Stock Entry and Delivery Challan transactions retain their existing hidden `cut_panel_movement` field because the bundle ledger requires it. “No references” means no new `cutting_plan` backlink on the target documents. Stock Reconciliation, Stock Update, balance-cloth Lot Transfer, and generic Stock Entry remain Cutting Plan stock tools and are not presented as legacy CPM root operations.

Server endpoints must enforce target create/write/submit/cancel permission, Cutting Plan ownership, valid document state, duplicate prevention, and atomic registry updates.

## Phase 3 — Reports workspace

### Shared report contract

- Every report has a compact filter bar, explicit Generate button, loading state, error state, intentional empty state, result summary, readable data table, and horizontal overflow containment.
- Dates display as `DD-MM-YYYY` while API values remain ISO dates.
- No report API is called when the page or tab opens.
- Report calculations stay server-side and retain Frappe 15 parity unless the migrated YRP stock model requires an adapter.

### Reports

1. **Daily Production Report**
   - Date and Cutting Location mode.
   - Existing Item/Lot/date-range summary mode.
   - Bundle Generated, Label Printed, and Created totals.
   - Planned, cumulative, pending, size totals, and short-panel detail.

2. **Daily Cut Sheet Report**
   - Date and Cutting Location filters.
   - Style/Lot/Location grouped panel quantities by size.

3. **Multi CCR**
   - Open Status, Lot, Item, and Category filters.
   - Existing CCR marker, cloth, completed/excess, recut, and print-panel information preserved.

4. **Cutting Detail Report**
   - From Date, To Date, and Cutting Location filters.
   - Bundle Generated, Label Printed, and Created totals plus grouped production detail.

5. **Stock Balance Report**
   - From/To dates and migrated stock-dimension filters.
   - Opening, in, out, and balance quantity/value columns.
   - Optional attributes, ageing, zero-balance removal, and inward-date split.
   - Essdee-owned adapter around the migrated YRP stock-balance calculation.

## Phase 4 — Verification

### Automated verification

- Python tests for CPM derivation, permission gates, save/submit/cancel transitions, selected-bundle validation, duplicate/foreign-plan protection, transaction creation, and child-registry integrity.
- Python tests for stock-editor dimension defaults, plan-lot ownership, Item schema resolution, attribute/quantity normalization, duplicate stock identities, server-owned warehouses, browser-rate rejection, and zero-quantity reconciliation rows.
- Python parity tests for every report using migrated fixtures.
- Frontend production build.

### Browser verification — pass 1

- Desktop layout, 80/20 Cutting Plan split, fixed tabs, independent scroll areas, dialogs, overflow, row selection, and all empty/loading/error states.
- Execute every tab and report with real migrated data.

### Browser verification — pass 2

- Repeat at the target desktop width after the visual polish pass.
- Check alignment, readable density, date formatting, status colors, numeric alignment, keyboard focus, and permission-driven action visibility.

### Screenshot acceptance

Send full-screen screenshots to Telegram topic `mrp_migration` for:

- Cutting landing page;
- Cutting Plan Details;
- Cutting Plan Summary;
- Cutting Plan Planned Detail;
- Cutting Plan CPM;
- Cutting Plan Stock Transfers;
- Stock Entry creation popup;
- Daily Production Report;
- Daily Cut Sheet Report;
- Multi CCR;
- Cutting Detail Report; and
- Stock Balance Report.

## Repository safety

The frontend is currently a broad untracked replacement beside previously deleted tracked files. Work is limited to explicitly named Cutting components, new Cutting/report components, the shared enterprise stylesheet, exact router entries, Essdee-owned backend adapters, DocType files, and focused tests. No broad staging, reset, checkout, or cleanup is permitted.
