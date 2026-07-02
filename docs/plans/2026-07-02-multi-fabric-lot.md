# Multi-Fabric Lot + Fabric-Process Work Orders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Lot declares 1..N fabrics (`yarn_item` + `cloth_item` + cloth IPD); cloth IPDs carry Knitting/Dyeing/Compacting config tabs that auto-generate IPD Process Matrix records; fabric-process Work Orders get a Calculate popup where the user enters deliverable weights and receivables are computed 1:1.

**Architecture:** Everything in `essdee_yrp` (base `yrp` untouched). Custom Fields via fixtures. New child doctypes for the Lot fabric table and the three IPD tabs. One server module for matrix generation (hooked on IPD `on_update`), one API module for the WO popup/calc, one doctype_js for the popup UI (modeled on `mgk_clothing_yrp/public/js/work_order_mgk.js` UX + `yrp_essdee/api/work_order.py` server shape).

**Tech Stack:** Frappe v16, Python (bench console verification), vanilla `frappe.ui.Dialog` JS (no Vue needed for the popup).

**Spec:** `apps/essdee_yrp/docs/multi_fabric_lot_design_2026-07-02.md` (user-approved). Read it before starting any task.

## Global Constraints

- Bench `/home/anas/frappe-16`, app repo `/home/anas/frappe-16/apps/essdee_yrp` (branch `develop`), site `essdee_yrp.site` (port 8003).
- **NEVER touch `apps/frappe`, `apps/erpnext`, `apps/yrp`.** All work in `essdee_yrp`.
- **Custom Fields deploy via FIXTURES ONLY**: create on the site via `bench console` `create_custom_fields(...)` → `bench --site essdee_yrp.site export-fixtures --app essdee_yrp` → the field must appear in `essdee_yrp/fixtures/custom_field.json`. NO `create_custom_fields` patch files.
- **NO `git commit` at any step.** Work stays uncommitted; the owner authorizes commits explicitly at the end. (Standing bench rule 2026-06-17.)
- **NO `frappe.db.commit()` inside any test/verification code you write into files.** (Console one-liners that end with commit for setup data are OK.)
- **v1 quantity math is strictly 1:1** (deliverable weight == receivable qty). No wastage/excess percentages anywhere.
- **Cloth items have NO dependent attribute.** Never add `in_stage`/`out_stage`, dependent-attribute mappings, or stage validation for cloth.
- Site facts (verified): Item Attributes `Dia` and `Colour` exist; Process records `Knitting`, `Dyeing`, `Compacting` exist; `Item Attribute Value` schema = `{attribute_name: Link→Item Attribute, attribute_value: Data}`, autoname `field:attribute_value`; WO header already has `lot` (stock-dimension engine — do NOT create one).
- Validation per `docs/claude/validation.md`: `python -m py_compile` after every Python edit; `bench --site essdee_yrp.site migrate` after schema changes; UI verification via `node .claude/hooks/pw-shot.mjs --url <route> --site http://essdee_yrp.site:8003`.
- **Testing approach (bench convention overrides generic TDD):** each server task carries a runnable *verification script* (bench console) with expected output, run once before implementation (expect failure/absence) and once after (expect pass). Final task is a UI-driven end-to-end (active driving: fill/click/read DOM, screenshots as evidence).
- After editing `hooks.py` or any Python consumed by the web tier: `bench --site essdee_yrp.site clear-cache`. The web server auto-reloads; workers are irrelevant here (no background jobs in this feature).

---

### Task 1: `Item.is_cloth_item` Custom Field

**Files:**
- Modify: `essdee_yrp/hooks.py` (fixtures or_filters name list)
- Generated: `essdee_yrp/fixtures/custom_field.json`

**Interfaces:**
- Produces: `Item.is_cloth_item` (Check) — read by Task 2 (lot.js query), Task 3 (IPD fetch + depends_on), Task 4 (`is_cloth_ipd()`).

- [ ] **Step 1: Verify absence (fail-first)**

Run:
```bash
cd /home/anas/frappe-16 && bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a CHECK
import frappe
print("CHECK:", frappe.db.exists("Custom Field", "Item-is_cloth_item"))
EOF
```
Expected: `CHECK: None`

- [ ] **Step 2: Create the field on the site**

```bash
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a CHECK
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
create_custom_fields({"Item": [{
    "fieldname": "is_cloth_item",
    "fieldtype": "Check",
    "label": "Is Cloth Item",
    "default": "0",
    "insert_after": "product_category",
}]})
frappe.db.commit()
print("CHECK:", frappe.db.exists("Custom Field", "Item-is_cloth_item"))
EOF
```
Expected: `CHECK: Item-is_cloth_item`
(`product_category` is an existing essdee_yrp Custom Field on Item — safe anchor.)

- [ ] **Step 3: Add to fixtures filter**

In `essdee_yrp/hooks.py`, extend the `or_filters` `name in [...]` list:

```python
				[
					"Item-product_category",
					"Item-is_cloth_item",
					"Supplier-apply_sewing_plan",
					"Process-additional_allowance",
					"Process-includes_packing",
					"Process-item",
				],
```

- [ ] **Step 4: Export fixtures + verify**

```bash
bench --site essdee_yrp.site export-fixtures --app essdee_yrp
python3 -c "
import json
j = json.load(open('/home/anas/frappe-16/apps/essdee_yrp/essdee_yrp/fixtures/custom_field.json'))
print('in fixtures:', any(c['name']=='Item-is_cloth_item' for c in j))
"
```
Expected: `in fixtures: True`

---

### Task 2: `Lot Fabric Detail` child doctype + Lot table field

**Files:**
- Create: `essdee_yrp/essdee_yrp/doctype/lot_fabric_detail/__init__.py`
- Create: `essdee_yrp/essdee_yrp/doctype/lot_fabric_detail/lot_fabric_detail.json`
- Create: `essdee_yrp/essdee_yrp/doctype/lot_fabric_detail/lot_fabric_detail.py`
- Modify: `essdee_yrp/essdee_yrp/doctype/lot/lot.json` (new section + Table field)
- Modify: `essdee_yrp/essdee_yrp/doctype/lot/lot.js` (child-row queries)

**Interfaces:**
- Consumes: `Item.is_cloth_item` (Task 1).
- Produces: `Lot.lot_fabric_details` — rows `{yarn_item: Link Item, cloth_item: Link Item, production_detail: Link Item Production Detail}`. Read by Task 5 (`get_fabric_deliverable_context`).

- [ ] **Step 1: Create the child doctype files**

`lot_fabric_detail.json`:
```json
{
 "actions": [],
 "creation": "2026-07-02 12:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": ["yarn_item", "cloth_item", "production_detail"],
 "fields": [
  {"fieldname": "yarn_item", "fieldtype": "Link", "in_list_view": 1, "label": "Yarn Item", "options": "Item", "reqd": 1},
  {"fieldname": "cloth_item", "fieldtype": "Link", "in_list_view": 1, "label": "Cloth Item", "options": "Item", "reqd": 1},
  {"fieldname": "production_detail", "fieldtype": "Link", "in_list_view": 1, "label": "Item Production Detail", "options": "Item Production Detail"}
 ],
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-07-02 12:00:00.000000",
 "modified_by": "Administrator",
 "module": "Essdee YRP",
 "name": "Lot Fabric Detail",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

`lot_fabric_detail.py`:
```python
# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LotFabricDetail(Document):
	pass
