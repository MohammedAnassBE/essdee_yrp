"""Essdee-specific Delivery Challan defaults from the selected Work Order."""

import frappe
from frappe import _
from frappe.utils import cint, flt

from essdee_yrp.cloth_execution import (
	get_row_execution_parameters,
	get_supported_execution_route,
	qualifies_cloth_transaction,
)


@frappe.whitelist()
def create_return_grn(doc_name, items, received_type=None, cut_panel_movement=None):
	"""Create the base-authorized return draft and optionally bind whole bundles."""
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		create_return_grn as create_base_return_grn,
	)

	name = create_base_return_grn(doc_name, items, received_type)
	if cut_panel_movement:
		grn = frappe.get_doc("YRP Goods Received Note", name)
		grn.cut_panel_movement = cut_panel_movement
		grn.save()
	return name


def onload(doc, method=None):
	"""Default Desk's print letter head like F15, and render a cutting DC as one panel/colour row with Size columns."""
	del method
	from essdee_yrp.print_helpers import get_dc_grn_letter_head

	doc.letter_head = get_dc_grn_letter_head(doc)
	if not doc.get("cut_panel_movement"):
		return

	from yrp.stock.save_stock_items import group_items_for_ui

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes

	doc.set_onload(
		"item_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("items") or []),
			"YRP Delivery Challan",
		),
	)


WORK_ORDER_FETCH_FIELDS = (
	"is_rework",
	"lot",
	"includes_packing",
)


def before_validate(doc, method=None):
	"""Keep Essdee's read-only Work Order context authoritative on the DC."""
	from essdee_yrp.cutting.movement import validate_transaction_link

	validate_transaction_link(doc)
	if not doc.work_order:
		return

	work_order_meta = frappe.get_meta("YRP Work Order")
	fieldnames = [
		fieldname
		for fieldname in WORK_ORDER_FETCH_FIELDS
		if work_order_meta.get_field(fieldname) and doc.meta.get_field(fieldname)
	]
	if not fieldnames:
		return

	values = frappe.db.get_value("YRP Work Order", doc.work_order, fieldnames, as_dict=True)
	if not values:
		return

	for fieldname in fieldnames:
		doc.set(fieldname, values.get(fieldname))
	# ``is_internal_unit`` deliberately is not copied from Work Order.  The WO
	# flag says only that its supplier is a company location, while a DC must
	# compare both endpoints (including the same-location no-transit case).  Base
	# Delivery Challan computes that transaction-specific value authoritatively.
	sync_exact_source_contract(doc)


def sync_exact_source_contract(doc):
	"""Restore server-owned execution metadata after the Desk matrix pivot."""
	if not doc.get("work_order"):
		return
	rows = [
		row
		for row in doc.get("items") or []
		if row.get("ref_doctype") == "YRP Work Order Deliverables"
		and row.get("ref_docname")
	]
	if not rows:
		return
	targets = {
		row.name: row
		for row in frappe.db.sql(
			"""
			SELECT name, additional_parameters
			FROM `tabYRP Work Order Deliverables`
			WHERE parent = %(work_order)s
				AND name IN %(names)s
			ORDER BY name
			""",
			{
				"work_order": doc.work_order,
				"names": tuple(sorted({row.ref_docname for row in rows})),
			},
			as_dict=True,
		)
	}
	for row in rows:
		target = targets.get(row.ref_docname)
		if target:
			row.additional_parameters = target.get("additional_parameters")


def requires_exact_source_lifecycle(doc):
	"""Return whether this DC belongs to the isolated version-1 cloth route."""
	if not doc or not doc.get("work_order"):
		return False
	if qualifies_cloth_transaction(doc):
		return True
	work_order = frappe.db.get_value(
		"YRP Work Order",
		doc.work_order,
		[
			"cloth_execution_version",
			"production_detail",
			"process_name",
		],
		as_dict=True,
	)
	if not work_order or cint(work_order.cloth_execution_version) != 1:
		return False
	if not work_order.production_detail or not work_order.process_name:
		return False
	ipd = frappe.get_cached_doc("YRP Item Production Detail", work_order.production_detail)
	route = get_supported_execution_route(ipd)
	return bool(
		route
		and work_order.process_name
		in {step["process_name"] for step in route.values()}
	)


