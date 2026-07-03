# Essdee YRP `/web` UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Execution note (per lessons-learned 2026-07-02):** the main agent implements directly; per-task fresh reviewers are NOT used. Gates = 2 plan reviewers (done before execution), the E2E active-driving gate (Task 11), one final whole-branch review (Task 12).

**Goal:** Replicate the mgk_clothing_yrp `/web` Vue SPA into the essdee_yrp app on `essdee_yrp.site`, managing exactly 8 DocTypes (Lot, Item, Item Production Detail, Work Order, Delivery Challan, Goods Received Note, Terms and Condition, Stock Entry), with post-login redirect to `/web` for non-System-Manager users and Desk (`/app`) blocked for them.

**Architecture:** Wholesale copy of `apps/mgk_clothing_yrp/frontend/` (Vue 3 + PrimeVue + Vite SPA → `public/frontend` bundle → `www/web.html`+`web.py` + `website_route_rules` catch-all) into `apps/essdee_yrp/frontend/`, then: (a) re-point the build/asset/namespace couplings, (b) rewrite the DocType registry to the 8 target DocTypes, (c) prune MGK-only features (mgk_items grid, MGK approval, Bill Tracking, parties, Inspection Entry, tree view, workflows), (d) port 6 generic server api modules + 2 per-user-settings DocTypes into essdee_yrp, (e) add net-new Lot support (custom items/order-details editors mirroring the Desk `LotOrder.vue`/`CutPlanItems.vue`), (f) add the essdee WO fabric-deliverables modal wired to the EXISTING `essdee_yrp.api.work_order` endpoints, (g) add the post-login redirect + a new `before_request` Desk-block hook.

**Tech Stack:** Vue 3, PrimeVue 4 (Aura preset), Vite 5, socket.io-client, vue-router 4, Frappe 16 whitelisted endpoints. Build with **yarn** (`frontend/yarn.lock` exists).

## Global Constraints

- **Never touch `apps/frappe`, `apps/yrp`, `apps/mgk_clothing_yrp`** — all changes land in `apps/essdee_yrp` only. (mgk is the READ-ONLY reference; base yrp endpoints are consumed as-is.)
- **NO `git commit` at any point** — user commits himself (conventions 2026-06-17). Repo = `apps/essdee_yrp` (git per-app; never run git at bench root).
- Site: `essdee_yrp.site`, served at `http://essdee_yrp.site:8003` (bench webserver_port 8003). Creds: `~/.frappe-debug-creds-mrp3` (Administrator / line 2).
- Rebuild = `cd apps/essdee_yrp/frontend && yarn build` then `bench --site essdee_yrp.site clear-cache`. `bench build --app essdee_yrp` does NOT rebuild the SPA (conventions 2026-06-17).
- `bench --site essdee_yrp.site migrate` is allowed (dev site, not prod).
- Keep `--mgk-*` CSS custom properties and `.mgk-*` CSS class names **verbatim** (internal tokens; renaming cascades through every .vue file for zero functional gain). Rename ONLY: user-facing branding strings, storage keys, console prefixes, the API namespace strings, and the vite/web.py asset coupling.
- Exact DocType name is **"Terms and Condition"** (no trailing s).
- The 8 managed DocTypes: Lot, Item, Item Production Detail, Work Order, Delivery Challan, Goods Received Note, Terms and Condition, Stock Entry. Nothing else appears in the sidebar/registry.
- Submittable among the 8: Work Order, Delivery Challan, Goods Received Note, Stock Entry. **Lot, Item, IPD, Terms and Condition are NOT submittable.** No workflow DocTypes among the 8 (`WORKFLOW = {}`).
- essdee Work Order has ZERO custom fields — it uses base-yrp `deliverables`/`receivables` (+ `deliverable_details`/`receivable_details` grouped-JSON). There is NO `mgk_items`, NO `mgk_approval_log` on this site.
- `User Listview` / `User Listview Field` + their endpoints live in base yrp → **do not port** (works as-is).
- sd_yrp_sync owns much of the Lot/IPD/Item data on this site (~1767 Lots synced from F15). The UI writes normally; do not add sync-special-casing (user manages sync manually).

## Reference files (read before the corresponding task — no-shortcut-replication)

- SPA source of truth: `/home/anas/frappe-16/apps/mgk_clothing_yrp/frontend/src/**`
- Serving: `.../mgk_clothing_yrp/mgk_clothing_yrp/www/{web.py,web.html}`, `www_home.py`, `hooks.py:14-27,61-70`
- Server api to port: `.../mgk_clothing_yrp/mgk_clothing_yrp/mgk_clothing_yrp/api/{link_search,bulk_edit,child_table_view,sidebar_view,bom_mapping,item_attribute}.py`
- Per-user settings doctypes to port: `.../mgk_clothing_yrp/mgk_clothing_yrp/mgk_clothing_yrp/doctype/{mgk_child_table_view_setting,mgk_sidebar_setting}/`
- Lot Desk editors to mirror: `/home/anas/frappe-16/apps/yrp/yrp/public/js/Lot/components/LotOrder.vue`, `/home/anas/frappe-16/apps/yrp/yrp/public/js/CuttingPlan/components/CutPlanItems.vue`, and `apps/essdee_yrp/essdee_yrp/essdee_yrp/doctype/lot/{lot.js,lot.py,lot.json}`
- essdee WO fabric flow: `apps/essdee_yrp/essdee_yrp/public/js/work_order.js` + `apps/essdee_yrp/essdee_yrp/api/work_order.py`

---

### Task 1: Copy the frontend and re-point the build coupling

**Files:**
- Create: `apps/essdee_yrp/frontend/**` (copy of `apps/mgk_clothing_yrp/frontend/` minus `node_modules`, minus built `../mgk_clothing_yrp/public/frontend` output)
- Modify: `apps/essdee_yrp/frontend/package.json`, `apps/essdee_yrp/frontend/vite.config.js`, `apps/essdee_yrp/frontend/index.html`

**Interfaces:**
- Produces: a Vite project whose `yarn build` emits `apps/essdee_yrp/essdee_yrp/public/frontend/assets/essdee-<hash>.js` + `index-<hash>.css`. Task 2's `web.py` globs `essdee-*.js`.

- [ ] **Step 1: Copy the tree**

```bash
rsync -a --exclude node_modules /home/anas/frappe-16/apps/mgk_clothing_yrp/frontend/ /home/anas/frappe-16/apps/essdee_yrp/frontend/
```

