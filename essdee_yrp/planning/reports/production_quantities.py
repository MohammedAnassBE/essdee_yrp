import frappe
from frappe import _

from essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection.sd_yrp_essdee_quality_inspection import (
	_display_colour,
)


def authorize_filter_values(doctype, values):
	"""Reject every supplied name that is absent from a permission-aware read."""
	if isinstance(values, str):
		values = frappe.parse_json(values)
	if values is None:
		return []
	if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
		frappe.throw(_("Report filter values must be a list of names."))
	values = list(dict.fromkeys(values))
	if values:
		readable = frappe.get_list(doctype, filters={"name": ["in", values]}, pluck="name", limit_page_length=0)
		if set(values) - set(readable):
			frappe.throw(_("You do not have access to one or more report filter values."), frappe.PermissionError)
	return values


def can_read(*doctypes):
	return frappe.session.user != "Guest" and all(frappe.has_permission(name, "read") for name in doctypes)


def require_report_access(allowed):
	if not allowed:
		frappe.throw(_("You do not have access to this Planning report."), frappe.PermissionError)


def column(fieldname, label, fieldtype="Data", **options):
	return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": 140, **options}


def child_rows(doctype, parents, fields, parenttype):
	if not parents:
		return []
	return frappe.get_all(doctype, filters={"parent": ["in", list(parents)], "parenttype": parenttype}, fields=["parent", *fields], limit_page_length=0)


def expand_processes(process, details=None):
	if not process:
		return []
	if details is None:
		details = frappe.get_all("YRP Process Details", fields=["parent", "process_name"], limit_page_length=0)
	def walk(start, source, target):
		found = {start}
		while True:
			added = {row[target] for row in details if row[source] in found} - found
			if not added:
				return found
			found.update(added)
	return sorted(walk(process, "parent", "process_name") | walk(process, "process_name", "parent"))


def work_orders(filters, include_rework=False, extra_fields=()):
	conditions = {"docstatus": 1, **filters}
	if not include_rework:
		conditions["is_rework"] = 0
	return frappe.get_list("YRP Work Order", filters=conditions, fields=[
		"name", "lot", "item", "process_name", "supplier", "supplier_name", "is_internal_unit",
		"first_dc_date", "last_dc_date", "first_grn_date", "last_grn_date",
		*extra_fields,
	], limit_page_length=0)


def calculated_items(orders):
	return child_rows("YRP Work Order Calculated Item", [row["name"] for row in orders], [
		"item_variant", "set_combination", "received_type_json", "received_qty", "delivered_quantity", "idx",
	], "YRP Work Order")


def supplier_names(orders):
	names = sorted({row["supplier"] for row in orders if row.get("supplier")})
	rows = frappe.get_all("Supplier", filters={"name": ["in", names]}, fields=["name", "supplier_name"], limit_page_length=0) if names else []
	return {row["name"]: row.get("supplier_name") or row["name"] for row in rows}


def actual_values(raw_values):
	names = sorted({value for value in raw_values if isinstance(value, str) and value.startswith("IAV-")})
	rows = frappe.get_all("YRP Item Attribute Value", filters={"name": ["in", names]}, fields=["name", "attribute_value"], limit_page_length=0) if names else []
	return {row["name"]: row["attribute_value"] for row in rows}


def variant_attributes(variants):
	# Batch equivalent of yrp.utils.get_variant_attr_details for an entire report.
	rows = child_rows("Item Variant Attribute", variants, ["attribute", "attribute_value"], "Item")
	values = actual_values(row["attribute_value"] for row in rows)
	result = {}
	for row in rows:
		result.setdefault(row["parent"], {})[row["attribute"]] = values.get(row["attribute_value"], row["attribute_value"])
	return result


def quantity_context(filters):
	from yrp.yrp.doctype.yrp_item.yrp_item import get_attribute_details
	from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import get_ipd_primary_values

	if not filters.get("lot") or not filters.get("process"):
		frappe.throw(_("Lot and Process are required."))
	lot = frappe.get_doc("SD YRP Lot", filters["lot"])
	lot.check_permission("read")
	authorize_filter_values("YRP Process", [filters["process"]])
	detail = frappe.get_cached_doc("YRP Item Production Detail", lot.production_detail)
	sizes = get_ipd_primary_values(detail.name) or get_attribute_details(lot.item)["primary_attribute_values"]
	orders = work_orders({"lot": lot.name, "process_name": ["in", expand_processes(filters["process"])]})
	items = calculated_items(orders)
	attributes = variant_attributes({row["item_variant"] for row in items})
	return lot, detail, sizes, orders, items, attributes