```

`__init__.py`: empty file.

- [ ] **Step 2: Add the section + table to `lot.json`**

In `field_order`, insert BEFORE `"section_break_ry89l"`:
```json
"fabric_details_section", "lot_fabric_details",
```
In `fields`, add (anywhere; order comes from field_order):
```json
  {"fieldname": "fabric_details_section", "fieldtype": "Section Break", "label": "Fabric Details"},
  {"fieldname": "lot_fabric_details", "fieldtype": "Table", "label": "Fabric Details", "options": "Lot Fabric Detail"}
```

- [ ] **Step 3: Add child-row queries to `lot.js`**

Inside the existing `setup(frm)` handler (which already sets `production_detail`/`production_order` queries), append:

```javascript
		frm.set_query("cloth_item", "lot_fabric_details", function () {
			return { filters: { is_cloth_item: 1 } };
		});
		frm.set_query("production_detail", "lot_fabric_details", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return { filters: { item: row.cloth_item || "" } };
		});
```

- [ ] **Step 4: Migrate + verify schema**

```bash
python3 -m py_compile apps/essdee_yrp/essdee_yrp/essdee_yrp/doctype/lot_fabric_detail/lot_fabric_detail.py
bench --site essdee_yrp.site migrate 2>&1 | tail -3
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a CHECK
import frappe
print("CHECK cols:", frappe.db.get_table_columns("Lot Fabric Detail"))
print("CHECK lotfield:", bool(frappe.get_meta("Lot").get_field("lot_fabric_details")))
EOF
```
Expected: columns include `yarn_item`, `cloth_item`, `production_detail`; `CHECK lotfield: True`

- [ ] **Step 5: UI check**

```bash
bench --site essdee_yrp.site clear-cache
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a LOT
import frappe
print("LOT:", frappe.get_all("Lot", limit_page_length=1, pluck="name"))
EOF
node .claude/hooks/pw-shot.mjs --url "/app/lot/<that lot name>" --site http://essdee_yrp.site:8003 --wait 4000 --full
```
Expected: the Lot form renders a "Fabric Details" section with the empty grid; no console errors. View the PNG to confirm.

---

### Task 3: IPD cloth-mode — child doctypes, tab Custom Fields, garment-tab hiding, validation gating, JS queries

**Files:**
- Create: `essdee_yrp/essdee_yrp/doctype/ipd_knitting_dia_detail/{__init__.py,ipd_knitting_dia_detail.json,ipd_knitting_dia_detail.py}`
- Create: `essdee_yrp/essdee_yrp/doctype/ipd_dyeing_colour_detail/{__init__.py,ipd_dyeing_colour_detail.json,ipd_dyeing_colour_detail.py}`
- Create: `essdee_yrp/essdee_yrp/doctype/ipd_compacting_dia_detail/{__init__.py,ipd_compacting_dia_detail.json,ipd_compacting_dia_detail.py}`
- Modify: `essdee_yrp/ipd_validations.py` (cloth-IPD gating)
- Modify: `essdee_yrp/public/js/item_production_detail.js` (queries)
- Generated: `essdee_yrp/fixtures/custom_field.json` (IPD tab fields)

**Interfaces:**
- Consumes: `Item.is_cloth_item` (Task 1).
- Produces (read by Tasks 4–6):
  - IPD fields: `is_cloth_item` (hidden Check, fetched), `knitting_process`/`dyeing_process`/`compacting_process` (Link → Process), `knitting_dia_details` (Table → IPD Knitting Dia Detail: `dia`), `dyeing_colour_details` (Table → IPD Dyeing Colour Detail: `from_colour`, `to_colour`), `compacting_dia_details` (Table → IPD Compacting Dia Detail: `from_dia`, `to_dia`). All Link values are `Item Attribute Value` names.
  - `essdee_yrp.ipd_validations.is_cloth_ipd(doc) -> bool`.

- [ ] **Step 1: Create the three child doctypes** (same JSON shape as Task 2 Step 1; module `Essdee YRP`, `istable: 1`):

- `IPD Knitting Dia Detail` — field_order `["dia"]`; fields: `{"fieldname": "dia", "fieldtype": "Link", "in_list_view": 1, "label": "Dia", "options": "Item Attribute Value", "reqd": 1}`
- `IPD Dyeing Colour Detail` — field_order `["from_colour", "to_colour"]`; both `{"fieldtype": "Link", "in_list_view": 1, "options": "Item Attribute Value", "reqd": 1}` with labels "From Colour" / "To Colour"
- `IPD Compacting Dia Detail` — field_order `["from_dia", "to_dia"]`; same shape, labels "From Dia" / "To Dia"

Each `.py` mirrors Task 2's controller (class names `IPDKnittingDiaDetail`, `IPDDyeingColourDetail`, `IPDCompactingDiaDetail`).

- [ ] **Step 2: Migrate, then create the IPD Custom Fields on the site**

```bash
bench --site essdee_yrp.site migrate 2>&1 | tail -3
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a CHECK
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
last_field = frappe.get_meta("Item Production Detail").fields[-1].fieldname
print("CHECK anchor:", last_field)
create_custom_fields({"Item Production Detail": [
  {"fieldname": "is_cloth_item", "fieldtype": "Check", "label": "Is Cloth Item",
   "fetch_from": "item.is_cloth_item", "read_only": 1, "hidden": 1, "insert_after": "item"},
  {"fieldname": "fabric_knitting_tab", "fieldtype": "Tab Break", "label": "Knitting",
   "depends_on": "eval:doc.is_cloth_item", "insert_after": last_field},
  {"fieldname": "knitting_process", "fieldtype": "Link", "label": "Knitting Process",
   "options": "Process", "insert_after": "fabric_knitting_tab"},
  {"fieldname": "knitting_dia_details", "fieldtype": "Table", "label": "Dia Details",
   "options": "IPD Knitting Dia Detail", "insert_after": "knitting_process"},
  {"fieldname": "fabric_dyeing_tab", "fieldtype": "Tab Break", "label": "Dyeing",
   "depends_on": "eval:doc.is_cloth_item", "insert_after": "knitting_dia_details"},
  {"fieldname": "dyeing_process", "fieldtype": "Link", "label": "Dyeing Process",
   "options": "Process", "insert_after": "fabric_dyeing_tab"},
  {"fieldname": "dyeing_colour_details", "fieldtype": "Table", "label": "Colour Details",
   "options": "IPD Dyeing Colour Detail", "insert_after": "dyeing_process"},
  {"fieldname": "fabric_compacting_tab", "fieldtype": "Tab Break", "label": "Compacting",
   "depends_on": "eval:doc.is_cloth_item", "insert_after": "dyeing_colour_details"},
  {"fieldname": "compacting_process", "fieldtype": "Link", "label": "Compacting Process",
   "options": "Process", "insert_after": "fabric_compacting_tab"},
  {"fieldname": "compacting_dia_details", "fieldtype": "Table", "label": "Dia Details",
   "options": "IPD Compacting Dia Detail", "insert_after": "compacting_process"},
]})
frappe.db.commit()
print("CHECK created:", frappe.db.count("Custom Field", {"dt": "Item Production Detail", "fieldname": ["like", "%knitting%"]}))
EOF
```
Expected: `CHECK created: 3` (`fabric_knitting_tab`, `knitting_process`, `knitting_dia_details` all match the LIKE).

- [ ] **Step 3: Hide the garment tabs on cloth IPDs**

```bash
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a TABS
import frappe
fabric_tabs = {"fabric_knitting_tab", "fabric_dyeing_tab", "fabric_compacting_tab"}
tabs = frappe.get_all("Custom Field",
    filters={"dt": "Item Production Detail", "fieldtype": "Tab Break"},
    fields=["name", "fieldname", "depends_on"])
