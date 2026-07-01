from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _field(fieldname, fieldtype, label=None, **kwargs):
	field = {
		"fieldname": fieldname,
		"fieldtype": fieldtype,
	}
	if label:
		field["label"] = label
	field.update(kwargs)
	return field


IPD_CUSTOM_FIELDS = [
	_field("packing_tab", "Tab Break", "Packing", depends_on="eval: !doc.__islocal"),
	_field("packing_section", "Section Break", "Packing Details"),
	_field(
		"packing_combo",
		"Int",
		"Packing Combo",
		mandatory_depends_on="eval: !doc.__islocal",
		description="Pcs per Box",
	),
	_field("column_break_gcku", "Column Break"),
	_field(
		"packing_attribute_no",
		"Int",
		"Packing Attribute No",
		mandatory_depends_on="eval: !doc.__islocal",
		description="Unique number of attribute values that will be put into a box.",
	),
	_field("section_break_rjdy", "Section Break"),
	_field("auto_calculate", "Check", "Auto Calculate", default="0"),
	_field(
		"get_packing_attribute_values",
		"Button",
		"Get Packing Attribute Values",
		depends_on="eval: doc.packing_attribute_no && doc.packing_attribute",
	),
	_field(
		"packing_attribute_details",
		"Table",
		"Packing Attribute Details",
		options="Item Production Detail Packing Attribute Detail",
	),
	_field(
		"based_on_other_attribute_mapping",
		"Check",
		"Based on Other Attribute Mapping",
		default="0",
	),
	_field(
		"packing_mode",
		"Select",
		"Packing Mode",
		options="\nSize Ratio Packing\nSize Wise Packing",
		depends_on="eval: doc.based_on_other_attribute_mapping",
		description=(
			"Size Ratio Packing: one box mixes sizes in a ratio that sums to Packing Combo. "
			"Size Wise Packing: each size is packed in its own box with its own pieces per box."
		),
	),
	_field(
		"packing_size_details",
		"Table",
		"Packing Size Details",
		options="Item Production Detail Packing Size Detail",
		depends_on="eval: doc.based_on_other_attribute_mapping && doc.packing_mode == 'Size Ratio Packing'",
	),
	_field(
		"packing_assortment_attributes",
		"Table MultiSelect",
		"Packing Assortment Attributes",
		options="Item Production Detail Packing Assortment Attribute",
		hidden=1,
		depends_on="eval: doc.based_on_other_attribute_mapping && !doc.packing_mode",
		description="Auto-derived from the pack stage; kept hidden.",
	),
	_field(
		"get_packing_combination",
		"Button",
		"Get Packing Combination",
		depends_on="eval: doc.based_on_other_attribute_mapping && !doc.packing_mode && !doc.__islocal",
	),
	_field(
		"packing_assortment_html",
		"HTML",
		"Packing Assortment",
		depends_on="eval: doc.based_on_other_attribute_mapping && !doc.packing_mode",
	),
	_field("packing_assortment_json", "JSON", "Packing Assortment JSON", hidden=1),
	_field("set_item_tab", "Tab Break", "Set Item", depends_on="eval: !doc.__islocal && doc.packing_attribute"),
	_field("set_item_details_section", "Section Break", "Set Item Details"),
	_field("is_set_item", "Check", "Is Set Item", default="0"),
	_field(
		"set_item_attribute",
		"Link",
		"Set Item Attribute",
		options="Item Attribute",
		depends_on="eval: doc.is_set_item",
		mandatory_depends_on="eval: doc.is_set_item",
	),
	_field(
		"major_attribute_value",
		"Link",
		"Major Attribute Value",
		options="Item Attribute Value",
		depends_on="eval: doc.is_set_item && doc.set_item_attribute",
		mandatory_depends_on="eval: doc.is_set_item",
		description="The main Set Item Attribute",
	),
	_field(
		"get_set_item_combination",
		"Button",
		"Get Set Item Combination",
		depends_on="eval: doc.is_set_item && doc.set_item_attribute && doc.major_attribute_value",
	),
	_field(
		"set_item_combination_details",
		"Table",
		"Set Item Combination Details",
		options="Item Production Detail Set Item Combination",
		hidden=1,
	),
	_field("set_items_html", "HTML", "Set Items HTML"),
	_field("stiching_tab", "Tab Break", "Stiching", depends_on="eval: !doc.__islocal"),
	_field("stiching_details_section", "Section Break", "Stiching Details"),
	_field(
		"stiching_major_attribute_value",
		"Link",
		"Stiching Major Attribute Value",
		options="Item Attribute Value",
		depends_on="eval: doc.stiching_attribute",
	),
	_field("section_break_lpco", "Section Break"),
	_field(
		"get_stiching_attribute_values",
		"Button",
		"Get Stiching Attribute Values",
		depends_on="eval: doc.stiching_major_attribute_value",
	),
	_field("stiching_item_details", "Table", "Stiching Item Details", options="Stiching Item Detail"),
	_field("section_break_wfps", "Section Break"),
	_field("is_same_packing_attribute", "Check", "Is Same Packing Attribute", default="0"),
	_field("get_stiching_item_combination", "Button", "Get Stiching Item Combination"),
	_field("stiching_items_html", "HTML", "Stiching Items HTML"),
	_field(
		"stiching_item_combination_details",
		"Table",
		"Stiching Item Combination Details",
		options="Item Production Detail Set Item Combination",
		hidden=1,
	),
	_field("bundle_details_section", "Section Break", "Bundle Details"),
	_field("cutting_marker_groups", "Table", "Cutting Marker Groups", options="Cutting Marker Group", hidden=1),
	_field("bundle_group_html", "HTML", "Bundle Group HTML"),
	_field("emblishment_tab", "Tab Break", "Emblishment"),
	_field("emblishment_details_html", "HTML", "Emblishment Details HTML"),
	_field("emblishment_details_json", "JSON", "Emblishment Details JSON", hidden=1),
	_field("cutting_tab", "Tab Break", "Cutting", depends_on="eval: !doc.__islocal"),
	_field("cutting_details_section", "Section Break", "Cloth Details"),
	_field(
		"cloth_attributes",
		"Table MultiSelect",
		"Cloth Attributes",
		options="Cutting Attribute Detail",
		hidden=1,
	),
	_field("cloth_detail", "Table", "Cloth Detail", options="Item Production Detail Cloth Detail"),
	_field("update_cloth_items", "Button", "Update Cloth Items"),
	_field("section_break_eorj", "Section Break", "Cutting Details"),
	_field(
		"cutting_attributes",
		"Table MultiSelect",
		"Cutting Attributes",
		options="Cutting Attribute Detail",
		hidden=1,
	),
	_field("select_attributes_html", "HTML", "Select Attributes HTML"),
	_field("get_cutting_combination", "Button", "Get Cutting Combination"),
	_field("cutting_items_html", "HTML", "Cutting Items HTML"),
	_field("cutting_items_json", "JSON", "Cutting Items JSON", hidden=1),
	_field("section_break_cqll", "Section Break", "Cloth Mapping Details"),
	_field("column_break_gwca", "Column Break", hidden=1),
	_field("select_cloths_attribute_html", "HTML", "Select Cloths Attribute HTML"),
	_field("get_cloth_combination", "Button", "Get Cloth Combination"),
	_field("cutting_cloths_html", "HTML", "Cutting Cloths HTML"),
	_field("cutting_cloths_json", "JSON", "Cutting Cloths JSON", hidden=1),
	_field("cloth_accessory_tab", "Tab Break", "Cloth Accessory", depends_on="eval: !doc.__islocal"),
	_field(
		"accessory_attributes",
		"Table MultiSelect",
		"Accessory Attributes",
		options="Cutting Attribute Detail",
		hidden=1,
	),
	_field("accessory_clothtype_combination_html", "HTML", "Accessory ClothType Combination HTML"),
	_field("select_cloth_accessory_html", "HTML", "Select Cloth Accessory HTML"),
	_field(
		"get_accessory_combination",
		"Button",
		"Get Accessory Combination",
		depends_on='eval: doc.accessory_clothtype_json != "{}"',
	),
	_field(
		"cloth_accessories_html",
		"HTML",
		"Cloth Accessories HTML",
		depends_on='eval: doc.accessory_clothtype_json != "{}"',
	),
	_field("cloth_accessory_json", "JSON", "Cloth Accessory JSON", hidden=1),
	_field("accessory_clothtype_json", "JSON", "Accessory Clothtype JSON", hidden=1),
	_field("section_break_bfkp", "Section Break"),
	_field(
		"get_stiching_accessory_combination",
		"Button",
		"Get Stiching Accessory Combination",
		depends_on='eval: doc.accessory_clothtype_json != "{}"',
	),
	_field("stiching_accessory_json", "JSON", "Stiching Accessory JSON", hidden=1),
	_field(
		"stiching_accessory_html",
		"HTML",
		"Stiching Accessory HTML",
		depends_on='eval: doc.accessory_clothtype_json != "{}"',
	),
	_field("advance_settings_tab", "Tab Break", "Advance Settings"),
	_field("packing_details_section", "Section Break", "Packing Details Section"),
	_field("packing_process", "Link", "Packing Process", options="Process"),
	_field(
		"pack_in_stage",
		"Link",
		"Pack In Stage",
		options="Item Attribute Value",
		depends_on="eval: doc.dependent_attribute_mapping",
		mandatory_depends_on="eval: doc.dependent_attribute_mapping && !doc.__islocal",
		description="The stage which is used for packing.",
	),
	_field("column_break_iknj", "Column Break"),
	_field(
		"packing_attribute",
		"Link",
		"Packing Attribute",
		options="Item Attribute",
		mandatory_depends_on="eval: !doc.__islocal",
		description="Attribute based on which Packing Depends",
	),
	_field(
		"pack_out_stage",
		"Link",
		"Pack Out Stage",
		options="Item Attribute Value",
		depends_on="eval: doc.dependent_attribute_mapping",
		mandatory_depends_on="eval: doc.dependent_attribute_mapping && !doc.__islocal",
	),
	_field("stitching_details_section_section", "Section Break", "Stitching Details Section"),
	_field("stiching_process", "Link", "Stiching Process", options="Process"),
	_field(
		"stiching_in_stage",
		"Link",
		"Stiching In Stage",
		options="Item Attribute Value",
		depends_on="eval: doc.stiching_attribute",
	),
	_field("column_break_xhgb", "Column Break"),
	_field("stiching_attribute", "Link", "Stiching Attribute", options="Item Attribute"),
	_field(
		"stiching_out_stage",
		"Link",
		"Stiching Out Stage",
		options="Item Attribute Value",
		depends_on="eval: doc.stiching_attribute",
	),
	_field("cutting_details_section_section", "Section Break", "Cutting Details Section"),
	_field("cutting_process", "Link", "Cutting Process", options="Process"),
]


def execute():
	insert_after = "bom_attribute_mapping_html"
	fields = []
	for field in IPD_CUSTOM_FIELDS:
		row = dict(field)
		row["insert_after"] = insert_after
		fields.append(row)
		insert_after = row["fieldname"]

	create_custom_fields({"Item Production Detail": fields})
