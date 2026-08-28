# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

from collections import defaultdict
from operator import itemgetter

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from yrp.stock.utils import get_combine_datetime
from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.item_production_detail.item_production_detail import (
	get_ipd_primary_values,
)


def _tuple_attributes(value):
	return {row[0]: row[1] for row in value}


class CutPanelMovement(Document):
	def onload(self):
		if not self.is_new() and self.docstatus == 1:
			from essdee_yrp.cutting.movement import get_active_root_transactions

			self.set_onload(
				"active_root_transactions",
				[
					{
						"doctype": row.doctype,
						"name": row.name,
						"docstatus": row.docstatus,
					}
					for row in get_active_root_transactions(self.name)
				],
			)
		if self.cut_panel_movement_json:
			self.set_onload(
				"movement_details",
				update_if_string_instance(self.cut_panel_movement_json),
			)

	def before_cancel(self):
		if self.against_id:
			frappe.throw(
				_("Cancel {0} {1} before cancelling this Cut Panel Movement.").format(
					self.against, self.against_id
				)
			)

	def before_validate(self):
		if self.docstatus == 1:
			return
		if self.is_new():
			existing = frappe.db.exists(
				"Cut Panel Movement",
				{
					"lot": self.lot,
					"from_warehouse": self.from_warehouse,
					"docstatus": 0,
				},
			)
			if existing:
				frappe.throw(
					_("Submit or delete draft Cut Panel Movement {0} for {1} / {2} first.").format(
						existing, self.from_warehouse, self.lot
					)
				)

		movement_data = self.get("movement_data")
		if self.is_new() or not movement_data:
			return
		items = update_if_string_instance(movement_data)
		if not isinstance(items, dict):
			frappe.throw(_("Movement Details must be a JSON object."))
		for item in items.get("accessory_data") or []:
			item["moved_weight"] = flt(item.get("moved_weight"))
			if flt(item.get("weight")) < item["moved_weight"]:
				frappe.throw(_("Accessory moving weight cannot exceed its available weight."))
		self.cut_panel_movement_json = get_total(items)

	def before_submit(self):
		json_data = update_if_string_instance(self.cut_panel_movement_json)
		if not isinstance(json_data, dict):
			frappe.throw(_("Fetch and select at least one panel before submitting."))
		panels = json_data.get("panels") or []
		is_set_item = cint(json_data.get("is_set_item"))
		selected = {}
		for colour, colour_data in (json_data.get("data") or {}).items():
			selected[colour] = {"part": colour_data.get("part"), "data": []}
			panel_names = (
				panels.get(colour_data.get("part"), []) if is_set_item else panels
			)
			for row in colour_data.get("data") or []:
				if row.get("bundle_moved") or any(
					row.get(panel) and row.get(f"{panel}_moved") for panel in panel_names
				):
					selected[colour]["data"].append(row)
		json_data["data"] = {
			colour: detail for colour, detail in selected.items() if detail["data"]
		}
		json_data["accessory_data"] = [
			row
			for row in (json_data.get("accessory_data") or [])
			if flt(row.get("moved_weight")) > 0
		]
		collapsed_details = []
		for row in json_data.get("collapsed_details") or []:
			move_qty = flt(row.get("move_qty"), 3)
			if not cint(row.get("moved")) or move_qty <= 0:
				continue
			if move_qty > flt(row.get("quantity"), 3):
				frappe.throw(
					_("Collapsed move qty cannot exceed its available quantity.")
				)
			row["move_qty"] = move_qty
			collapsed_details.append(row)
		json_data["collapsed_details"] = collapsed_details
		if (
			not json_data["data"]
			and not json_data["accessory_data"]
			and not json_data["collapsed_details"]
		):
			frappe.throw(_("Select at least one panel or accessory quantity."))
		self.cut_panel_movement_json = json_data

	def on_submit(self):
		if self.movement_from_cutting:
			update_accessory(self.cutting_plan, self.cut_panel_movement_json, submit=True)

	def on_cancel(self):
		if self.movement_from_cutting:
			update_accessory(self.cutting_plan, self.cut_panel_movement_json, submit=False)