- [ ] **Step 2: package.json** — `"name": "essdee-yrp-frontend"`; build script base flag → `"build": "vite build --base=/assets/essdee_yrp/frontend/"`.

- [ ] **Step 3: vite.config.js** — `outDir: "../essdee_yrp/public/frontend"`; `entryFileNames: "assets/essdee-[hash].js"` (keep `chunkFileNames`/`assetFileNames`/`emptyOutDir` as-is; the dev proxy is bench-generic — keep).

- [ ] **Step 4: index.html** — `<title>Essdee YRP</title>`.

- [ ] **Step 5: Install + build to verify the pipeline**

```bash
cd /home/anas/frappe-16/apps/essdee_yrp/frontend && yarn install && yarn build
ls ../essdee_yrp/public/frontend/assets/ | grep -E '^essdee-.*\.js$'   # must match exactly one entry file
ls ../essdee_yrp/public/frontend/assets/ | grep -E '^index-.*\.css$'
```
Expected: build exits 0, both globs match. (The app still contains MGK branding/registry — fixed in later tasks; this step only proves the pipeline.)

### Task 2: Serving layer — www/web.py, web.html, www_home.py, hooks.py

**Files:**
- Create: `apps/essdee_yrp/essdee_yrp/www/web.py`, `apps/essdee_yrp/essdee_yrp/www/web.html`, `apps/essdee_yrp/essdee_yrp/www_home.py`
- Modify: `apps/essdee_yrp/essdee_yrp/hooks.py`

**Interfaces:**
- Produces: `/web` route serving the SPA on essdee_yrp.site; `get_website_user_home_page` post-login redirect. Consumed by Task 3 (desk block) and all E2E.

- [ ] **Step 1: Copy `www/web.py` + `www/web.html` from mgk and adapt web.py:**
  - `ASSET_BASE = "/assets/essdee_yrp/frontend/"`
  - `_resolve_frontend_assets()`: base = `"/assets/essdee_yrp/frontend/assets/"`, JS fallback `"essdee.js"`, glob `essdee-*.js` (keep `index-*.css` glob)
  - `get_boot()`: `app_logo` fallback asset `"essdee-logo.png"` (Task 5 ships the logo file); guest redirect target stays `/login?redirect-to=/web`
  - Docstrings: Essdee. web.html: `<title>Essdee YRP</title>` (rest verbatim — it injects `csrf_token`, `boot|tojson`, `frontend_css/js`).

- [ ] **Step 2: Create `www_home.py`** — verbatim port of mgk's (module docstring re-titled). Exact logic (matches the user's requirement: Administrator + System Manager keep Desk, everyone else lands on `/web`):

```python
import frappe

DESK_ROLES = {"System Manager"}

def get_website_user_home_page(user=None):
    user = user or frappe.session.user
    if user in ("Guest", "Administrator"):
        return None
    if set(frappe.get_roles(user)) & DESK_ROLES:
        return None
    return "web"
```

- [ ] **Step 3: hooks.py additions** (top-level, after `required_apps`):

```python
add_to_apps_screen = [
    {
        "name": "essdee_yrp",
        "logo": "/assets/essdee_yrp/frontend/favicon.png",
        "title": "Essdee YRP",
        "route": "/web",
    }
]

website_route_rules = [
    {"from_route": "/web/<path:app_path>", "to_route": "web"},
]

get_website_user_home_page = "essdee_yrp.www_home.get_website_user_home_page"
```

