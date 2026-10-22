import json

# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from six import string_types
from yrp.attribute_links import value as _attribute_value
from yrp.yrp.doctype.yrp_item.yrp_item import get_attribute_details
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import get_ipd_primary_values

from essdee_yrp.cutting.parent_adapter import (
	get_detail_doc,
	get_parent_context,
	get_parent_ref,
	get_primary_sizes,
	validate_parent_status,
)
from essdee_yrp.cutting.parent_adapter import (
	get_panels as adapter_get_panels,
)


class SDYRPCuttingMarker(Document):
	def onload(self):
		items = fetch_marker_details(self.cutting_marker_ratios, self.selected_type)
		items2 = fetch_group_marker_details(self.calculated_parts, self.cutting_marker_groups)
		details = {
			"cutting_marker_ratios": items,
			"cutting_marker_groups": items2,
		}
		self.set_onload("marker_detail", details)

	def autoname(self):
		self.naming_series = "CM-.YY..MM.-.{#####}."

	def before_submit(self):
		if not self.length or not self.width:
			frappe.throw("Enter the Values for Length and Width")

		if self.version == "V3" and len(self.cutting_marker_groups) == 0:
			items = []
			for part in self.calculated_parts.split(","):
				part = part.strip()
				items.append({"group_panels": part})
			self.set("cutting_marker_groups", items)

	def before_validate(self):
		if not self.cutting_plan and not self.cutting_order:
			frappe.throw("Either Cutting Plan or Cutting Order is required")

		parent_dt, parent_name = get_parent_ref(self)
		validate_parent_status(parent_dt, parent_name)

		# Populate fields server-side (covers CO path where fetch_from won't fire)
		ctx = get_parent_context(parent_dt, parent_name)
		self.item = ctx["item"]
		self.lot = ctx.get("lot")
		self.version = ctx.get("version") or "V3"
		self.is_manual_entry = ctx.get("is_manual_entry") or 0

		if self.required_piece_weight:
			min_wt = frappe.db.get_single_value("SD YRP MRP Settings", "piece_weight_min") or 0
			max_wt = frappe.db.get_single_value("SD YRP MRP Settings", "piece_weight_max") or 0
			if min_wt and max_wt and not (min_wt <= self.required_piece_weight <= max_wt):
				frappe.throw(
					f"Required piece weight {self.required_piece_weight} kg is outside the allowed range ({min_wt} - {max_wt} kg)."
				)

		if self.get("marker_details"):
			marker_details = self.marker_details["ratio_items"]
			items = []
			if self.selected_type == "Manual":
				for item in marker_details:
					ratio = round(item["ratio"], 1)
					str_num = str(ratio)
					if "." in str_num:
						precision = int(str_num.split(".")[1]) % 10
						if not (precision == 5 or precision == 0):
							frappe.throw(f"Size {_attribute_value(item['size'])}: only 0.5 increments are allowed.")
					items.append(
						{
							"size": _attribute_value(item["size"]),
							"panel": _attribute_value(item["panel"]),
							"ratio": ratio,
						}
					)
			else:
				if self.calculated_parts:
					panels = self.calculated_parts.split(",")
					for item in marker_details:
						ratio = round(item["ratio"], 1)
						str_num = str(ratio)
						if "." in str_num:
							precision = int(str_num.split(".")[1]) % 10
							if not (precision == 5 or precision == 0):
								frappe.throw(f"Size {_attribute_value(item['size'])}: only 0.5 increments are allowed.")
						for panel in panels:
							items.append(
								{"size": _attribute_value(item["size"]), "panel": panel, "ratio": ratio}
							)
			self.set("cutting_marker_ratios", items)

			group_items = self.marker_details["group_items"]
			items2 = []
			for item in group_items:
				item["selected"].sort()
				selected = ",".join(item["selected"])
				if selected:
					items2.append(
						{
							"group_panels": selected,
						}
					)
			self.set("cutting_marker_groups", items2)


def fetch_marker_details(marker_details, selected_type):
	items = []
	if selected_type == "Manual":
		for item in marker_details:
			items.append(
				{
					"size": _attribute_value(item.size),
					"panel": _attribute_value(item.panel),
					"ratio": round(item.ratio, 1),
				}
			)
	else:
		sizes = []
		for item in marker_details:
			if _attribute_value(item.size) not in sizes:
				sizes.append(_attribute_value(item.size))
				items.append(
					{
						"size": _attribute_value(item.size),
						"panel": _attribute_value(item.panel),
						"ratio": item.ratio,
					}
				)
	return items


