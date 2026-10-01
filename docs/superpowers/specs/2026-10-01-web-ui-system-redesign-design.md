# Essdee YRP Web UI System Redesign

**Date:** 2026-10-01  
**Status:** Proposed for implementation  
**Scope:** Shared `/web` foundation and the complete Cutting workspace  

## Context

The current frontend is a Vue 3 and PrimeVue application with a complete Cutting workspace and placeholder routes for the other departments. The Cutting feature set is functionally broad: list and form views, filters, configurable columns, Cutting Plan tabs, marker and lay-sheet side panels, CPM, stock-transfer workflows, dialogs, print actions, and five reports.

The visual implementation is fragmented. Forty Vue components contain local scoped styles, while `main.css` and `enterprise.css` cover only part of the system. Similar tables, context strips, status badges, empty states, section headers, and dialog footers are repeatedly styled with slightly different values. Some labels render below 10px, component hierarchy relies too heavily on nested cards, department accents compete with the emerald manufacturing theme, and the current type stack starts with Inter without shipping a font asset.

This is a preserve-mode redesign. Business behavior, permissions, routes, field names, data, print formats, calculations, document transitions, and report results remain unchanged.

## Design Read

This is a desktop-first manufacturing ERP for operators, supervisors, planners, and administrators. It should feel precise, trustworthy, compact, and current. The design language is a light enterprise system with cool neutral surfaces, restrained emerald accents, crisp typography, and very limited decorative motion.

Design dials:

- **Design variance: 3/10.** Predictable grids and consistent alignment are more valuable than expressive composition.
- **Motion intensity: 2/10.** Use hover, focus, pressed, and short state transitions only.
- **Visual density: 8/10.** Preserve high information density while eliminating cramped typography and redundant containers.

## Goals

- Make every active Cutting screen feel like one coherent product.
- Improve scan speed, alignment, typography, contrast, and state recognition.
- Keep important data visible without creating excessive vertical space.
- Centralize reusable visual rules so future departments inherit the same system.
- Preserve current workflows and permission-driven visibility.
- Support the current desktop layouts and intentional responsive fallbacks.
- Provide complete loading, empty, error, disabled, hover, active, and focus states.

## Non-Goals

- Rebuilding the nine placeholder department workspaces in this phase.
- Changing URLs, navigation labels, report calculations, or server contracts.
- Reordering business fields unless an existing requirement already specifies it.
- Adding a second component library or replacing PrimeVue.
- Adding decorative animations, glassmorphism, gradients, or marketing-page patterns.
- Generating or sending screenshots. Review will happen directly in the office environment.

## Considered Approaches

### 1. CSS surface polish only

Keep all current component markup and override colors, shadows, and spacing globally.

Benefits:

- Smallest code change.
- Lowest immediate regression risk.

Costs:

- Leaves repeated scoped styles and inconsistent structures in place.
- Cannot reliably fix nested-card hierarchy or tiny component-specific typography.
- Future pages would continue copying divergent CSS.

### 2. System-first targeted evolution

Keep Vue, PrimeVue, routes, and component behavior. Establish semantic tokens and shared enterprise patterns first, then migrate active Cutting surfaces in controlled passes.

Benefits:

- Preserves functionality while fixing the root visual inconsistency.
- Produces reusable patterns for later departments.
- Allows verification after each page family.
- Avoids a second UI framework.

Costs:

- Requires disciplined refactoring across shared and Cutting components.
- Temporarily mixes migrated and unmigrated styles during implementation.

### 3. Full component-system replacement

Replace PrimeVue and rebuild the frontend with Fluent, Carbon, or another enterprise system.

Benefits:

- Strong external design-system baseline.

Costs:

- High workflow and accessibility regression risk.
- Expensive rewrite of dialogs, tabs, forms, tables, and filters.
- Conflicts with the current functional implementation and delivery priority.

### Decision

Use **system-first targeted evolution**. PrimeVue Aura remains the only component system. Essdee semantic tokens and reusable layout classes will customize it into a manufacturing-specific interface.

