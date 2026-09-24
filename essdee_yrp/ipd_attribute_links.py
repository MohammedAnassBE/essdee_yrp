import frappe
from yrp.attribute_values import ensure_value_master, get_mapping_document


def actual_value(value):
	return frappe.db.get_value('YRP Item Attribute Value', value, 'attribute_value') or value if value else value


def major_stitching_value(doc):
	return actual_value(doc.get('stiching_major_attribute_value'))


def normalize_major_value(doc):
	value = doc.get('stiching_major_attribute_value')
	attribute = doc.get('stiching_attribute')
	if not value or not attribute:
		return
	linked = frappe.db.get_value('YRP Item Attribute Value', value, 'attribute_name')
	if linked and linked != attribute:
		frappe.throw('Stitching Major Attribute Value must belong to the Stitching Attribute')
	if not linked:
		doc.stiching_major_attribute_value = ensure_value_master(attribute, value)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_values(doctype, txt, searchfield, start, page_len, filters):
	mapping = filters.get('mapping')
	if not mapping:
		return []
	doc = get_mapping_document(mapping)
	doc.check_permission('read')
	values = [row.attribute_value for row in doc.get('values') or []]
	return frappe.get_list('YRP Item Attribute Value', filters={
		'attribute_name': doc.attribute_name, 'attribute_value': ['in', values],
	}, or_filters={'attribute_value': ['like', '%' + txt + '%'], 'name': ['like', '%' + txt + '%']},
		fields=['name', 'attribute_value'], as_list=True, start=start, page_length=page_len)
