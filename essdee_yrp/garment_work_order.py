"""Desk Work Order calculation for Essdee garment processes.

The F15 ``production_api`` Work Order exposed ``Calculate Items`` for every
draft, non-rework garment Work Order.  Cloth processes use the separate fabric
calculator in :mod:`essdee_yrp.api.work_order`; this module restores the
garment path over the migrated F16 data model.
"""

import math

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from essdee_yrp.fabric_requirement import (
	calculate_accessory,
	get_cloth_combination,
	get_stich_details,
	get_stitching_combination,
)
from essdee_yrp.garment_bom import calculate_essdee_accessory_bom
from essdee_yrp.garment_bom_matrix import (
	_delete_generated_matrices,
	_get_variant_cloth_rows,
	regenerate_garment_bom_matrices,
)
from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes
from yrp.stock.uom import resolve_item_uom
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.item.item import build_variant_attributes, get_or_create_variant
from yrp.yrp.utils.ipd_engine import calculate_major_deliverables


@frappe.whitelist()
def regenerate_ipd_process_matrices(ipd_name):
	"""Rebuild derived matrices without editing the source IPD.

	This is intentionally available for approved migrated IPDs: their authored
	configuration remains immutable while missing generated child documents are
	backfilled from that approved configuration.
	"""
	ipd = frappe.get_doc("Item Production Detail", ipd_name)
	ipd.check_permission("write")

	if _is_cloth_ipd(ipd):
		from essdee_yrp.fabric_ipd import sync_fabric_process_matrices

		sync_fabric_process_matrices(ipd)
		skipped = []
		matrix_filters = {"ipd": ipd.name, "docstatus": ["<", 2]}
	else:
		variants = _garment_reference_variants(ipd)
		if not variants:
			frappe.throw(
				_("No {0} Item Variants are available for IPD {1}.").format(
					ipd.get("pack_in_stage") or "finished-stage", ipd.name
				)
			)
		valid_variants = []
		skipped = []
		has_bom_cloth = any(row.is_bom_item for row in ipd.get("cloth_detail") or [])
		for variant in variants:
			try:
				cloth_rows, _output_attrs = _get_variant_cloth_rows(ipd, variant)
			except frappe.ValidationError as exc:
				skipped.append({"item_variant": variant, "reason": cstr(exc)})
				continue
			if has_bom_cloth and not cloth_rows:
				skipped.append(
					{
						"item_variant": variant,
						"reason": _("No BOM cloth requirement was generated."),
					}
				)
				continue
			valid_variants.append(variant)
		_delete_generated_matrices(ipd.name, ipd.cutting_process, variants)
		if valid_variants:
			regenerate_garment_bom_matrices(ipd.name, valid_variants)
		matrix_filters = {
			"ipd": ipd.name,
			"process_name": ipd.cutting_process,
			"docstatus": ["<", 2],
		}

	matrices = frappe.get_all(
		"IPD Process Matrix",
		filters=matrix_filters,
		fields=["name", "process_name"],
		order_by="process_name asc, name asc",
	)
	return {
		"count": len(matrices),
		"processes": list(dict.fromkeys(row.process_name for row in matrices)),
		"skipped": skipped,
	}


