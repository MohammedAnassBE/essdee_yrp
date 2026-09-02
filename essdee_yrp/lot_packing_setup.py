"""Install the Essdee-owned Lot and packing boundary customizations."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
	"Purchase Order": [
		{
			"fieldname": "lot_details_section",
			"fieldtype": "Section Break",
			"label": "Linked Lots",
			"insert_after": "delivery_address_display",
			"hidden": 1,
			"module": "Essdee YRP",
		},
		{
			"fieldname": "default_lot",
			"fieldtype": "Link",
			"label": "Default Lot",
			"options": "Lot",
			"insert_after": "lot_details_section",
			"allow_on_submit": 1,
			"hidden": 1,
			"module": "Essdee YRP",
		},
		{
			"fieldname": "sd_lot",
			"fieldtype": "Table",
			"label": "Linked Lots",
			"options": "Lot MultiSelect",
			"insert_after": "default_lot",
			"allow_on_submit": 1,
			"hidden": 1,
			"module": "Essdee YRP",
		},
	],
	"Process": [
		{
			"fieldname": "includes_packing",
			"fieldtype": "Check",
			"label": "Includes Packing",
			"insert_after": "is_manual_entry_in_grn",
			"default": "0",
			"module": "Essdee YRP",
		},
	],
	"Work Order": [
		{
			"fieldname": "includes_packing",
			"fieldtype": "Check",
			"label": "Includes Packing",
			"insert_after": "is_manual_entry",
			"default": "0",
			"read_only": 1,
			"allow_on_submit": 1,
			"fetch_from": "process_name.includes_packing",
			"fetch_if_empty": 0,
			"module": "Essdee YRP",
		},
	],
}


def ensure_custom_fields():
	"""Create/update the fields without redefining them in base YRP."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


def migrate_legacy_purchase_order_lot_rows():
	"""Copy legacy base child rows to Lot MultiSelect without dropping data.

	The old physical table is intentionally retained. This makes the operation
	idempotent and keeps rollback/reconciliation possible.
	"""
	if not frappe.db.table_exists("Purchase Order Lot"):
		return {"found": 0, "copied": 0, "skipped": 0}

	legacy_rows = frappe.db.sql(
		"""
		select parent, lot, idx
		from `tabPurchase Order Lot`
		where parenttype = 'Purchase Order' and parentfield = 'sd_lot'
		order by parent, idx, creation
		""",
		as_dict=True,
	)
	existing = {
		(row.parent, row.lot)
		for row in frappe.db.sql(
			"""
			select parent, lot
			from `tabLot MultiSelect`
			where parenttype = 'Purchase Order' and parentfield = 'sd_lot'
			""",
			as_dict=True,
		)
	}

	copied = 0
	skipped = 0
	skipped_rows = []
	for row in legacy_rows:
		key = (row.parent, row.lot)
		if (
			not row.parent
			or not row.lot
			or key in existing
			or not frappe.db.exists("Purchase Order", row.parent)
			or not frappe.db.exists("Lot", row.lot)
		):
			skipped += 1
			skipped_rows.append({"parent": row.parent, "lot": row.lot, "idx": row.idx})
			continue
		actor = frappe.session.user
		if not actor or actor == "Guest":
			actor = "Administrator"
		frappe.db.sql(
			"""
			insert into `tabLot MultiSelect`
				(name, creation, modified, modified_by, owner, docstatus,
				 idx, parent, parentfield, parenttype, lot)
			values (%s, now(), now(), %s, %s, 0, %s, %s, 'sd_lot', 'Purchase Order', %s)
			""",
			(
				frappe.generate_hash(length=10),
				actor,
				actor,
				row.idx or 0,
				row.parent,
				row.lot,
			),
		)
		existing.add(key)
		copied += 1

	if skipped_rows:
		frappe.log_error(
			title="Legacy Purchase Order Lot rows skipped",
			message=frappe.as_json(skipped_rows, indent=2),
		)
	return {"found": len(legacy_rows), "copied": copied, "skipped": skipped}


def ensure_boundary():
	ensure_custom_fields()
	return migrate_legacy_purchase_order_lot_rows()
