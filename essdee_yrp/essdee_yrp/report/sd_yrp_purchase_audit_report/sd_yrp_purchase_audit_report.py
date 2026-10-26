import frappe
from frappe import _
from frappe.utils import add_months, getdate

DIRECTIONS = ("inward", "outward")

TRANSFER_PURPOSES = "('Send to Warehouse', 'Receive at Warehouse')"

INWARD_COLUMNS = (
	(
		"po_grn",
		_("PO GRN"),
		"sle.voucher_type = 'YRP Goods Received Note' AND grn.against = 'Purchase Order' AND grn.is_return = 0",
	),
	("se_material_receipt", _("SE Material Receipt"), "se.purpose = 'Material Receipt'"),
	("added_stock", _("Added Stock"), "su.update_type = 'Add'"),
	("received_warehouse", _("Received Warehouse"), f"se.purpose IN {TRANSFER_PURPOSES}"),
	("conversion_inward", _("Conversion Inward"), "sle.voucher_type = 'SD YRP Item Conversion'"),
	("other_inward", _("Other Inward"), "1 = 1"),
)
OUTWARD_COLUMNS = (
	("dc_qty", _("DC Qty"), "sle.voucher_type = 'YRP Delivery Challan'"),
	("se_material_issue", _("SE Material Issue"), "se.purpose = 'Material Issue'"),
	("reduced_stock", _("Reduced Stock"), "su.update_type = 'Reduce'"),
	("sent_warehouse", _("Sent Warehouse"), f"se.purpose IN {TRANSFER_PURPOSES}"),
	("conversion_outward", _("Conversion Outward"), "sle.voucher_type = 'SD YRP Item Conversion'"),
	("other_outward", _("Other Outward"), "1 = 1"),
)

SUPPLIER = """CASE sle.voucher_type
	WHEN 'YRP Goods Received Note' THEN grn.supplier
	WHEN 'YRP Delivery Challan' THEN dc.supplier
	WHEN 'YRP Stock Entry' THEN se.transfer_supplier
	WHEN 'YRP Stock Update' THEN su.supplier
END"""

PERIODS = {
	"detailed": (),
	"summarized": (),
	"month_wise": (("DATE_FORMAT(sle.posting_date, '%%Y-%%m')", "month"),),
}

ITEM_EXPRESSION = "COALESCE(NULLIF(variant.variant_of, ''), variant.name)"

DIMENSIONS = (
	(ITEM_EXPRESSION, "item"),
	("sle.item", "item_variant"),
	("variant.item_group", "item_group"),
	("supplier.name", "supplier"),
	("supplier.supplier_name", "supplier_name"),
	("sle.warehouse", "warehouse"),
	("sle.lot", "lot"),
	("sle.received_type", "received_type"),
)

FILTER_CONDITIONS = {
	"supplier": "supplier.name = %(supplier)s",
	"warehouse": "sle.warehouse = %(warehouse)s",
	"item": f"{ITEM_EXPRESSION} IN %(item)s",
	"item_variant": "sle.item = %(item_variant)s",
	"lot": "sle.lot = %(lot)s",
	"received_type": "sle.received_type = %(received_type)s",
	"item_group": """variant.item_group IN (
		SELECT child.name FROM `tabItem Group` child
		JOIN `tabItem Group` parent ON parent.name IN %(item_group)s
		WHERE child.lft >= parent.lft AND child.rgt <= parent.rgt)""",
}

MULTI_SELECT_FILTERS = ("item", "item_group")

BALANCE_KEY = "sle.item, sle.warehouse, IFNULL(sle.lot, ''), IFNULL(sle.received_type, '')"
BALANCE_LEDGER = """FROM `tabYRP Stock Ledger Entry` sle
	JOIN `tabItem` variant ON variant.name = sle.item
	WHERE sle.is_cancelled = 0 AND sle.docstatus < 2 AND sle.posting_date <= %(to_date)s"""
RECONCILIATION = "'YRP Stock Reconciliation'"
BALANCE_QUERY = f"""SELECT {BALANCE_KEY}, SUM(sle.qty) {BALANCE_LEDGER} {{conditions}}
	AND sle.voucher_type != {RECONCILIATION}
	GROUP BY {BALANCE_KEY}"""