- [ ] **Step 4: Verify** — `bench --site essdee_yrp.site clear-cache`, then `node .claude/hooks/pw-shot.mjs --url /web` renders the SPA shell (still MGK-branded at this point) with no 404 on the entry JS. EXPECTED console noise: 404s from the still-mgk-namespaced `mgk_clothing_yrp.*` endpoint calls (that app isn't installed here) — those go away after Tasks 4-5; the gate here is only "entry JS + CSS load, Vue mounts".

### Task 3: Desk block for non-System-Manager users (NEW — mgk does not have this)

**Files:**
- Create: `apps/essdee_yrp/essdee_yrp/auth.py`
- Modify: `apps/essdee_yrp/essdee_yrp/hooks.py`

**Interfaces:**
- Produces: `essdee_yrp.auth.block_desk_for_non_managers` wired via `before_request`. Any authenticated user without System Manager/Administrator hitting `/app*` is redirected to `/web`.

- [ ] **Step 1: Create `auth.py`** — REVIEW-CORRECTED version. Frappe 16's Desk lives at **`/desk`** (`/app`/`/apps` are 301 aliases via frappe `website_redirects`), and `frappe.Redirect` raised from `before_request` does NOT redirect (it lands in `frappe.app.handle_exception`, which has no Redirect branch → error page). Use a werkzeug `HTTPException` carrying a real 302 (converted by `frappe/app.py:145` `e.get_response()`). Session/roles ARE initialized before `before_request` hooks (LoginManager runs at `frappe/app.py:205`), so `frappe.get_roles` is safe:

```python
"""Desk gate for the Essdee /web deployment.

Non-privileged users live in the /web SPA; the Frappe Desk is reserved for
Administrator + System Manager. Wired via `before_request` in hooks.py.

Frappe 16 serves the Desk at /desk; /app, /app/*, and /apps are 301 aliases
(frappe/hooks.py website_redirects), so all four roots are gated. `/` is also
redirected for gated users (the website home resolution would otherwise render
the SPA at URL "/" where the vue-router base /web doesn't match). Guests are
left alone (Frappe's own login redirect handles them). /api, /assets, /files,
/web and websockets are untouched so the SPA keeps working.

NOTE: this is a NAVIGATIONAL gate, not a security boundary — /api stays open
and role-based DocType permissions remain the real enforcement.
"""

import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect as _redirect

DESK_ROOTS = {"app", "apps", "desk"}


def block_desk_for_non_managers():
    request = getattr(frappe.local, "request", None)
    if request is None:
        return
    path = (request.path or "").strip("/ ")
    root = path.split("/", 1)[0]
    if root not in DESK_ROOTS and path != "":
        return
    user = getattr(frappe.session, "user", None)
    if not user or user in ("Guest", "Administrator"):
        return
    if "System Manager" in frappe.get_roles(user):
        return
    raise HTTPException(response=_redirect("/web", 302))
```

- [ ] **Step 2: hooks.py** — `before_request = ["essdee_yrp.auth.block_desk_for_non_managers"]`

- [ ] **Step 3: Gate the SPA's own Desk affordances** (HARD RULE 2026-05-29: a restricted /web user is NEVER sent to Desk):
  - `frontend/src/components/layout/AppSidebar.vue` foot "Desk" link (`href="/app"`, ~L54-69): wrap in `v-if="isAdmin || hasRole('System Manager')"` using `usePermissions()` (mgk shows it to everyone — this is one of the approved "do better" improvements).

- [ ] **Step 4: Verify server-side** (throwaway request-level check, not browser yet). Expectations per frappe's own redirects: admin `GET /app` → **301** (alias to /desk, NOT 200); admin `GET /desk` → 200; non-SM user `GET /desk` → **302 Location:/web** (asserted fully in Task 11 once the test user exists):

```bash
cd /home/anas/frappe-16 && python3 - <<'EOF'
import requests
s = requests.Session()
creds = open('/home/anas/.frappe-debug-creds-mrp3').read().split()
s.post('http://essdee_yrp.site:8003/api/method/login', data={'usr': creds[0], 'pwd': creds[1]})
for p in ('/app', '/desk'):
    r = s.get('http://essdee_yrp.site:8003' + p, allow_redirects=False)
    print('admin', p, '->', r.status_code, r.headers.get('Location'))
# expect: /app -> 301 /desk ; /desk -> 200 None
EOF
```

### Task 4: Port the generic server api modules + the two per-user-settings DocTypes

**Files:**
- Create: `apps/essdee_yrp/essdee_yrp/api/link_search.py`, `api/bulk_edit.py`, `api/child_table_view.py`, `api/sidebar_view.py`, `api/bom_mapping.py`, `api/item_attribute.py` (`api/__init__.py` + `api/work_order.py` already exist — do NOT touch work_order.py)
- Create: `apps/essdee_yrp/essdee_yrp/essdee_yrp/doctype/essdee_child_table_view_setting/{__init__.py,essdee_child_table_view_setting.json,essdee_child_table_view_setting.py}`
- Create: `apps/essdee_yrp/essdee_yrp/essdee_yrp/doctype/essdee_sidebar_setting/{__init__.py,essdee_sidebar_setting.json,essdee_sidebar_setting.py}`

**Interfaces:**
- Produces (whitelisted, exact dotted paths the frontend calls in Task 5):
  - `essdee_yrp.api.link_search.link_search`
  - `essdee_yrp.api.bulk_edit.get_bulk_edit_fields`, `essdee_yrp.api.bulk_edit.bulk_update_field`
  - `essdee_yrp.api.child_table_view.get_view`, `.save_view`
  - `essdee_yrp.api.sidebar_view.get_collapsed`, `.set_collapsed`
  - `essdee_yrp.api.bom_mapping.create_mapping`, `.configure_columns`
  - `essdee_yrp.api.item_attribute.update_mapping_values`

  **NOTE the namespace shape:** mgk's modules live at `<app>/<app>/api/` giving `mgk_clothing_yrp.mgk_clothing_yrp.api.*`; essdee's existing `api/` package lives ONE level up (`apps/essdee_yrp/essdee_yrp/api/`), giving **`essdee_yrp.api.*`** (see the existing `essdee_yrp.api.work_order.get_fabric_deliverable_context`). Follow the essdee convention — shorter, and consistent with the app's own precedent.

- [ ] **Step 1: Copy the 6 modules from mgk** and apply exactly these edits:
  - `child_table_view.py`: `SETTING_DOCTYPE = "Essdee Child Table View Setting"`; docstring re-titled.
  - `sidebar_view.py`: `SETTING_DOCTYPE = "Essdee Sidebar Setting"`; docstring re-titled.
  - `link_search.py`, `item_attribute.py`: verbatim (generic, meta-driven — permission posture stays: standard perms, NO ignore_permissions on the endpoint layer per lessons-learned 2026-05-30). Update only docstring app references.
  - `bulk_edit.py`: verbatim PLUS a review-mandated hardening — `get_bulk_edit_fields` must open with `frappe.has_permission(doctype, "read", throw=True)` (the mgk original leaks field metadata of arbitrary doctypes to any logged-in user).
  - `bom_mapping.py`: verbatim PLUS review-mandated hardening — in `create_mapping`, before the `frappe.db.set_value("Item BOM", bom_row, ...)` back-link, add `frappe.get_doc("Item Production Detail", ipd).check_permission("write")` and verify the `bom_row` actually belongs to that IPD's `item_bom` child table (the mgk original writes the back-link with no parent-perm/ownership check).

- [ ] **Step 2: Port the two DocTypes** — copy the mgk JSONs, rename (`name`, module → `Essdee YRP`), folder = `frappe.scrub(name)` (lessons 2026-05-16: folder MUST equal scrubbed DocType name):
  - `Essdee Child Table View Setting`: fields `user` (Link→User, reqd), `parent_doctype` (Data), `child_table` (Data), `visible_columns` (Long Text), `column_widths` (Long Text); controller autoname `sha1(f"{user}|{parent_doctype}|{child_table}")[:20]` — copy mgk controller, class renamed `EssdeeChildTableViewSetting`.
  - `Essdee Sidebar Setting`: `user` (Link→User, reqd, unique), `collapsed_sections` (Long Text); autoname `sha1(user)[:20]`, class `EssdeeSidebarSetting`.
  - Permissions in JSON: System Manager only (API layer scopes to session user with ignore_permissions, mirroring mgk).

- [ ] **Step 2b: Permissions for the 8 doctypes (REVIEW-CRITICAL — without this, IPD is invisible to every non-SM user).** Base-yrp DocPerms: Item Production Detail = System Manager ONLY; Work Order write/create/submit = Production Planner only; Terms and Condition read/create limited to Merch/PD/Purchase/Sales User. Base yrp must NOT be edited, so ship **Custom DocPerm** rows from essdee_yrp:
  - First inventory the site: `bench --site essdee_yrp.site console` → list non-SM users + their roles + existing Custom DocPerms for the 8 doctypes. Choose grant roles to match the deployment's real floor roles (expected: `Merchandiser`, `Item Master Manager`, `Production Planner` — mirror Lot's own permission roles).
  - Create Custom DocPerm rows granting: **Item Production Detail** → read/write/create to Merchandiser + Item Master Manager + Production Planner; **Terms and Condition** → read/write/create to Merchandiser + Production Planner (base grants stay).
  - Export via fixtures: add to hooks.py `fixtures` list: `{"dt": "Custom DocPerm", "filters": [["parent", "in", ["Item Production Detail", "Terms and Condition"]]]}` then `bench --site essdee_yrp.site export-fixtures --app essdee_yrp` (fixtures-not-patches per conventions 2026-07-02).
  - NOTE for Task 12 report: Lot's base perms give role "All" write (not create) — every authenticated user can edit Lots via /api regardless of the desk gate; pre-existing, surface it to the user.