def fetch_group_marker_details(calculated_parts, cutting_marker_groups):
	options = []
	items = []
	if calculated_parts:
		panels = calculated_parts.split(",")
		for panel in panels:
			options.append({"option": panel, "id": panel})
		index = 0
		for item in cutting_marker_groups:
			panels = item.group_panels.split(",")
			default_list = []
			for panel in panels:
				default_list.append(panel)

			items.append(
				{
					"id": index,
					"options": options,
					"setDefault": True,
					"defaultList": default_list,
					"selected": panels,
				}
			)
			index += 1
	return items


@frappe.whitelist()
def get_primary_and_bundle_detail(
	lot=None, selected_value=None, panels=None, grp_panels=None, cutting_order=None
):
	if cutting_order:
		frappe.get_doc("SD YRP Cutting Order", cutting_order).check_permission("read")
		primary_values = get_primary_sizes("SD YRP Cutting Order", cutting_order)
	else:
		frappe.get_doc("SD YRP Lot", lot).check_permission("read")
		ipd = frappe.get_value("SD YRP Lot", lot, "production_detail")
		primary_values = get_ipd_primary_values(ipd)
	primary_attributes = []
	if isinstance(panels, string_types):
		panels = json.loads(panels)
	for attr in primary_values:
		if selected_value == "Machine":
			primary_attributes.append(
				{
					"size": attr,
					"ratio": 0,
				}
			)
		else:
			for panel in panels:
				primary_attributes.append(
					{
						"size": attr,
						"panel": panel,
						"ratio": 0,
					}
				)
	grp_items = []
	if not cutting_order:
		doc = frappe.get_doc("YRP Item Production Detail", ipd)
		if len(doc.cutting_marker_groups) > 0:
			d = {}
			grp_panels = frappe.json.loads(grp_panels)
			idx = 0
			for grp_panel in grp_panels:
				grp_panels[idx] = {
					"option": grp_panel,
					"id": grp_panel,
				}
				idx += 1
			for row in doc.cutting_marker_groups:
				for p in row.group_panels.split(","):
					d[p] = row.group_panels.split(",")
			grouped_panels = []
			for panel in panels:
				if panel not in grouped_panels:
					grp_list = d[panel]
					check = True
					for p in grp_list:
						if p not in panels:
							check = False
							break
					if check:
						for p in grp_list:
							grouped_panels.append(p)
						grp_items.append(
							{
								"options": grp_panels,
								"defaultList": d[panel],
								"id": len(grp_items),
								"selected": d[panel],
							}
						)
					else:
						grp_items = []
						break

	return {
		"primary": primary_attributes,
		"grp_items": grp_items,
	}


@frappe.whitelist()
def calculate_parts(cutting_plan=None, cutting_order=None):
	if cutting_order:
		frappe.get_doc("SD YRP Cutting Order", cutting_order).check_permission("read")
		return adapter_get_panels("SD YRP Cutting Order", cutting_order)
	frappe.get_doc("SD YRP Cutting Plan", cutting_plan).check_permission("read")
	ipd = frappe.get_value("SD YRP Cutting Plan", cutting_plan, "production_detail")
	ipd_doc = frappe.get_doc("YRP Item Production Detail", ipd)
	attribute_list = []
	for item in ipd_doc.stiching_item_details:
		attribute_list.append(
			{
				"part": _attribute_value(item.stiching_attribute_value),
			}
		)
	return attribute_list


@frappe.whitelist()
def get_panels_and_size(lot=None, cutting_plan=None, cutting_order=None):
	if cutting_order:
		primary_values = get_primary_sizes("SD YRP Cutting Order", cutting_order)
		panels = calculate_parts(cutting_order=cutting_order)
	else:
		frappe.get_doc("SD YRP Lot", lot).check_permission("read")
		ipd = frappe.get_value("SD YRP Lot", lot, "production_detail")
		primary_values = get_ipd_primary_values(ipd)
		panels = calculate_parts(cutting_plan=cutting_plan)
	return {
		"sizes": primary_values,
		"panels": panels,
	}


