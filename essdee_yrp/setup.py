"""Consumer-site setup tasks for essdee_yrp.

The app supports both lightweight Frappe + YRP consumer sites and the combined
ERPNext + YRP + SD YRP deployment. Records that may be absent on lightweight
sites are created idempotently, while optional integrations such as Spine are
configured only when installed.

Wired from hooks.py as `after_install` and `after_migrate` — both idempotent.
"""

import frappe
from frappe.contacts.doctype.address_template.address_template import (
	get_default_address_template,
)
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from essdee_yrp.web_build import build_web_spa

# Roles referenced by the migrated MRP DocType permissions but not provided by
# base YRP. Keep these as setup records rather than a Role fixture so migrations
# never delete or recreate an existing role.
MRP_SCHEMA_ROLES = (
	"Brand QA Manager",
	"Brand QA User",
	"CAD User",
	"Cutting User",
	"Merch Manager",
	"Store Manager",
	"T & A Admin",
	"T & A Manager",
	"T & A User",
	"T & A Viewer",
)

MRP_SYSTEM_MANAGER_CANCEL_PERMISSIONS = {
	'SD YRP Cut Panel Movement': {"submit": 0},
	'SD YRP Cutting Marker': {"submit": 1},
}

DOCPERM_FIELDS = (
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"mask",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
)

ESSDEE_REQUIRED_STOCK_DIMENSIONS = (
	{
		"dimension_doctype": 'SD YRP Lot',
		"fieldname": "lot",
		"label": "Lot",
		"mandatory": 1,
		"in_valuation": 1,
		"is_production_group": 1,
	},
	{
		"dimension_doctype": 'YRP Received Type',
		"fieldname": "received_type",
		"label": "Received Type",
		"mandatory": 1,
		"in_valuation": 1,
		"is_production_group": 0,
	},
)


def after_install():
	ensure_purchase_invoice_commercial_fields()
	ensure_process_billing_items()
	ensure_yrp_valuation_contract()
	ensure_required_stock_dimensions()
	ensure_essdee_stock_dimensions()
	ensure_stock_transaction_indexes()
	ensure_finishing_plan_dispatch_naming_series()
	ensure_default_address_template()
	ensure_mrp_schema_roles()
	ensure_mrp_cancel_permissions()
	ensure_yrp_production_order_settings()
	ensure_lot_packing_boundary()


def after_migrate():
	ensure_purchase_invoice_commercial_fields()
	ensure_process_billing_items()
	ensure_yrp_valuation_contract()
	ensure_required_stock_dimensions()
	ensure_essdee_stock_dimensions()
	ensure_stock_transaction_indexes()
	ensure_finishing_plan_dispatch_naming_series()
	ensure_default_address_template()
	ensure_mrp_schema_roles()
	ensure_mrp_cancel_permissions()
	ensure_sd_yrp_consumer_config()
	ensure_yrp_production_order_settings()
	ensure_lot_packing_boundary()
	from essdee_yrp.purchase_invoice import (
		backfill_legacy_commercial_items,
		backfill_unprojected_work_order_drafts,
	)

	backfill_legacy_commercial_items()
	backfill_unprojected_work_order_drafts()
	build_web_spa()