def get_total(items):
	colour_panel = {}
	total_bundle = {}
	for colour, colour_data in (items.get("data") or {}).items():
		colour_panel[colour] = {}
		total_bundle[colour] = 0
		panels = (
			(items.get("panels") or {}).get(colour_data.get("part"), [])
			if items.get("is_set_item")
			else (items.get("panels") or [])
		)
		for item in colour_data.get("data") or []:
			moved_panel_count = 0
			for panel in panels:
				colour_panel[colour].setdefault(panel, 0)
				if panel in item and item.get(f"{panel}_moved"):
					moved_panel_count += 1
					colour_panel[colour][panel] += flt(item.get(panel))
			item["total"] = moved_panel_count
			total_bundle[colour] += moved_panel_count
	items["total_pieces"] = colour_panel
	items["total_bundles"] = total_bundle
	return items


def update_accessory(cutting_plan, movement_value, *, submit):
	movement = update_if_string_instance(movement_value)
	accessory_rows = (movement or {}).get("accessory_data") or []
	if not accessory_rows:
		return
	order = "asc" if submit else "desc"
	laysheets = frappe.get_all(
		"Cutting LaySheet",
		filters={"cutting_plan": cutting_plan, "status": "Label Printed"},
		pluck="name",
		order_by=f"lay_no {order}",
	)
	remaining = defaultdict(float)
	for row in accessory_rows:
		key = (row.get("cloth_type"), row.get("colour"), row.get("shade"), row.get("dia"))
		remaining[key] += flt(row.get("moved_weight"))

	for name in laysheets:
		doc = frappe.get_doc("Cutting LaySheet", name)
		changed = False
		for row in doc.get("cutting_laysheet_accessory_details") or []:
			key = (row.cloth_type, row.colour, row.shade, row.dia)
			needed = remaining.get(key, 0)
			if needed <= 0:
				continue
			if submit:
				available = max(flt(row.weight) - flt(row.moved_weight), 0)
				delta = min(available, needed)
				row.moved_weight = flt(row.moved_weight) + delta
			else:
				delta = min(flt(row.moved_weight), needed)
				row.moved_weight = flt(row.moved_weight) - delta
			if delta:
				changed = True
				remaining[key] -= delta
		if changed:
			doc.save(ignore_permissions=True)
	if any(value > 1e-6 for value in remaining.values()):
		frappe.throw(_("Accessory movement could not be reconciled with the Cutting LaySheets."))


def _check_unmoved_access(from_location, lot):
	if not (
		frappe.has_permission("Cut Panel Movement", "create")
		or frappe.has_permission("Cut Panel Movement", "write")
	):
		frappe.throw(_("Not permitted to prepare a Cut Panel Movement."), frappe.PermissionError)
	frappe.get_doc("Lot", lot).check_permission("read")
	frappe.has_permission("Cut Bundle Movement Ledger", "read", throw=True)
	if not frappe.db.exists("Supplier", from_location):
		frappe.throw(_("Supplier {0} does not exist.").format(from_location))


def _latest_logical_bundle_rows(rows):
	"""Return the positive latest row for each logical bundle identity.

	``set_combination`` is historical JSON text. Grouping that column directly
	in SQL treats whitespace/key-order variants as different stock buckets and
	can resurrect a consumed bundle. Compare its canonical business key in
	Python, using the same major-colour/part identity as the ledger lifecycle.
	"""
	from essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger import (
		_collapsed_set_combination_key,
	)

	latest = {}
	for row in rows:
		key = (row.cbm_key, _collapsed_set_combination_key(row.set_combination))
		current = latest.get(key)
		row_order = (row.posting_datetime, row.creation, row.name)
		if current and row_order <= (
			current.posting_datetime,
			current.creation,
			current.name,
		):
			continue
		latest[key] = row
	return sorted(
		(row for row in latest.values() if flt(row.quantity_after_transaction) > 0),
		key=lambda row: (row.lay_no, row.creation, row.name),
	)


def _get_latest_available_bundle_rows(filters):
	rows = frappe.get_all(
		"Cut Bundle Movement Ledger",
		filters=filters,
		fields=[
			"name",
			"cbm_key",
			"set_combination",
			"posting_datetime",
			"creation",
			"lay_no",
			"quantity_after_transaction",
		],
		order_by="posting_datetime desc, creation desc, name desc",
		limit_page_length=0,
	)
	return _latest_logical_bundle_rows(rows)


