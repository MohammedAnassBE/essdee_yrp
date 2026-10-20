"""OMS page shapes over native YRP sales documents."""

import math
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate


def column(fieldname, label, fieldtype="Data", options=None):
	result = dict(fieldname=fieldname, label=_(label), fieldtype=fieldtype, width=120)
	if options:
		result["options"] = options
	return result


def matrix(
	catalog,
	attributes,
	configured_sizes,
	quantities,
	stock=None,
	*,
	show_stock=False,
	packed=False,
	search="",
):
	"""Flatten per-item page tables into one labelled Desk size matrix."""
	stock = stock or {}
	secondary, sizes = [], []
	groups = {}
	for item in catalog:
		attrs = attributes.get(item["name"], {})
		primary = item.get("primary_attribute")
		for attr in attrs:
			if attr != primary and attr not in secondary:
				secondary.append(attr)
		for size in configured_sizes.get(item["item"], []):
			if primary and size not in sizes:
				sizes.append(size)
		if primary and attrs.get(primary) and attrs[primary] not in sizes:
			sizes.append(attrs[primary])
		values = tuple((key, value) for key, value in sorted(attrs.items()) if key != primary)
		# An unattributed variant is an independent page row.
		key = (item["item"], values, None if primary else item["name"])
		group = groups.setdefault(
			key,
			dict(
				item=item["item"], attributes=dict(values), order=defaultdict(float), stock=defaultdict(float)
			),
		)
		size = attrs.get(primary) if primary else "__quantity"
		group["order"][size] += flt(quantities.get(item["name"]))
		group["stock"][size] += flt(stock.get(item["name"]))
	columns = [column("serial_no", "S.No", "Int"), column("item", "Item Name", "Link", "Item")]
	columns += [column(f"secondary_{i}", attr) for i, attr in enumerate(secondary)]
	if not packed:
		columns.append(column("type", "Type"))
	columns += [column(f"size_{i}", size, "Float") for i, size in enumerate(sizes)]
	if not sizes or any("__quantity" in g["order"] for g in groups.values()):
		columns.append(column("quantity", "Quantity", "Float"))
	columns.append(column("total_boxes", "Total Boxes", "Float"))
	rows = []
	serial = 0
	for group in groups.values():
		if (
			search
			and search.casefold()
			not in " ".join([group["item"], *map(str, group["attributes"].values())]).casefold()
		):
			continue
		serial += 1
		for kind in ["order", "stock"] if show_stock else ["order"]:
			values = group[kind]
			row = dict(serial_no=serial, item=group["item"], total_boxes=sum(values.values()))
			if not packed:
				row["type"] = kind.title()
			row.update({f"secondary_{i}": group["attributes"].get(attr) for i, attr in enumerate(secondary)})
			row.update({f"size_{i}": values.get(size, 0) for i, size in enumerate(sizes)})
			if any(c["fieldname"] == "quantity" for c in columns):
				row["quantity"] = values.get("__quantity", 0)
			rows.append(row)
	return columns, rows


