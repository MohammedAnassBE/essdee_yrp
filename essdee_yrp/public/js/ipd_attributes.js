frappe.provide("essdee_yrp");

// Colour and Dia attribute names are owned by SD YRP IPD Settings and sent in boot.
const IPD_ATTRIBUTE_SETTINGS = {
	colour: "Default Packing Attribute",
	dia: "Default Dia Attribute",
};

function get_ipd_attribute(key) {
	const attribute = frappe.boot.essdee_yrp_ipd_attributes?.[key];
	if (!attribute) {
		frappe.throw(__("Set {0} in SD YRP IPD Settings", [__(IPD_ATTRIBUTE_SETTINGS[key])]));
	}
	return attribute;
}

essdee_yrp.get_colour_attribute = () => get_ipd_attribute("colour");
essdee_yrp.get_dia_attribute = () => get_ipd_attribute("dia");