## Information Architecture

The current information architecture stays unchanged:

```text
Administrator
└── Cutting
    ├── Cutting Plans
    │   ├── List
    │   └── Cutting Plan
    │       ├── Details
    │       ├── Summary
    │       ├── Planned Detail
    │       ├── CPM
    │       └── Stock Transfers
    └── Reports
        ├── Daily Production
        ├── Daily Cut Sheet
        ├── Multi CCR
        ├── Cutting Detail
        └── Stock Balance
```

The placeholder department routes remain visible but are not expanded during this phase.

## Visual System

### Typography

- Use a native, production-safe sans stack led by `Segoe UI Variable`, `Segoe UI`, and system UI fonts.
- Use one font family throughout the application.
- Use tabular numerals for quantities, weights, dates, IDs where alignment matters, and all numeric table columns.
- Do not render operational text below 11px.
- Default application body text is 14px with a 1.4 line height.
- Table body text is 12.5-13px; headers are 11-11.5px with restrained letter spacing.
- Page titles are 22-26px, section titles are 15-17px, and component titles are 13-14px.
- Uppercase is reserved for compact table headers and genuinely structural labels. Repeated decorative eyebrows are removed.

### Color

Use one cool-neutral palette and one emerald accent:

- Canvas: cool off-white with a very subtle mint cast.
- Primary surface: white.
- Secondary surface: cool gray-mint tint for read-only data and grouped controls.
- Primary text: deep charcoal-green.
- Secondary text: neutral green-gray with WCAG AA contrast.
- Border: soft cool gray-green.
- Accent: restrained emerald for primary actions, active tabs, focus rings, selected rows, and positive totals.
- Semantic colors: muted green, amber, red, and blue only for real statuses and feedback.

Department accent colors will not recolor the entire product shell. They may appear as small identity markers on the administrator page only.

### Shape and Depth

- Inputs and compact controls: 8px radius.
- Cards, panels, and dialogs: 12px radius.
- Status and count chips: pill radius.
- Use borders and spacing for most grouping.
- Use subtle tinted shadows only for elevated dialogs, popovers, and primary page surfaces.
- Avoid cards nested inside cards when a divider or grouped section is sufficient.

### Spacing

Use a strict 4px base scale with primary steps of 4, 8, 12, 16, 20, 24, and 32px.

- Desktop page gutters: 16-24px depending on viewport width.
- Dense control gaps: 8px.
- Field group gaps: 12-16px.
- Section gaps: 16-24px.
- Table cell padding: approximately 8px vertical and 10-12px horizontal.

## Shared Application Shell

`App.vue`, `DepartmentPage.vue`, `AdministratorPage.vue`, and the global styles establish the product shell.

- Replace the decorative radial canvas treatment with a stable cool-neutral background.
- Keep the main content nearly full-width for operational screens.
- Present the back action, page identity, status, and page actions in one aligned header region.
- Avoid oversized empty margins around list and form pages.
- Keep desktop navigation and action rows on one line whenever practical.
- Use clear responsive collapse rules below tablet widths.

The administrator page remains a department chooser. Cards become tighter, use consistent icon containers, and avoid unnecessary subtitles when the destination is self-explanatory.

## Cutting Landing Page

The Cutting landing page keeps exactly two primary destinations: Cutting Plans and Reports.

- Remove decorative eyebrow text and long explanatory copy.
- Use clear destination names and one concise supporting line only where it helps distinguish the workflows.
- Keep both actions visually equal because neither is globally primary.
- Preserve permission-based visibility and the no-permission state.

## List View System

The shared list view becomes the reference implementation for future departmental lists.

- One compact header row contains title, search, filter, columns, refresh, clear filters, and permitted bulk actions.
- Do not display redundant record-count prose in the page header.
- Keep quick-filter fields in a compact responsive grid without explanatory UI text.
- Preserve the one-second filter debounce.
- Preserve field-aware filter controls, including Link, Select, Check, Date, DateTime, numeric, and text behavior.
- Preserve Frappe-style operators and link search semantics.
- Make applied filters visible as compact removable chips only when they are useful.
- Keep column customization drag-and-drop based and keyboard operable.
- Use sticky headers, aligned numeric columns, readable row density, selected-row treatment, and clear pagination.
- Preserve row navigation and bulk-action permission checks.