def matrix_identity(item, attributes, detail):
	combination = frappe.parse_json(item.get("set_combination") or "{}")
	variant = attributes.get(item["item_variant"], {})
	major = combination.get("major_colour", "")
	colour = _display_colour(variant, frappe._dict(set_combination=combination), {
		"colour_attribute": detail.get("packing_attribute"),
		"is_set_item": detail.get("is_set_item"),
		"set_attribute": detail.get("set_item_attribute"),
		"major_attribute_value": detail.get("major_attribute_value"),
	}) if detail.get("is_set_item") else major
	return colour or major, variant.get(detail.get("set_item_attribute"), "") if detail.get("is_set_item") else "", variant.get(detail.get("primary_item_attribute"), "")


def matrix_columns(sizes, is_set_item=False, supplier=False):
	columns = [column("number", "S.No", "Int"), column("colour", "Colour")]
	if is_set_item or supplier:
		columns.append(column("part", "Part"))
	if supplier:
		columns.append(column("supplier", "Supplier"))
	return columns + [column("type", "Type")] + [column(f"size_{index}", str(size), "Float") for index, size in enumerate(sizes)] + [column("total", "Total", "Float")]


def numeric_row(identity, quantities, sizes):
	return {**identity, **{f"size_{index}": quantities.get(size, 0) for index, size in enumerate(sizes)}, "total": sum(quantities.values())}


def validate_dates(filters):
	from frappe.utils import getdate

	start, end = filters.get("from_date"), filters.get("to_date")
	if bool(start) != bool(end):
		frappe.throw(_("Set both From Date and To Date."))
	if start and getdate(start) > getdate(end):
		frappe.throw(_("From Date cannot be after To Date."))
	return start, end


def process_comparison(process, detail):
	# Literal legacy equality: two missing stages also compare against cut.
	return "cut" if process.get("in_stage") == detail.get("stiching_in_stage") else "piece"


def production_lots(filters, category_field="category", *, creation_end_midnight=False):
	lots = authorize_filter_values("SD YRP Lot", filters.get("lot"))
	items = authorize_filter_values("Item", filters.get("item"))
	category = filters.get(category_field)
	if not lots and not items and not category:
		frappe.throw(_("Select at least one Lot, Item or Category."))
	status = filters.get("lot_status") or "Open"
	if status not in ("Open", "Closed"):
		frappe.throw(_("Lot Status must be Open or Closed."))
	conditions = {"status": status, "production_detail": ["is", "set"]}
	if lots:
		conditions["name"] = ["in", lots]
	if category:
		authorize_filter_values("SD YRP Product Category", [category])
		members = frappe.get_all("Item", filters={"product_category": category}, pluck="name", limit_page_length=0)
		category_items = frappe.get_list("Item", filters={"name": ["in", members]}, pluck="name", limit_page_length=0) if members else []
		items = [item for item in items if item in category_items] if items else category_items
		conditions["item"] = ["in", items]
	elif items:
		conditions["item"] = ["in", items]
	start, end = validate_dates(filters)
	if start:
		from frappe.utils import add_days, getdate

		conditions["creation"] = [">=", str(getdate(start))]
		conditions = [["SD YRP Lot", key, *(value if isinstance(value, list) else ["=", value])] for key, value in conditions.items()]
		# WIP preserves the legacy SQL BETWEEN date-string midnight boundary.
		conditions.append(["SD YRP Lot", "creation", "<=" if creation_end_midnight else "<", str(getdate(end) if creation_end_midnight else add_days(getdate(end), 1))])
	return frappe.get_list("SD YRP Lot", filters=conditions, fields=["name", "item", "production_detail"], order_by="name", limit_page_length=0)


