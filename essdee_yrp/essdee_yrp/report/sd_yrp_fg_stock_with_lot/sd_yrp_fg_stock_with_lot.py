"""Source-compatible migrated fg stock with lot report."""

import frappe
from frappe import _


def getColumns():
	return [
		{
			"label": _("Item"),
			"fieldname": "item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 120,
		},
		{
			"label": _("Warehouse Name"),
			"fieldname": "warehouse_name",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Lot"),
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"width": 150,
		},
		{
			"label": _("Quantity (Boxes)"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 140,
		},
		{"label": _("Pieces Per Box"), "fieldname": "pcs_per_box", "fieldtype": "int", "width": 140},
		{"label": _("Stock Qty (Pieces)"), "fieldname": "stock_in_pcs", "fieldtype": "Float", "width": 140},
		{"label": _("Stock Value"), "fieldname": "stock_price", "fieldtype": "Currency", "width": 140},
		{"label": _("Stock Entry Date"), "fieldname": "entry_date", "fieldtype": "Datetime", "width": 140},
	]


def calculate_and_update_price_and_valuation(report: dict, data: dict):
	report.update(
		{
			"stock_price": (data["price"] / data["conversion_factor"])
			* report["pcs_per_box"]
			* report["qty"],
		}
	)


def get_next_non_fg_lot(fg_lot, list_items, curr_index):
	if curr_index >= len(list_items) - 1:
		return list_items[curr_index]["lot"]

	if not list_items[curr_index]["lot"] or list_items[curr_index]["lot"] in ["Not Applicable", fg_lot]:
		for i in range(curr_index + 1, len(list_items)):
			if list_items[i]["lot"] and list_items[i]["lot"] not in ["Not Applicable", fg_lot]:
				return list_items[i]["lot"]
		return fg_lot
	else:
		return list_items[curr_index]["lot"]


def duplicate_removed_data(data):
	result = {}
	for i in data:
		key = (i["item"], i["lot"])
		if key not in result:
			result[key] = i
		else:
			result[key]["qty"] += i["qty"]
			result[key]["stock_in_pcs"] += i["stock_in_pcs"]
			result[key]["stock_price"] += i["stock_price"]
	return [v for k, v in result.items()]


def get_prev_fg_stock_entries(filters, stock):

	received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	default_fg_lot = frappe.db.get_single_value("YRP Stock Settings", "default_fg_lot")

	query = """
		SELECT
			t0.item_variant, SUM(t0.qty) as qty, t0.lot, t1.warehouse, t3.supplier_name as warehouse_name, t2.variant_of AS item, t4.pcs_per_box, t1.creation as entry_date
		FROM
		`tabSD YRP FG Stock Entry Detail` t0 JOIN
		 `tabSD YRP FG Stock Entry` t1 ON t0.parent=t1.name
		JOIN `tabItem` t2 ON t0.item_variant=t2.name
		JOIN `tabSupplier` t3 ON t3.name=t1.warehouse
		JOIN `tabSD YRP FG Item Master` t4 ON t4.item = t2.variant_of
		WHERE t1.docstatus=1 AND t0.received_type = %(received_type)s AND t1.warehouse = %(warehouse)s
		AND t1.posting_date <= %(filter_date)s
		GROUP BY t2.name, t1.name, t0.lot
		ORDER BY t1.posting_date DESC, t1.posting_time DESC
	"""

	resp = frappe.db.sql(
		query,
		{
			"received_type": received_type,
			"warehouse": filters["warehouse"],
			"filter_date": filters["filter_date"],
			"lot": default_fg_lot,
		},
		as_dict=True,
	)

	item_stock = construct_item_wise_stock_detail(stock)
	report = allocate_fg_entries(resp, item_stock, default_fg_lot)
	old_data = get_old_sms_data(item_stock, filters["warehouse"], filter_date=filters["filter_date"])
	report = report + old_data

	return duplicate_removed_data(report)


def old_warehouse_mapping(warehouse):

	query = """
		SELECT
			t1.old_location_id as loc_id, t1.warehouse, t2.supplier_name as warehouse_name
		FROM `tabSD YRP Stock Settings Old Warehouse Mapping` t1 JOIN `tabSupplier` t2 ON t1.warehouse=t2.name
		WHERE t2.name=%(warehouse)s
		;
	"""
	resp = frappe.db.sql(query, {"warehouse": warehouse}, as_dict=True)
	if not resp:
		frappe.throw("Please Setup Old Sales System Warehouse Mapping")

	return [resp[0]["loc_id"], resp[0]["warehouse"], resp[0]["warehouse_name"]]


def get_stock(filters):
	settings = frappe.get_single("YRP Stock Settings")
	query = """
		WITH latest_sle AS (
		    SELECT
		        name,
		        item,
		        warehouse,
		        lot,
		        ROW_NUMBER() OVER (
		            PARTITION BY item
		            ORDER BY posting_date DESC, posting_time DESC, creation DESC
		        ) AS rn
		    FROM `tabYRP Stock Ledger Entry`
		    WHERE posting_date <= %(filter_date)s
			AND is_cancelled = 0
			AND docstatus = 1
			AND received_type = %(received_type)s
			AND lot = %(lot)s
			AND warehouse = %(warehouse)s
		)
		SELECT
		    t1.lot,
		    (SUM(t1.qty_after_transaction) / t4.pcs_per_box) AS stock,
		    t2.variant_of AS item,
			t1.item as item_variant,
		    t3.supplier_name AS warehouse_name,
		    t3.name AS warehouse
		FROM `tabYRP Stock Ledger Entry` t1
		JOIN `tabItem` t2 ON t2.name = t1.item
		JOIN `tabSupplier` t3 ON t3.name = t1.warehouse
		JOIN `tabSD YRP FG Item Master` t4 ON t4.item = t2.variant_of
		JOIN latest_sle ON latest_sle.name = t1.name AND latest_sle.rn = 1
		WHERE
		    t1.posting_date <= %(filter_date)s
		    AND t1.is_cancelled = 0
		    AND t1.docstatus = 1
		    AND t1.received_type = %(received_type)s
		    AND t1.lot = %(lot)s
		    AND t1.warehouse = %(warehouse)s
		GROUP BY t1.item
		;
	"""

	return frappe.db.sql(
		query,
		{
			"filter_date": filters["filter_date"],
			"warehouse": filters["warehouse"],
			"lot": settings.get("default_fg_lot"),
			"received_type": settings.get("default_received_type"),
		},
		as_dict=True,
	)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for field in ("filter_date", "warehouse"):
		if not filters.get(field):
			frappe.throw(_("Please set {0}").format(field))
	return getColumns(), get_prev_fg_stock_entries(filters, get_stock(filters))


def construct_item_wise_stock_detail(stock):
	"""Load all UOM factors together rather than once per stock variant."""
	prices = get_price_valuation_for_items()
	conversions = frappe.db.sql(
		"""SELECT iv.name AS item_variant, u.uom, u.conversion_factor
		FROM `tabItem` iv JOIN `tabUOM Conversion Detail` u ON u.parent = iv.variant_of
		WHERE u.parenttype = 'Item' AND u.parentfield = 'uoms'""",
		as_dict=True,
	)
	factors = {(row.item_variant, row.uom): row.conversion_factor for row in conversions}
	return {
		row["item_variant"]: {
			**prices.get(row["item_variant"], {"price": 0.0, "uom": "Box"}),
			"stock": row["stock"],
			"item": row["item"],
			"conversion_factor": factors.get(
				(row["item_variant"], prices.get(row["item_variant"], {}).get("uom", "Box"))
			)
			or 1.0,
		}
		for row in stock
	}


def get_price_valuation_for_items():
	"""Use the same configured sales service as the MRP report."""
	import requests

	settings = frappe.get_single("SD YRP MRP Settings")
	if not settings.sales_site_url or not settings.sales_api_key or not settings.sales_api_secret:
		frappe.throw(_("Please Setup The Sales Credentials"))
	response = requests.get(
		settings.sales_site_url.rstrip("/")
		+ "/api/method/essdee_sales.api.mrp.get_wholesales_price_details_for_items",
		headers={
			"Authorization": f"token {settings.sales_api_key}:{settings.get_password('sales_api_secret')}",
			"Content-Type": "application/json",
		},
		timeout=30,
	)
	response.raise_for_status()
	return response.json()["message"]


def get_old_connection():
	"""Open the configured legacy SMS database for read-only queries."""
	import pymysql

	settings = frappe.get_single("YRP Stock Settings")
	fields = (
		"sms_old_database_host",
		"sms_old_database_name",
		"sms_old_database_port",
		"sms_old_database_user",
		"sms_old_database_password",
	)
	if any(not settings.get(field) for field in fields):
		frappe.throw(_("Please Set The Migration Properties"))
	return pymysql.connect(
		host=settings.sms_old_database_host,
		user=settings.sms_old_database_user,
		password=settings.get_password("sms_old_database_password"),
		db=settings.sms_old_database_name,
		port=int(settings.sms_old_database_port),
		connect_timeout=15,
		read_timeout=30,
	)


def get_old_sms_data(stock_detail, warehouse, filter_date):
	"""Allocate remaining boxes from the legacy SMS history in date order."""
	import pymysql.cursors

	location, warehouse, warehouse_name = old_warehouse_mapping(warehouse)
	items = tuple({row["item"] for row in stock_detail.values() if row["stock"] > 0})
	if not items:
		return []
	connection = get_old_connection()
	sizes = [f"size{index}" for index in range(1, 11)]
	report = []
	try:
		with connection.cursor(pymysql.cursors.DictCursor) as cursor:
			cursor.execute("""SELECT t1.name,
				t2.size1 AS x_size1, t2.size2 AS x_size2, t2.size3 AS x_size3,
				t2.size4 AS x_size4, t2.size5 AS x_size5, t2.size6 AS x_size6,
				t2.size7 AS x_size7, t2.size8 AS x_size8, t2.size9 AS x_size9, t2.size10 AS x_size10,
				t3.size1, t3.size2, t3.size3, t3.size4, t3.size5,
				t3.size6, t3.size7, t3.size8, t3.size9, t3.size10
				FROM iteminfo t1 JOIN sizerange t2 ON t1.sizerange = t2.idsize
				JOIN sizetype t3 ON t3.id = t2.idsizetype""")
			variants = {
				row["name"]: {
					size: f"{row['name']}-{row[size]}" if row[f"x_{size}"] == 1 else None for size in sizes
				}
				for row in cursor.fetchall()
			}
			cursor.execute(
				"""SELECT t3.name AS item,
				t2.size1, t2.size2, t2.size3, t2.size4, t2.size5,
				t2.size6, t2.size7, t2.size8, t2.size9, t2.size10,
				t1.lotnumber AS lot, t3.pieces AS pcs_per_box, t1.creationdate AS entry_date
				FROM stockentrydetails t1
				JOIN stockentryitems t2 ON t1.idstockentry = t2.idstockentry
				JOIN iteminfo t3 ON t3.iditem = t2.iditem
				WHERE t3.name IN %s AND t1.idlocation = %s AND t1.creationdate <= %s
				ORDER BY t1.creationdate DESC""",
				(items, location, filter_date),
			)
			for entry in cursor.fetchall():
				for size in sizes:
					variant = variants[entry["item"]][size]
					if not variant or variant not in stock_detail or stock_detail[variant]["stock"] <= 0:
						continue
					stock_detail[variant]["stock"] -= entry[size]
					if stock_detail[variant]["stock"] <= 0:
						entry[size] += stock_detail[variant]["stock"]
					if not entry[size]:
						continue
					row = {
						"item": entry["item"],
						"qty": entry[size],
						"lot": entry["lot"],
						"warehouse": warehouse,
						"warehouse_name": warehouse_name,
						"stock_in_pcs": entry[size] * entry["pcs_per_box"],
						"pcs_per_box": entry["pcs_per_box"],
						"entry_date": entry["entry_date"],
					}
					calculate_and_update_price_and_valuation(row, stock_detail[variant])
					report.append(row)
	finally:
		connection.close()
	return report


def allocate_fg_entries(entries, item_stock, default_fg_lot):
	"""Allocate newest FG receipts, clipping each variant to its stock balance."""
	report = []
	for index, i in enumerate(entries):
		i["lot"] = get_next_non_fg_lot(default_fg_lot, entries, index)
		if i["item_variant"] not in item_stock or item_stock[i["item_variant"]]["stock"] <= 0:
			continue

		item_stock[i["item_variant"]]["stock"] -= i["qty"]
		if item_stock[i["item_variant"]]["stock"] <= 0:
			i["qty"] += item_stock[i["item_variant"]]["stock"]
		row = {
			"item": i["item"],
			"item_variant": i["item_variant"],
			"qty": i["qty"],
			"lot": i["lot"],
			"warehouse": i["warehouse"],
			"warehouse_name": i["warehouse_name"],
			"stock_in_pcs": i["qty"] * i["pcs_per_box"],
			"pcs_per_box": i["pcs_per_box"],
			"entry_date": i["entry_date"],
		}
		calculate_and_update_price_and_valuation(row, item_stock[i["item_variant"]])
		report.append(row)
	return report