def ensure_purchase_invoice_commercial_fields():
	"""Install Essdee's commercial PI view without changing base YRP schemas."""
	create_custom_fields(
		{
			'YRP Purchase Invoice': [
				{
					"fieldname": "essdee_items",
					"fieldtype": "Table",
					"label": "Process Items",
					"options": 'SD YRP Essdee Purchase Invoice Item',
					"insert_after": "items",
					"depends_on": "eval:doc.against == 'YRP Work Order'",
				},
				{
					"fieldname": "essdee_rate_table_source",
					"fieldtype": "Data",
					"label": "Essdee Rate Table Source",
					"insert_after": "essdee_items",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				},
			],
			'YRP Purchase Invoice Item': [
				{
					"fieldname": "essdee_group_key",
					"fieldtype": "Data",
					"label": "Essdee Commercial Group Key",
					"insert_after": "set_combination",
					"hidden": 1,
					"read_only": 1,
				},
				{
					"fieldname": "essdee_rate_weight",
					"fieldtype": "Float",
					"label": "Essdee Commercial Rate Weight",
					"insert_after": "essdee_group_key",
					"hidden": 1,
					"precision": 9,
					"read_only": 1,
				},
			],
			'YRP PI Work Order Billed Detail': [
				{
					"fieldname": "essdee_group_key",
					"fieldtype": "Data",
					"label": "Essdee Commercial Group Key",
					"insert_after": "set_combination",
					"hidden": 1,
					"read_only": 1,
				},
			],
		},
		update=True,
	)
	for doctype, fieldnames in {
		'YRP Purchase Invoice': ("essdee_items", "essdee_rate_table_source"),
		'YRP Purchase Invoice Item': ("essdee_group_key", "essdee_rate_weight"),
		'YRP PI Work Order Billed Detail': ("essdee_group_key",),
	}.items():
		for fieldname in fieldnames:
			frappe.db.set_value(
				"Custom Field",
				f"{doctype}-{fieldname}",
				{"module": "Essdee YRP", "is_system_generated": 1},
				update_modified=False,
			)


def ensure_process_billing_items():
	"""Complete the migrated production_api billing-item contract for Cutting."""
	if (
		not frappe.get_meta('YRP Process').get_field("item")
		or not frappe.db.exists('YRP Process', "Cutting")
		or not frappe.db.exists('YRP Item', "Cutting Charges")
	):
		return
	if not frappe.db.get_value('YRP Process', "Cutting", "item"):
		frappe.db.set_value('YRP Process', "Cutting", "item", "Cutting Charges", update_modified=False)


def ensure_stock_transaction_indexes():
	"""Index the stock lookup paths used on every submit/cancel.

	The migrated Essdee ledger is large enough that filtering SLEs by voucher
	without this composite index scans the whole ledger. Base YRP's repost,
	cancel, and ownership guards all use the same three columns.

	Every effective SLE also recomputes the active reserved quantity for its
	item/warehouse/dimension bucket. The migrated reservation table is large,
	so leaving that lookup unindexed multiplies a full-table scan by every stock
	row in a DC, GRN, Stock Entry, or Stock Reconciliation. production_api uses
	the same item/warehouse/status optimization; Essdee additionally includes
	the complete stock-dimension bucket used by base YRP's authoritative query.
	DC submit/cancel also resolves the Work Order reservation once per child row;
	the voucher-detail index keeps that ownership lookup out of the same scan.
	"""
	frappe.db.add_index(
		'YRP Stock Ledger Entry',
		["voucher_type", "voucher_no", "is_cancelled"],
		index_name="idx_sle_voucher_active",
	)
	frappe.db.add_index(
		'YRP Stock Reservation Entry',
		[
			"item_code",
			"warehouse",
			"lot",
			"received_type",
			"docstatus",
			"status",
		],
		index_name="idx_sre_active_stock_bucket",
	)
	frappe.db.add_index(
		'YRP Stock Reservation Entry',
		[
			"voucher_type",
			"voucher_no",
			"voucher_detail_no",
			"docstatus",
		],
		index_name="idx_sre_voucher_detail_active",
	)