for t in tabs:
    if t.fieldname in fabric_tabs:
        continue
    existing = (t.depends_on or "").strip()
    if existing.startswith("eval:"):
        new = f"eval:(!doc.is_cloth_item) && ({existing[5:]})"
    elif existing:
        new = f"eval:(!doc.is_cloth_item) && doc.{existing}"
    else:
        new = "eval:!doc.is_cloth_item"
    frappe.db.set_value("Custom Field", t.name, "depends_on", new)
frappe.db.commit()
frappe.clear_cache(doctype="Item Production Detail")
print("TABS updated:", [t.fieldname for t in tabs if t.fieldname not in fabric_tabs])
EOF
```
Expected: prints the garment tab fieldnames (Packing / Set Item / Stiching / Emblishment / Cutting / Cloth Accessory / Advance Settings tabs).

- [ ] **Step 4: Gate the garment validations for cloth IPDs**

In `essdee_yrp/ipd_validations.py`, add near the top (after imports):

```python
def is_cloth_ipd(doc):
	"""Cloth-item IPDs skip every garment validation/mutation in this module."""
	if doc.get("is_cloth_item"):
		return True
	if not doc.get("item"):
		return False
	return bool(frappe.db.get_value("Item", doc.item, "is_cloth_item"))
```

Then add an early return as the FIRST line of the four hook entrypoints (`before_validate`, `validate`, `on_update`, `on_trash`):

```python
	if is_cloth_ipd(doc):
		return
```

- [ ] **Step 5: JS queries for the new tables**

In `essdee_yrp/public/js/item_production_detail.js`, inside the existing `frappe.ui.form.on("Item Production Detail", { setup(frm) {...} })` (add a `setup` handler if the file only has other events):

```javascript
	setup(frm) {
		frm.set_query("dia", "knitting_dia_details", () => ({ filters: { attribute_name: "Dia" } }));
		frm.set_query("from_colour", "dyeing_colour_details", () => ({ filters: { attribute_name: "Colour" } }));
		frm.set_query("to_colour", "dyeing_colour_details", () => ({ filters: { attribute_name: "Colour" } }));
		frm.set_query("from_dia", "compacting_dia_details", () => ({ filters: { attribute_name: "Dia" } }));
		frm.set_query("to_dia", "compacting_dia_details", () => ({ filters: { attribute_name: "Dia" } }));
	},
```
(If a `setup` already exists, merge these lines into it — do not create a duplicate key.)

- [ ] **Step 6: Export fixtures + verify + UI check**

```bash
python3 -m py_compile apps/essdee_yrp/essdee_yrp/ipd_validations.py
bench --site essdee_yrp.site export-fixtures --app essdee_yrp
python3 -c "
import json
j = json.load(open('/home/anas/frappe-16/apps/essdee_yrp/essdee_yrp/fixtures/custom_field.json'))
names = {c['fieldname'] for c in j if c['dt']=='Item Production Detail'}
need = {'is_cloth_item','fabric_knitting_tab','knitting_process','knitting_dia_details','fabric_dyeing_tab','dyeing_process','dyeing_colour_details','fabric_compacting_tab','compacting_process','compacting_dia_details'}
print('missing:', need - names)
"
bench --site essdee_yrp.site clear-cache
```
Expected: `missing: set()`. Then create a cloth item + IPD in the UI check of Task 7 (full E2E); for now pw-shot any EXISTING (garment) IPD and confirm the garment tabs still render and no fabric tabs show:
```bash
node .claude/hooks/pw-shot.mjs --url "/app/item-production-detail" --site http://essdee_yrp.site:8003 --wait 4000
```
Expected: list view loads, no console errors.

---

### Task 4: Auto-matrix generation (`essdee_yrp/fabric_ipd.py`) + IPD hook

**Files:**
- Create: `essdee_yrp/fabric_ipd.py`
- Modify: `essdee_yrp/hooks.py` (IPD `on_update` becomes a list)

**Interfaces:**
- Consumes: IPD fabric fields (Task 3); base `IPD Process Matrix` doctype (fields: `ipd`, `process_name`, `input_item`, `output_item`, `input_attributes`/`output_attributes` → `IPD Matrix Attribute {attribute}`, `combinations` → `IPD Matrix Combination {group_index, group_name, side, combo_index, quantity, uom, wastage_pct}`, `combination_attributes` → `IPD Matrix Combination Attribute {group_index, side, combo_index, attribute, attribute_value}`).
- Produces: `sync_fabric_process_matrices(doc, method=None)` — idempotent; one draft IPD Process Matrix per configured fabric process. Read by Task 5 conceptually (Task 5 reads the IPD tabs directly for options and the matrices exist as the calculation record — see spec §3.4).

- [ ] **Step 1: Fail-first verification**

```bash
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a CHECK
import importlib
try:
    importlib.import_module("essdee_yrp.fabric_ipd")
    print("CHECK: module exists")
except ImportError:
    print("CHECK: missing")
EOF
```
Expected: `CHECK: missing`

- [ ] **Step 2: Write `essdee_yrp/fabric_ipd.py`**

```python
# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe

from essdee_yrp.ipd_validations import is_cloth_ipd

FABRIC_DIA_ATTRIBUTE = "Dia"
FABRIC_COLOUR_ATTRIBUTE = "Colour"

# (ipd process-link fieldname, kind)
FABRIC_PROCESS_FIELDS = (
	("knitting_process", "knitting"),
	("dyeing_process", "dyeing"),
	("compacting_process", "compacting"),
)


def get_fabric_process_kind(ipd_doc, process_name):
	"""Which fabric process (knitting/dyeing/compacting) `process_name` is on this IPD, or None."""
	if not process_name:
		return None
	for fieldname, kind in FABRIC_PROCESS_FIELDS:
		if ipd_doc.get(fieldname) == process_name:
			return kind
	return None