@frappe.whitelist()
def get_garment_work_order_context(work_order):
	"""Return the editable Lot quantities for the legacy ``Calculate Items`` dialog."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	_validate_garment_work_order(wo)
	lot = frappe.get_doc("Lot", wo.lot)
	ipd = frappe.get_cached_doc("Item Production Detail", wo.production_detail)
	quantity_field = _quantity_field(ipd, wo.process_name, wo.get("includes_packing"))

	rows = []
	matrix_rows = []
	matrix_rows_by_key = {}
	display_attributes = []
	from yrp.yrp.doctype.item_production_detail.item_production_detail import (
		get_ipd_primary_values,
	)

	primary_values = list(get_ipd_primary_values(ipd.name) or [])
	for source in lot.get("lot_order_details") or []:
		quantity = flt(source.get(quantity_field))
		attrs = get_variant_attr_details(source.item_variant)
		visible_attrs = {
			key: value
			for key, value in attrs.items()
			if key != ipd.dependent_attribute
		}
		row = {
			"source_row": source.name,
			"item_variant": source.item_variant,
			"attributes": visible_attrs,
			"available_qty": quantity,
			"qty": quantity,
			"table_index": source.get("table_index"),
			"row_index": source.get("row_index"),
		}
		rows.append(row)

		for attribute in visible_attrs:
			if attribute != ipd.primary_item_attribute and attribute not in display_attributes:
				display_attributes.append(attribute)

		# F15's WorkOrderItemView groups the variants belonging to the same
		# Lot-order row and renders the primary attribute (normally Size) as
		# editable columns.  Keep the flat ``rows`` contract for the calculator,
		# but expose this presentation model so Desk preserves that operator UI.
		group_key = (
			cstr(source.get("table_index")),
			cstr(source.get("row_index")),
		)
		matrix_row = matrix_rows_by_key.get(group_key)
		if matrix_row is None:
			matrix_row = {
				"attributes": {
					key: value
					for key, value in visible_attrs.items()
					if key != ipd.primary_item_attribute
				},
				"values": {},
			}
			matrix_rows_by_key[group_key] = matrix_row
			matrix_rows.append(matrix_row)

		primary_value = visible_attrs.get(ipd.primary_item_attribute) or "default"
		if primary_value not in primary_values:
			primary_values.append(primary_value)
		matrix_row["values"][primary_value] = {
			"source_row": source.name,
			"item_variant": source.item_variant,
			"available_qty": quantity,
			"qty": quantity,
		}

	missing_matrix_variants = _missing_matrix_variants(ipd, wo.process_name, rows)
	return {
		"ipd": ipd.name,
		"process": wo.process_name,
		"quantity_field": quantity_field,
		"primary_attribute": ipd.primary_item_attribute,
		"primary_values": primary_values,
		"display_attributes": display_attributes,
		"matrix_rows": matrix_rows,
		"rows": rows,
		"matrix_ready": not missing_matrix_variants,
		"missing_matrix_variants": missing_matrix_variants,
	}


@frappe.whitelist()
def calculate_garment_work_order(work_order, rows, modified=None):
	"""Calculate garment deliverables/receivables from selected Lot quantities."""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("write")
	_validate_garment_work_order(wo)
	if wo.docstatus != 0:
		frappe.throw(_("Calculate can only update a draft Work Order."))
	if modified and cstr(wo.modified) != cstr(modified):
		frappe.throw(
			_("{0} was modified after you opened it. Please refresh and try again.").format(wo.name),
			frappe.TimestampMismatchError,
		)

	lot = frappe.get_doc("Lot", wo.lot)
	ipd = frappe.get_cached_doc("Item Production Detail", wo.production_detail)
	quantity_field = _quantity_field(ipd, wo.process_name, wo.get("includes_packing"))
	demands = _validated_demands(lot, ipd, rows, quantity_field)
	if not demands:
		frappe.throw(_("Enter a quantity greater than zero for at least one row."))

	processes = _processes(wo.process_name)
	first_inputs, first_outputs = _process_rows(ipd, lot, processes[0], demands)
	last_inputs, last_outputs = _process_rows(ipd, lot, processes[-1], demands)
	deliverables = first_inputs + _accessory_rows(ipd, lot, demands, processes)
	receivables = last_outputs
	core_processes = {ipd.cutting_process, ipd.stiching_process, ipd.packing_process}
	if len(processes) > 1 and not core_processes.intersection(
		(processes[0], processes[-1])
	):
		# Preserve Production API's group rule when both boundaries are IPD
		# extra processes: both boundary inputs are deliverable and both boundary
		# outputs are receivable. Main-process groups keep only the outside edges.
		deliverables += last_inputs
		receivables += first_outputs
	deliverables = _aggregate_rows(deliverables)
	receivables = _aggregate_rows(receivables)
	deliverables = normalize_item_matrix_row_indexes(deliverables)
	receivables = normalize_item_matrix_row_indexes(receivables)
	if not deliverables:
		frappe.throw(_("The IPD calculation did not produce any deliverables."))
	if not receivables and not wo.get("no_receivables"):
		frappe.throw(_("The IPD calculation did not produce any receivables."))

	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	if not default_received_type:
		frappe.throw(_("Set Default Received Type in YRP Stock Settings first."))

	wo.set("deliverables", [])
	for index, row in enumerate(deliverables):
		qty = flt(row["qty"], 3)
		wo.append(
			"deliverables",
			_filter_child_fields(
				"Work Order Deliverables",
				{
					**row,
					"qty": qty,
					"pending_quantity": qty,
					"received_type": default_received_type,
					"is_calculated": 1,
					"lot": lot.name,
					"table_index": row.get("table_index", index),
					"row_index": cstr(row.get("row_index", index)),
				},
			),
		)

	wo.set("receivables", [])
	for index, row in enumerate(receivables):
		qty = flt(row["qty"], 3)
		wo.append(
			"receivables",
			_filter_child_fields(
				"Work Order Receivables",
				{
					**row,
					"qty": qty,
					"pending_quantity": qty,
					"lot": lot.name,
					"table_index": row.get("table_index", index),
					"row_index": cstr(row.get("row_index", index)),
				},
			),
		)

	wo.set("work_order_calculated_items", [])
	for index, demand in enumerate(demands):
		wo.append(
			"work_order_calculated_items",
			{
				"item_variant": demand["item_variant"],
				"quantity": demand["qty"],
				"table_index": demand["table_index"],
				"row_index": demand["row_index"] if demand["row_index"] is not None else index,
				"set_combination": demand["set_combination"],
			},
		)
	wo.deliverable_details = ""
	wo.receivable_details = ""
	wo.wo_colours = _colour_summary(ipd, demands)
	wo.save()
	_update_cutting_tracking_json(wo, ipd, processes)

	return {
		"deliverables": len(deliverables),
		"receivables": len(receivables),
		"calculated_items": len(demands),
	}


def _is_cloth_ipd(ipd):
	return bool(
		ipd.get("is_cloth_item")
		or frappe.db.get_value("Item", ipd.item, "is_cloth_item")
	)


def _validate_garment_work_order(wo):
	if wo.get("is_rework"):
		frappe.throw(_("Use the rework item editor for a Rework Work Order."))
	if not wo.lot or not wo.process_name or not wo.production_detail:
		frappe.throw(_("Set Process, Lot, Item, and Item Production Detail first."))
	if frappe.db.get_value("Process", wo.process_name, "is_cloth_process"):
		frappe.throw(_("Use Calculate Fabric Deliverables for a cloth process."))
	lot_ipd = frappe.db.get_value("Lot", wo.lot, "production_detail")
	if lot_ipd != wo.production_detail:
		frappe.throw(_("Work Order Item Production Detail must match Lot {0}.").format(wo.lot))


def _garment_reference_variants(ipd):
	filters = {"item": ipd.item}
	if ipd.dependent_attribute and ipd.get("pack_in_stage"):
		parents = frappe.get_all(
			"Item Variant Attribute",
			filters={
				"parenttype": "Item Variant",
				"attribute": ipd.dependent_attribute,
				"attribute_value": ipd.pack_in_stage,
			},
			pluck="parent",
		)
		if not parents:
			return []
		filters["name"] = ["in", parents]
	return frappe.get_all(
		"Item Variant", filters=filters, pluck="name", order_by="name asc", limit_page_length=0
	)


def _processes(process_name):
	process = frappe.get_cached_doc("Process", process_name)
	if not process.get("is_group"):
		return [process_name]
	processes = [row.process_name for row in process.get("process_details") or [] if row.process_name]
	if not processes:
		frappe.throw(_("Process group {0} has no sub-processes.").format(process_name))
	return processes


def _quantity_field(ipd, process_name, includes_packing=False):
	process = _processes(process_name)[0]
	if includes_packing:
		return "cut_qty"
	if process == ipd.cutting_process:
		return "quantity"
	if process == ipd.stiching_process:
		return "cut_qty"
	if process == ipd.packing_process:
		return "stich_qty"
	row = next((row for row in ipd.get("ipd_processes") or [] if row.process_name == process), None)
	if not row:
		frappe.throw(_("Mention process {0} in Item Production Detail {1}.").format(process, ipd.name))
	stage = row.get("in_stage") or row.get("stage")
	if stage == ipd.stiching_in_stage:
		return "cut_qty"
	if stage == ipd.pack_in_stage:
		return "stich_qty"
	if stage == ipd.pack_out_stage:
		return "pack_qty"
	frappe.throw(
		_("Process {0} has no supported input stage on Item Production Detail {1}.").format(
			process, ipd.name
		)
	)


def _validated_demands(lot, ipd, rows, quantity_field):
	rows = rows or []
	by_name = {row.name: row for row in lot.get("lot_order_details") or []}
	demands = []
	seen = set()
	for incoming in rows:
		source_name = incoming.get("source_row")
		if not source_name or source_name in seen:
			frappe.throw(_("Each Lot row may be selected only once."))
		seen.add(source_name)
		source = by_name.get(source_name)
		if not source:
			frappe.throw(_("Unknown Lot Order Detail row {0}.").format(source_name))
		qty = flt(incoming.get("qty"))
		if qty <= 0:
			continue
		available = flt(source.get(quantity_field))
		if qty > available + 0.001:
			frappe.throw(
				_("Quantity {0} exceeds available {1} for {2}.").format(
					qty, available, source.item_variant
				)
			)
		attrs = get_variant_attr_details(source.item_variant)
		if frappe.db.get_value("Item Variant", source.item_variant, "item") != ipd.item:
			frappe.throw(_("Item Variant {0} does not belong to IPD {1}.").format(source.item_variant, ipd.name))
		demands.append(
			{
				"item_variant": source.item_variant,
				"qty": qty,
				"attrs": attrs,
				"table_index": cint(source.table_index),
				"row_index": cint(source.row_index),
				"set_combination": source.set_combination or "{}",
			}
		)
	return demands


def _missing_matrix_variants(ipd, process_name, rows):
	if ipd.cutting_process not in _processes(process_name):
		return []
	references = {row["item_variant"] for row in rows if flt(row.get("qty")) > 0}
	if not references:
		return []
	found = set(
		frappe.get_all(
			"IPD Process Matrix",
			filters={
				"ipd": ipd.name,
				"process_name": ipd.cutting_process,
				"reference_item_variant": ["in", list(references)],
				"docstatus": ["<", 2],
			},
			pluck="reference_item_variant",
		)
	)
	return sorted(references.difference(found))


def _process_rows(ipd, lot, process_name, demands):
	if process_name == ipd.cutting_process:
		return _cutting_inputs(ipd, process_name, demands), (
			_panel_rows(ipd, demands, ipd.stiching_in_stage)
			+ _cutting_accessory_outputs(ipd, demands)
		)
	if process_name == ipd.stiching_process:
		return (
			_panel_rows(ipd, demands, ipd.stiching_in_stage),
			_stage_rows(ipd, demands, ipd.pack_in_stage),
		)
	if process_name == ipd.packing_process:
		return (
			_stage_rows(ipd, demands, ipd.pack_in_stage),
			_packing_rows(ipd, lot, demands),
		)

	process_row = next(
		(row for row in ipd.get("ipd_processes") or [] if row.process_name == process_name),
		None,
	)
	if not process_row:
		frappe.throw(_("Mention process {0} in Item Production Detail {1}.").format(process_name, ipd.name))
	in_stage = process_row.get("in_stage") or process_row.get("stage")
	out_stage = process_row.get("out_stage") or in_stage
	inputs = (
		_panel_rows(ipd, demands, in_stage, process_name=process_name)
		if in_stage == ipd.stiching_in_stage
		else _stage_rows(ipd, demands, in_stage)
	)
	outputs = (
		_panel_rows(ipd, demands, out_stage, process_name=process_name)
		if out_stage == ipd.stiching_in_stage
		else _stage_rows(ipd, demands, out_stage)
	)
	return inputs, outputs


def _cutting_inputs(ipd, process_name, demands):
	missing = [
		demand["item_variant"]
		for demand in demands
		if not frappe.db.exists(
			"IPD Process Matrix",
			{
				"ipd": ipd.name,
				"process_name": process_name,
				"reference_item_variant": demand["item_variant"],
				"docstatus": ["<", 2],
			},
		)
	]
	if missing:
		frappe.throw(
			_(
				"IPD {0} has no generated Cutting matrix for {1}. Open the IPD and click "
				"Generate / Regenerate IPD Process Matrix."
			).format(ipd.name, ", ".join(missing[:5]))
		)
	calculated = calculate_major_deliverables(
		ipd.name,
		[{"item_variant": row["item_variant"], "qty": row["qty"]} for row in demands],
		process_names=[process_name],
	)
	return [
		{
			"item_variant": row["item_variant"],
			"qty": flt(row["required_qty"], 3),
			"uom": row.get("uom"),
			"set_combination": "{}",
		}
		for row in calculated
		if flt(row.get("required_qty")) > 0
	]


def _cutting_accessory_outputs(ipd, demands):
	"""Return the legacy Cutting receivable rows for cut cloth accessories."""
	accessory_types = update_if_string_instance(ipd.get("accessory_clothtype_json")) or {}
	if not accessory_types:
		return []
	cloth_combination = get_cloth_combination(ipd)
	stitching_combination = get_stitching_combination(ipd)
	cloth_items = {
		row.name1: row.cloth
		for row in ipd.get("cloth_detail") or []
		if row.name1 and row.cloth
	}
	rows = []
	for demand in demands:
		attrs = {
			key: value
			for key, value in demand["attrs"].items()
			if key != ipd.dependent_attribute
		}
		for requirement in calculate_accessory(
			ipd,
			cloth_combination,
			stitching_combination,
			attrs,
			demand["qty"],
		):
			cloth_item = cloth_items.get(requirement["cloth_type"])
			if not cloth_item:
				frappe.throw(
					_("Accessory cloth type {0} is not mapped in Cloth Detail.").format(
						requirement["cloth_type"]
					)
				)
			variant = get_or_create_variant(
				cloth_item,
				{
					ipd.packing_attribute: requirement["colour"],
					"Dia": requirement["dia"],
				},
			)
			rows.append(
				{
					"item_variant": variant,
					"qty": flt(requirement["quantity"], 3),
					"uom": frappe.db.get_value(
						"Item", cloth_item, "default_unit_of_measure"
					),
					"set_combination": "{}",
					"table_index": demand["table_index"],
					"row_index": demand["row_index"],
					"is_accessory": 1,
				}
			)
	return rows


def _panel_rows(ipd, demands, stage, process_name=None):
	combination = get_stitching_combination(ipd)
	panel_counts = combination.get("stitching_attribute_count") or {}
	panel_colours = combination.get("stitching_combination") or {}
	allowed_panels = None
	if process_name:
		embellishments = update_if_string_instance(ipd.get("emblishment_details_json")) or {}
		if embellishments.get(process_name):
			allowed_panels = set(embellishments[process_name])
	rows = []
	set_parts = get_stich_details(ipd) if ipd.get("is_set_item") else {}
	for demand in demands:
		attrs = dict(demand["attrs"])
		major_colour = attrs.get(ipd.packing_attribute)
		key = major_colour
		if ipd.get("is_set_item"):
			key = (major_colour, attrs.get(ipd.set_item_attribute))
		mapped = panel_colours.get(key) or {}
		for panel, count in panel_counts.items():
			if allowed_panels is not None and panel not in allowed_panels:
				continue
			if ipd.get("is_set_item") and set_parts.get(panel) != attrs.get(ipd.set_item_attribute):
				continue
			panel_attrs = dict(attrs)
			panel_attrs[ipd.stiching_attribute] = panel
			panel_attrs[ipd.packing_attribute] = mapped.get(panel) or major_colour
			variant = get_or_create_variant(
				ipd.item,
				build_variant_attributes(panel_attrs, stage, ipd.name),
				dependent_attr=ipd.dependent_attribute_mapping,
			)
			rows.append(
				{
					"item_variant": variant,
					"qty": flt(demand["qty"] * flt(count), 3),
					"set_combination": demand["set_combination"],
					"table_index": demand["table_index"],
					"row_index": f"{demand['table_index']}{demand['row_index']}{len(rows)}",
				}
			)
	return rows


def _stage_rows(ipd, demands, stage):
	rows = []
	for demand in demands:
		variant = get_or_create_variant(
			ipd.item,
			build_variant_attributes(demand["attrs"], stage, ipd.name),
			dependent_attr=ipd.dependent_attribute_mapping,
		)
		rows.append(
			{
				"item_variant": variant,
				"qty": demand["qty"],
				"set_combination": demand["set_combination"],
				"table_index": demand["table_index"],
				"row_index": demand["row_index"],
			}
		)
	return rows


def _packing_rows(ipd, lot, demands):
	dynamic_ratio = bool(
		ipd.get("based_on_other_attribute_mapping")
		and ipd.get("packing_mode") == "Size Ratio Packing"
	)
	parts_count = len({row.set_item_attribute_value for row in ipd.get("stiching_item_details") or [] if row.set_item_attribute_value}) or 1
	rows = []
	for demand in demands:
		attrs = dict(demand["attrs"])
		size = attrs.get(ipd.primary_item_attribute)
		if not size:
			continue
		quantity = flt(demand["qty"])
		if not dynamic_ratio:
			quantity /= parts_count
			input_uom = resolve_item_uom(demand["item_variant"]).uom
			output_variant = get_or_create_variant(
				ipd.item,
				build_variant_attributes({ipd.primary_item_attribute: size}, ipd.pack_out_stage, ipd.name),
				dependent_attr=ipd.dependent_attribute_mapping,
			)
			output_uom = resolve_item_uom(output_variant).uom
			quantity = math.ceil(quantity * _uom_factor(ipd.item, input_uom, output_uom))
		else:
			output_variant = get_or_create_variant(
				ipd.item,
				build_variant_attributes({ipd.primary_item_attribute: size}, ipd.pack_out_stage, ipd.name),
				dependent_attr=ipd.dependent_attribute_mapping,
			)
		rows.append(
			{
				"item_variant": output_variant,
				"qty": quantity,
				"set_combination": "{}",
				"table_index": 0,
				"row_index": demand["row_index"],
			}
		)
	return rows


def _uom_factor(item_name, from_uom, to_uom):
	if from_uom == to_uom:
		return 1
	item = frappe.get_cached_doc("Item", item_name)
	factors = {
		row.uom: flt(row.conversion_factor)
		for row in item.get("uom_conversion_details") or []
		if row.uom
	}
	from_factor = factors.get(from_uom)
	to_factor = factors.get(to_uom)
	if not from_factor or not to_factor:
		frappe.throw(
			_("Missing UOM conversion from {0} to {1} on Item {2}.").format(
				from_uom, to_uom, item_name
			)
		)
	return from_factor / to_factor


def _accessory_rows(ipd, lot, demands, processes):
	calculated = calculate_essdee_accessory_bom(
		ipd.name,
		[{"item_variant": row["item_variant"], "qty": row["qty"]} for row in demands],
		lot,
	)
	process_set = set(processes)
	return [
		{
			"item_variant": row["item_variant"],
			"qty": flt(row["required_qty"], 3),
			"uom": row.get("uom"),
			"set_combination": "{}",
		}
		for row in calculated
		if row.get("process_name") in process_set and flt(row.get("required_qty")) > 0
	]


def _aggregate_rows(rows):
	aggregated = {}
	for row in rows:
		qty = flt(row.get("qty"))
		if qty <= 0:
			continue
		combination = update_if_string_instance(row.get("set_combination")) or {}
		key = (
			row.get("item_variant"),
			tuple(sorted(combination.items())),
			row.get("uom"),
			row.get("table_index"),
			cstr(row.get("row_index")),
		)
		if key not in aggregated:
			aggregated[key] = {
				**row,
				"qty": 0,
				"set_combination": frappe.as_json(combination),
			}
		aggregated[key]["qty"] += qty
	return list(aggregated.values())


def _filter_child_fields(doctype, values):
	meta = frappe.get_meta(doctype)
	return {key: value for key, value in values.items() if meta.get_field(key)}


def _colour_summary(ipd, demands):
	colours = list(
		dict.fromkeys(
			row["attrs"].get(ipd.packing_attribute)
			for row in demands
			if row["attrs"].get(ipd.packing_attribute)
		)
	)
	return ", ".join(colours) if colours else "All"


def _update_cutting_tracking_json(work_order, ipd, processes):
	cut_stage_processes = {
		row.process_name
		for row in ipd.get("ipd_processes") or []
		if (row.get("in_stage") or row.get("stage")) == ipd.stiching_in_stage
	}
	sets_received = ipd.cutting_process in processes or bool(cut_stage_processes.intersection(processes))
	sets_delivered = ipd.stiching_process in processes or bool(cut_stage_processes.intersection(processes))
	if not (sets_received or sets_delivered):
		work_order.completed_items_json = "{}"
		work_order.incompleted_items_json = "{}"
		work_order.wo_delivered_completed_json = "{}"
		work_order.wo_delivered_incompleted_json = "{}"
		work_order.save()
		return

	from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import (
		get_complete_incomplete_structure,
	)
	from essdee_yrp.essdee_yrp.doctype.lot.lot import fetch_order_item_details

	items = fetch_order_item_details(
		work_order.get("work_order_calculated_items") or [], ipd.name
	)
	complete, incomplete = get_complete_incomplete_structure(ipd.name, items)
	if sets_received:
		work_order.completed_items_json = complete
		work_order.incompleted_items_json = incomplete
	if sets_delivered:
		work_order.wo_delivered_completed_json = complete
		work_order.wo_delivered_incompleted_json = incomplete
	work_order.save()