def ensure_required_stock_dimensions():
	"""Install Essdee's required stock-dimension columns before indexing them.

	Base YRP intentionally leaves stock dimensions configurable. Essdee's stock
	contract requires Lot and Received Type, so a fresh customization-app install
	must seed those rows before ``ensure_stock_transaction_indexes`` refers to the
	dynamic columns. Existing dimension rows and any additional user-configured
	dimensions are preserved.
	"""
	missing_doctypes = [
		dimension["dimension_doctype"]
		for dimension in ESSDEE_REQUIRED_STOCK_DIMENSIONS
		if not frappe.db.exists("DocType", dimension["dimension_doctype"])
	]
	if missing_doctypes:
		frappe.throw(
			"Essdee stock dimensions cannot be configured because these DocTypes "
			f"are missing: {', '.join(missing_doctypes)}"
		)

	settings = frappe.get_single('YRP YRP Stock Settings')
	rows_by_fieldname = {
		row.fieldname: row for row in (settings.stock_dimensions or [])
	}
	changed = False
	for dimension in ESSDEE_REQUIRED_STOCK_DIMENSIONS:
		if dimension["fieldname"] in rows_by_fieldname:
			continue
		settings.append("stock_dimensions", dimension)
		changed = True

	if changed:
		# YRP Stock Settings.on_update clears the dimension cache and creates the
		# corresponding Custom Fields/columns on every stock-bearing DocType.
		settings.save(ignore_permissions=True)
		return

	# Repair an already-configured site whose dynamic fields were not materialized
	# (for example, an interrupted earlier installation).
	from yrp.stock.dimensions import clear_dimension_cache, create_dimension_fields

	clear_dimension_cache()
	create_dimension_fields()


def ensure_yrp_valuation_contract():
	"""Fail deployment before Essdee can activate a partial stock contract."""
	required_fields = {
		'YRP Stock Ledger Entry': (
			"paired_stock_ledger_entry",
			"valuation_adjustment_value",
		),
		'SD YRP YRP GRN Deliverable': (
			"goods_received_note_item",
			"received_item_variant",
			"material_value",
			"consumption_sle",
			"output_receipt_sle",
			"stock_dimensions",
		),
		'YRP Work Order Excess Usage Item': (
			"actual_value",
			"source_sle",
			"stock_dimensions",
		),
	}
	missing = []
	for doctype, fieldnames in required_fields.items():
		if not frappe.db.exists("DocType", doctype):
			missing.append(doctype)
			continue
		meta = frappe.get_meta(doctype)
		missing.extend(
			f"{doctype}.{fieldname}"
			for fieldname in fieldnames
			if not meta.get_field(fieldname)
		)
	for doctype in (
		'YRP Stock Valuation Adjustment',
		'YRP Stock Valuation Production Link',
	):
		if not frappe.db.exists("DocType", doctype):
			missing.append(doctype)
	if missing:
		frappe.throw(
			"YRP valuation contract is incomplete. Deploy and migrate the matching "
			f"yrp develop revision together with essdee_yrp. Missing: {', '.join(missing)}"
		)


def ensure_finishing_plan_dispatch_naming_series():
	"""Remove the migrated hard-coded FY option; the controller derives it."""
	frappe.db.delete(
		"Property Setter",
		{"name": "Finishing Plan Dispatch-naming_series-options"},
	)
	frappe.clear_cache(doctype='SD YRP Finishing Plan Dispatch')


def ensure_mrp_schema_roles():
	"""Create only the missing application roles referenced by MRP schemas."""
	for role_name in MRP_SCHEMA_ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
			}
		).insert(ignore_permissions=True)


def ensure_mrp_cancel_permissions():
	"""Restore F15 cancel authority without hiding the floor-role permissions.

	Frappe switches a DocType entirely to ``Custom DocPerm`` as soon as the first
	custom row exists. Creating only the System Manager override therefore makes
	the standard Store User/Store Manager rows disappear from authorization.
	Mirror every standard row first, then apply the one intended override.
	"""
	for doctype, overrides in MRP_SYSTEM_MANAGER_CANCEL_PERMISSIONS.items():
		standard_rows = frappe.get_all(
			"DocPerm",
			filters={"parent": doctype},
			fields=["role", "permlevel", "if_owner", *DOCPERM_FIELDS],
			order_by="idx asc",
		)
		for standard in standard_rows:
			filters = {
				"parent": doctype,
				"role": standard.role,
				"permlevel": standard.permlevel,
				"if_owner": standard.if_owner,
			}
			values = {fieldname: standard.get(fieldname) for fieldname in DOCPERM_FIELDS}
			if standard.role == "System Manager" and standard.permlevel == 0 and not standard.if_owner:
				values.update({"submit": overrides["submit"], "cancel": 1})
			name = frappe.db.get_value("Custom DocPerm", filters, "name")
			if name:
				doc = frappe.get_doc("Custom DocPerm", name)
				doc.update(values)
				doc.save(ignore_permissions=True)
			else:
				frappe.get_doc(
					{
						"doctype": "Custom DocPerm",
						**filters,
						**values,
					}
				).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)