def ensure_cloth_item_attributes(doc, method=None):
	"""Cloth IPDs must list every attribute their fabric tabs use in
	`item_attributes` — base IPDProcessMatrix.validate_attributes_belong_to_ipd
	rejects matrix attributes missing from that table (the garment UI copies
	them via client JS; cloth mode ensures them server-side). Hooked on
	before_validate so the rows persist with the save."""
	if not is_cloth_ipd(doc):
		return
	needed = []
	if doc.get("knitting_process") or doc.get("compacting_process"):
		needed.append(FABRIC_DIA_ATTRIBUTE)
	if doc.get("dyeing_process"):
		needed.append(FABRIC_COLOUR_ATTRIBUTE)
	have = {row.attribute for row in doc.get("item_attributes") or []}
	for attribute in needed:
		if attribute not in have:
			doc.append("item_attributes", {"attribute": attribute})


def sync_fabric_process_matrices(doc, method=None):
	"""Regenerate the IPD Process Matrix docs for a cloth IPD's fabric processes.

	Idempotent: existing matrices for (ipd, process) are deleted and rebuilt
	from the IPD tab tables on every IPD save. Matrices stay draft — the
	fabric WO calculation owns how they are read. Never hand-authored
	(standing 2026-06-25 rule).
	"""
	if not is_cloth_ipd(doc):
		return

	uom = frappe.db.get_value("Item", doc.item, "default_unit_of_measure")

	# Matrices are NEVER hand-authored (2026-06-25 rule), so wiping every
	# matrix of this IPD is safe and also clears orphans left behind when a
	# process link is changed or removed.
	_delete_all_matrices(doc.name)

	for fieldname, kind in FABRIC_PROCESS_FIELDS:
		process = doc.get(fieldname)
		if not process:
			continue
		builder = {
			"knitting": _build_knitting_matrix,
			"dyeing": _build_dyeing_matrix,
			"compacting": _build_compacting_matrix,
		}[kind]
		matrix = builder(doc, process, uom)
		if matrix:
			matrix.insert(ignore_permissions=True)


def _delete_all_matrices(ipd_name):
	for name in frappe.get_all("IPD Process Matrix", filters={"ipd": ipd_name}, pluck="name"):
		frappe.delete_doc("IPD Process Matrix", name, force=1, ignore_permissions=True)


def _new_matrix(doc, process):
	return frappe.get_doc({
		"doctype": "IPD Process Matrix",
		"ipd": doc.name,
		"process_name": process,
		"output_item": doc.item,
	})


def _build_knitting_matrix(doc, process, uom):
	"""Output combos = cloth x each Dia row. Input (yarn) is lot-specific and
	stamped at WO-calculation time, so the input side stays empty here."""
	rows = doc.get("knitting_dia_details") or []
	if not rows:
		return None
	matrix = _new_matrix(doc, process)
	matrix.append("output_attributes", {"attribute": FABRIC_DIA_ATTRIBUTE})
	for idx, row in enumerate(rows):
		matrix.append("combinations", {
			"group_index": idx, "group_name": row.dia, "side": "Output",
			"combo_index": 0, "quantity": 1, "uom": uom, "wastage_pct": 0,
		})
		matrix.append("combination_attributes", {
			"group_index": idx, "side": "Output", "combo_index": 0,
			"attribute": FABRIC_DIA_ATTRIBUTE, "attribute_value": row.dia,
		})
	return matrix


def _build_value_swap_matrix(doc, process, uom, rows, attribute, from_field, to_field):
	"""Shared shape for dyeing (Colour swap) and compacting (Dia swap):
	one group per mapping row; Input combo carries the from-value,
	Output combo the to-value. Quantities 1:1 (v1)."""
	if not rows:
		return None
	matrix = _new_matrix(doc, process)
	matrix.input_item = doc.item
	matrix.append("input_attributes", {"attribute": attribute})
	matrix.append("output_attributes", {"attribute": attribute})
	for idx, row in enumerate(rows):
		for side, value in (("Input", row.get(from_field)), ("Output", row.get(to_field))):
			matrix.append("combinations", {
				"group_index": idx, "group_name": f"{row.get(from_field)} -> {row.get(to_field)}",
				"side": side, "combo_index": 0, "quantity": 1, "uom": uom, "wastage_pct": 0,
			})
			matrix.append("combination_attributes", {
				"group_index": idx, "side": side, "combo_index": 0,
				"attribute": attribute, "attribute_value": value,
			})
	return matrix


def _build_dyeing_matrix(doc, process, uom):
	return _build_value_swap_matrix(
		doc, process, uom, doc.get("dyeing_colour_details") or [],
		FABRIC_COLOUR_ATTRIBUTE, "from_colour", "to_colour",
	)


def _build_compacting_matrix(doc, process, uom):
	return _build_value_swap_matrix(
		doc, process, uom, doc.get("compacting_dia_details") or [],
		FABRIC_DIA_ATTRIBUTE, "from_dia", "to_dia",
	)
```

- [ ] **Step 3: Hook it on IPD `on_update`**

In `essdee_yrp/hooks.py` `doc_events`, change the IPD `before_validate` and `on_update` values to lists:

```python
		"before_validate": [
			"essdee_yrp.ipd_validations.before_validate",
			"essdee_yrp.fabric_ipd.ensure_cloth_item_attributes",
		],
		"on_update": [
			"essdee_yrp.ipd_validations.on_update",
			"essdee_yrp.fabric_ipd.sync_fabric_process_matrices",
		],
```

- [ ] **Step 4: Verify end-to-end on the site**

```bash
python3 -m py_compile apps/essdee_yrp/essdee_yrp/fabric_ipd.py apps/essdee_yrp/essdee_yrp/hooks.py
bench --site essdee_yrp.site clear-cache
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a "FT-"
import frappe
# -- minimal cloth master setup (idempotent, prefixed FT-) --
def ensure(doctype, name, payload):
    if not frappe.db.exists(doctype, name):
        frappe.get_doc(payload).insert(ignore_permissions=True)
    return name
ensure("Item Attribute Value", "FT-D30", {"doctype": "Item Attribute Value", "attribute_name": "Dia", "attribute_value": "FT-D30"})
ensure("Item Attribute Value", "FT-D32", {"doctype": "Item Attribute Value", "attribute_name": "Dia", "attribute_value": "FT-D32"})
ensure("Item Attribute Value", "FT-White", {"doctype": "Item Attribute Value", "attribute_name": "Colour", "attribute_value": "FT-White"})
ensure("Item Attribute Value", "FT-Black", {"doctype": "Item Attribute Value", "attribute_name": "Colour", "attribute_value": "FT-Black"})
# cloth item with Dia + Colour attributes (adapt to the Item schema on this bench:
# check an existing synced cloth-ish Item via frappe.get_doc("Item", <name>).as_dict()
# and mirror its attribute child rows; set is_cloth_item=1)
uom = frappe.get_all("UOM", filters={"secondary_only": 0}, limit_page_length=1, pluck="name")[0]
item_group = frappe.get_all("Item Group", limit_page_length=1, pluck="name")[0]
if not frappe.db.exists("Item", "FT-CLOTH"):
    it = frappe.new_doc("Item")
    it.name1 = "FT-CLOTH"            # yrp Item has no item_name; autoname derives from name1
    it.item_group = item_group        # reqd on yrp Item
    it.default_unit_of_measure = uom
    it.append("attributes", {"attribute": "Dia"})
    it.append("attributes", {"attribute": "Colour"})
    it.is_cloth_item = 1
    it.insert(ignore_permissions=True)