RECONCILED_BALANCE_QUERY = f"""SELECT recon.item, recon.warehouse, recon.lot, recon.received_type,
	recon.qty_after_transaction + COALESCE(SUM(later.qty), 0)
	FROM (
		SELECT sle.item, sle.warehouse, IFNULL(sle.lot, '') AS lot, IFNULL(sle.received_type, '') AS received_type,
			sle.qty_after_transaction, sle.posting_datetime, sle.creation,
			ROW_NUMBER() OVER (PARTITION BY {BALANCE_KEY} ORDER BY sle.posting_datetime DESC, sle.creation DESC)
				AS position
		{BALANCE_LEDGER} {{conditions}} AND sle.voucher_type = {RECONCILIATION}
	) recon
	LEFT JOIN `tabYRP Stock Ledger Entry` later ON later.item = recon.item AND later.warehouse = recon.warehouse
		AND IFNULL(later.lot, '') = recon.lot AND IFNULL(later.received_type, '') = recon.received_type
		AND later.is_cancelled = 0 AND later.docstatus < 2 AND later.posting_date <= %(to_date)s
		AND later.voucher_type != {RECONCILIATION}
		AND (later.posting_datetime, later.creation) > (recon.posting_datetime, recon.creation)
	WHERE recon.position = 1
	GROUP BY recon.item, recon.warehouse, recon.lot, recon.received_type, recon.qty_after_transaction"""


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for field in MULTI_SELECT_FILTERS:
		filters[field] = get_filter_values(filters.get(field))
	validate_dates(filters)
	view = get_view(filters)
	months = get_months(filters) if view == "month_wise" else []
	return get_columns(view, months), get_data(filters, view, months)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query(doctype, txt, searchfield, start, page_len, filters):
	"""Item (or variant, with filters.variant) options inside the selected Item Group trees, matching the report filters."""
	filters = frappe._dict(filters or {})
	item_group = get_filter_values(filters.item_group)
	variant_key = "variant.name" if filters.variant else ITEM_EXPRESSION
	conditions = [
		"item.disabled = 0",
		"item.has_variants = 0" if filters.variant else "IFNULL(item.variant_of, '') = ''",
		"(item.name LIKE %(txt)s OR item.item_name LIKE %(txt)s)",
	]
	if item_group:
		conditions.append(
			f"item.name IN (SELECT {variant_key} FROM `tabItem` variant WHERE {FILTER_CONDITIONS['item_group']})"
		)
	return frappe.db.sql(
		f"""SELECT item.name, item.item_name FROM `tabItem` item
		WHERE {" AND ".join(conditions)}
		ORDER BY item.name LIMIT %(start)s, %(page_len)s""",
		{"txt": f"%{txt}%", "item_group": item_group, "start": start, "page_len": page_len},
	)


def get_filter_values(value):
	"""MultiSelectList values as a tuple for SQL IN; a single name is accepted too."""
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	return tuple(name for name in value or [] if name)