- [ ] **Step 3: Migrate + import-check**

```bash
cd /home/anas/frappe-16 && bench --site essdee_yrp.site migrate
cd sites && ../env/bin/python -c "
import frappe
frappe.init(site='essdee_yrp.site'); frappe.connect()
for m in ['essdee_yrp.api.link_search.link_search','essdee_yrp.api.bulk_edit.get_bulk_edit_fields','essdee_yrp.api.child_table_view.get_view','essdee_yrp.api.sidebar_view.get_collapsed','essdee_yrp.api.bom_mapping.create_mapping','essdee_yrp.api.item_attribute.update_mapping_values']:
    frappe.get_attr(m); print('OK', m)
print(frappe.db.exists('DocType','Essdee Child Table View Setting'), frappe.db.exists('DocType','Essdee Sidebar Setting'))
"
```
Expected: 6× OK + both DocTypes exist.

### Task 5: Frontend re-namespace, registry rewrite, branding

**Files:**
- Modify: `frontend/src/api/client.js` (3 method strings), `frontend/src/composables/useChildTableColumns.js`, `useSidebarCollapse.js`, `useTheme.js`, `useListContext.js`, `frontend/src/views/dynamic/{IPDConfigView,BOMMappingEditor,ItemAttributeListView}.vue` (endpoint strings), `frontend/src/config/doctypes.js` (full rewrite), `frontend/src/components/layout/{AppSidebar,AppTopbar}.vue`, `frontend/src/views/AppLayout.vue` (PIN_KEY), `frontend/src/router/index.js` (log prefix + route pruning), `frontend/src/main.js`/`theme.js` (preset identifier rename optional — keep), `frontend/index.html`
- Create: `frontend/public/essdee-logo.png`, keep `favicon.png` (swap art if the user supplies one later; placeholder = copy mgk's for now is NOT acceptable branding-wise → generate a simple wordmark or reuse `~/essdee_logo.png` from the user's home dir, which exists)

**Interfaces:**
- Consumes: Task 4's `essdee_yrp.api.*` endpoints.
- Produces: `config/doctypes.js` exporting the same API (`DOCTYPES`, `SUBMITTABLE`, `WORKFLOW`, `WORKFLOW_SEVERITY`, `getRegistryByRoute`, `getRegistryByDoctype`, `getSidebarGroups`, `GENERIC_FIELDS`) with the 8-DocType registry. Route slugs: `lot`, `item`, `item-production-detail`, `work-order`, `delivery-challan`, `goods-received-note`, `terms-and-condition`, `stock-entry`.

- [ ] **Step 1: Endpoint re-namespace** (exact old → new):
  - client.js:289,297 `mgk_clothing_yrp.mgk_clothing_yrp.api.bulk_edit.*` → `essdee_yrp.api.bulk_edit.*`
  - client.js:404 `...api.link_search.link_search` → `essdee_yrp.api.link_search.link_search`
  - useChildTableColumns.js:43-44 → `essdee_yrp.api.child_table_view.get_view` / `.save_view`
  - useSidebarCollapse.js:24-25 → `essdee_yrp.api.sidebar_view.get_collapsed` / `.set_collapsed`
  - IPDConfigView.vue:1054 → `essdee_yrp.api.bom_mapping.create_mapping`; :1117 → `essdee_yrp.api.item_attribute.update_mapping_values`
  - BOMMappingEditor.vue:1028 → `essdee_yrp.api.bom_mapping.configure_columns`
  - ItemAttributeListView.vue:245 → `essdee_yrp.api.item_attribute.update_mapping_values`
  - Verify zero leftovers: `grep -rn "mgk_clothing_yrp" frontend/src/` → must return ONLY comments (clean those too) — target: 0 hits.

- [ ] **Step 2: Rewrite `config/doctypes.js` GROUPS** (keep every helper/export shape; replace the GROUPS array + SUBMITTABLE + WORKFLOW):

```js
const SUBMITTABLE = new Set([
	"Work Order",
	"Delivery Challan",
	"Goods Received Note",
	"Stock Entry",
])

// No workflow-managed doctypes among the essdee /web 8.
const WORKFLOW = {}
export const WORKFLOW_SEVERITY = {
	Approved: "success",
	Rejected: "danger",
	Expired: "danger",
	"Approval Pending": "warn",
	Draft: "warn",
}

const GROUPS = [
	{
		group: "Production",
		roles: "*",
		items: [
			{ doctype: "Lot", icon: "pi pi-inbox", tabMode: "status" },
			{ doctype: "Work Order", icon: "pi pi-bars", dateTabs: "wo_date", tabMode: "status" },
			{ doctype: "Delivery Challan", icon: "pi pi-send", dateTabs: "posting_date" },
			{ doctype: "Goods Received Note", icon: "pi pi-plus-circle", dateTabs: "posting_date" },
		],
	},
	{
		group: "Stock",
		roles: "*",
		items: [{ doctype: "Stock Entry", icon: "pi pi-sync", dateTabs: "posting_date" }],
	},
	{
		group: "Item Masters",
		roles: "*",
		items: [
			{ doctype: "Item", icon: "pi pi-box" },
			{ doctype: "Item Production Detail", icon: "pi pi-table" },
		],
	},
	{
		group: "Setup",
		roles: "*",
		items: [{ doctype: "Terms and Condition", icon: "pi pi-book" }],
	},
]
```
(Lot has a `status` Select Open/Closed and is non-submittable → per the finalized tab rules, status-option tabs + All. Work Order keeps `tabMode:"status"` — same rationale as mgk.)