## Cutting Plan Workspace

The Cutting Plan retains the existing 80/20 desktop split.

### Header and Actions

- Show `Cutting Plan`, record ID, and status as one identity group.
- Keep Edit visually separate from process commands.
- Present process commands in a compact toolbar with consistent icon spacing.
- Collapse lower-priority commands into an overflow menu only when viewport width requires it.
- Preserve every existing permission and document-state condition.

### Tabs and Scrolling

- Keep Details, Summary, Planned Detail, CPM, and Stock Transfers fixed below the header.
- Use a thin emerald active indicator and quiet inactive labels.
- Only the active tab content scrolls.
- Preserve direct programmatic activation of Summary from actions.

### Details

- Use a balanced two-column field grid matching the Desk field order.
- Use light tinted read-only fields and clear editable controls.
- Avoid a large outer card around every field group.
- Keep labels compact but readable and preserve required markers and helper text.

### Summary

- Separate completed quantity, excess quantity, recut, and print-panel content through headings, spacing, and selective surface tint.
- Use status icons only where they communicate real completion state.
- Keep dense matrices readable through sticky headers, numeric alignment, and total emphasis.

### Planned Detail

- Keep Work Order information as an analytical table.
- Distinguish Planned and Completed rows using subtle row tint and typography.
- Emphasize totals without heavy backgrounds.

### CPM and Stock Transfers

- Remove repeated headings and instructional copy already conveyed by the active tab or selected operation.
- Keep CPM focused on movements only.
- Keep Stock Entry, Stock Update, Stock Reconciliation, Lot Transfer, and Delivery Challan as the Stock Transfers operation selector.
- Make record time, status, quantities, and document identity immediately scannable.
- Preserve the current dialogs and document-state actions.

## Marker and Lay Sheet Sidebar

The right sidebar remains persistent on desktop and visible only when the user has permission to read at least one section.

- Split available sidebar height evenly between Markers and Lay Sheets.
- Each section has a fixed header, Create New action when permitted, and a filter action.
- Only each section's list region scrolls.
- Marker cards show marker name first, ID second, length, width, required piece weight, panel tags, and status.
- Lay Sheet cards show lay number first, marker identity, marker panels, bundle-generated date, printed time, print state, and status.
- Dates display as `DD-MM-YYYY`; time remains easy to scan.
- Cards open the existing modal and never redirect to Desk.

## Dialog System

All marker, lay-sheet, CPM, stock, delivery, print, filter, and column dialogs use one shared visual contract.

- Strong title and document identity in the header.
- Optional compact context strip for server-owned values.
- Scrollable body with sticky action footer for long forms.
- Clear primary, secondary, destructive, Save Draft, and Save & Submit hierarchy.
- Buttons render only when the corresponding Frappe permission and document state allow them.
- Outside-click dismissal remains enabled when safe; dirty dialogs require explicit discard handling.
- Data-entry matrices retain separate Item, dimension, attribute, primary-value, quantity, and UOM columns.
- Destructive row actions provide visible feedback and update immediately after confirmed success.

## Reports

The Reports page retains the five permission-filtered tabs.

- Remove duplicate report titles and explanatory headers inside each active tab.
- Keep the report tab bar fixed while report content scrolls.
- Use a compact filter bar with an explicit Generate action.
- Do not generate reports automatically.
- Preserve copy-report actions for Daily Production and Daily Cut Sheet.
- Show summary values in a compact strip rather than oversized dashboard cards.
- Use sticky table headers, aligned numbers, clear grouped rows, restrained totals, and deliberate empty states.
- Preserve all current server-side calculations and report-specific fields.

## Component and CSS Architecture