@frappe.whitelist()
def get_cut_bundle_unmoved_data(
	from_location,
	lot,
	posting_date,
	posting_time,
	movement_from_cutting,
	cutting_plan=None,
	bundle_colour=None,
	get_collapsed=False,
):
	_check_unmoved_access(from_location, lot)
	if cutting_plan:
		plan = frappe.get_doc("Cutting Plan", cutting_plan)
		plan.check_permission("read")
		if plan.lot != lot:
			frappe.throw(_("Cutting Plan {0} does not belong to Lot {1}.").format(plan.name, lot))
		if plan.version == "V1":
			frappe.throw(_("Cut Panel Movement is not supported for a V1 Cutting Plan."))

	production_detail = frappe.db.get_value("Lot", lot, "production_detail")
	if not production_detail:
		frappe.throw(_("Lot {0} has no Item Production Detail.").format(lot))
	sizes = get_ipd_primary_values(production_detail)
	ipd_doc = frappe.get_cached_doc("Item Production Detail", production_detail)
	panels = []
	major_part_value = None
	set_part_value = None
	set_item_combinations = {}
	indexes = {}
	if ipd_doc.is_set_item:
		major_part_value = ipd_doc.major_attribute_value
		panels = {}
		for row in ipd_doc.get("stiching_item_details") or []:
			if row.set_item_attribute_value != major_part_value:
				set_part_value = row.set_item_attribute_value
			panels.setdefault(row.set_item_attribute_value, []).append(
				row.stiching_attribute_value
			)
		for row in ipd_doc.get("set_item_combination_details") or []:
			if indexes.get(row.index):
				set_item_combinations[indexes[row.index]] = row.attribute_value
			else:
				indexes[row.index] = row.attribute_value
				set_item_combinations[row.attribute_value] = None

	posting_datetime = get_combine_datetime(posting_date, posting_time)
	latest_rows = _get_latest_available_bundle_rows(
		{
			"posting_datetime": ["<=", posting_datetime],
			"is_cancelled": 0,
			"collapsed_bundle": 0,
			"is_collapsed": 0,
			"transformed": 0,
			"supplier": from_location,
			"lot": lot,
		}
	)

	lay_details = {}
	for result in latest_rows:
		row = frappe.get_doc("Cut Bundle Movement Ledger", result.name)
		parts = row.panel
		combination = update_if_string_instance(row.set_combination) or {}
		major_colour = combination.get("major_colour") or row.colour
		if ipd_doc.is_set_item:
			major_part = combination.get("major_part")
			current = parts.split(",")[0].strip()
			if major_part and current not in panels.get(major_part, []):
				set_part = combination.get("set_part")
				if not set_part:
					set_colour = set_item_combinations.get(major_colour) or ""
					major_colour = f"({major_colour}){set_colour}-{set_part_value}"
					if set_part_value and parts not in panels.setdefault(set_part_value, []):
						panels[set_part_value].append(parts)
				else:
					if parts not in panels.setdefault(set_part, []):
						panels[set_part].append(parts)
					major_colour = f"({major_colour}){combination.get('set_colour')}-{set_part}"
			else:
				if major_part and parts not in panels.setdefault(major_part, []):
					panels[major_part].append(parts)
				if major_part:
					major_colour = f"{major_colour}-{major_part}"
		elif parts not in panels:
			panels.append(parts)

		if bundle_colour and major_colour != bundle_colour:
			continue
		combination_key = {"major_colour": combination.get("major_colour")}
		if combination.get("major_part"):
			combination_key["major_part"] = combination.get("major_part")
		key = tuple(sorted(combination_key.items()))
		panel = (
			lay_details
			.setdefault(row.lay_no, {})
			.setdefault(major_colour, {})
			.setdefault(row.bundle_no, {})
			.setdefault(row.size, {})
			.setdefault(row.shade, {})
			.setdefault(key, {})
			.setdefault(parts, {"qty": 0, "colour": row.colour})
		)
		panel["qty"] += flt(row.quantity_after_transaction)

	accessory_details = []
	if cint(movement_from_cutting):
		if not cutting_plan:
			frappe.throw(_("Cutting Plan is required for a movement from Cutting."))
		accessories = defaultdict(float)
		for laysheet_name in frappe.get_all(
			"Cutting LaySheet",
			filters={"cutting_plan": cutting_plan, "status": "Label Printed"},
			pluck="name",
		):
			laysheet = frappe.get_doc("Cutting LaySheet", laysheet_name)
			for row in laysheet.get("cutting_laysheet_accessory_details") or []:
				balance = flt(row.weight) - flt(row.moved_weight)
				if balance > 0:
					accessories[(row.cloth_item, row.cloth_type, row.colour, row.dia, row.shade)] += balance
		for (cloth_item, cloth_type, colour, dia, shade), weight in accessories.items():
			accessory_details.append(
				{
					"cloth_name": cloth_item,
					"cloth_type": cloth_type,
					"colour": colour,
					"shade": shade,
					"dia": dia,
					"weight": weight,
					"moved_weight": 0,
				}
			)

	final_data = {}
	for size in sizes:
		for lay_number, colours in lay_details.items():
			for colour, bundles in colours.items():
				for bundle_no, size_details in bundles.items():
					for current_size, shade_details in size_details.items():
						if current_size != size:
							continue
						part = colour.rsplit("-", 1)[-1] if ipd_doc.is_set_item else None
						colour_output = final_data.setdefault(colour, {"part": part, "data": []})
						for shade, combinations in shade_details.items():
							for combination, panel_rows in combinations.items():
								output = {
									"lay_no": lay_number,
									"size": size,
									"shade": shade,
									"bundle_no": bundle_no,
									"set_combination": _tuple_attributes(combination),
									"bundle_moved": False,
								}
								for panel_name, detail in panel_rows.items():
									output[panel_name] = detail["qty"]
									output[f"{panel_name}_colour"] = detail["colour"]
									output[f"{panel_name}_moved"] = False
								colour_output["data"].append(output)
	for detail in final_data.values():
		detail["data"] = sorted(detail["data"], key=itemgetter("size", "shade", "lay_no"))

	collapsed = []
	if cint(get_collapsed):
		filters = {
			"posting_datetime": ["<=", posting_datetime],
			"is_cancelled": 0,
			"collapsed_bundle": 1,
			"transformed": 0,
			"supplier": from_location,
			"lot": lot,
		}
		if bundle_colour:
			filters["colour"] = bundle_colour
		rows = _get_latest_available_bundle_rows(filters)
		for result in rows:
			row = frappe.get_doc("Cut Bundle Movement Ledger", result.name)
			collapsed.append(
				{
					"moved": False,
					"size": row.size,
					"colour": row.colour,
					"panel": row.panel,
					"quantity": row.quantity_after_transaction,
					"shade": row.shade,
					"lay_no": row.lay_no,
					"bundle_no": row.bundle_no,
					"set_combination": update_if_string_instance(row.set_combination),
					"move_qty": 0,
				}
			)

	return {
		"panels": panels,
		"data": final_data,
		"accessory_data": accessory_details,
		"is_set_item": ipd_doc.is_set_item,
		"collapsed_details": collapsed,
	}


@frappe.whitelist()
def create_stock_entry(doc_name):
	from essdee_yrp.cutting.movement import build_stock_entry_defaults

	return build_stock_entry_defaults(doc_name)


@frappe.whitelist()
def create_delivery_challan(doc_name, work_order):
	from essdee_yrp.cutting.movement import build_delivery_challan_defaults

	return build_delivery_challan_defaults(doc_name, work_order)


@frappe.whitelist()
def create_goods_received_note(
	doc_name, work_order, return_items=False, delivery_challan=None
):
	from essdee_yrp.cutting.movement import build_goods_received_note_defaults

	return build_goods_received_note_defaults(
		doc_name,
		work_order,
		return_items=return_items,
		delivery_challan=delivery_challan,
	)


def on_doctype_update():
	frappe.db.add_index("Cut Panel Movement", ["item", "lot"])
	frappe.db.add_index("Cut Panel Movement", ["against", "against_id"])
