import frappe
from essdee_yrp.ipd_attribute_links import normalize_major_value


def execute():
	for name in frappe.get_all('YRP Item Production Detail', pluck='name'):
		doc=frappe.get_doc('YRP Item Production Detail',name)
		old=doc.get('stiching_major_attribute_value')
		if old and doc.get('stiching_attribute') and not frappe.db.exists('YRP Item Attribute Value', old):
			# Preserve historical panel names missing from the current catalogue.
			from yrp.yrp.doctype.yrp_item.yrp_item import ensure_global_attribute_values
			ensure_global_attribute_values(doc.stiching_attribute, [old])
		normalize_major_value(doc)
		if doc.get('stiching_major_attribute_value') != old:
			frappe.db.set_value(doc.doctype,name,'stiching_major_attribute_value',doc.stiching_major_attribute_value,update_modified=False)
	frappe.db.set_value('Custom Field', 'YRP Item Production Detail-stiching_major_attribute_value',
		{'fieldtype':'Link', 'options':'YRP Item Attribute Value'})
	frappe.clear_cache(doctype='YRP Item Production Detail')
