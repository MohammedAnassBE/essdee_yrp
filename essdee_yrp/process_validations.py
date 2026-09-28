import frappe
from frappe import _


def validate(doc, method=None):
	input_attributes = _validate_unique_attributes(doc, "conversion_input_attributes", _("Input Attributes"))
	output_attributes = _validate_unique_attributes(doc, "conversion_output_attributes", _("Output Attributes"))
	configured = input_attributes or output_attributes

	if configured and (
		doc.get("is_group")
		or not doc.get("is_cloth_process")
		or not doc.get("is_item_conversion")
	):
		frappe.throw(
			_(
				"Cloth Conversion Attributes can only be configured on a non-group "
				"Cloth Process that is an Item Conversion."
			)
		)

	if (
		doc.get("is_cloth_process")
		and doc.get("is_item_conversion")
		and doc.get("value_change_attributes")
	):
		frappe.throw(
			_(
				"A Cloth Item Conversion Process must use Input Attributes and Output Attributes. "
				"Value Change Attributes are only for same-item processes."
			)
		)


def _validate_unique_attributes(doc, fieldname, label):
	attributes = [row.attribute for row in doc.get(fieldname) or [] if row.attribute]
	seen = set()
	for attribute in attributes:
		if attribute in seen:
			frappe.throw(_("Attribute {0} is listed more than once in {1}.").format(
				frappe.bold(attribute), label
			))
		seen.add(attribute)
	return attributes
