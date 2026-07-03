# Essdee YRP `/web` UI — E2E acceptance results (2026-07-03)

Runner: `apps/essdee_yrp/scripts/web-ui-e2e.mjs` (headless Playwright, real
fills/clicks + literal DOM/DB reads). Site `essdee_yrp.site:8003`. Test user
`webuser@essdee.fit` (Production Planner, Merchandiser, Merch User, Item Master
Manager, Stock User, Stock Manager — NOT System Manager).

**23 / 23 PASS.**

| ID | Check | Result |
|----|-------|--------|
| T1 | Form login as non-SM user lands on `/web` | landed `/web/home` |
| T2 | Desk block: `/app`, `/app/item`, `/desk`, `/apps`, `/` all → `/web`; `/api` stays open | all → `/web`, api 200 |
| T3 | Sidebar shows only the 8 registry doctypes; no Desk link for non-SM | 8 slugs, desk-link=false |
| T4 | Tab contracts: WO status tabs; Stock Entry docstatus tabs; Lot Open/Closed+All | all correct, rows render |
| T5 | Prev/next doc arrows follow list order | row3=FT-CLOTH → next=FT-YARN |
| T6 | Per-user list columns (User Listview) persist across reload | column added, survived reload |
| T7 | Lot detail Order Items / Order Details editors render real data | 5 / 4 rows |
| T8 | Bare Lot create (webuser); Delete button correctly hidden (no delete perm) | created + button gated |
| T9 | Terms and Condition create with 2 detail rows | created, 2 rows |
| T10 | Admin keeps Desk (`/desk` 200, `/app`→301→desk, never bounced) | login→/desk, /desk→/desk |
| T11 | **Synced-Lot no-change save preserves children** (review-critical contract) | editor-rows=5, items 8→8, order-details 32→32, cut 0→0, pack 0→0 |
| T12 | Fabric-deliverables modal loads its context on a fabric WO | WO-00004 (dyeing), 1 fabric row |
| T13 | Realtime stale-doc banner shows when another user edits the open doc | banner shown |
| T14 | Dark mode measured (getComputedStyle, not eyeball) | html.dark=true, page-bg rgb(26,34,48) |
| cleanup | Admin deletes the webuser test records | both 202 → gone |

## Bugs the E2E caught and fixed

1. **Edit-mode Lot editors were missing.** The first insertion script aborted on
   a later assertion, so `LotOrderEditor` / `LotOrderDetailGrid` only landed in
   the view tabs, not the edit form — editing a Lot showed no Order Items / Order
   Details grid (T11 editor-rows=0). Fixed by inserting the edit-mode block.
2. **Fabric modal never opened.** `onCalculateDeliverables` + `calcDeliverablesOpen`
   were dropped by an earlier prune cutblock; the template referenced them (a
   runtime error Vite can't catch). Fixed by re-adding the handler + ref.

## Standing notes (not defects)

- The desk gate is **navigational, not a security boundary** — `/api` stays open;
  role-based DocType permissions are the real enforcement.
- Lot's base permissions grant role **"All" write** (not create) — every
  authenticated user can edit Lots via `/api` regardless of the desk gate
  (pre-existing base-yrp/essdee behaviour).

## Final code review (2026-07-03) — applied fixes

Fresh-context whole-branch review: **no critical/ships-broken issues**; the two
highest-risk areas (Lot save/child-preservation contract, Desk gate) verified
correct against the actual controllers + frappe source. Applied:

- **IMPORTANT — `is_transferred` Lot editor lock (Desk parity).** A transferred
  Lot's Order Items / Order Details editors now render read-only (lock note +
  Fetch/edit/delete suppressed), and buildPayload omits the rebuild JSON so a
  save can't rebuild `items`/`lot_order_details` that downstream Cutting Plans
  reference. Verified by flipping `is_transferred` on a Lot: lock-note shown,
  Fetch Item hidden, 0 edit icons, 0 order-detail inputs; flag restored.
- MINOR: hide the dead empty `size_set_colour` Select on the /web Lot form;
  `item_attribute.update_mapping_values` rejects an attribute-name that doesn't
  match the mapping; `link_search` guards a non-int `page_length`; `bulk_edit`
  docstring corrected (parent field uses db_set, child uses save); removed the
  orphan `config/fields/process-cost.js`; cleaned a stale `<template v-if="true">`
  and a stale header comment.