def catalog_data(include_disabled=False):
	"""Read readable FG variants, titled attributes and configured size order in batches."""
	item_filters = {"has_variants": 0}
	if not include_disabled:
		item_filters["disabled"] = 0
	readable = frappe.get_list(
		"Item",
		filters=item_filters,
		pluck="name",
		limit_page_length=0,
	)
	if not readable:
		return [], {}, {}, {}
	catalog = frappe.db.sql(
		"""
		SELECT i.name, COALESCE(NULLIF(i.variant_of, ''), i.name) AS item,
			COALESCE(t.primary_attribute, i.primary_attribute) AS primary_attribute,
			i.stock_uom, fg.pcs_per_box
		FROM `tabItem` i
		LEFT JOIN `tabItem` t ON t.name = i.variant_of
		JOIN `tabSD YRP FG Item Master` fg
			ON fg.item = COALESCE(NULLIF(i.variant_of, ''), i.name)
		WHERE i.name IN %(readable)s AND (%(include_disabled)s OR fg.disabled = 0)
		ORDER BY item, i.name
	""",
		{"readable": readable, "include_disabled": int(include_disabled)},
		as_dict=True,
	)
	if not catalog:
		return [], {}, {}, {}
	names = list({i.name for i in catalog} | {i.item for i in catalog})
	attributes, sizes, conversions = defaultdict(dict), defaultdict(list), defaultdict(dict)
	for row in frappe.db.sql(
		"""
		SELECT a.parent, a.attribute, COALESCE(v.attribute_value, a.attribute_value) AS value
		FROM `tabItem Variant Attribute` a
		LEFT JOIN `tabYRP Item Attribute Value` v ON v.name = a.attribute_value
		WHERE a.parent IN %(names)s ORDER BY a.parent, a.idx
	""",
		{"names": names},
		as_dict=True,
	):
		attributes[row.parent][row.attribute] = row.value
	for row in frappe.db.sql(
		"""
		SELECT a.parent, v.attribute_value AS value
		FROM `tabItem Variant Attribute` a
		JOIN `tabItem` i ON i.name = a.parent AND i.primary_attribute = a.attribute
		JOIN `tabYRP Item Item Attribute Mapping Value` mv ON mv.parent = a.mapping
		JOIN `tabYRP Item Attribute Value` v ON v.name = mv.attribute_value
		WHERE a.parent IN %(names)s ORDER BY a.parent, mv.idx
	""",
		{"names": names},
		as_dict=True,
	):
		sizes[row.parent].append(row.value)
	for row in frappe.get_all(
		"UOM Conversion Detail",
		filters={"parent": ["in", names], "parenttype": "Item"},
		fields=["parent", "uom", "conversion_factor"],
		limit_page_length=0,
	):
		conversions[row.parent][row.uom] = flt(row.conversion_factor)
	return catalog, attributes, sizes, conversions


def boxes(stock_qty, item, conversions, *, ceiling=False):
	"""Convert stock units to Box; unknown conversions must not produce false totals."""
	if not stock_qty:
		return 0
	factor = conversions.get(item["name"], {}).get("Box") or conversions.get(item["item"], {}).get("Box")
	if item.get("stock_uom") == "Box":
		factor = 1
	if not factor and item.get("stock_uom") in ("Nos", "Pcs", "Pieces"):
		factor = flt(item.get("pcs_per_box"))
	if not factor:
		frappe.throw(_("Configure a Box UOM conversion for Item {0}.").format(item["name"]))
	value = flt(stock_qty) / factor
	return math.ceil(value) if ceiling else value


def date_bounds(filters):
	"""Inclusive posting dates; YRP Packing Slip records no posting time."""
	if not filters.get("start_date") or not filters.get("end_date"):
		frappe.throw(_("Start Date and End Date are required."))
	start, end = getdate(filters["start_date"]), getdate(filters["end_date"])
	if start > end:
		frappe.throw(_("Start Date must be before End Date."))
	if end > getdate():
		frappe.throw(_("Travelling To Future Is Not Enabled"))
	return start, end


def readable_names(doctype, filters):
	frappe.has_permission(doctype, "read", throw=True)
	frappe.has_permission(doctype, "report", throw=True)
	return frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0)


def fg_bin_filters(warehouses):
	"""Source FG stock bucket: default FG lot and received type in the chosen warehouses."""
	settings = frappe.db.get_value(
		"YRP Stock Settings", None, ["default_fg_lot", "default_received_type"], as_dict=True
	)
	if not settings.default_fg_lot:
		frappe.throw(_("Please set default FG Lot in YRP Stock Settings."))
	query = {"lot": settings.default_fg_lot}
	if settings.default_received_type:
		query["received_type"] = settings.default_received_type
	if isinstance(warehouses, str):
		warehouses = frappe.parse_json(warehouses) if warehouses.startswith("[") else [warehouses]
	if warehouses:
		query["warehouse"] = ["in", warehouses]
	return query