# cloth IPD with all three tabs configured
if not frappe.db.exists("Item Production Detail", {"item": "FT-CLOTH"}):
    ipd = frappe.new_doc("Item Production Detail")
    ipd.item = "FT-CLOTH"
    ipd.knitting_process = "Knitting"
    ipd.append("knitting_dia_details", {"dia": "FT-D30"})
    ipd.append("knitting_dia_details", {"dia": "FT-D32"})
    ipd.dyeing_process = "Dyeing"
    ipd.append("dyeing_colour_details", {"from_colour": "FT-White", "to_colour": "FT-Black"})
    ipd.compacting_process = "Compacting"
    ipd.append("compacting_dia_details", {"from_dia": "FT-D32", "to_dia": "FT-D30"})
    ipd.insert(ignore_permissions=True)
    ipd.save(ignore_permissions=True)
frappe.db.commit()
ipd_name = frappe.get_value("Item Production Detail", {"item": "FT-CLOTH"})
mats = frappe.get_all("IPD Process Matrix", filters={"ipd": ipd_name}, fields=["name", "process_name"])
print("FT- matrices:", sorted(m.process_name for m in mats))
# item_attributes were auto-ensured by the before_validate hook:
print("FT- item_attributes:", sorted(r.attribute for r in frappe.get_doc("Item Production Detail", ipd_name).item_attributes))
# idempotency: save again, count must not grow
doc = frappe.get_doc("Item Production Detail", ipd_name); doc.save(ignore_permissions=True); frappe.db.commit()
print("FT- after resave:", frappe.db.count("IPD Process Matrix", {"ipd": ipd_name}))
# orphan cleanup: clearing a process link removes its matrix on the next save
doc = frappe.get_doc("Item Production Detail", ipd_name); doc.compacting_process = None; doc.save(ignore_permissions=True); frappe.db.commit()
print("FT- after clearing compacting:", frappe.db.count("IPD Process Matrix", {"ipd": ipd_name}))
doc = frappe.get_doc("Item Production Detail", ipd_name); doc.compacting_process = "Compacting"; doc.save(ignore_permissions=True); frappe.db.commit()
EOF
```
Expected: `FT- matrices: ['Compacting', 'Dyeing', 'Knitting']`, `FT- item_attributes: ['Colour', 'Dia']`, `FT- after resave: 3`, `FT- after clearing compacting: 2`.
NOTE: if any doctype demands more mandatory fields on this bench, inspect one synced record and fill exactly what the schema demands — do NOT weaken validations to make setup pass; this setup script may be adapted, the assertions may not.

---

### Task 5: Fabric WO calculation endpoints (`essdee_yrp/api/work_order.py`)

**Files:**
- Create: `essdee_yrp/api/__init__.py` (empty)
- Create: `essdee_yrp/api/work_order.py`

**Interfaces:**
- Consumes: `Lot.lot_fabric_details` (Task 2); IPD fabric fields + `get_fabric_process_kind` (Tasks 3–4); base yrp `get_or_create_variant(template, args)` from `yrp.yrp.doctype.item.item`; `wo.lot` (dimension field); WO child tables `deliverables`/`receivables` (fields verified: deliverables carry `item_variant, qty, uom, pending_quantity, received_type, is_calculated`; receivables carry `item_variant, qty, uom, pending_quantity`).
- Produces (called by Task 6 JS):
  - `get_fabric_deliverable_context(work_order) -> {is_fabric_process, kind, rows: [{fabric_row, kind, yarn_item, cloth_item, production_detail, yarn_attributes: [str], cloth_attributes: [str], dia_options: [str], colour_from_options: [str], dia_from_options: [str], attribute_options: {attr: [values]}}]}` — `kind` is per-row; the top-level `kind` is display-only (dialog title).
  - `calculate_fabric_deliverables(work_order, rows) -> {deliverables, receivables}` where input rows = `[{fabric_row, weight, attribute_values: {attr: value}, target_dia?, cloth_attribute_values?: {attr: value}}]` — for knitting, `attribute_values` = yarn attrs and `cloth_attribute_values` = the OTHER cloth attributes (everything except Dia, e.g. the greige Colour); the receivable variant is built from `cloth_attribute_values + {Dia: target_dia}` because `create_variant` requires EVERY template attribute.

- [ ] **Step 1: Fail-first**

```bash
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a CHECK
import importlib
try:
    importlib.import_module("essdee_yrp.api.work_order")
    print("CHECK: module exists")
except ImportError:
    print("CHECK: missing")
EOF
```
Expected: `CHECK: missing`

- [ ] **Step 2: Write `essdee_yrp/api/work_order.py`**

```python
# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_ipd import (
	FABRIC_COLOUR_ATTRIBUTE,
	FABRIC_DIA_ATTRIBUTE,
	get_fabric_process_kind,
)