def production_context(lots, processes):
	detail_names = {lot["production_detail"] for lot in lots}
	details = frappe.get_list("YRP Item Production Detail", filters={"name": ["in", list(detail_names)]}, fields=["name", "primary_item_attribute", "packing_attribute", "set_item_attribute", "is_set_item", "major_attribute_value", "stiching_in_stage", "stiching_process", "cutting_process", "packing_combo"], limit_page_length=0) if detail_names else []
	if detail_names - {row["name"] for row in details}:
		frappe.throw(_("You do not have access to a Lot's production detail."), frappe.PermissionError)
	details = {row["name"]: row for row in details}
	process_details = frappe.get_all("YRP Process Details", fields=["parent", "process_name"], limit_page_length=0)
	expanded = {process: expand_processes(process, process_details) for process in processes}
	for detail in details.values():
		for field in ("cutting_process", "stiching_process"):
			expanded.setdefault(detail.get(field), expand_processes(detail.get(field), process_details))
	stages = child_rows("YRP IPD Process", details, ["process_name", "in_stage", "out_stage"], "YRP Item Production Detail")
	order_rows = child_rows("SD YRP Lot Order Detail", [lot["name"] for lot in lots], ["item_variant", "quantity", "cut_qty", "set_combination", "idx"], "SD YRP Lot")
	orders = work_orders({"lot": ["in", [lot["name"] for lot in lots]]}, extra_fields=("includes_packing",)) if lots else []
	items = calculated_items(orders)
	attributes = variant_attributes({row["item_variant"] for row in [*order_rows, *items]})
	return {"lots": lots, "details": details, "expanded": expanded, "stages": stages, "order_rows": order_rows, "orders": orders, "items": items, "attributes": attributes}


def production_size_orders(details):
	attributes = child_rows("YRP IPD Item Attribute", details, ["attribute", "mapping"], "YRP Item Production Detail")
	mappings = {row["parent"]: row["mapping"] for row in attributes if row.get("mapping") and row["attribute"] == details[row["parent"]]["primary_item_attribute"]}
	values = child_rows("YRP Item Item Attribute Mapping Value", set(mappings.values()), ["attribute_value", "idx"], "YRP Item Item Attribute Mapping")
	labels = actual_values(row["attribute_value"] for row in values)
	return {name: [labels.get(row["attribute_value"], row["attribute_value"]) for row in sorted(values, key=lambda row: row["idx"]) if row["parent"] == mappings.get(name)] for name in details}


def finishing_context(lots, details):
	plans = frappe.get_list("SD YRP Finishing Plan", filters={"lot": ["in", [lot["name"] for lot in lots]]}, fields=["name", "lot", "pieces_per_box", "work_order"], limit_page_length=0) if lots else []
	plan_map = {row["name"]: row for row in plans}
	attributes = child_rows("YRP IPD Item Attribute", details, ["attribute", "mapping"], "YRP Item Production Detail")
	mappings = {row["mapping"] for row in attributes if row.get("mapping")}
	values = child_rows("YRP Item Item Attribute Mapping Value", mappings, ["attribute_value"], "YRP Item Item Attribute Mapping")
	counts = {mapping: sum(row["parent"] == mapping for row in values) for mapping in mappings}
	parts = {name: 1 for name in details}
	for row in attributes:
		detail = details[row["parent"]]
		if detail.get("is_set_item") and row["attribute"] == detail.get("set_item_attribute"):
			parts[row["parent"]] = counts.get(row.get("mapping")) or 1
	return {"plans": plan_map, "parts": parts,
		"dispatches": child_rows("SD YRP Finishing Plan GRN Detail", plan_map, ["item_variant", "dispatched"], "SD YRP Finishing Plan"),
		"inwards": child_rows("SD YRP Finishing Plan Detail", plan_map, ["item_variant", "dc_qty", "transferred_qty"], "SD YRP Finishing Plan")}


def dependency_doctypes(filters=None):
	return ["YRP Work Order", "YRP Work Order Calculated Item", "SD YRP Lot", "Item", "Item Variant Attribute", "YRP Item Attribute Value", "YRP Item Production Detail", "YRP IPD Item Attribute", "YRP Item Item Attribute Mapping", "YRP Item Item Attribute Mapping Value", "YRP Process", "YRP Process Details"]