PrimeVue Aura remains the base component system. No new UI dependency is required.

The implementation will:

1. Expand `styles/enterprise.css` into semantic foundations for color, typography, spacing, radii, shadows, control heights, layers, and states.
2. Keep `styles/main.css` responsible for reset, canvas, shell, and high-level responsive layout.
3. Add shared structural classes for page headers, command bars, sections, data tables, context strips, status chips, empty states, dialogs, and scroll regions.
4. Migrate repeated scoped CSS into shared patterns while retaining component-specific layout rules locally.
5. Normalize PrimeVue buttons, inputs, selects, tabs, dialogs, messages, tags, and skeletons through stable application-level selectors.
6. Avoid broad selectors that could affect the Desk UI outside the Vue `/web` mount.

Component behavior stays in the existing Vue files. This phase does not introduce a new state-management layer.

## Interaction States and Accessibility

- Every interactive element has visible hover, active, disabled, and keyboard-focus states.
- Focus uses a high-contrast emerald ring with sufficient offset.
- Primary button text and all form text meet WCAG AA contrast.
- Loading skeletons match the approximate final geometry.
- Empty states explain what is absent and expose the permitted next action when applicable.
- Errors remain contextual and do not rely only on color.
- Status meanings use text in addition to color.
- Table headers remain associated with their columns.
- Dialog focus remains trapped by PrimeVue and returns to the invoking control on close.
- Motion respects `prefers-reduced-motion`; no automatic animation is required.

## Responsive Behavior

- The primary target is desktop widths used in production.
- At narrower desktop widths, action bars wrap deliberately and the 80/20 plan layout can collapse to one column.
- The sidebar moves below the main workspace when the split cannot remain readable.
- Tables and matrices scroll horizontally inside their own containers.
- Filters and form fields collapse from two or more columns to one column at mobile widths.
- Sticky regions must not overlap controls when the viewport is short.

## Performance

The current production bundle builds successfully but emits a chunk-size warning. Visual work must not add another runtime library. The implementation plan should include route-level lazy loading for Cutting Plan and report page families if it can be introduced without destabilizing navigation.

## Verification Strategy

Verification happens after each migration phase:

- Run the existing frontend production build.
- Run the existing list-filter, sidebar-filter, report-header, stock-workflow, and permission verification scripts where applicable.
- Verify behavior directly against `erp-migration-test.site` using the existing authenticated browser workflow.
- Check the administrator page, Cutting landing, Cutting Plans list, every Cutting Plan tab, sidebar filters, primary dialogs, and every report tab.
- Check loading, empty, error, read-only, and permission-restricted states.
- Check target desktop layout and responsive collapse behavior.
- Do not create or send screenshots unless explicitly requested again.

## Implementation Sequence

1. Shared tokens, reset, PrimeVue normalization, and page shell.
2. Shared buttons, inputs, status chips, sections, tables, empty states, and dialogs.
3. Administrator, Cutting landing, and Cutting Plans list.
4. Cutting Plan header, actions, fixed tabs, Details, Summary, and Planned Detail.
5. Marker and Lay Sheet sidebar plus their dialogs.
6. CPM and Stock Transfers tabs plus transaction dialogs and matrices.
7. Reports tabs, filters, summaries, tables, and empty states.
8. Responsive and accessibility pass.
9. Automated verification, production build, and two direct browser review passes.

## Acceptance Criteria

- The application uses one coherent light enterprise theme and one emerald accent.
- No operational label or data value is too small to read comfortably.
- All active Cutting routes share the same spacing, typography, control, table, dialog, and status conventions.
- The Cutting Plan keeps its fixed header and tabs, 80/20 split, and independent scroll regions on supported desktop widths.
- Every existing Cutting workflow, permission condition, field, value, calculation, print action, and document-state transition still works.
- Reports retain their current data while losing redundant headers and visual clutter.
- No new component framework or animation dependency is added.
- Production build and focused verification scripts pass.
- The checkpoint commit `90b0b48` remains the clean baseline for comparing the redesign.