def _web_marker_payload(doc):
	from essdee_yrp.print_registry import get_document_print_formats

	doc.run_method("onload")
	marker_detail = (doc.get("__onload") or {}).get("marker_detail") or {}
	return {
		"name": doc.name,
		"docstatus": doc.docstatus,
		"modified": doc.modified,
		"marker_name": doc.marker_name,
		"length": doc.length,
		"width": doc.width,
		"total_no_of_plys": doc.total_no_of_plys,
		"efficiency": doc.efficiency,
		"required_piece_weight": doc.required_piece_weight,
		"selected_type": doc.selected_type or "Machine",
		"calculated_parts": doc.calculated_parts,
		"panels": [part.strip() for part in (doc.calculated_parts or "").split(",") if part.strip()],
		"ratio_items": marker_detail.get("cutting_marker_ratios") or [],
		"group_items": marker_detail.get("cutting_marker_groups") or [],
		"print_formats": get_document_print_formats(doc),
		"permissions": {
			"can_write": bool(doc.docstatus == 0 and frappe.has_permission(doc.doctype, "write", doc=doc)),
			"can_submit": bool(doc.docstatus == 0 and frappe.has_permission(doc.doctype, "submit", doc=doc)),
			"can_cancel": bool(doc.docstatus == 1 and frappe.has_permission(doc.doctype, "cancel", doc=doc)),
			"can_print": bool(frappe.has_permission(doc.doctype, "print", doc=doc)),
		},
	}


def _web_parent(cutting_plan=None, cutting_order=None):
	if cutting_order:
		doc = frappe.get_doc("SD YRP Cutting Order", cutting_order)
		return doc, "SD YRP Cutting Order", cutting_order, "cutting_order"
	if cutting_plan:
		doc = frappe.get_doc("SD YRP Cutting Plan", cutting_plan)
		return doc, "SD YRP Cutting Plan", cutting_plan, "cutting_plan"
	frappe.throw("Cutting Plan or Cutting Order is required")


def _web_parent_can_start(parent_doc, parent_field):
	if parent_doc.docstatus != 1:
		return False
	if parent_field == "cutting_plan":
		return parent_doc.cp_status != "Planned"
	return parent_doc.co_status != "Completed"


@frappe.whitelist()
def get_web_marker(cutting_plan=None, marker=None, cutting_order=None):
	parent_doc, _parent_dt, parent_name, parent_field = _web_parent(cutting_plan, cutting_order)
	parent_doc.check_permission("read")
	context = get_panels_and_size(
		lot=parent_doc.get("lot"),
		cutting_plan=cutting_plan,
		cutting_order=cutting_order,
	)
	context["panels"] = [row.get("part") for row in context.get("panels") or [] if row.get("part")]
	context["is_manual_entry"] = bool(parent_doc.get("is_manual_entry"))
	context["can_create"] = bool(
		_web_parent_can_start(parent_doc, parent_field)
		and frappe.has_permission("SD YRP Cutting Marker", "create")
	)
	context["can_submit"] = bool(frappe.has_permission("SD YRP Cutting Marker", "submit"))
	if not marker:
		return {"marker": None, "context": context}

	doc = frappe.get_doc("SD YRP Cutting Marker", marker)
	doc.check_permission("read")
	if doc.get(parent_field) != parent_name:
		frappe.throw(f"This Cutting Marker does not belong to the selected {parent_doc.doctype}")
	return {"marker": _web_marker_payload(doc), "context": context}