def ensure_lot_packing_boundary():
	"""Keep Essdee-owned fields reliable on fresh installs and upgrades."""
	from essdee_yrp.lot_packing_setup import ensure_boundary

	ensure_boundary()


def ensure_essdee_stock_dimensions():
	"""Extend the configured YRP dimension contract to Essdee stock rows."""
	from essdee_yrp.stock_dimensions import ensure_essdee_stock_dimension_fields

	ensure_essdee_stock_dimension_fields()


def ensure_sd_yrp_consumer_config():
	"""Keep the Spine consumer handler mappings in step with SYNC_DOCTYPES.

	Spine treats an unmapped doctype as success — the message is marked
	Processed and silently discarded — so a SYNC_DOCTYPES addition without its
	mapping row drops data with no error. Running the (idempotent)
	ensure_consumer_config on every migrate closes that class permanently.
	"""
	from essdee_yrp.sd_yrp_sync import ensure_consumer_config

	ensure_consumer_config()


def ensure_default_address_template():
	"""Create a default Address Template if none is marked default.

	Without a default, opening any Address (e.g. a synced Supplier's) throws
	"No default Address Template found" from
	frappe.contacts.doctype.address.address.get_address_templates.

	Idempotent: no-op when a default already exists.
	"""
	if frappe.db.get_value("Address Template", {"is_default": 1}, "name"):
		return

	doc = frappe.new_doc("Address Template")
	doc.country = "India"
	doc.is_default = 1
	doc.template = get_default_address_template()
	doc.insert(ignore_permissions=True)


def ensure_yrp_production_order_settings():
	"""Install the Production Order mapping required by the SD YRP consumer.

	The base YRP app intentionally leaves these customer-specific choices blank.
	Essdee's F15 Production Orders are size-grid documents whose generated
	variants use Stage=Pack. A missing mapping prevents the Production Order from
	syncing and every linked Lot then fails with a misleading missing-dependency
	error.

	The function is idempotent and preserves additional configured attributes.
	On a brand-new site it waits until the synced Size/Stage/Pack masters exist;
	the first Production Order message calls it again before validation.
	"""
	from essdee_yrp.sd_yrp_sync import (
		PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE,
		PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE,
		PRODUCTION_ORDER_GRID_ATTRIBUTE,
	)

	required_links = (
		('YRP Item Attribute', PRODUCTION_ORDER_GRID_ATTRIBUTE),
		('YRP Item Attribute', PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE),
		('YRP Item Attribute Value', PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE),
	)
	if any(not frappe.db.exists(doctype, name) for doctype, name in required_links):
		return False

	settings = frappe.get_doc('YRP YRP Settings')
	changed = False
	grid_row = None
	for row in settings.production_order_attributes or []:
		if row.attribute == PRODUCTION_ORDER_GRID_ATTRIBUTE:
			grid_row = row
		should_be_grid = row.attribute == PRODUCTION_ORDER_GRID_ATTRIBUTE
		if bool(row.is_grid_attribute) != should_be_grid:
			row.is_grid_attribute = should_be_grid
			changed = True

	if grid_row is None:
		settings.append(
			"production_order_attributes",
			{
				"attribute": PRODUCTION_ORDER_GRID_ATTRIBUTE,
				"is_grid_attribute": 1,
			},
		)
		changed = True

	if settings.po_dependent_attribute != PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE:
		settings.po_dependent_attribute = PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE
		changed = True
	if (
		settings.po_dependent_attribute_value
		!= PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE
	):
		settings.po_dependent_attribute_value = PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
	return changed