def pending(filters=None):
	filters = frappe._dict(filters or {})
	names = readable_names(
		"YRP Sales Order", {"docstatus": 1, "status": ["in", ["To Deliver", "Partially Delivered"]]}
	)
	catalog, attrs, sizes, conversions = catalog_data()
	items = {i.name: i for i in catalog}
	quantities = defaultdict(float)
	if names:
		for row in frappe.db.sql(
			"""
			SELECT item_code, SUM(GREATEST(qty - delivered_qty - cancelled_qty, 0)
				* conversion_factor) AS quantity
			FROM `tabYRP Sales Order Item` WHERE parent IN %(names)s
				AND parenttype = 'YRP Sales Order'
			GROUP BY item_code
		""",
			{"names": names},
			as_dict=True,
		):
			if row.item_code in items:
				quantities[row.item_code] = boxes(row.quantity, items[row.item_code], conversions)
	manager_roles = {
		"System Manager",
		"Sales User",
		"Sales Manager",
		"Stock User",
		"Stock Manager",
		"Report User",
	}
	show_stock = bool(
		manager_roles.intersection(frappe.get_roles()) and frappe.has_permission("YRP Bin", "read")
	)
	stock = defaultdict(float)
	if show_stock:
		for row in frappe.get_list(
			"YRP Bin",
			filters=fg_bin_filters(filters.get("warehouse")),
			fields=["item_code", "actual_qty", "reserved_qty"],
			limit_page_length=0,
		):
			balance = flt(row.actual_qty) - flt(row.reserved_qty)
			if row.item_code in items and balance > 0:
				stock[row.item_code] += balance
		stock = {name: boxes(qty, items[name], conversions, ceiling=True) for name, qty in stock.items()}
	columns, rows = matrix(
		catalog, attrs, sizes, quantities, stock, show_stock=show_stock, search=filters.get("search") or ""
	)
	return (
		columns,
		rows,
		_(
			"Open submitted YRP Sales Orders; pending = quantity less delivered and cancelled. Quantities are in Box; stock uses YRP Bin. Warehouse filters stock. OMS parity pending: compare with live MRP later."
		),
	)


def packed(filters=None):
	filters = frappe._dict(filters or {})
	# Check access before dates, including direct Python execution.
	frappe.has_permission("YRP Packing Slip", "report", throw=True)
	start, end = date_bounds(filters)
	query = {"docstatus": 1}
	if filters.get("customer"):
		query["customer"] = filters.customer
	if filters.get("sales_partner"):
		customers = frappe.get_list(
			"Customer",
			filters={"default_sales_partner": filters.sales_partner},
			pluck="name",
			limit_page_length=0,
		)
		if filters.get("customer"):
			customers = [c for c in customers if c == filters.customer]
		query["customer"] = ["in", customers]
	names = readable_names("YRP Packing Slip", query)
	# Both linked documents must be readable, including partner/customer scope.
	notes = readable_names("YRP Delivery Note", {"docstatus": 1, "is_return": 0})
	catalog, attrs, sizes, _conversions = catalog_data(include_disabled=True)
	quantities = defaultdict(float)
	if names and notes:
		for row in frappe.db.sql(
			"""
			SELECT d.item_code, SUM(d.qty) AS quantity FROM `tabYRP Packing Slip Item` d
			JOIN `tabYRP Packing Slip` p ON p.name = d.parent
			WHERE p.name IN %(names)s AND p.delivery_note IN %(notes)s
				AND d.parenttype = 'YRP Packing Slip' AND d.uom = 'Box'
				AND p.posting_date BETWEEN %(start)s AND %(end)s
			GROUP BY d.item_code
		""",
			{"names": names, "notes": notes, "start": start, "end": end},
			as_dict=True,
		):
			quantities[row.item_code] += flt(row.quantity)
	catalog = [i for i in catalog if i.name in quantities]
	columns, rows = matrix(catalog, attrs, sizes, quantities, packed=True, search=filters.get("search") or "")
	return (
		columns,
		rows,
		_(
			"Submitted YRP Packing Slips in Box UOM, excluding return Delivery Notes. YRP Packing Slip records only a posting date and no Sales Partner, so dates are whole posting days and Customer Sales Partner is the customer's current assignment. OMS Ordinary/stock-adjustment settings have no native equivalent. Parity pending: compare with live MRP later."
		),
	)