def lock_transaction_lots(doc):
	"""Enter the shared Lot-first lock order before the DC lifecycle."""
	lot = (
		frappe.db.get_value("YRP Work Order", doc.work_order, "lot")
		if doc.get("work_order")
		else None
	)
	if not lot:
		frappe.throw(_("A versioned cloth Delivery Challan requires a Lot lock."))
	doc.lot = lot
	frappe.db.sql(
		"SELECT name FROM `tabSD YRP Lot` WHERE name = %s FOR UPDATE",
		(lot,),
	)
	return lot


def validate_exact_source_limits(doc, method=None):
	"""Validate a DC against current exact predecessor-GRN availability."""
	del method
	if cint(doc.get("docstatus")) == 2 or not requires_exact_source_lifecycle(doc):
		return
	if any(
		flt(row.get("qty") or row.get("delivered_quantity")) > 0
		for row in doc.get("correction_items") or []
	):
		frappe.throw(
			_(
				"Work Order correction rows cannot dispatch material from a versioned "
				"exact-source cloth Work Order."
			)
		)

	pool = _prepare_dispatch_source_pool(doc)
	if pool is None:
		# Default Knitting has no predecessor GRN bucket. Its yarn dispatch keeps
		# the existing base-YRP authority while still using the Lot lifecycle lock.
		return

	quantities = {}
	rows_by_reference = {}
	for row in doc.get("items") or []:
		quantity = flt(row.get("delivered_quantity") or row.get("qty"), 6)
		if quantity <= 0:
			continue
		if (
			row.get("ref_doctype") != "YRP Work Order Deliverables"
			or not row.get("ref_docname")
		):
			frappe.throw(_("A versioned cloth dispatch row lost its Work Order reference."))
		quantities[row.ref_docname] = flt(
			quantities.get(row.ref_docname, 0) + quantity, 6
		)
		rows_by_reference.setdefault(row.ref_docname, []).append(row)
	if not quantities:
		return

	targets = _load_dispatch_targets(
		doc,
		tuple(sorted(quantities)),
		for_update=_has_lot_lock(doc),
	)
	aggregated = {}
	for name in sorted(quantities):
		target = targets.get(name)
		if not target:
			frappe.throw(
				_("Exact-source Work Order deliverable {0} is unavailable.").format(name)
			)
		parameters = get_row_execution_parameters(target)
		bucket_key = parameters.get("source_bucket_key")
		if not target.get("source_grn_item") or not bucket_key:
			if _item_belongs_to_template(target.get("item_variant"), pool.get("cloth_item")):
				frappe.throw(
					_("Exact-source Work Order deliverable {0} lost its GRN lineage.").format(name)
				)
			# Dyes, chemicals and other non-cloth deliverables retain base-YRP
			# dispatch and stock validation. They never consume a fabric bucket.
			continue
		for row in rows_by_reference[name]:
			_validate_dispatch_row(row, target, pool.get("dimension_fields") or [])
		stock_qty = flt(quantities[name], 6) * _conversion_factor(
			target.item_variant, target.uom
		)
		entry = aggregated.setdefault(
			bucket_key,
			frappe._dict(target, stock_qty=0),
		)
		entry.stock_qty = flt(entry.stock_qty + stock_qty, 6)
		entry.dispatch_warehouse = doc.get("from_warehouse")

	for bucket_key in sorted(aggregated):
		_consume_dispatch_source(pool, aggregated[bucket_key])


def _prepare_dispatch_source_pool(doc):
	work_order = frappe.db.get_value(
		"YRP Work Order",
		doc.work_order,
		[
			"lot",
			"production_detail",
			"process_name",
			"item",
			"fabric_source_process",
			"fabric_source_process_step",
		],
		as_dict=True,
	)
	if not work_order or not work_order.fabric_source_process:
		return None
	if not work_order.fabric_source_process_step:
		frappe.throw(_("The exact fabric source-process step changed. Reopen Calculate."))

	from essdee_yrp.fabric_source import prepare_source_pool

	pool = prepare_source_pool(
		work_order.lot,
		work_order.production_detail,
		work_order.fabric_source_process,
		for_update=_has_lot_lock(doc),
	)
	pool["cloth_item"] = work_order.item
	return pool


