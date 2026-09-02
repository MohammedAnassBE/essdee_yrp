// Essdee Item BOM mappings must use the linked IPD's exact Cutting
// combinations. The base editor's local Item-master Cartesian product is kept
// as a fallback for mappings that do not belong to an IPD.

(function install_essdee_item_bom_mapping_editor() {
	const BaseEditor = frappe.production?.ui?.EditBOMAttributeMapping;
	if (!BaseEditor || BaseEditor.__essdee_ipd_combinations) return;

	function patch_combination_source(editor, frm) {
		const component = editor?.bomEntry;
		if (!component || component.__essdee_ipd_combinations) return;

		// Base YRP clears every BOM input inside toggle_row, including when a
		// saved row is being enabled during load_data. Keep the value on enable;
		// disabling a row must continue to clear its editable BOM values.
		component.toggle_row = function (index, included) {
			const row = this.data?.[index];
			if (!row) return;
			row.included = Boolean(included);

			for (const attribute of this.bom_attributes) {
				const attribute_name = this.get_attribute_name("bom", attribute);
				const input = this.attribute_inputs?.[index]?.[attribute_name];
				if (!input) continue;
				if (!included) {
					row[attribute_name] = null;
					input.set_value("");
				}
				input.df.reqd = Boolean(included);
				input.df.read_only = !included;
				input.refresh();
			}
		};

		const base_set_attributes = component.set_attributes.bind(component);
		component.set_attributes = async function (attributes) {
			if (!frm.doc.item_production_detail) {
				return base_set_attributes(attributes);
			}

			this.remove_attribute_inputs();
			this.attributes = attributes || [];
			this.item_attributes = this.get_mapping_attributes("item", this.attributes);
			this.bom_attributes = this.get_mapping_attributes("bom", this.attributes);
			this.attribute_values = this.get_item_attribute_values(this.attributes);
			this.data = [];

			if (!this.attributes.length || !this.item_attributes.length) return;

			const response = await frappe.call({
				method: "essdee_yrp.item_bom_attribute_mapping.get_item_bom_mapping_combinations",
				args: {
					ipd: frm.doc.item_production_detail,
					item: frm.doc.item,
					item_attributes: this.item_attributes,
					bom_attributes: this.bom_attributes,
				},
			});

			this.data = response.message || [];
			await this.$nextTick();
			this.create_attribute_inputs();
			$(this.$el).find(".control-label").remove();
		};
		component.__essdee_ipd_combinations = true;
	}

	class EssdeeItemBOMAttributeMappingEditor extends BaseEditor {
		constructor(wrapper) {
			super(wrapper);
			patch_combination_source(this, cur_frm);
		}
	}

	EssdeeItemBOMAttributeMappingEditor.__essdee_ipd_combinations = true;
	frappe.production.ui.EditBOMAttributeMapping = EssdeeItemBOMAttributeMappingEditor;
})();