- [ ] **Step 3: Branding + storage keys:**
  - AppSidebar.vue: logo alt/text → "Essdee YRP"; fallback logo path → `/assets/essdee_yrp/frontend/essdee-logo.png`; Desk link gating done in Task 3.
  - AppTopbar.vue ROUTE_TITLES: drop entries for removed routes (production-order); keep IPD/matrix/BOM titles.
  - AppLayout.vue: `PIN_KEY = "essdee.sidebar.pinned"`.
  - useTheme.js: `STORAGE_KEY = "essdee-theme"`.
  - useListContext.js: `STORE_KEY = "essdee:list-nav-ctx"`.
  - DocDetail.vue: `DUPLICATE_DRAFT_STORAGE_PREFIX` → `"essdee_yrp:duplicate_draft:"` (underscore — matches the mgk suffix shape exactly).
  - router/index.js:124 log prefix `[mgk]` → `[essdee]`; useChildTableColumns/useSidebarCollapse log prefixes likewise.
  - `cp /home/anas/essdee_logo.png frontend/public/essdee-logo.png` (user's own logo, exists at home dir).
  - www/web.py `_website_asset` fallbacks already point at `essdee-logo.png`/`favicon.png` (Task 2).

- [ ] **Step 4: Router pruning** (`router/index.js`): DELETE the `production-order/:id` route + its import. KEEP: home, the 3 IPD-flow routes (`item-production-detail/new`, `:id/fields`, `:id` → IPDConfigView), `ipd-process-matrix/:id`, `item-bom-attribute-mapping/:id`, generic `:docRoute/:id` + `:docRoute`. (IPD is in scope; its rich chain stays.)

- [ ] **Step 5: config/fields** — keep `item.js`, `item-production-detail.js`, `work-order.js`, `delivery-challan.js`, `goods-received-note.js`; DELETE `purchase-order.js`, `stock-reconciliation.js`, `inspection-entry.js`, `item-master-template.js` and their entries in `config/fields/index.js`. **`process-cost.js` is NOT deleted here** — it has no index.js entry; it is imported directly by `DocDetail.vue:1506` — its deletion happens in Task 6 together with that import (review finding I2). In `work-order.js` remove mgk_items-referencing comments/entries (keep the "Job-worker" supplier label + detailGroups — base-yrp fields, and KEEP its `searchAddressForParty`-based address handlers — base WO has supplier_address/delivery_address). In `item.js`/`item-production-detail.js` drop `is_yarn_item`/`yarn_item` references (mgk fields, absent on essdee).

- [ ] **Step 6: Build check** — `yarn build` exits 0. (The zero-`mgk_clothing_yrp` grep gate moves to the END of Task 7 — WorkOrderApproval/CalculateDeliverablesModal/DocDetail:3760/HomePage still reference mgk until Tasks 6-7 finish.)

### Task 6: DocDetail + list-page pruning (drop MGK-only features)

**Files:**
- Modify: `frontend/src/views/dynamic/DocDetail.vue`, `frontend/src/views/dynamic/DynamicListPage.vue`, `frontend/src/api/client.js`
- Delete: `frontend/src/views/dynamic/{WorkOrderApproval,CalculateDeliverablesModal,AssignDepartmentModal,PurchaseInvoiceWOClose,InspectionEntryEditor,ProductionOrderView,WorkflowActions,AddressContactTab}.vue`, `frontend/src/components/{DocTree,DocTreeNode}.vue`

**Interfaces:**
- Consumes: registry from Task 5 (none of the 8 are trees, workflows, or parties).
- Produces: DocDetail whose per-doctype surface = STOCK_GROUPED_MAP (Stock Entry, DC, GRN, WO deliverables+receivables) + GRNReceivedTypeEditor + Item attribute/dependent editors + IPD launch points + connections (WO→DC, WO→GRN, DC→GRN). Later tasks (8, 9) re-add essdee-specific blocks.

- [ ] **Step 1: DocDetail.vue removals** (each = import line + template usage + computed flag + handlers):
  - `mgkItemsTable` grid: template ~637-795, computeds ~2750-2794, `onMgkItemLinkComplete` ~3368-3394, validation branch ~3467-3473, `"mgk_items"` in childTables PRIORITY ~4210 → PRIORITY becomes `["deliverables", "receivables"]`, `woCommentsField` re-anchor: keep the comments-at-bottom block but anchor below the receivables pivot (mgk anchored below mgk_items).
  - `WorkOrderApproval` (import 1510, usage ~369-377, gate banner ~1083-1086, Approval Log tab ~1239-1268, side card ~1345-1381, `approvalLog`/`approvalState` ~4296-4302/4524-4531) and `mgk_approval_log` in `CHILD_TABLE_EXCLUDE` (~1841) — keep `work_order_tracking_logs`/`work_order_track_pieces` excludes (base-yrp fields).
  - `CalculateDeliverablesModal` (import 1513, button ~121-129, dialog ~389-397, `onCalculateDeliverables`/`onDeliverablesCalculated`/`get_yarn_deliverable_rows` ~3750-3793). Replaced in Task 8 by the fabric modal.
  - `PurchaseInvoiceWOClose`, `AssignDepartmentModal`, `InspectionEntryEditor` + `isInspectionEntry`/`isPurchaseInvoice`/`isBillTracking`/`isItemMasterTemplate` branches, Inspection/Stock-Update/Stock-Reconciliation/Purchase-Order entries in STOCK_GROUPED_MAP (~1868-1929 keep ONLY Stock Entry, Delivery Challan, Goods Received Note, Work Order), forward actions "Create Debit"/"Convert Stock" **AND `grn-ie` "Create Inspection Entry" (~1688-1689, handler `onCreateInspectionFromGrn` ~3863) AND the dead `po-grn` action (~1686-1687, handler `onCreateGrnFromPo` ~3830)** (review finding I3 — grn-ie would ship a broken button on every submitted GRN), `CONNECTIONS_MAP` GRN→Inspection Entry entry (~2011) and the whole Purchase Order connections entry.
  - `config/fields/process-cost.js`: DELETE the file + the `DocDetail.vue:1506` direct import + its entry in `CHILD_COLUMN_RULE_CONFIGS` (~2906).
  - `navigateDoc` fallback (~4473-4479): the else-branch `window.open('/app/<slug>/<name>')` fires constantly with only 8 registered doctypes (supplier, process_name, production_order, uom links…). Replace: if `isAdmin || hasRole('System Manager')` keep the Desk fallback, else show a toast ("Only available in Desk — ask an administrator") and do nothing (HARD RULE 2026-05-29: restricted /web users are never sent to Desk).
  - `WorkflowActions` + `isWorkflow` render branch (~92) — registry has `WORKFLOW = {}` so the branch is dead; remove import+usage.
  - `AddressContactTab` + `hasAddressContact` tab (~1284).
- [ ] **Step 2: DynamicListPage.vue removals:** Bill Tracking blocks (lines ~47-56, 187-196, 338-385, 574, 613-638, 820-822, 1649-1759: `isBillTracking`, Show-Assigned-To-Me, Bulk Assign + its two yrp endpoint calls), tree-view blocks (~37-45, 317-322) + `DocTree` import.
- [ ] **Step 3: client.js cleanup:** remove `getTreeChildren` (L282) and any now-unused helpers flagged by the build. **KEEP `searchAddressForParty`** (client.js:419) — the KEPT `config/fields/work-order.js:19,136,140` uses it for the WO supplier_address/delivery_address party-scoped search (review finding I1). Delete only `getAddressList` (L440) + `getContactList` (L463) — used solely by the deleted AddressContactTab.
- [ ] **Step 4:** `yarn build` — exits 0 with no unused-import warnings for the deleted files; `grep -rn "mgk_items\|mgk_approval_log\|Bill Tracking\|Inspection Entry\|MGK Agent" frontend/src/` → 0 hits.

### Task 7: Home page rewrite

**Files:**
- Modify: `frontend/src/views/home/HomePage.vue`, `frontend/src/composables/useHomeQueues.js`

**Interfaces:**
- Consumes: registry (Task 5), `getCount` (client.js), `canRead`/`canCreate`.
- Produces: 4 queue cards + quick-create + recents scoped to the 8 DocTypes.

- [ ] **Step 1: HomePage.vue** — `QUICK_CREATE = ["Lot", "Work Order", "Delivery Challan"]`; `RECENT = ["Work Order", "Delivery Challan", "Goods Received Note", "Stock Entry"]` (submittable-only constraint of the recents table holds).
- [ ] **Step 2: useHomeQueues.js** — replace the 4 mgk queues with:

```js
const QUEUES = [
	{ key: "open-lots", label: "Open Lots", doctype: "Lot",
	  filters: [["status", "=", "Open"]], icon: "pi pi-inbox" },
	{ key: "open-work-orders", label: "Open Work Orders", doctype: "Work Order",
	  filters: [["docstatus", "=", 1], ["status", "not in", ["Closed", "Cancelled"]]], icon: "pi pi-bars" },
	{ key: "draft-dcs", label: "Draft Delivery Challans", doctype: "Delivery Challan",
	  filters: [["docstatus", "=", 0]], icon: "pi pi-send" },
	{ key: "draft-grns", label: "Draft GRNs", doctype: "Goods Received Note",
	  filters: [["docstatus", "=", 0]], icon: "pi pi-plus-circle" },
]
```
Delete the `MGK Settings` loader (`loadApprovalProcesses`, useHomeQueues.js:112-123) and the `design-approvals` queue plumbing. Keep the per-queue `canRead` gate, parallel `getCount`, deep-link click-through exactly as-is.
- [ ] **Step 3:** `yarn build` exits 0. pw-shot `/web/home`: 4 cards render with live counts (Administrator sees all).
- [ ] **Step 4 (moved gate from Task 5):** `grep -rn "mgk_clothing_yrp" frontend/src/` → 0 hits; `grep -rn "MGK" frontend/src/ | grep -v '\-\-mgk\|\.mgk'` → 0 functional hits.

### Task 8: Work Order fabric-deliverables modal (essdee flow replacing mgk's yarn modal)

**Files:**
- Create: `frontend/src/views/dynamic/FabricDeliverablesModal.vue`
- Modify: `frontend/src/views/dynamic/DocDetail.vue` (button + dialog + reload hook, where CalculateDeliverablesModal sat)

**Interfaces:**
- Consumes (existing essdee endpoints — read `apps/essdee_yrp/essdee_yrp/api/work_order.py` + Desk dialog in `apps/essdee_yrp/essdee_yrp/public/js/work_order.js` and mirror the Desk contract exactly):
  - `essdee_yrp.api.work_order.get_fabric_deliverable_context(work_order)` → `{rows: [...], ...}` context for the popup (per-fabric-process rows from the WO's Lot's `lot_fabric_details` + fabric IPD tabs)
  - `essdee_yrp.api.work_order.calculate_fabric_deliverables(work_order, rows)` → writes WO deliverables/receivables (v1: receivable = deliverable, user enters deliverable kgs)
- Produces: "Calculate Deliverables" button on a WO whose process is a fabric process; on apply → toast + `reloadView()` so the deliverables/receivables pivots re-hydrate.

- [ ] **Step 1:** Read the two reference files; mirror the Desk dialog's field set (per-row fabric item + user-entered deliverable qty/weight) in a PrimeVue Dialog. The modal fetches context on open, renders rows (LinkField for items read-only, InputNumber for qty), Apply calls `calculate_fabric_deliverables`, emits `applied`.
- [ ] **Step 2:** DocDetail wiring — show the button in view mode for Work Order, `docstatus === 0` (deliverables are calculated pre-submit; confirm the exact Desk gating from `work_order.js` while implementing and match it), gated `canWrite("Work Order")`. On `applied` → `reloadView()`.
- [ ] **Step 3:** Verify: `yarn build`; on a real WO for a fabric-process Lot (site data has synced lots), open the modal via CDP/pw-shot `--eval`, confirm context rows render. Full E2E with a save lands in Task 11.

### Task 9: Lot support (net-new — the only doctype with no mgk code)

**Files:**
- Create: `frontend/src/views/dynamic/LotOrderEditor.vue` (mirror of yrp Desk `Lot/components/LotOrder.vue`), `frontend/src/views/dynamic/LotOrderDetailGrid.vue` (mirror of `CuttingPlan/components/CutPlanItems.vue`)
- Create: `frontend/src/config/fields/lot.js`; Modify: `frontend/src/config/fields/index.js`
- Modify: `frontend/src/views/dynamic/DocDetail.vue` (Lot blocks: editors, payload, field-change chains, BOM tab)

**Interfaces:**
- Consumes (all EXISTING whitelisted methods on `essdee_yrp.essdee_yrp.doctype.lot.lot`):
  - `get_item_details(item_name, production_detail=..., uom=..., dependent_attr_mapping=..., ppo=...)` → item-structure `{item, primary_attribute, primary_attribute_values, default_uom, items:[{attributes:{...}, values:{<size>:{qty,ratio,mrp}}}]}` for the items editor
  - `fetch_order_item_details(items, production_detail, ...)` → grouped matrix for the order-details grid
  - `get_isfinal_uom(item_production_detail, get_pack_stage=true)` → `{uom, pack_in_stage, pack_out_stage, packing_uom, dependent_attribute_mapping, tech_pack_version, pattern_version, packing_combo}`
  - `get_packing_attributes(ipd)` → `size_set_colour` options
  - `check_enabled_po()` → gates whether `item`/`production_order` are user-editable
  - `update_order_details(doc_name)` → the "Calculate Order Items" action
  - `yrp.yrp.doctype.item_production_detail.item_production_detail.get_calculated_bom(item_production_detail, items, lot_name)` → BOM rows for `bom_summary`
- Produces: Lot create/edit/view inside the generic DocDetail (same shell, tabs, dirty-tracking as every other doctype).
- **Save contract (REVIEW-CORRECTED — the stock-pivot "empty children + grouped JSON" pattern does NOT transfer to Lot):** the Desk contract (lot.js:176-187) sends the **full loaded child rows** PLUS the two JSON strings on top; `save_order_item_details` (lot.py:248-288) rebuilds `qty_dict` from the incoming doc's `lot_order_details` rows with hard `qty_dict[key]['cut_qty']` lookups — blanking that table crashes the save (KeyError) or wipes cut/stich/pack progress on the ~1767 synced lots. Therefore:
  - NEVER blank `items` or `lot_order_details` in the payload — send the loaded/edited rows verbatim (buildPayload's default copy of `form` already does this; just don't add them to any exclusion list).
  - Add `payload.item_details = JSON.stringify(lotItemsEditor.getItems())` ONLY when the items editor actually hydrated; when skipping, OMIT the key entirely — never send `"[]"` (`self.get('item_details')` is truthy for the string `"[]"` → `save_item_details("[]")` wipes items AND `before_save` then deletes the linked Production Ordered Detail rows).
  - Same for `payload.order_item_details` — only when the order grid hydrated, else omit.
  - `getItems()` on LotOrderEditor returns the ARRAY-WRAPPED structure `[itemStructure]` (server does `item_details[0]`, lot.py:294; mirror `yrp/public/js/Lot/index.js:26-27` `get_data`). `loadData()` accepts the BARE dict (what `__onload.item_details`/`get_item_details` return) and wraps it — mirror `LotOrder.vue::load_data`.
  - The controller's `before_validate` rebuilds children + runs `calculate_order()` server-side — NEVER compute the explosion client-side.

- [ ] **Step 1: `config/fields/lot.js`** — hide the Desk-only HTML/transient fields from the generic form/detail (they're replaced by the custom editors):

```js
export default {
	hideFormFields: [
		"items_html", "lot_item_order_detail_html", "ocr_detail_html", "alternative_html",
		"lot_order_details_json", "bom_summary_json", "size_set_colour_colour",
	],
	labels: { production_detail: "Item Production Detail" },
}
```
(match the exact config-module shape of `config/fields/item.js` — read it first; extend keys only if that shape differs.)

- [ ] **Step 2: `LotOrderEditor.vue`** — public surface identical to StockItemGridEditor so DocDetail composes it the same way: props `{ initialData, readonly }`, emits `['change']`, exposes `loadData(itemStructure)`, `getItems()`, `hasItems()`. Renders: dependent-attribute value pickers (LinkField → `Item Attribute Value` filtered via the item-structure), per-size Qty/Ratio/MRP inputs (per-cell, PrimeVue InputNumber), add/edit/delete rows — mirroring LotOrder.vue's grid + add-form behavior. `watch(() => props.initialData, v => v != null && loadData(v))` (lessons 2026-06-01: reactive prop hydration).
- [ ] **Step 3: `LotOrderDetailGrid.vue`** — props/emits/expose same shape; renders the size×row matrix from `fetch_order_item_details` output; qty cells editable in edit mode (docstatus is always 0 for Lot), cut/stich/pack columns read-only.
- [ ] **Step 4: DocDetail Lot integration:**
  - Add `const isLot = computed(() => doctype.value === "Lot")`.
  - Exclude `items`, `lot_order_details`, `planned_qty`, `bom_summary`, `bom_additional_items`, `lot_fabric_details` handled specially: `lot_fabric_details` STAYS a generic editable child table (3 Link columns; plain grid is correct per the Desk); `planned_qty` hidden (meta-hidden already); `items`/`lot_order_details` excluded from generic tables (add to a LOT_CHILD_EXCLUDE list merged into the existing exclusion logic) and rendered by the two custom editors in both view + edit modes (view = readonly prop).
  - Hydration: on load (view or edit), call `get_item_details(form.item, {production_detail, uom, dependent_attr_mapping, ppo: form.production_order})` → `lotItemsEditor.loadData(...)`; call `fetch_order_item_details(doc.lot_order_details ? onload cache : [], form.production_detail)` — PREFER the doc's `__onload.order_item_details`/`item_details` (Lot.onload already builds both; use `getDocWithOnload`) and only fall back to the whitelisted calls when absent (create mode).
  - Field-change chains in `runDocAutofill`: `production_order` change → `frappe.client.get_value("Production Order", v, "item")` → set `form.item`; `production_detail` change → `get_isfinal_uom(v, get_pack_stage=1)` → returns up to **8 keys and the key is `dependent_attr_mapping`** (NOT `dependent_attribute_mapping`); when the IPD has no dependent-attribute mapping it returns ONLY `{uom}` — mirror lot.js:195-216's else-branch and CLEAR the other header fields in that case; then re-call `get_item_details` → reload items editor; `check_enabled_po()` on create-mode boot → if disabled, `production_order` hidden + `item` editable, else `item` read-only.
  - `buildPayload`: when `isLot`, per the REVIEW-CORRECTED save contract above — children stay in the payload untouched; `item_details`/`order_item_details` added only when their editor hydrated, omitted (not `"[]"`) otherwise.
  - BOM tab: add a "Bill of Materials" view tab for Lot rendering `doc.bom_summary` rows (read-only DataTable: item_name, process_name, uom, required_qty) + a "Calculate BOM" button (gated `canWrite("Lot")`, blocked while `isDirty`) → calls `get_calculated_bom(form.production_detail, doc.lot_order_details, doc.name)` then `reloadView()` — mirror lot.js:245's contract exactly (read it while implementing; persist server-side the way the Desk button does).
  - Header actions: Lot is non-submittable — Submit/Cancel/Amend never render (registry drives this); "Calculate Order Items" as a secondary action in view mode → `update_order_details(doc.name)` + `reloadView()`.
- [ ] **Step 5: Verify (browser, real drive):** `yarn build`; create a NEW throwaway Lot end-to-end in /web (pick production_detail from synced data → items editor loads → enter qty/ratio → Save → re-open → entries persisted; server re-fetch shows `items` + `lot_order_details` rebuilt). Delete the throwaway Lot after. Verify an EXISTING synced Lot opens read-only-correct (items editor shows its entries from onload, totals match Desk).

### Task 10: Full build + migrate + smoke pass

- [ ] `cd apps/essdee_yrp/frontend && yarn build` (exit 0)
- [ ] `bench --site essdee_yrp.site migrate` (Task 4 doctypes already migrated; re-run idempotent)
- [ ] `bench --site essdee_yrp.site clear-cache`
- [ ] pw-shot every route: `/web/home`, `/web/lot`, `/web/item`, `/web/item-production-detail`, `/web/work-order`, `/web/delivery-challan`, `/web/goods-received-note`, `/web/terms-and-condition`, `/web/stock-entry` — no console errors, list rows render from real site data.
- [ ] Sidebar shows exactly 4 groups / 8 items (as Administrator).

### Task 11: E2E acceptance — active driving (the gate)

**Setup:** create test user `webuser@essdee.fit` (roles: **Production Planner, Merchandiser, Merch User, Item Master Manager, Stock User, Stock Manager** — Production Planner is required for WO write/submit, Merch User for T&C create; "Merchandiser" ≠ "Merch User", both needed; NOT System Manager) with a known password via bench console. Verify none of these Roles has `home_page` set and Portal Settings default homepage is empty (both pre-empt the `get_website_user_home_page` hook); `bench --site essdee_yrp.site clear-cache` after any role change (home page is cached per user). Keep the user; note it in the final report.

Drive with Playwright (`~/.claude/playwright` install) — real fills/clicks + DOM reads, screenshots as evidence (memory: UI testing = active driving):

- [ ] **Login redirect:** log in via `/login` as webuser → landing URL IS `/web` (assert `location.pathname`). Log in as Administrator → lands on Desk (no redirect).
- [ ] **Desk block:** as webuser navigate to `/app`, `/app/item`, **`/desk`, `/apps`, and `/`** → all end at `/web` (assert final URL). As Administrator → `/desk` loads (and `/app` 301s to it). API sanity: webuser `GET /api/method/frappe.auth.get_logged_user` still works (desk block must not break /api).
- [ ] **Sidebar/permissions:** webuser sees only doctypes they canRead; no "Desk" link, no "Open in Desk" buttons anywhere (grep DOM).
- [ ] **List views (all 8):** rows render; tab strips per contract (WO status tabs; DC/GRN/SE docstatus tabs; Lot Open/Closed+All; Item/IPD/T&C All); search narrows; a filter via FilterPanel narrows (include one child-table filter on WO deliverables → row count stays deduped); pagination works.
- [ ] **User-based list view:** customize columns on Item (add/remove/reorder) → persists across reload AND is user-scoped (Administrator unaffected).
- [ ] **User-based child-table view:** on a WO child table, change visible columns + a column width → persists across reload (row in `Essdee Child Table View Setting` for webuser exists — verify via console).
- [ ] **Prev/next arrows:** from Item list click row 3 → arrows navigate to rows 2/4 respecting list order; boundary disables; Shift+Ctrl+arrow shortcut works.
- [ ] **Doc views:** open one real doc of each of the 8 — Details tab cards render, pivots show grouped item view (DC/GRN/SE/WO), IPD opens IPDConfigView with attribute cards + BOM + processes.
- [ ] **Write path:** create + save a Stock Entry via the grid editor (throwaway, then delete); Lot create flow (Task 9 Step 5 re-run as webuser); fabric-deliverables modal on a fabric WO (context loads; if a safe WO exists, apply + verify deliverables/receivables pivots populate; else document "context verified, apply deferred").
- [ ] **Terms and Condition:** create with 2 detail rows + `is_default_wo_term` checked → save → verify single-default enforcement (check another record's flag cleared).
- [ ] **Realtime:** open a WO in two tabs (admin + webuser), admin edits+saves → webuser's tab shows the stale-doc notice; webuser's stale save is rejected (conflict banner, not silent clobber).
- [ ] **Theme:** toggle dark mode → `getComputedStyle` assert list row background is dark (measure, don't eyeball — lessons 2026-06-19).
- [ ] Each check: screenshot + literal DOM assertion logged to `apps/essdee_yrp/docs/design/2026-07-03-web-ui-e2e-results.md`.

### Task 12: Final whole-branch review (mandatory — >50-line change)

- [ ] Dispatch ONE fresh code-review agent (`superpowers:requesting-code-review` flow) over the full `apps/essdee_yrp` diff (`git -C apps/essdee_yrp status/diff` — note pre-existing uncommitted develop changes are OUT of scope; review only files this task created/modified — list them explicitly for the reviewer).
- [ ] Fix Critical/Important findings; re-run affected verification.
- [ ] Report to user: what shipped, E2E evidence, NOT-verified list (if any), that nothing is committed (user commits), PLUS two standing notes: (a) the desk gate is navigational, not a security boundary — /api stays open and DocType permissions are the real enforcement; (b) Lot's base perms grant role "All" write via /api (pre-existing).

## Explicit scope boundaries (agreed defaults, flag-don't-build)

- **IPD custom-tab rich editors** (essdee's 95 IPD custom fields — packing/stiching/cutting JSON-blob Desk islands): NOT ported to /web in v1. The /web IPD surface = mgk-parity (IPDConfigView chain + generic `/fields` form where the essdee custom Table fields are editable generically and JSON fields hidden). Porting the Desk islands is a follow-up feature.
- **OCR Detail / Alternative Detail** Lot tabs: not ported (hidden tabs, niche); Lot v1 = items + order details + fabric details + BOM.
- **Purchase Order, Production Order, Inspection Entry, etc.:** not in the registry; their base-yrp endpoints remain but no UI.
- **No commits** — working tree handed to the user.
