# Sales Production Orders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete `/web` Sales workspace with compact Production Order workflows and the PPO Report.

**Architecture:** A new permission-safe Sales service projects Production Order state and delegates all mutations to the existing F16 workflow. Vue pages consume that explicit contract and reuse the established `/web` launcher, list, document, dialog, and report visual primitives.

**Tech Stack:** Frappe/Python, Vue 3, PrimeVue 4, Vite, Playwright verification scripts.

**Spec:** `docs/superpowers/specs/2026-10-09-sales-production-orders-design.md`

## Global Constraints

- Sales exposes exactly `Production Orders` and `Reports` on its launcher.
- Reports initially exposes only `PPO Report`.
- Domain mutations delegate to `essdee_yrp.production_order_workflow`; do not duplicate workflow validation in Vue or the adapter.
- Use `YRP Production Order`, current item variants, and `SD YRP Lot`; do not use frappe-15 schema names.
- Dates shown to users use `DD-MM-YYYY`.
- Match the existing `/web` theme and avoid unnecessary nested scrolling.
- Preserve unrelated dirty-worktree changes and stage only Sales-owned files.

## Review Focus

- A readable document with no mutation permission exposes data but no unauthorized action; Task 1 tests this.
- Pending PPO, quantity, status, price, and transfer requests expose only the matching approval action; Task 2 tests this.
- A stale `modified` token rejects an edit or command without partial mutation; Task 2 tests this.
- Variant groups with different size sets retain correct positional columns and totals in PPO Report; Task 3 tests this.
- Wide matrices and action dialogs remain reachable at desktop, tablet, and mobile widths; Task 6 tests this.

---

### Task 1: Sales capabilities and Production Order projection

**Files:**
- Create: `essdee_yrp/sales/__init__.py`
- Create: `essdee_yrp/sales/web_workspace.py`
- Create: `essdee_yrp/test_sales_web_workspace.py`
- Modify: `essdee_yrp/hooks.py`
- Modify: `essdee_yrp/www/web.py`

**Interfaces:**
- Produces: `get_capabilities() -> dict` and `get_production_order_workspace(production_order: str) -> dict`.
- The workspace returns `record`, `fields`, `matrix`, `ordered`, `linked_lots`, `histories`, `permissions`, and named `capabilities` with labels and disabled reasons.

- [ ] Write failing Python tests for exact two-section capability output, independent report permission, read-only projection, effective role/state action filtering, authenticated-only access, and web catalog registration.
- [ ] Run `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sales_web_workspace` and verify the missing module/contract failures.
- [ ] Implement the smallest projection and capability service, including allowlisted fields and existing workflow `onload` state.
- [ ] Run the same module and verify it passes.
- [ ] Commit only Task 1 files with `feat: add sales production order workspace contract`.

### Task 2: Editor and command coordination

**Files:**
- Modify: `essdee_yrp/sales/web_workspace.py`
- Create: `essdee_yrp/test_sales_production_order_commands.py`

**Interfaces:**
- Produces: `get_production_order_editor(name: str | None = None, source=None) -> dict`, `save_production_order(values, name=None, submit=False, expected_modified=None) -> dict`, and `execute_production_order_command(name, command, payload=None, expected_modified=None) -> dict`.
- Commands cover lifecycle, PPO approval, requested changes, quantity/ratio request and approval, price, dates, status, transfer request and approval, lot creation/linking, and reopen.

- [ ] Write failing tests proving allowlisted draft saves, required matrix preservation, stale-write rejection, malformed payload rejection, permissions, and exact delegation for every supported command.
- [ ] Run `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sales_production_order_commands` and verify contract failures.
- [ ] Implement editor serialization, safe save coordination, command registry, stale guards, and refreshed workspace responses.
- [ ] Run Task 1 and Task 2 Python modules and verify both pass.
- [ ] Commit only Task 2 files with `feat: expose production order editor and actions`.

### Task 3: F16 PPO Report service

**Files:**
- Create: `essdee_yrp/sales/ppo_report.py`
- Create: `essdee_yrp/test_sales_ppo_report.py`
- Modify: `essdee_yrp/sales/web_workspace.py`

**Interfaces:**
- Produces: `get_ppo_report(filters=None) -> dict`, `get_ppo_dispatch_summary(production_order: str) -> dict`, and `download_ppo_report(...)`.
- Report payload contains `orders`, `size_groups`, `max_columns`, and `summary` with literal totals.