def _load_dispatch_targets(doc, names, *, for_update):
	from yrp.stock.dimensions import assert_safe_fieldname, get_dimension_fieldnames

	dimension_fields = get_dimension_fieldnames()
	for fieldname in dimension_fields:
		assert_safe_fieldname(fieldname)
	dimension_sql = "".join(f", `{fieldname}`" for fieldname in dimension_fields)
	locking = "FOR UPDATE" if for_update else ""
	rows = frappe.db.sql(
		f"""
		SELECT name, parent, item_variant, qty, pending_quantity, uom,
			set_combination, source_grn, source_grn_item, additional_parameters
			{dimension_sql}
		FROM `tabYRP Work Order Deliverables`
		WHERE parent = %(work_order)s
			AND name IN %(names)s
		ORDER BY name
		{locking}
		""",
		{"work_order": doc.work_order, "names": names},
		as_dict=True,
	)
	return {row.name: row for row in rows}


def _validate_dispatch_row(row, target, dimension_fields):
	if row.get("item_variant") != target.get("item_variant") or row.get("uom") != target.get(
		"uom"
	):
		frappe.throw(
			_("Exact-source deliverable {0} item or UOM changed.").format(target.name)
		)
	if _normalise_json(row.get("set_combination")) != _normalise_json(
		target.get("set_combination")
	):
		frappe.throw(
			_("Exact-source deliverable {0} set combination changed.").format(target.name)
		)
	if get_row_execution_parameters(row) != get_row_execution_parameters(target):
		frappe.throw(
			_("Exact-source deliverable {0} execution identity changed.").format(target.name)
		)
	for fieldname in dimension_fields:
		if (row.get(fieldname) or None) != (target.get(fieldname) or None):
			frappe.throw(
				_("Exact-source deliverable {0} stock dimension {1} changed.").format(
					target.name, fieldname
				)
			)


def _consume_dispatch_source(pool, row):
	from essdee_yrp.fabric_source import (
		_validate_source_bucket_identity,
		consume_source_bucket,
	)

	bucket_key = get_row_execution_parameters(row).get("source_bucket_key")
	bucket = (pool.get("buckets") or {}).get(bucket_key)
	if not bucket:
		frappe.throw(_("The selected source GRN row is no longer available. Reopen Calculate."))
	if row.get("dispatch_warehouse") and row.get("dispatch_warehouse") != bucket.get(
		"source_warehouse"
	):
		frappe.throw(_("The exact source warehouse changed. Reopen Calculate."))
	_validate_source_bucket_identity(
		row,
		bucket,
		pool.get("dimension_fields") or [],
	)
	consume_source_bucket(pool, bucket_key, flt(row.get("stock_qty"), 6))


def _conversion_factor(item_variant, uom):
	from yrp.stock.utils import get_conversion_factor

	return flt(
		(get_conversion_factor(item_variant, uom) or {}).get("conversion_factor")
	) or 1


def _item_belongs_to_template(item_code, template):
	if not item_code or not template:
		return False
	if item_code == template:
		return True
	return frappe.get_cached_value("Item", item_code, "variant_of") == template


def _normalise_json(value):
	if isinstance(value, dict):
		return value
	try:
		return frappe.parse_json(value or "{}") or {}
	except (TypeError, ValueError):
		return {}


def _has_lot_lock(doc):
	flags = getattr(doc, "flags", None) or {}
	return bool(flags.get("cloth_execution_lot_locked"))


def sync_cutting_plan_received_cloth(doc, method=None):
	"""Reflect a submitted/cancelled DC in every linked Cutting Plan."""
	del method
	if not doc.get("work_order"):
		return
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		rebuild_received_cloth,
	)

	for name in frappe.get_all(
		"SD YRP Cutting Plan",
		filters={"work_order": doc.work_order, "docstatus": 1},
		pluck="name",
	):
		rebuild_received_cloth(frappe.get_doc("SD YRP Cutting Plan", name))