Re-ran the full suite after the fixes: **23/23 PASS**.

## Post-review regression + fix (2026-07-03) — blank lists

The user found every list view rendering **visually blank** (header only). Root
cause: a review-pass "cleanup" turned a `<template v-if="true">` wrapper in
`DynamicListPage.vue` into a bare `<template>`, which Vue 3 emits as a literal
`display:none` HTML `<template>` element — hiding the tab strip + DataTable +
paginator on all 8 lists. The original DOM-count E2E missed it (rows stay in the
DOM under `display:none`). Fixed by removing the wrapper tags entirely; added a
**geometry assertion** (T4a — every list's table must paint at non-zero width)
so this can't regress silently. Suite now **31/31 PASS**, including all 8 lists
verified painting at 1314px.

## Comprehensive subagent-driven E2E (2026-07-03, second pass)

After the user reported "clicking a row shows nothing," a 7-agent workflow drove
every surface with REAL clicks + screenshots + rendered-geometry assertions (54
checks; screenshots in `apps/essdee_yrp/docs/design/e2e-shots/`). Result: **the
/web app works end-to-end, zero functional defects.** Row-click navigation and
detail rendering confirmed for BOTH a floor user and Administrator across all 8
doctypes — the user's issue was a stale cached bundle (hard-refresh needed).

Coverage (all PASS unless noted):
- Auth/desk-block (all of /app,/apps,/desk,/), sidebar (8 doctypes, no Desk link),
  API-open, home cards+quick-create+recents+card-nav, dark-mode (measured),
  command palette, admin→Desk, logout.
- Lot: list→click→detail→(Order Items / Order Details / BOM Summary tabs)→edit
  (Fetch Item + editable grids, PO-mode gating)→create→More(Calc Order/BOM).
- Work Order: list→click→detail→Deliverables/Receivables pivots→Fabric modal→
  prev/next→create.
- Item: list→click→detail→Attribute Values (Dia/Colour chips)→edit→create.
- Terms and Condition: list→click→detail→child table→create (Add Row).
- IPD: list→click→rich IPDConfigView→Edit-fields→create→BOMMappingEditor +
  ProcessMatrixEditor (both open + paint on real data).
- List features: search, parent + CHILD-TABLE filters (distinct, no dup rows),
  column customizer (persists), pagination, bulk select+edit, sort, row-click
  from filtered/searched lists.
- Delivery Challan, GRN, Stock Entry: lists + create forms paint; details had 0
  records to open. CLOSED for Stock Entry by seeding a throwaway draft
  (STE-2026-00001) → detail + size-pivot rendered (Item/Lot/Received Type/Dia/
  Colour/Qty/UOM row) → list→click navigated → record deleted. DC reuses the same
  StockItemGridEditor (verified). GRN's received-type editor is unverifiable on a
  real record here — the site has no submitted Work Orders to receive against (a
  master-data site); its create form + shared DocDetail shell render correctly.

## Premium elevation pass (2026-07-03, design authority delegated)

User: "this is your call… but the final output will be a massive one." Applied the
full elevated direction (proof: `docs/design/mockups/elevated-web-ui.html`):

- **Palette deepened** (global.css tokens + theme.js ramps, BOTH layers): picked
  teal-biased neutrals (page #F2F6F4, hairlines #DFE8E4, green-biased ink
  #0F1613), refined deep teal accent family (#0E8C7F / #0C7A6F / #0A5F58),
  retinted status washes; royal-blue input focus kept.
- **Premium dark theme**: green-biased charcoal world (#0E1512 page / #17211C
  cards / luminous #2FB8A6 accent) — designed, not inverted.
- **Record-led detail pages**: new hero-facts strip above the tabs (first 4
  Quick Info values, value-forward type) — the first glance answers "what is
  this record". Additive template block; reuses quickInfo's resolve rules.
- **Craft layer**: status pills with dot; uppercase micro table headers;
  tabular-nums in cells; accent-tinted row hover with inset accent bar; motion
  (card lift, button press, eased transitions — reduced-motion-safe); branded
  empty states; Item list duplicate-"Name" header fixed ("Item Name").

Functional regression after the reskin: **31/31 PASS** (full suite incl. the 8
list-paint geometry checks). Palette/structure changes are token-level +
additive; zero data-path edits.