@frappe.whitelist()
def get_fabric_deliverable_context(work_order):
	"""Popup context: one row per Lot Fabric Detail whose IPD maps this WO's
	process to knitting/dyeing/compacting. Empty rows => not a fabric process."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	lot = _get_lot(wo)

	rows = []
	kind = None
	for fabric in lot.get("lot_fabric_details") or []:
		if not fabric.production_detail:
			continue
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		row_kind = get_fabric_process_kind(ipd, wo.process_name)
		if not row_kind:
			continue
		kind = row_kind
		rows.append({
			"fabric_row": fabric.name,
			"yarn_item": fabric.yarn_item,
			"cloth_item": fabric.cloth_item,
			"production_detail": fabric.production_detail,
			"kind": row_kind,
			"yarn_attributes": _item_attributes(fabric.yarn_item),
			"cloth_attributes": _item_attributes(fabric.cloth_item),
			"attribute_options": _attribute_options(fabric.yarn_item if row_kind == "knitting" else fabric.cloth_item),
			"dia_options": [r.dia for r in ipd.get("knitting_dia_details") or []],
			"colour_from_options": [r.from_colour for r in ipd.get("dyeing_colour_details") or []],
			"dia_from_options": [r.from_dia for r in ipd.get("compacting_dia_details") or []],
		})

	return {"is_fabric_process": bool(rows), "kind": kind, "rows": rows}


@frappe.whitelist()
def calculate_fabric_deliverables(work_order, rows):
	"""User-entered deliverables (variant attrs + weight) -> receivables, 1:1 (v1).

	knitting:   deliver yarn variant,        receive cloth variant at target_dia
	dyeing:     deliver cloth (from colour), receive cloth with to_colour swapped
	compacting: deliver cloth (from dia),    receive cloth with to_dia swapped
	"""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("write")
	if wo.docstatus != 0:
		frappe.throw(_("Calculate can only update a draft Work Order."))

	lot = _get_lot(wo)
	fabric_rows = {f.name: f for f in lot.get("lot_fabric_details") or []}
	default_received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	if not default_received_type:
		frappe.throw(_("Set Default Received Type in YRP Stock Settings first."))

	from yrp.yrp.doctype.item.item import get_or_create_variant

	deliverables, receivables = [], []
	for entry in rows:
		weight = flt(entry.get("weight"))
		if weight <= 0:
			continue
		fabric = fabric_rows.get(entry.get("fabric_row"))
		if not fabric:
			frappe.throw(_("Unknown Lot fabric row {0}.").format(entry.get("fabric_row")))
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		kind = get_fabric_process_kind(ipd, wo.process_name)
		if not kind:
			frappe.throw(_("{0} is not a fabric process on IPD {1}.").format(wo.process_name, ipd.name))

		attrs = entry.get("attribute_values") or {}

		if kind == "knitting":
			target_dia = entry.get("target_dia")
			valid = [r.dia for r in ipd.get("knitting_dia_details") or []]
			if target_dia not in valid:
				frappe.throw(_("Dia {0} is not configured on IPD {1}.").format(target_dia, ipd.name))
			# create_variant requires EVERY template attribute -> the popup
			# collects the non-Dia cloth attributes (e.g. greige Colour) too.
			out_attrs = dict(entry.get("cloth_attribute_values") or {})
			out_attrs[FABRIC_DIA_ATTRIBUTE] = target_dia
			_require_all_attributes(fabric.cloth_item, out_attrs, fabric.name)
			in_variant = get_or_create_variant(fabric.yarn_item, attrs)
			out_variant = get_or_create_variant(fabric.cloth_item, out_attrs)
			in_item, out_item = fabric.yarn_item, fabric.cloth_item
		elif kind == "dyeing":
			mapping = {r.from_colour: r.to_colour for r in ipd.get("dyeing_colour_details") or []}
			out_attrs = _swap(attrs, FABRIC_COLOUR_ATTRIBUTE, mapping, ipd)
			in_variant = get_or_create_variant(fabric.cloth_item, attrs)
			out_variant = get_or_create_variant(fabric.cloth_item, out_attrs)
			in_item = out_item = fabric.cloth_item
		else:  # compacting
			mapping = {r.from_dia: r.to_dia for r in ipd.get("compacting_dia_details") or []}
			out_attrs = _swap(attrs, FABRIC_DIA_ATTRIBUTE, mapping, ipd)
			in_variant = get_or_create_variant(fabric.cloth_item, attrs)
			out_variant = get_or_create_variant(fabric.cloth_item, out_attrs)
			in_item = out_item = fabric.cloth_item
		if kind in ("dyeing", "compacting"):
			_require_all_attributes(fabric.cloth_item, attrs, fabric.name)

		deliverables.append({
			"item_variant": in_variant,
			"qty": weight,
			"uom": frappe.db.get_value("Item", in_item, "default_unit_of_measure"),
			"pending_quantity": weight,
			"received_type": default_received_type,
			"is_calculated": 1,
		})
		# v1: receivable strictly 1:1 with the entered deliverable weight
		receivables.append({
			"item_variant": out_variant,
			"qty": weight,
			"uom": frappe.db.get_value("Item", out_item, "default_unit_of_measure"),
			"pending_quantity": weight,
		})

	if not deliverables:
		frappe.throw(_("Enter a weight greater than zero for at least one fabric row."))

	# Idempotent rewrite (MGK pattern): drop prior calculated deliverables,
	# replace receivables wholesale, clear the grouped-JSON so sync_vue_item_details
	# doesn't resurrect stale rows.
	kept = [d for d in wo.get("deliverables") or [] if not d.get("is_calculated")]
	wo.set("deliverables", kept)
	for d in deliverables:
		wo.append("deliverables", d)
	wo.set("receivables", [])
	for r in receivables:
		wo.append("receivables", r)
	wo.deliverable_details = ""
	wo.receivable_details = ""
	wo.save()

	return {"deliverables": len(deliverables), "receivables": len(receivables)}


def _get_lot(wo):
	if not wo.get("lot"):
		frappe.throw(_("Select a Lot on the Work Order first."))
	lot = frappe.get_doc("Lot", wo.lot)
	lot.check_permission("read")
	return lot


def _item_attributes(item):
	if not item:
		return []
	doc = frappe.get_cached_doc("Item", item)
	return [row.attribute for row in doc.get("attributes") or []]


def _attribute_options(item):
	"""{attribute: [attribute_value, ...]} for every attribute of `item`."""
	options = {}
	for attribute in _item_attributes(item):
		options[attribute] = frappe.get_all(
			"Item Attribute Value", filters={"attribute_name": attribute},
			pluck="name", order_by="attribute_value asc", limit_page_length=0,
		)
	return options


def _require_all_attributes(item, attrs, fabric_row):
	"""Friendly pre-check: create_variant throws a raw framework error on any
	missing template attribute — name the fabric row + attribute instead."""
	for attribute in _item_attributes(item):
		if not attrs.get(attribute):
			frappe.throw(_("Select a value for {0} on fabric row {1}.").format(attribute, fabric_row))


def _swap(attrs, attribute, mapping, ipd):
	current = attrs.get(attribute)
	if current not in mapping:
		frappe.throw(_("{0} value {1} has no mapping on IPD {2}.").format(attribute, current, ipd.name))
	out = dict(attrs)
	out[attribute] = mapping[current]
	return out
```

- [ ] **Step 3: Prerequisite — one submitted Process Cost per fabric process**

`WorkOrder.save()` ALWAYS runs `set_receivable_process_costs`, which THROWS when
no submitted Process Cost matches — and the lookup filters by `wo.item`,
`supplier`, AND the production-group dimension (`lot`). Zero Process Costs
exist on this site. Create + submit one per process BEFORE the WO check
(reqd fields verified: item, lot, uom, from_date, supplier, process_name,
tax_slab, process_cost_values):

```bash
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a PC
import frappe
lot_name = frappe.get_all("Lot", limit_page_length=1, pluck="name")[0]
supplier = frappe.get_all("Supplier", limit_page_length=1, pluck="name")[0]
uom = frappe.get_all("UOM", filters={"secondary_only": 0}, limit_page_length=1, pluck="name")[0]
tax_slab_dt = frappe.get_meta("Process Cost").get_field("tax_slab").options
tax_slab = frappe.get_all(tax_slab_dt, limit_page_length=1, pluck="name")[0]
for process, item in (("Knitting", "FT-CLOTH"), ("Dyeing", "FT-CLOTH"), ("Compacting", "FT-CLOTH")):
    if frappe.db.exists("Process Cost", {"process_name": process, "item": item, "docstatus": 1}):
        continue
    pc = frappe.new_doc("Process Cost")
    pc.item = item; pc.lot = lot_name; pc.uom = uom; pc.from_date = frappe.utils.today()
    pc.supplier = supplier; pc.process_name = process; pc.tax_slab = tax_slab
    pc.append("process_cost_values", {"price": 1})  # inspect child meta for the exact rate fieldname
    pc.insert(ignore_permissions=True); pc.submit()
print("PC:", frappe.db.count("Process Cost", {"docstatus": 1}))
EOF
```
Expected: `PC: 3` (or more). If the child-row fieldnames differ, inspect
`frappe.get_meta(<child doctype>)` and fill what the schema demands — do not
bypass validation.

- [ ] **Step 4: Verify with a scripted calculation**

```bash
python3 -m py_compile apps/essdee_yrp/essdee_yrp/api/__init__.py apps/essdee_yrp/essdee_yrp/api/work_order.py
bench --site essdee_yrp.site clear-cache
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a "CALC"
import frappe, json
# uses the FT- masters from Task 4. Create yarn item + lot + WO scaffolding:
if not frappe.db.exists("Item", "FT-YARN"):
    it = frappe.new_doc("Item"); it.name1 = "FT-YARN"
    it.item_group = frappe.get_all("Item Group", limit_page_length=1, pluck="name")[0]
    it.default_unit_of_measure = frappe.get_all("UOM", filters={"secondary_only": 0}, limit_page_length=1, pluck="name")[0]
    it.insert(ignore_permissions=True)
lot_name = frappe.get_all("Lot", limit_page_length=1, pluck="name")[0]
lot = frappe.get_doc("Lot", lot_name)
ipd_name = frappe.get_value("Item Production Detail", {"item": "FT-CLOTH"})
if not [f for f in lot.get("lot_fabric_details") or [] if f.cloth_item == "FT-CLOTH"]:
    lot.append("lot_fabric_details", {"yarn_item": "FT-YARN", "cloth_item": "FT-CLOTH", "production_detail": ipd_name})
    lot.save(ignore_permissions=True)  # plain save: adding a fabric row must pass Lot validation; if it fails, diagnose - never bypass
frappe.db.commit()
# WO for Knitting — inspect an existing WO for mandatory fields; supplier etc.
supplier = frappe.get_all("Supplier", limit_page_length=1, pluck="name")[0]
address = frappe.get_all("Address", limit_page_length=1, pluck="name")[0]
wo = frappe.new_doc("Work Order")
wo.process_name = "Knitting"
wo.lot = lot_name
wo.item = "FT-CLOTH"                       # reqd; also drives the Process Cost lookup
wo.supplier = supplier
wo.supplier_address = address              # reqd
wo.delivery_address = address              # reqd
wo.planned_start_date = frappe.utils.today()   # wo_date auto-fills via set_missing_dates
wo.planned_end_date = frappe.utils.today()     # reqd, NOT auto-filled
wo.insert(ignore_permissions=True)
frappe.db.commit()
from essdee_yrp.api.work_order import get_fabric_deliverable_context, calculate_fabric_deliverables
ctx = get_fabric_deliverable_context(wo.name)
print("CALC ctx:", ctx["is_fabric_process"], ctx["kind"], len(ctx["rows"]))
res = calculate_fabric_deliverables(wo.name, [{"fabric_row": ctx["rows"][0]["fabric_row"], "weight": 100, "attribute_values": {}, "target_dia": "FT-D30", "cloth_attribute_values": {"Colour": "FT-White"}}])
frappe.db.commit()
wo.reload()
print("CALC rows:", [(d.item_variant, d.qty, d.received_type) for d in wo.deliverables], "|", [(r.item_variant, r.qty) for r in wo.receivables])
EOF
```
Expected: `CALC ctx: True knitting 1`, then deliverable `("FT-YARN", 100.0, "Accepted")` (yarn has no attributes → variant named FT-YARN; received_type from YRP Stock Settings = "Accepted" on this site — deliberate spec-compatible source) and a receivable cloth variant carrying BOTH FT-D30 and FT-White with qty 100. If any doctype demands more mandatory fields, inspect a synced record and fill what the schema demands — do NOT bypass validation.

- [ ] **Step 5: Dyeing + compacting variants of the same check**

Repeat Step 4's WO creation with `process_name = "Dyeing"` and rows `[{"fabric_row": ..., "weight": 50, "attribute_values": {"Colour": "FT-White", "Dia": "FT-D30"}}]` → expect deliverable variant with FT-White and receivable variant with FT-Black (Dia untouched). Then `process_name = "Compacting"` with `attribute_values: {"Colour": "FT-Black", "Dia": "FT-D32"}` → receivable with FT-D30 (Colour untouched).

---

### Task 6: Work Order Calculate popup (doctype_js)

**Files:**
- Create: `essdee_yrp/public/js/work_order.js`
- Modify: `essdee_yrp/hooks.py` (`doctype_js` += Work Order)

**Interfaces:**
- Consumes: `essdee_yrp.api.work_order.get_fabric_deliverable_context` / `calculate_fabric_deliverables` (Task 5 signatures).

- [ ] **Step 1: Write `essdee_yrp/public/js/work_order.js`** (dialog UX modeled on `mgk_clothing_yrp/public/js/work_order_mgk.js`):

```javascript
frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Calculate Fabric Deliverables"), () => open_fabric_calculate(frm));
	},
});

function open_fabric_calculate(frm) {
	frappe.call({
		method: "essdee_yrp.api.work_order.get_fabric_deliverable_context",
		args: { work_order: frm.doc.name },
		callback(r) {
			const ctx = r.message || {};
			if (!ctx.is_fabric_process) {
				frappe.msgprint(__("{0} is not a fabric process for this Lot's fabrics.", [frm.doc.process_name || ""]));
				return;
			}
			render_fabric_dialog(frm, ctx);
		},
	});
}

function render_fabric_dialog(frm, ctx) {
	const fields = [];
	ctx.rows.forEach((row, i) => {
		fields.push({ fieldtype: "Section Break", label: `${row.cloth_item} (${row.production_detail})` });
		if (row.kind === "knitting") {
			fields.push({ fieldtype: "HTML", options: `<div class="text-muted small">${__("Yarn")}: ${frappe.utils.escape_html(row.yarn_item || "")}</div>` });
			(row.yarn_attributes || []).forEach((attr) => {
				fields.push({
					fieldtype: "Select", label: `${attr} (${__("yarn")})`, fieldname: `attr_${i}_${attr}`,
					options: [""].concat((row.attribute_options || {})[attr] || []).join("\n"),
				});
			});
			fields.push({
				fieldtype: "Select", label: __("Cloth Dia"), fieldname: `target_dia_${i}`, reqd: 1,
				options: [""].concat(row.dia_options || []).join("\n"),
			});
			// create_variant needs EVERY cloth attribute -> collect the non-Dia ones too
			(row.cloth_attributes || []).filter((a) => a !== "Dia").forEach((attr) => {
				fields.push({
					fieldtype: "Select", label: `${attr} (${__("cloth")})`, fieldname: `cloth_attr_${i}_${attr}`, reqd: 1,
					options: [""].concat((row.attribute_options || {})[attr] || []).join("\n"),
				});
			});
		} else {
			(row.cloth_attributes || []).forEach((attr) => {
				const restrict = (row.kind === "dyeing" && attr === "Colour") ? row.colour_from_options
					: (row.kind === "compacting" && attr === "Dia") ? row.dia_from_options
					: (row.attribute_options || {})[attr];
				fields.push({
					fieldtype: "Select", label: attr, fieldname: `attr_${i}_${attr}`, reqd: 1,
					options: [""].concat(restrict || []).join("\n"),
				});
			});
		}
		fields.push({ fieldtype: "Float", label: __("Weight (deliverable qty)"), fieldname: `weight_${i}` });
	});

	const d = new frappe.ui.Dialog({
		title: __("Calculate Fabric Deliverables — {0}", [frm.doc.process_name]),
		fields,
		primary_action_label: __("Calculate"),
		primary_action(values) {
			const rows = [];
			ctx.rows.forEach((row, i) => {
				const weight = values[`weight_${i}`];
				if (!weight || weight <= 0) return;
				const attrs = {};
				const attr_list = row.kind === "knitting" ? row.yarn_attributes : row.cloth_attributes;
				(attr_list || []).forEach((attr) => {
					const v = values[`attr_${i}_${attr}`];
					if (v) attrs[attr] = v;
				});
				const cloth_attrs = {};
				if (row.kind === "knitting") {
					(row.cloth_attributes || []).filter((a) => a !== "Dia").forEach((attr) => {
						const v = values[`cloth_attr_${i}_${attr}`];
						if (v) cloth_attrs[attr] = v;
					});
				}
				rows.push({
					fabric_row: row.fabric_row,
					weight,
					attribute_values: attrs,
					cloth_attribute_values: cloth_attrs,
					target_dia: values[`target_dia_${i}`] || null,
				});
			});
			if (!rows.length) {
				frappe.msgprint(__("Enter a weight for at least one fabric."));
				return;
			}
			frappe.call({
				method: "essdee_yrp.api.work_order.calculate_fabric_deliverables",
				args: { work_order: frm.doc.name, rows },
				freeze: true,
				callback(res) {
					d.hide();
					const m = res.message || {};
					frappe.show_alert({ message: __("Calculated {0} deliverable(s) and {1} receivable(s).", [m.deliverables, m.receivables]), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}
```

- [ ] **Step 2: Register + build**

In `essdee_yrp/hooks.py`:
```python
doctype_js = {
	"Item Production Detail": "public/js/item_production_detail.js",
	"Production Order": "public/js/production_order.js",
	"Work Order": "public/js/work_order.js",
}
```
Then:
```bash
node -e "new Function(require('fs').readFileSync('/home/anas/frappe-16/apps/essdee_yrp/essdee_yrp/public/js/work_order.js','utf8'))" && echo JS-OK
bench build --app essdee_yrp 2>&1 | tail -2
bench --site essdee_yrp.site clear-cache
```
Expected: `JS-OK`, build DONE.

- [ ] **Step 3: UI smoke**

```bash
node .claude/hooks/pw-shot.mjs --url "/app/work-order/<the Task 5 knitting WO>" --site http://essdee_yrp.site:8003 --wait 4000
```
Expected: form renders with the "Calculate Fabric Deliverables" button, no console errors.

---

### Task 7: End-to-end UI drive + docs

**Files:**
- Modify: `apps/essdee_yrp/docs/sd_yrp_session_status_2026-07-01.md` (or a new dated status doc) — record what was built + how verified.

**Interfaces:** none produced; this is the acceptance gate.

- [ ] **Step 1: Active-driving E2E (Playwright-style, not screenshots-only)**

Drive the real UI on `essdee_yrp.site` (headless via pw-shot `--eval` or a driving script). The canonical path, reading literal DOM at each step and reacting to errors:
1. Open the FT-CLOTH IPD → confirm only Knitting/Dyeing/Compacting tabs show (garment tabs hidden), grids hold the FT- rows. **Then WRITE via the form:** add a Dia row (create FT-D34 first) and SAVE → confirm the Knitting matrix regenerated with 3 output combos (`frappe.get_all("IPD Matrix Combination", ...)` count).
2. Open the Lot used in Task 5 → Fabric Details grid shows the FT- row; cloth_item picker offers only `is_cloth_item` items. **Then WRITE via the grid:** add a second fabric row through the pickers and SAVE; delete it after verifying.
3. Open the knitting WO → click "Calculate Fabric Deliverables" → popup shows the fabric section + Cloth Dia select + weight → enter 100 + FT-D30 → Calculate → read the deliverables/receivables tables from the DOM: yarn 100 / FT-CLOTH@FT-D30 100.
4. Repeat for a Dyeing WO (FT-White in → FT-Black out) and a Compacting WO (FT-D32 in → FT-D30 out).
5. Re-run Calculate on the same WO with weight 80 → rows REPLACED (not duplicated).
6. Check `Error Log` for the session window — must be empty of new server errors.
Save screenshots at each step as evidence (they are evidence, not the test).

- [ ] **Step 2: Full-suite sanity**

```bash
bench --site essdee_yrp.site migrate 2>&1 | tail -3   # fixtures re-sync cleanly
git -C /home/anas/frappe-16/apps/essdee_yrp status --short   # review the full change set (do NOT commit)
```

Sync-safety assert (spec §3.2 — fabric rows must survive a Lot re-sync):
```bash
bench --site essdee_yrp.site console <<'EOF' 2>&1 | grep -a SYNCSAFE
import frappe
from essdee_yrp.sd_yrp_sync import upsert_filtered_doc
lot = frappe.get_all("Lot", filters=[["Lot Fabric Detail","cloth_item","=","FT-CLOTH"]], limit_page_length=1, pluck="name")[0]
before = frappe.db.count("Lot Fabric Detail", {"parent": lot})
doc = frappe.get_doc("Lot", lot)
payload = {"doctype": "Lot", "name": lot, "lot_name": doc.lot_name, "status": doc.status}  # F15-style payload WITHOUT lot_fabric_details
upsert_filtered_doc(payload)
frappe.db.commit()
print("SYNCSAFE before:", before, "after:", frappe.db.count("Lot Fabric Detail", {"parent": lot}))
EOF
```
Expected: before == after (rows untouched).

- [ ] **Step 3: Update the status/handoff doc** with: what was built (map to spec sections), the FT- test masters created, verification evidence paths, and the deferred items (percentage math, lot fabric quantities, and the recorded v1 limitation: ONE (dia, weight) entry per fabric row per knitting WO — knitting the same fabric into multiple Dias means multiple Work Orders).

---

## Self-review notes (run after drafting — resolved inline)

- Spec §3.1–§3.5 all map to Tasks 1/2/3/4/5(+6); §4 popup = Task 6; §5 out-of-scope respected (no percentages, no lot qty, three processes only, no stages).
- Type consistency: `get_fabric_process_kind(ipd_doc, process_name)` defined Task 4, consumed Task 5; context/calc payload field names match between Task 5 (`fabric_row`, `weight`, `attribute_values`, `target_dia`) and Task 6 JS.
- Known judgment points for the implementer (not placeholders — decision recorded): Item/WO creation scaffolding in verification scripts may need extra mandatory fields depending on synced schema — copy them from existing records, never bypass validation; if Process Cost is required on WO save, create an approved Process Cost for the three fabric processes and note it.
