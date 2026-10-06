# Extractable components

## DepartmentPage

- Source: `frontend/src/components/DepartmentPage.vue`
- Category: layout
- Description: Shared department/page canvas with back navigation and content surface.
- Extractable props: `accent`, `title`, `showTitle`, `flat`, `fullWidth`, `backTo`, `backLabel`.
- Hardcoded: PrimeVue Card/Button structure, back icon, shell classes.

## FabricDocumentWorkspace

- Source: `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- Category: layout
- Description: Canonical Fabric record shell with identity facts, status, action bar, content, and totals/activity rail.
- Extractable props: record identity, title, status, facts, totals, back label, busy state.
- Hardcoded: shell geometry, action/content/rail slots, responsive behavior.

## DocumentActionStrip

- Source: `frontend/src/components/documents/DocumentActionStrip.vue`
- Category: basic
- Description: Permission-aware primary, secondary, overflow, refresh, and print action strip.
- Extractable props: action arrays, busy state, compact mode.
- Hardcoded: PrimeVue buttons/menu, action icon treatment.

## DocumentConfirmationDialog

- Source: `frontend/src/components/documents/DocumentConfirmationDialog.vue`
- Category: basic
- Description: App-native destructive/important action confirmation.
- Extractable props: visibility, title, message, confirm label, severity, busy state.
- Hardcoded: dialog rhythm and footer order.

## WorkspaceLauncher

- Source: `frontend/src/components/common/WorkspaceLauncher.vue`
- Category: basic
- Description: Permission-filtered department workspace tile launcher.
- Extractable props: sections, loading, error, accent.
- Hardcoded: tile hierarchy, icons, empty/error state.

## ListView

- Source: `frontend/src/components/common/ListView.vue`
- Category: layout
- Description: Shared data list with search, quick filters, advanced filters, columns, bulk actions, pagination, and keyboard row navigation.
- Extractable props: doctype, title, columns, status field, create label, filters.
- Hardcoded: list toolbar, table, filter and bulk-edit dialog patterns.

## FormView

- Source: `frontend/src/components/common/FormView.vue`
- Category: layout
- Description: Shared Frappe-like editor with permission-aware save/submit actions and field rendering.
- Extractable props: doctype, document, fields, permissions, action labels.
- Hardcoded: editor shell, field layout, action area.

## FormField

- Source: `frontend/src/components/common/FormField.vue`
- Category: basic
- Description: Metadata-driven field control for Data, Link, Date/Time, Check, Select, and text fields.
- Extractable props: field metadata, model value, disabled/read-only state, error.
- Hardcoded: label/help/error rhythm and control selection.

## StockItemMatrix

- Source: `frontend/src/components/stock/StockItemMatrix.vue`
- Category: basic
- Description: Attribute-aware transaction matrix supporting pricing, fulfillment, totals, and compact variants.
- Extractable props: groups, primary attribute, pricing/fulfillment visibility, editable state.
- Hardcoded: grouped headers, numeric cell hierarchy, responsive scroll.