@frappe.whitelist()
def save_web_marker(
	cutting_plan=None,
	values=None,
	marker=None,
	submit=False,
	cutting_order=None,
	expected_modified=None,
):
	parent_doc, parent_dt, parent_name, parent_field = _web_parent(cutting_plan, cutting_order)
	parent_doc.check_permission("read")
	if not _web_parent_can_start(parent_doc, parent_field):
		frappe.throw(f"The {parent_dt} is not available for a new or updated marker")

	values = frappe.parse_json(values) if isinstance(values, string_types) else values
	values = values or {}
	if marker:
		doc = frappe.get_doc("SD YRP Cutting Marker", marker)
		doc.check_permission("write")
		if expected_modified and str(doc.modified) != str(expected_modified):
			frappe.throw(
				"This Cutting Marker changed after it was opened. Reload it and try again.",
				frappe.TimestampMismatchError,
			)
		if doc.get(parent_field) != parent_name:
			frappe.throw(f"This Cutting Marker does not belong to the selected {parent_dt}")
		if doc.docstatus != 0:
			frappe.throw("Only a Draft Cutting Marker can be edited")
	else:
		frappe.has_permission("SD YRP Cutting Marker", "create", throw=True)
		doc = frappe.new_doc("SD YRP Cutting Marker")
		doc.set(parent_field, parent_name)

	allowed_fields = (
		"marker_name",
		"length",
		"width",
		"total_no_of_plys",
		"efficiency",
		"required_piece_weight",
	)
	for fieldname in allowed_fields:
		if fieldname in values:
			setattr(doc, fieldname, values.get(fieldname))

	selected_type = values.get("selected_type") or "Machine"
	if selected_type not in ("Machine", "Manual"):
		frappe.throw("Select Type must be Machine or Manual")
	available_panels = {
		row.get("part")
		for row in calculate_parts(cutting_plan=cutting_plan, cutting_order=cutting_order) or []
		if row.get("part")
	}
	panels = [str(part).strip() for part in values.get("panels") or [] if str(part).strip()]
	if not panels:
		frappe.throw("Select at least one panel")
	invalid_panels = sorted(set(panels) - available_panels)
	if invalid_panels:
		frappe.throw(f"Invalid panel(s): {', '.join(invalid_panels)}")

	ratio_items = values.get("ratio_items") or []
	available_sizes = set(get_primary_sizes(parent_dt, parent_name))
	expected_ratio_keys = (
		{(size, panel) for size in available_sizes for panel in panels}
		if selected_type == "Manual"
		else {(size, None) for size in available_sizes}
	)
	ratio_keys = []
	for row in ratio_items:
		size = row.get("size")
		panel = row.get("panel") if selected_type == "Manual" else None
		ratio_keys.append((size, panel))
	if set(ratio_keys) != expected_ratio_keys or len(ratio_keys) != len(set(ratio_keys)):
		frappe.throw("The marker ratios must contain every available size exactly once")
	if not parent_doc.get("is_manual_entry") and not any(frappe.utils.flt(row.get("ratio")) > 0 for row in ratio_items):
		frappe.throw("Enter the Ratio Values")
	if selected_type == "Manual":
		for row in ratio_items:
			if row.get("panel") not in panels:
				frappe.throw(f"Ratio panel {row.get('panel')} is not selected")

	group_items = values.get("group_items") or [
		{"id": index, "selected": [panel]} for index, panel in enumerate(panels)
	]
	grouped_panels = [panel for row in group_items for panel in row.get("selected") or []]
	if sorted(grouped_panels) != sorted(panels) or len(grouped_panels) != len(set(grouped_panels)):
		frappe.throw("Each selected panel must belong to exactly one group")

	doc.selected_type = selected_type
	doc.calculated_parts = ",".join(panels)
	doc.marker_details = {
		"ratio_items": ratio_items,
		"group_items": group_items,
	}
	doc.save()
	if frappe.utils.sbool(submit):
		doc.check_permission("submit")
		doc.submit()
	return _web_marker_payload(doc)


@frappe.whitelist()
def change_web_marker_status(cutting_plan=None, marker=None, action=None, cutting_order=None):
	parent_doc, parent_dt, parent_name, parent_field = _web_parent(cutting_plan, cutting_order)
	parent_doc.check_permission("read")
	doc = frappe.get_doc("SD YRP Cutting Marker", marker)
	if doc.get(parent_field) != parent_name:
		frappe.throw(f"This Cutting Marker does not belong to the selected {parent_dt}")
	if action == "submit":
		doc.check_permission("submit")
		if doc.docstatus != 0:
			frappe.throw("Only a Draft Cutting Marker can be submitted")
		doc.submit()
	elif action == "cancel":
		doc.check_permission("cancel")
		if doc.docstatus != 1:
			frappe.throw("Only a Submitted Cutting Marker can be cancelled")
		doc.cancel()
	else:
		frappe.throw("Unsupported Cutting Marker action")
	return _web_marker_payload(doc)


CuttingMarker = SDYRPCuttingMarker
