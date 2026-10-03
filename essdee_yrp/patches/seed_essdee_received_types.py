import frappe


ESSDEE_RECEIVED_TYPES = (
	"Accepted",
	"Adas",
	"Fabric Mistake",
	"Fusing Mistake",
	"Misstitch",
	"Oil Mark",
	"Other Mistake",
	"Printing Mistake",
	"Rejected",
	"Shade Mistake",
)


def execute():
	if not frappe.db.exists("DocType", "Received Type"):
		return

	for received_type in ESSDEE_RECEIVED_TYPES:
		if frappe.db.exists("Received Type", received_type):
			continue
		frappe.get_doc({
			"doctype": "Received Type",
			"received_type_name": received_type,
			"is_default": received_type == "Accepted",
		}).insert(ignore_permissions=True)

	if (
		frappe.get_meta("YRP Stock Settings").has_field("default_rejected_received_type")
		and not frappe.db.get_single_value(
			"YRP Stock Settings", "default_rejected_received_type"
		)
	):
		frappe.db.set_single_value(
			"YRP Stock Settings", "default_rejected_received_type", "Rejected"
		)