def validate_dates(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def get_view(filters):
	if not filters.get("summarized_view"):
		return "detailed"
	return "month_wise" if filters.get("month_wise_report") else "summarized"


def get_months(filters):
	"""Return YYYY-MM keys for every month touched by the date range."""
	month, last = getdate(filters.from_date).replace(day=1), getdate(filters.to_date)
	months = []
	while month <= last:
		months.append(month.strftime("%Y-%m"))
		month = add_months(month, 1)
	return months


def get_bucket_expression():
	"""SQL CASE naming the report column each ledger row belongs to."""
	inward = " ".join(
		f"WHEN sle.qty > 0 AND {condition} THEN '{field}'" for field, _label, condition in INWARD_COLUMNS
	)
	outward = " ".join(
		f"WHEN sle.qty < 0 AND {condition} THEN '{field}'" for field, _label, condition in OUTWARD_COLUMNS
	)
	return f"CASE {inward} {outward} END"


def get_ledger_rows(filters, view):
	period = PERIODS[view]
	selects = [f"{expression} AS {alias}" for expression, alias in DIMENSIONS + period]
	conditions = [
		"sle.is_cancelled = 0",
		"sle.docstatus = 1",
		"sle.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	conditions += [condition for field, condition in FILTER_CONDITIONS.items() if filters.get(field)]
	group_fields = [expression for expression, _alias in DIMENSIONS + period]
	order_fields = [alias for _expression, alias in period + DIMENSIONS]
	return frappe.db.sql(
		f"""
		SELECT {", ".join(selects)}, {get_bucket_expression()} AS bucket, SUM(ABS(sle.qty)) AS qty
		FROM `tabYRP Stock Ledger Entry` sle
		JOIN `tabItem` variant ON variant.name = sle.item
		LEFT JOIN `tabYRP Goods Received Note` grn
			ON sle.voucher_type = 'YRP Goods Received Note' AND grn.name = sle.voucher_no
		LEFT JOIN `tabYRP Delivery Challan` dc ON sle.voucher_type = 'YRP Delivery Challan' AND dc.name = sle.voucher_no
		LEFT JOIN `tabYRP Stock Entry` se ON sle.voucher_type = 'YRP Stock Entry' AND se.name = sle.voucher_no
		LEFT JOIN `tabYRP Stock Update` su ON sle.voucher_type = 'YRP Stock Update' AND su.name = sle.voucher_no
		LEFT JOIN `tabSupplier` supplier ON supplier.name = {SUPPLIER}
		WHERE sle.qty != 0 AND {" AND ".join(conditions)}
		GROUP BY {", ".join(group_fields)}, bucket
		ORDER BY {", ".join(order_fields)}
		""",
		filters,
		as_dict=True,
	)


def get_data(filters, view, months):
	rows = get_bucket_rows(filters, view)
	if view == "month_wise":
		rows = get_month_rows(rows, months)
	balances = get_stock_balances(filters, {row["item_variant"] for row in rows})
	for row in rows:
		key = (row["item_variant"], row["warehouse"], row["lot"] or "", row["received_type"] or "")
		row["stock_balance"] = balances.get(key, 0.0)
	return rows


def get_stock_balances(filters, variants):
	"""Closing qty at To Date per variant, warehouse, lot and received type, computed like YRP Stock Balance.

	The latest Stock Reconciliation entry sets the balance to its qty_after_transaction; later entries add qty.
	"""
	if not variants:
		return {}
	conditions = "".join(
		f" AND {condition}"
		for field, condition in FILTER_CONDITIONS.items()
		if field != "supplier" and filters.get(field)
	)
	values = {**filters, "variants": tuple(variants)}
	balances = {}
	for query in (BALANCE_QUERY, RECONCILED_BALANCE_QUERY):
		rows = frappe.db.sql(query.format(conditions=f" AND sle.item IN %(variants)s{conditions}"), values)
		balances.update({tuple(row[:4]): row[4] for row in rows})
	return balances


def get_bucket_rows(filters, view):
	"""Pivot ledger buckets into one row per dimension and period."""
	rows = {}
	for ledger_row in get_ledger_rows(filters, view):
		bucket, qty = ledger_row.pop("bucket"), ledger_row.pop("qty")
		key = tuple(ledger_row.values())
		row = rows.setdefault(key, {**ledger_row, **dict.fromkeys(get_quantity_fields(), 0.0)})
		row[bucket] += qty
	for row in rows.values():
		row["total_inward"] = sum(row[field] for field, _label, _condition in INWARD_COLUMNS)
		row["total_outward"] = sum(row[field] for field, _label, _condition in OUTWARD_COLUMNS)
		row["difference"] = row["total_inward"] - row["total_outward"]
	return list(rows.values())


def get_month_rows(rows, months):
	"""Fold per-month rows into one row per dimension with month inward/outward columns."""
	month_fields = [get_month_field(month, direction) for month in months for direction in DIRECTIONS]
	totals = ("total_inward", "total_outward", "difference")
	result = {}
	for row in rows:
		dimensions = {alias: row[alias] for _expression, alias in DIMENSIONS}
		target = result.setdefault(
			tuple(dimensions.values()), {**dimensions, **dict.fromkeys(month_fields + list(totals), 0.0)}
		)
		for direction in DIRECTIONS:
			target[get_month_field(row["month"], direction)] += row[f"total_{direction}"]
		for field in totals:
			target[field] += row[field]
	return list(result.values())


def get_month_field(month, direction):
	return f"{month.replace('-', '_')}_{direction}"


def get_quantity_fields():
	return [field for field, _label, _condition in INWARD_COLUMNS + OUTWARD_COLUMNS]


def get_columns(view, months):
	columns = [
		link_column(_("Item"), "item", "Item"),
		link_column(_("Item Variant"), "item_variant", "Item"),
		link_column(_("Item Group"), "item_group", "Item Group"),
		link_column(_("Supplier"), "supplier", "Supplier"),
		{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 160},
		link_column(_("Warehouse"), "warehouse", "Warehouse"),
		link_column(_("Lot"), "lot", "SD YRP Lot"),
		link_column(_("Received Type"), "received_type", "YRP Received Type"),
	]
	if view == "detailed":
		columns += get_detail_columns()
	else:
		for month in months:
			label = getdate(f"{month}-01").strftime("%b %Y")
			columns.append(qty_column(f"{label} {_('Inward')}", get_month_field(month, "inward")))
			columns.append(qty_column(f"{label} {_('Outward')}", get_month_field(month, "outward")))
		columns.append(qty_column(_("Total Inward"), "total_inward"))
		columns.append(qty_column(_("Total Outward"), "total_outward"))
	columns.append(qty_column(_("Difference"), "difference"))
	columns.append({**qty_column(_("Stock Balance"), "stock_balance"), "disable_total": 1})
	return columns


def get_detail_columns():
	columns = [qty_column(label, field) for field, label, _condition in INWARD_COLUMNS]
	columns.append(qty_column(_("Total Inward"), "total_inward"))
	columns += [qty_column(label, field) for field, label, _condition in OUTWARD_COLUMNS]
	columns.append(qty_column(_("Total Outward"), "total_outward"))
	return columns


def link_column(label, fieldname, options):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Link", "options": options, "width": 140}


def qty_column(label, fieldname):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Float", "width": 110}