- [ ] Write failing tests for permission denial, date/status/category filters, mixed size-group alignment, totals, no-record output, dispatch grouping, and Excel response metadata.
- [ ] Run `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sales_ppo_report` and verify missing service failures.
- [ ] Port the frappe-15 report behavior to current F16 doctypes with batched reads and deterministic ordering.
- [ ] Run all three Sales Python modules and verify they pass.
- [ ] Commit only Task 3 files with `feat: add sales PPO report service`.

### Task 4: Sales launcher, list, API, and routes

**Files:**
- Modify: `frontend/src/departments/Sales.vue`
- Create: `frontend/src/departments/sales/SalesLauncher.vue`
- Create: `frontend/src/departments/sales/SalesSection.vue`
- Create: `frontend/src/departments/sales/ProductionOrders.vue`
- Create: `frontend/src/api/sales.js`
- Modify: `frontend/src/router/index.js`
- Create: `scripts/verify_sales_workspace.mjs`

**Interfaces:**
- Consumes: Task 1 capability endpoint.
- Produces: Sales launcher and list routes plus typed request wrappers consumed by Tasks 5 and 6.

- [ ] Add a failing Playwright suite for exactly two launcher cards, capability hiding, compact full-width layout, Production Order status filters, safe route ordering, row navigation, retry/error dialogs, and responsive overflow.
- [ ] Run `node scripts/verify_sales_workspace.mjs launcher` and verify the placeholder/card/route failures.
- [ ] Implement launcher, section shell, Production Order list, API wrappers, and routes using existing shared primitives.
- [ ] Re-run the launcher suite and verify it passes.
- [ ] Commit only Task 4 files with `feat: add sales launcher and production order list`.

### Task 5: Production Order view, editor, and workflow dialogs

**Files:**
- Create: `frontend/src/departments/sales/ProductionOrder.vue`
- Create: `frontend/src/departments/sales/ProductionOrderEditorPage.vue`
- Create: `frontend/src/departments/sales/ProductionOrderEditor.vue`
- Create: `frontend/src/departments/sales/ProductionOrderMatrix.vue`
- Create: `frontend/src/departments/sales/ProductionOrderOverview.vue`
- Create: `frontend/src/departments/sales/ProductionOrderActionDialog.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `scripts/verify_sales_workspace.mjs`

**Interfaces:**
- Consumes: Task 2 editor/workspace/command endpoints and Task 4 API wrappers.
- Produces: complete create/view/edit/action UI for all approved Production Order workflows.

- [ ] Add failing browser tests for compact identity hierarchy, matrix data, draft save, PPO request/approval, quantity/ratio, price, date, status, transfer, lot, reopen, lifecycle actions, capability hiding, stale responses, and standard error dialogs.
- [ ] Run `node scripts/verify_sales_workspace.mjs production-orders` and verify the missing-page/action failures.
- [ ] Implement the document workspace, matrix editor, action strip, and focused dialogs without recreating server eligibility rules.
- [ ] Re-run the Production Order suite and verify it passes.
- [ ] Commit only Task 5 files with `feat: build production order web workflow`.

### Task 6: PPO Report UI and final verification

**Files:**
- Create: `frontend/src/departments/sales/SalesReports.vue`
- Create: `frontend/src/departments/sales/PpoReport.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/api/sales.js`
- Modify: `scripts/verify_sales_workspace.mjs`

**Interfaces:**
- Consumes: Task 3 report endpoints and Task 4 API wrappers.
- Produces: `/sales/reports` with one PPO Report and Excel download.

- [ ] Add failing browser tests for one report, all four filters, explicit fetch, totals, mixed size headers, expandable dispatch summaries, `DD-MM-YYYY`, empty/error states, Excel URL, normal page flow, and geometry from 390px through 1600px.
- [ ] Run `node scripts/verify_sales_workspace.mjs reports` and verify missing report failures.
- [ ] Implement the report shell and responsive PPO matrix in the existing `/web` theme.
- [ ] Run `node scripts/verify_sales_workspace.mjs all`, all Sales Python tests, `node scripts/verify_web_ui_redesign.mjs`, and `npm run build` from `frontend`; verify zero failures.
- [ ] Commit only Sales-owned files with `feat: add PPO report to sales workspace`.
