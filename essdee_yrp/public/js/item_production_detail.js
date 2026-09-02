// Copyright (c) 2024, Essdee and contributors
// For license information, please see license.txt

const IPD_LAYOUT_FIELDTYPES = new Set([
	"Section Break", "Column Break", "Tab Break", "Heading", "Fold",
]);

const APPROVED_IPD_HTML_LOCK_CLASS = "essdee-approved-ipd-html-locked";

function ensure_approved_ipd_lock_styles() {
	if (document.getElementById("essdee-approved-ipd-lock-styles")) return;
	$("<style>", {
		id: "essdee-approved-ipd-lock-styles",
		text: `
			.${APPROVED_IPD_HTML_LOCK_CLASS} button,
			.${APPROVED_IPD_HTML_LOCK_CLASS} .btn,
			.${APPROVED_IPD_HTML_LOCK_CLASS} .cursor-pointer,
			.${APPROVED_IPD_HTML_LOCK_CLASS} td:has(svg use[href*="delete"]) {
				display: none !important;
			}
			.${APPROVED_IPD_HTML_LOCK_CLASS} input,
			.${APPROVED_IPD_HTML_LOCK_CLASS} select,
			.${APPROVED_IPD_HTML_LOCK_CLASS} textarea,
			.${APPROVED_IPD_HTML_LOCK_CLASS} .form-control {
				pointer-events: none !important;
				background: var(--control-bg-disabled, var(--control-bg)) !important;
				cursor: not-allowed !important;
			}
		`,
	}).appendTo(document.head);
}

function restore_approved_ipd_lock(frm) {
	const state = frm._essdee_approved_ipd_lock_state;
	if (!state) return;
	for (const [fieldname, values] of Object.entries(state.fields)) {
		if (!frm.fields_dict[fieldname]) continue;
		frm.set_df_property(fieldname, "read_only", values.read_only);
		frm.set_df_property(fieldname, "hidden", values.hidden);
	}
	for (const [fieldname, values] of Object.entries(state.html)) {
		const wrapper = frm.fields_dict[fieldname]?.wrapper;
		if (!wrapper) continue;
		$(wrapper).css({
			"pointer-events": values.pointer_events,
			"opacity": values.opacity,
		}).removeClass(APPROVED_IPD_HTML_LOCK_CLASS);
	}
	frm._essdee_approved_ipd_lock_state = null;
	if (frm.doc.docstatus === 0 && (frm.perm || []).some((permission) => permission.write)) {
		frm.enable_save();
	}
}

function apply_approved_ipd_lock(frm) {
	if (frm.is_new() || frm.doc.approval_status !== "Approved") return;
	ensure_approved_ipd_lock_styles();

	const state = { fields: {}, html: {} };
	for (const df of frm.meta.fields || []) {
		if (!df.fieldname || IPD_LAYOUT_FIELDTYPES.has(df.fieldtype)) continue;
		state.fields[df.fieldname] = {
			read_only: Number(Boolean(df.read_only)),
			hidden: Number(Boolean(df.hidden)),
		};
		if (df.fieldtype === "Button") {
			frm.set_df_property(df.fieldname, "hidden", 1);
		} else if (df.fieldtype !== "HTML") {
			frm.set_df_property(df.fieldname, "read_only", 1);
		}
	}

	// The panel-wise matrix has a purpose-built locked view that keeps its panel
	// tabs usable. Other HTML islands expose their own editing controls, so make
	// those islands view-only as one unit while the IPD is approved.
	for (const df of (frm.meta.fields || []).filter((field) => field.fieldtype === "HTML")) {
		if (df.fieldname === "panel_wise_consumption_matrix_html") continue;
		const wrapper = frm.fields_dict[df.fieldname]?.wrapper;
		if (!wrapper) continue;
		const style = getComputedStyle(wrapper);
		state.html[df.fieldname] = {
			pointer_events: style.pointerEvents,
			opacity: style.opacity,
		};
		$(wrapper)
			.addClass(APPROVED_IPD_HTML_LOCK_CLASS)
			.css({ "pointer-events": "none", "opacity": "1" });
	}

	frm._essdee_approved_ipd_lock_state = state;
	frm.disable_save();
}

function add_ipd_process_matrix_button(frm) {
	const label = __("Generate / Regenerate IPD Process Matrix");
	frm.remove_custom_button(label);
	if (frm.is_new() || !frm.doc.name) return;
	frm.add_custom_button(label, () => {
		frappe.call({
			method: "essdee_yrp.garment_work_order.regenerate_ipd_process_matrices",
			args: { ipd_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Generating IPD Process Matrix..."),
			callback(r) {
				const result = r.message || {};
				const skipped = result.skipped || [];
				frappe.show_alert({
					message: __("Generated {0} matrix record(s) for: {1}.{2}", [
						result.count || 0,
						(result.processes || []).join(", ") || __("No processes"),
						skipped.length ? ` ${__("Skipped {0} invalid variant(s).", [skipped.length])}` : "",
					]),
					indicator: skipped.length ? "orange" : "green",
				}, 8);
				if (skipped.length) {
					frappe.msgprint({
						title: __("Matrix Generation Needs IPD Setup"),
						indicator: "orange",
						message: skipped.map((row) =>
							`<b>${frappe.utils.escape_html(row.item_variant)}</b>: ${frappe.utils.escape_html(row.reason)}`
						).join("<br>"),
					});
				}
			},
		});
	});
}

frappe.ui.form.on("YRP Item Production Detail", {
	setup:function(frm) {
		frm.trigger("declarations")
		frm.set_query("dia", "knitting_dia_details", () => ({ filters: { attribute_name: "Dia" } }));
		frm.set_query("from_colour", "dyeing_colour_details", () => ({ filters: { attribute_name: "Colour" } }));
		frm.set_query("to_colour", "dyeing_colour_details", () => ({ filters: { attribute_name: "Colour" } }));
		frm.set_query("from_dia", "compacting_dia_details", () => ({ filters: { attribute_name: "Dia" } }));
		frm.set_query("to_dia", "compacting_dia_details", () => ({ filters: { attribute_name: "Dia" } }));
		frm.set_query("colour", "colour_yarn_recipes", () => ({ filters: { attribute_name: "Colour" } }));
		frm.set_query("cloth_item", "colour_yarn_recipes", () => {
			const cloths = frm.doc.is_cloth_item
				? [frm.doc.item]
				: (frm.doc.cloth_detail || []).map((row) => row.cloth).filter(Boolean);
			return cloths.length ? { filters: { name: ["in", cloths] } } : {};
		});
		frm.set_query("colour", "compacting_reference_details", () => ({ filters: { attribute_name: "Colour" } }));
		frm.set_query("input_dia", "compacting_reference_details", () => ({ filters: { attribute_name: "Dia" } }));
		frm.set_query("compacting_dia", "compacting_reference_details", () => ({ filters: { attribute_name: "Dia" } }));
		const setAttributeQuery = (doc)=>{
			const attributes = (doc.item_attributes || []).map(attr => attr.attribute)
			return { filters: { name: ["in", attributes] } };
		};
		// frm.set_query("item", ()=> {
		// 	frappe.call({
		// 		method: "essdee_yrp.ipd_ui.get_ipd_item_group",
		// 		callback: function(r) {
		// 			if (r.message) {
		// 				let item_groups = r.message;
		// 				frm.set_query("item", () => {
		// 					return {
		// 						filters: {
		// 							item_group: ["in", item_groups]
		// 						}
		// 					};
		// 				});
		// 			}
		// 		}
		// 	});
		// })
		frm.set_query('set_item_attribute', setAttributeQuery);
		frm.set_query('packing_attribute', setAttributeQuery);
		frm.set_query('stiching_attribute', setAttributeQuery);

		frm.set_query('attribute_value','packing_attribute_details',() => {
			if(!frm.doc.packing_attribute){
				frappe.throw("Please select the packing attribute first")
			}
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.set_packing_attr_map_value,
				}
			}
		});
		frm.set_query('in_stage','ipd_processes',() => {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		});
		frm.set_query('out_stage','ipd_processes',() => {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		});
		frm.set_query('pack_in_stage', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		})
		frm.set_query('cutting_in_stage', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		})
		frm.set_query('stiching_out_stage', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		})
		frm.set_query('stiching_in_stage', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		})
		frm.set_query('pack_out_stage', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		})
		frm.set_query('stiching_attribute_value','stiching_item_details', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stiching_attribute_mapping,
				}
			}
		})
		frm.set_query('stiching_major_attribute_value', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stiching_attribute_mapping,
				}
			}
		})
		frm.set_query('set_item_attribute_value','stiching_item_details', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.set_item_attr_map_value,
				}
			}
		})
		frm.set_query('item','item_bom', ()=> {
			return {
				filters: {
					'disabled': 0,
				}
			}
		})
		frm.set_query('dependent_attribute_value','item_bom', ()=> {
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.stage,
				}
			}
		})
		frm.set_query('major_attribute_value', ()=> {
			if(!frm.doc.set_item_attribute){
				frappe.throw("Please set the Set Attribute Item")
			}
			return {
				query:'essdee_yrp.ipd_ui.get_attribute_detail_values',
				filters: {
					'mapping': frm.set_item_attr_map_value,
				}
			}
		})
	},
	declarations(frm){
		frm.set_packing_attr_map_value = null;
		frm.set_item_attr_map_value = null
		frm.stage = null
		frm.stiching_attribute_mapping = null
		frm.cutting_attrs = frm.cutting_attrs || []

		for(let i = 0; i < (frm.doc.item_attributes || []).length; i++){
			if(frm.doc.item_attributes[i].attribute == frm.doc.packing_attribute){
				frm.set_packing_attr_map_value = frm.doc.item_attributes[i].mapping;
			}
			if(frm.doc.item_attributes[i].attribute == frm.doc.set_item_attribute){
				frm.set_item_attr_map_value= frm.doc.item_attributes[i].mapping
			}
			if(frm.doc.item_attributes[i].attribute == frm.doc.dependent_attribute){
				frm.stage = frm.doc.item_attributes[i].mapping
			}
			if(frm.doc.item_attributes[i].attribute == frm.doc.stiching_attribute){
				frm.stiching_attribute_mapping = frm.doc.item_attributes[i].mapping
			}
		}
	},
	refresh: async function(frm) {
		restore_approved_ipd_lock(frm)
		frm.trigger('declarations')
		frm.trigger('onload_post_render')
		if(!frm.is_new()){
			const approval_status = frm.doc.approval_status || "Not Approved"
			const approval_colour = approval_status === "Approved"
				? "green"
				: "orange"
			frm.page.set_indicator(__(approval_status), approval_colour)
		}
		if (!frm.is_new()) {
			frappe.xcall("essdee_yrp.ipd_ui.get_approval_roles").then(settings => {
				let allowed = settings || [];
				if (allowed.some(role => frappe.user_roles.includes(role))) {
					if (frm.doc.approval_status !== "Approved") {
						frm.add_custom_button(__("Approve"), () => {
							frappe.call({
								method: "essdee_yrp.ipd_ui.approve_ipd",
								args: { doc_name: frm.doc.name, approval_type: "Approved" },
								callback: function () {
									frappe.show_alert({ message: __("Item Production Detail Approved"), indicator: "green" });
									frm.reload_doc();
								}
							});
						});
						frm.change_custom_button_type(__("Approve"), null, "success");
					}
					if (frm.doc.approval_status && frm.doc.approval_status !== "Not Approved") {
						frm.add_custom_button(__("Revert Approval"), () => {
							frappe.confirm(__("Revert approval status to Not Approved?"), () => {
								frappe.call({
									method: "essdee_yrp.ipd_ui.revert_ipd_approval",
									args: { doc_name: frm.doc.name },
									callback: function () {
										frappe.msgprint({
											title: __("Success"),
											message: __("IPD Reverted Successfully"),
											indicator: "green",
										});
										frm.reload_doc();
									}
								});
							});
						});
						frm.change_custom_button_type(__("Revert Approval"), null, "danger");
					}
				}
			});
		}
		clear_html_fields(frm, [
			"item_attribute_list_values_html", "dependent_attribute_details_html",
			"bom_attribute_mapping_html", "set_items_html", "stiching_items_html",
			"cutting_items_html", "cutting_cloths_html", "cloth_accessories_html",
			"stiching_accessory_html", "accessory_clothtype_combination_html",
			"emblishment_details_html", "select_cloths_attribute_html",
			"select_attributes_html", "select_cloth_accessory_html", "bundle_group_html",
			"panel_wise_consumption_matrix_html", "colour_yarn_recipe_editor"
		])
		if(frm.doc.stiching_in_stage && frm.doc.dependent_attribute){
			frm.cutting_attrs = await get_stich_in_attributes(frm.doc.dependent_attribute_mapping,frm.doc.stiching_in_stage, frm.doc.item)
			if(frm.doc.is_set_item){
				frm.cutting_attrs.push(frm.doc.set_item_attribute)
			}
			if(!frm.doc.enable_panel_wise_consumption_matrix){
				make_select_attributes(frm,'select_attributes_html','select_attributes_wrapper','select_attrs_multicheck','cutting_attributes','cutting_items_json','get_cutting_combination')
			}
			make_select_attributes(frm,'select_cloths_attribute_html','select_cloths_attributes_wrapper','select_cloth_attrs_multicheck','cloth_attributes','cutting_cloths_json', 'get_cloth_combination')
			let accessoryClothTypeObj = parse_json_value(frm.doc.accessory_clothtype_json, {});
			if (Object.keys(accessoryClothTypeObj).length > 0) {
				make_select_attributes(frm, 'select_cloth_accessory_html', 'select_cloths_accessory_wrapper', 'select_cloth_accessory_multicheck', 'accessory_attributes', 'cloth_accessory_json', 'get_accessory_combination');
			}
		}
		frm.refresh_field('emblishment_details_json')
		frm.refresh_field('cutting_items_json')
		frm.refresh_field('cutting_cloths_json')
		frm.refresh_field('cloth_accessory_json')
		frm.refresh_field('accessory_clothtype_json')
		frm.refresh_field('stiching_accessory_json')
		if (frm.doc.__islocal) {
			hide_field(["item_attribute_list_values_html", "bom_attribute_mapping_html",'dependent_attribute_details_html']);
		} 
		else {
			unhide_field(["item_attribute_list_values_html", "bom_attribute_mapping_html",'dependent_attribute_details_html']);
			frm.trigger('load_item_attribute_details')
			
			if (!frm.doc.is_set_item){
				hide_field('set_items_html')
			} 
			else{
				unhide_field('set_items_html')
				frm.trigger('make_set_combination')
			}
			frm.add_custom_button("Duplicate IPD", ()=> {
				let d = new frappe.ui.Dialog({
					title: "Duplicate IPD",
					fields: [
						{
							label: "Item",
							fieldname: "item",
							fieldtype: "Link",
							options: "YRP Item",
							default: frm.doc.item,
							reqd: 1,
						}
					],
					primary_action_label: "Duplicate",
					primary_action(values){
						frappe.call({
							method: "essdee_yrp.ipd_ui.duplicate_ipd",
							args: {
								"ipd": frm.doc.name,
								"item": values.item,
							},
							freeze: true,
							freeze_message: "Duplicating IPD",
							callback: function(r){
								d.hide()
								frappe.set_route("Form", "YRP Item Production Detail", r.message)
							}
						})
					},
				})
				frappe.call({
					method: "essdee_yrp.ipd_ui.get_ipd_item_group",
					callback: function(r) {
						if (r.message) {
							d.fields_dict.item.get_query = () => {
								return {
									filters: {
										item_group: ["in", r.message]
									}
								};
							};
						}
					}
				});
				d.show()
			})
		}
		
		await frm.trigger('make_hide_and_unhide_tabs')
		if((frm.doc.cloth_detail || []).length == 0){
			frm.set_df_property('get_cutting_combination','hidden',true);
		}
		else{
			frm.set_df_property('get_cutting_combination','hidden',false);
		}
			await frm.trigger("render_panel_wise_consumption_matrix")
			await frm.trigger("render_panel_wise_cloth_mapping")

			add_ipd_process_matrix_button(frm)
			apply_approved_ipd_lock(frm)
		},
	async make_hide_and_unhide_tabs(frm){
		if(frm.doc.dependent_attribute){
			await frm.trigger('make_stiching_combination')
			await frm.trigger("bundle_combination")
			// Both Cutting Details and Cloth Mapping use async Vue mounts. Waiting
			// here prevents the later refresh renderers from clearing the cloth
			// wrapper while its saved cutting_cloths_json is still loading.
			await frm.trigger('make_cutting_combination')
			await frm.trigger('make_packing_assortment')
			await frm.trigger('make_cloth_accessories')
			await frm.trigger('make_stiching_accessory_combination')
			await frm.trigger("emblishment_details")
			if ((frm.doc.cloth_detail || []).length > 0) {
				await frm.trigger('make_clothtype_accessory_combination')
			}
		}

		if(!frm.doc.packing_attribute){
			frm.$wrapper.find("[data-fieldname='set_item_tab']").hide();
		}
		else{
			frm.$wrapper.find("[data-fieldname='set_item_tab']").show();
		}
	},
	bundle_combination(frm){
		if((frm.doc.stiching_item_details || []).length > 0){
			frm.bundle_group = new frappe.production.ui.BundleGroup(frm.fields_dict['bundle_group_html'].wrapper)
			if(frm.doc.__onload && frm.doc.__onload.bundle_group_details){
				frm.bundle_group.load_data(frm.doc.__onload.bundle_group_details)
			}
		}
	},
	load_item_attribute_details(frm){
		if (!frm.doc.__onload) {
			return
		}
		$(frm.fields_dict['item_attribute_list_values_html'].wrapper).html("");
		new frappe.production.ui.ItemAttributeList({
			wrapper: frm.fields_dict["item_attribute_list_values_html"].wrapper,
			attr_values: frm.doc.__onload["attr_list"] || []
		});
		$(frm.fields_dict['dependent_attribute_details_html'].wrapper).html("");
		new frappe.production.ui.ItemDependentAttributeDetail(frm.fields_dict["dependent_attribute_details_html"].wrapper);

		$(frm.fields_dict['bom_attribute_mapping_html'].wrapper).html("");
		new frappe.production.ui.BomItemAttributeMapping(frm.fields_dict["bom_attribute_mapping_html"].wrapper);

	},
	async make_set_combination(frm){
		$(frm.fields_dict['set_items_html'].wrapper).html("");
		frm.set_item = new frappe.production.ui.CombinationItemDetail(frm.fields_dict['set_items_html'].wrapper);
		if(frm.doc.__onload && frm.doc.__onload.set_item_detail) {
			frm.doc['set_item_detail'] = JSON.stringify(frm.doc.__onload.set_item_detail);
			await frm.set_item.load_data(frm.doc.__onload.set_item_detail);
			frm.set_item.set_attributes()
		}
	},
	async update_cloth_items(frm){
		if(frm.cloth_item){
			if(frm.doc.cutting_cloths_json) {
				let cloths = []
				for(let i = 0 ; i < frm.doc.cloth_detail.length; i++){
					if(frm.doc.cloth_detail[i].name1 && frm.doc.cloth_detail[i].cloth){
						cloths.push(frm.doc.cloth_detail[i].name1)
					}
				}
				let cut_json = frm.doc.cutting_cloths_json
				if (typeof(cut_json) == "string"){
					cut_json = JSON.parse(cut_json)
				}
				cut_json['select_list'] = cloths
				await frm.cloth_item.load_data(cut_json);
				frm.cloth_item.set_attributes()
			}
		}
		if(frm.stiching_accessory){
			if(frm.doc.stiching_accessory_json){
				let cloths = []
				for(let i = 0 ; i < frm.doc.cloth_detail.length; i++){
					if(frm.doc.cloth_detail[i].name1 && frm.doc.cloth_detail[i].cloth){
						cloths.push(frm.doc.cloth_detail[i].name1)
					}
				}	
				let stich_json = frm.doc.stiching_accessory_json
				stich_json = parse_json_value(stich_json, {})
				stich_json['select_list'] = cloths
				await frm.stiching_accessory.load_data(stich_json);
				frm.stiching_accessory.set_attributes()
			}
		}
	},
	async make_stiching_combination(frm){
		$(frm.fields_dict['stiching_items_html'].wrapper).html("");
		frm.stiching_item = new frappe.production.ui.CombinationItemDetail(frm.fields_dict['stiching_items_html'].wrapper);
		if(frm.doc.__onload && frm.doc.__onload.stiching_item_detail) {
			frm.doc['stiching_item_detail'] = JSON.stringify(frm.doc.__onload.stiching_item_detail);
			await frm.stiching_item.load_data(frm.doc.__onload.stiching_item_detail);
			frm.stiching_item.set_attributes()
		}
	},
	async make_cutting_combination(frm){
		if(!frm.doc.enable_panel_wise_consumption_matrix){
			$(frm.fields_dict['cutting_items_html'].wrapper).html("");
			frm.cutting_item = new frappe.production.ui.CuttingItemDetail(frm.fields_dict['cutting_items_html'].wrapper);
			if(frm.doc.cutting_items_json) {
				await frm.cutting_item.load_data(frm.doc.cutting_items_json);
				frm.cutting_item.set_attributes()
			}
		}
		if(frm.doc.enable_panel_wise_consumption_matrix){
			frm.cloth_item = null
			await frm.trigger("render_panel_wise_cloth_mapping")
			return
		}
		$(frm.fields_dict['cutting_cloths_html'].wrapper).html("");
		frm.cloth_item = new frappe.production.ui.CuttingItemDetail(frm.fields_dict['cutting_cloths_html'].wrapper);
		if(frm.doc.cutting_cloths_json) {
			await frm.cloth_item.load_data(frm.doc.cutting_cloths_json);
			frm.cloth_item.set_attributes()
		}
	},
	async make_cloth_accessories(frm){
		$(frm.fields_dict['cloth_accessories_html'].wrapper).html("");
		frm.cloth_accessories = new frappe.production.ui.ClothAccessory(frm.fields_dict['cloth_accessories_html'].wrapper);
		if(frm.doc.cloth_accessory_json) {
			await frm.cloth_accessories.load_data(frm.doc.cloth_accessory_json);
			frm.cloth_accessories.set_attributes()
		}
	},
	async make_stiching_accessory_combination(frm){
		$(frm.fields_dict['stiching_accessory_html'].wrapper).html("");
		frm.stiching_accessory = new frappe.production.ui.ClothAccessoryCombination(frm.fields_dict['stiching_accessory_html'].wrapper);
		if(frm.doc.stiching_accessory_json) {
			let acc = frm.doc.stiching_accessory_json
			let cloth_list = []
			for(let i = 0; i < frm.doc.cloth_detail.length; i++ ){
				cloth_list.push(frm.doc.cloth_detail[i]['name1'])
			}
			if(typeof(acc) == "string"){
				acc = JSON.parse(acc)
			}
			acc['select_list'] = cloth_list
			await frm.stiching_accessory.load_data(acc);
			frm.stiching_accessory.set_attributes()
		}
	},
	async make_clothtype_accessory_combination(frm){
		$(frm.fields_dict['accessory_clothtype_combination_html'].wrapper).html("");
		frm.accessory_clothtype = new frappe.production.ui.AccessoryItems(frm.fields_dict['accessory_clothtype_combination_html'].wrapper);
		if(frm.doc.accessory_clothtype_json) {
			await frm.accessory_clothtype.load_data(frm.doc.accessory_clothtype_json);
		}
	},
	emblishment_details(frm){
		$(frm.fields_dict['emblishment_details_html'].wrapper).html("");
		frm.emblishment = new frappe.production.ui.EmblishmentDetails(frm.fields_dict['emblishment_details_html'].wrapper);
		if(frm.doc.emblishment_details_json){
			frm.emblishment.load_data(frm.doc.emblishment_details_json)
		}
	},
	onload_post_render(frm){
		showOrHideColumns(frm,['dependent_attribute_value'],'item_bom', frm.doc.dependent_attribute ? 0 : 1)
		updateChildTableReqd(frm, ['dependent_attribute_value'],'item_bom', frm.doc.dependent_attribute ? 1 : 0)
		showOrHideColumns(frm,['set_item_attribute_value','is_default'],'stiching_item_details', frm.doc.is_set_item ? 0 : 1)
		updateChildTableReqd(frm, ['set_item_attribute_value',"is_default"],'stiching_item_details', frm.doc.is_set_item ? 1 : 0)
	},
	is_set_item(frm){
		showOrHideColumns(frm,['set_item_attribute_value','is_default'],'stiching_item_details', frm.doc.is_set_item ? 0 : 1)
		updateChildTableReqd(frm, ['set_item_attribute_value',"is_default"],'stiching_item_details', frm.doc.is_set_item ? 1 : 0)
	},
	get_packing_attribute_values: function(frm){
		frappe.call({
			method: 'essdee_yrp.ipd_ui.get_mapping_attribute_values',
			args: {
				attribute_mapping_value: frm.set_packing_attr_map_value ,
				attribute_no : frm.doc.packing_attribute_no,
			},
			callback: function(r){
				if(r.message){
					frm.set_value('packing_attribute_details', r.message)
					frm.refresh_field('packing_attribute_details')
				}
			}
		})
	},
	get_stiching_attribute_values(frm){
		frappe.call({
			method: 'essdee_yrp.ipd_ui.get_mapping_attribute_values',
			args: {
				attribute_mapping_value: frm.stiching_attribute_mapping ,
				attribute_no : null,
			},
			callback: function(r){
				if(r.message){
					const stitching_details = r.message.map(row => ({
						...row,
						quantity: 1,
						category: "Body",
					}))
					frm.set_value('stiching_item_details', stitching_details)
					frm.refresh_field('stiching_item_details')
				}
			}
		})
	},
	validate:async function(frm){
		if(!frm.doc.__islocal){
			if(frm.doc.enable_panel_wise_consumption_matrix && frm.panel_wise_consumption_matrix){
				let matrix = frm.panel_wise_consumption_matrix.get_data()
				if(matrix){
					frm.doc.panel_wise_consumption_matrix_json = matrix
				}
			}
			if(frm.doc.enable_panel_wise_consumption_matrix && frm.panel_wise_cloth_mapping){
				let matrix = frm.panel_wise_cloth_mapping.get_data()
				if(matrix){
					frm.doc.panel_wise_cloth_mapping_json = matrix
				}
			}
			if(frm.set_item && frm.doc.is_set_item){
				let item_details = frm.set_item.get_data()
				frm.doc['set_item_detail'] = JSON.stringify(item_details);
			}

			if(frm.stiching_item){
				let item_details = frm.stiching_item.get_data()
				if(item_details['values'].length > 0){
					frm.doc['stiching_item_detail'] = JSON.stringify(item_details);
				}
			}

			if(frm.select_attrs_multicheck){
				let cutting_attr_list = []
				let get_checked_attributes = frm.select_attrs_multicheck.get_checked_options()
				for(let i = 0 ; i< get_checked_attributes.length; i++){
					cutting_attr_list.push({'attribute':get_checked_attributes[i]})
				}
				frm.set_value('cutting_attributes',cutting_attr_list)
			}

			if(frm.select_cloth_attrs_multicheck){
				let cutting_attr_list = []
				let get_checked_attributes = frm.select_cloth_attrs_multicheck.get_checked_options()
				for(let i = 0 ; i< get_checked_attributes.length; i++){
					cutting_attr_list.push({'attribute':get_checked_attributes[i]})
				}
				frm.set_value('cloth_attributes',cutting_attr_list)
			}

			if(frm.select_cloth_accessory_multicheck){
				let cloth_accessories_list = []
				let get_checked_attributes = frm.select_cloth_accessory_multicheck.get_checked_options()
				for(let i = 0 ; i< get_checked_attributes.length; i++){
					cloth_accessories_list.push({'attribute':get_checked_attributes[i]})
				}
				frm.set_value('accessory_attributes',cloth_accessories_list)
			}

			// Only overwrite each tab's stored JSON when its widget actually rendered
			// and returned rows. When get_data()/get_items() is null (tab never opened,
			// e.g. on a freshly-synced doc) PRESERVE the stored value — wiping it to {}
			// here was destroying synced Cutting / Cloth-Accessory data on the first save.
			if(frm.cutting_item && !frm.doc.enable_panel_wise_consumption_matrix){
				let item_details = frm.cutting_item.get_data()
				if(item_details && item_details.items && item_details.items.length > 0){
					frm.doc.cutting_items_json = item_details
				}
			}

			if(frm.cloth_item){
				let item_details = frm.cloth_item.get_data()
				if(item_details && item_details.items && item_details.items.length > 0){
					frm.doc.cutting_cloths_json = item_details
				}
			}

			if(frm.cloth_accessories){
				let item_details = frm.cloth_accessories.get_data()
				if(item_details && item_details.items && item_details.items.length > 0){
					frm.doc.cloth_accessory_json = item_details
				}
			}

			if(frm.stiching_accessory){
				let item_details = frm.stiching_accessory.get_data()
				if(item_details && item_details.items && item_details.items.length > 0){
					frm.doc.stiching_accessory_json = item_details
				}
			}

			if(frm.accessory_clothtype){
				let item_details = frm.accessory_clothtype.get_data()
				if(item_details != null){
					frm.doc.accessory_clothtype_json = item_details
				}
			}
			if(frm.emblishment){
				let items = frm.emblishment.get_items()
				if(items){
					frm.doc.emblishment_details_json = items
				}
			}
			if(frm.bundle_group){
				let items = frm.bundle_group.get_items()
            	frm.doc['marker_details'] = items
			}
		}
	},
	item: function(frm) {
		if (frm.doc.item) {
			frappe.call({
				method: "essdee_yrp.ipd_ui.get_complete_item_details",
				args: {
					item_name: frm.doc.item
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value('primary_item_attribute',r.message.primary_attribute)
                        frm.set_value('item_attributes',r.message.attributes)
						frm.set_value('dependent_attribute', r.message.dependent_attribute)
						frm.set_value('dependent_attribute_mapping', r.message.dependent_attribute_mapping)
					}
				}
			});
		}
        else{
            frm.set_value('primary_item_attribute','')
            frm.set_value('item_attributes',[])
			frm.set_value('dependent_attribute','')
			frm.set_value('dependent_attribute_mapping','')
        }
	},
	get_set_item_combination(frm){
		if(!frm.doc.major_attribute_value){
			frappe.msgprint("Set the major attribute value")
			return
		}
		frappe.call({
			method:'essdee_yrp.ipd_ui.get_new_combination',
			args: {
				attribute_mapping_value : frm.set_item_attr_map_value,
				packing_attribute_details : frm.doc.packing_attribute_details,
				major_attribute_value : frm.doc.major_attribute_value,
			},
			callback:async function(r){
				await frm.set_item.load_data(r.message)
				frm.set_item.set_attributes()
			}
		})
	},
	get_stiching_item_combination(frm){
		if(!frm.doc.stiching_attribute){
			return
		}
		if(!frm.doc.stiching_major_attribute_value){
			frappe.msgprint("Set the stiching major attribute value")
			return
		}
		if(frm.doc.stiching_item_details.length == 0){
			frappe.msgprint("Set the Stiching Item Detail")
			return
		}
		frappe.call({
			method:'essdee_yrp.ipd_ui.get_new_combination',
			args: {
				attribute_mapping_value : frm.stiching_attribute_mapping,
				packing_attribute_details : frm.doc.packing_attribute_details,
				major_attribute_value : frm.doc.stiching_major_attribute_value,
				is_same_packing_attribute: frm.doc.is_same_packing_attribute,
				doc_name : frm.doc.name,
			},
			callback:async function(r){
				await frm.stiching_item.load_data(r.message)
				frm.stiching_item.set_attributes()
				frm.dirty()
			}
		})
	},
	get_cutting_combination(frm){
		let get_checked_attributes = frm.select_attrs_multicheck.get_checked_options()
		if(get_checked_attributes.length == 0){
			frappe.msgprint("Select the attributes to make combination")
			frm.cutting_item.load_data([])
		}
		else{
			frappe.call({
				method: 'essdee_yrp.ipd_ui.get_combination',
				args: {
					doc_name: frm.doc.name,
					attributes: get_checked_attributes,
					combination_type: 'Cutting',
				},
				callback:(async (r)=> {
					await frm.cutting_item.load_data(r.message)
					frm.cutting_item.set_attributes()
				})
			})
		}
	},
	get_packing_combination(frm){
		// Separator + assorted attributes are derived from the IDAM pack stage on the server.
		frappe.call({
			method: 'essdee_yrp.ipd_ui.get_packing_assortment_combination',
			args: { doc_name: frm.doc.name },
			callback: (r) => {
				if(r.message){
					frm.doc.packing_assortment_json = r.message
					frm.dirty()
					render_packing_assortment(frm)
				}
			}
		})
	},
	make_packing_assortment(frm){
		render_packing_assortment(frm)
	},
	packing_mode(frm){
		if(!frm.doc.based_on_other_attribute_mapping || !frm.doc.packing_mode){
			return
		}
		if(frm.doc.packing_mode === 'Size Wise Packing'){
			// Carton / free-count: each carton holds any number of pieces, entered at GRN time.
			// Packing Combo = 1 makes those pieces pass through 1:1; no size-ratio table is used.
			frm.set_value('packing_combo', 1)
			frm.clear_table('packing_size_details')
			frm.refresh_field('packing_size_details')
			return
		}
		// Size Ratio Packing: pre-fill one row per size (qty 0) so the user just types the ratio.
		frappe.call({
			method: 'essdee_yrp.ipd_ui.get_packing_size_values',
			args: { doc_name: frm.doc.name },
			callback: (r) => {
				if(!r.message){ return }
				// Preserve any quantities the user already entered for a size.
				let existing = {}
				;(frm.doc.packing_size_details || []).forEach(row => { existing[row.attribute_value] = row.quantity })
				// Sizes that carried a quantity but are no longer valid for this item.
				let dropped = Object.keys(existing).filter(s => existing[s] > 0 && !r.message.includes(s))
				frm.clear_table('packing_size_details')
				r.message.forEach(size => {
					let row = frm.add_child('packing_size_details')
					row.attribute_value = size
					row.quantity = existing[size] || 0
				})
				frm.refresh_field('packing_size_details')
				frm.dirty()
				if(dropped.length){
					frappe.msgprint("These sizes are no longer valid for this item; their quantities were cleared: " + dropped.join(', '))
				}
			}
		})
	},
	get_cloth_combination(frm){
		if(frm.doc.enable_panel_wise_consumption_matrix){
			if((frm.doc.cloth_detail || []).length === 0){
				frappe.msgprint("Fill The Cloth Details")
				return
			}
			const checked = frm.select_cloth_attrs_multicheck
				? frm.select_cloth_attrs_multicheck.get_checked_options()
				: []
			frm.set_value(
				"cloth_attributes",
				checked.map(attribute => ({attribute}))
			).then(() => frm.trigger("render_panel_wise_cloth_mapping"))
			return
		}
		if(!frm.cloth_item){
			$(frm.fields_dict['cutting_cloths_html'].wrapper).html("");
			frm.cloth_item = new frappe.production.ui.CuttingItemDetail(frm.fields_dict['cutting_cloths_html'].wrapper);
		}
		if(frm.doc.cloth_detail.length == 0){
			frappe.msgprint("Fill The Cloth Details")
			return
		}
		cloth_list = []
		for(let i = 0; i < frm.doc.cloth_detail.length; i++ ){
			cloth_list.push(frm.doc.cloth_detail[i]['name1'])
		}
		let get_checked_attributes = frm.select_cloth_attrs_multicheck.get_checked_options()
		if(get_checked_attributes.length == 0){
			frappe.msgprint("Select the attributes to make combination")
			frm.cloth_item.load_data([])
			return
		}
		frappe.call({
			method: 'essdee_yrp.ipd_ui.get_combination',
			args: {
				doc_name: frm.doc.name,
				attributes: get_checked_attributes,
				combination_type:'Cloth',
				cloth_list: cloth_list
			},
			callback:(async (r)=> {
				await frm.cloth_item.load_data(r.message)
				frm.cloth_item.set_attributes()
			})
		})
	},
	get_accessory_combination(frm){
		let get_checked_attributes = frm.select_cloth_accessory_multicheck.get_checked_options()
		if(get_checked_attributes.length == 0){
			frappe.msgprint("Select the attributes to make combination")
			frm.cloth_accessories.load_data([])
			return
		}
		frappe.call({
			method: 'essdee_yrp.ipd_ui.get_combination',
			args: {
				doc_name: frm.doc.name,
				attributes: get_checked_attributes,
				combination_type:'Accessory',
			},
			callback:(async (r)=> {
				await frm.cloth_accessories.load_data(r.message)
				frm.cloth_accessories.set_attributes()
			})
		})
	},
	get_stiching_accessory_combination(frm){
		cloth_list = []
		for(let i = 0; i < frm.doc.cloth_detail.length; i++ ){
			cloth_list.push(frm.doc.cloth_detail[i]['name1'])
		}
		frappe.call({
			method:"essdee_yrp.ipd_ui.get_stiching_accessory_combination",
			args: {
				cloth_list: cloth_list,
				doc_name:frm.doc.name,
			},
			callback:async function(r){
				await frm.stiching_accessory.load_data(r.message)
				frm.stiching_accessory.set_attributes()
			}
		})
	},
	set_item_attribute(frm){
		frm.set_item = new frappe.production.ui.CombinationItemDetail(frm.fields_dict['set_items_html'].wrapper);
		if(frm.doc.major_attribute_value){
			frm.trigger('get_set_item_combination')
		}
		if(frm.doc.is_set_item && frm.doc.set_item_attribute){
			frm.trigger('declarations')
			unhide_field(['set_items_html'])
			if(frm.doc.major_attr_value){
				frm.trigger('get_set_item_combination')
			}
		}
	},
	packing_attribute(frm){
		if(frm.doc.packing_attribute){
			frm.trigger('declarations')
		}
	},
	major_attribute_value(frm){
		frm.trigger('get_set_item_combination')
	},
	stiching_attribute(frm){
		if(frm.doc.stiching_attribute){
			frm.trigger('declarations')
		}
	},
	async enable_panel_wise_consumption_matrix(frm){
		await frm.trigger("render_panel_wise_consumption_matrix")
		await frm.trigger("render_panel_wise_cloth_mapping")
		if(!frm.doc.enable_panel_wise_consumption_matrix && frm.doc.stiching_in_stage && frm.doc.dependent_attribute){
			make_select_attributes(frm,'select_attributes_html','select_attributes_wrapper','select_attrs_multicheck','cutting_attributes','cutting_items_json','get_cutting_combination')
			await frm.trigger("make_cutting_combination")
		}
	},
	async render_panel_wise_consumption_matrix(frm){
		const enabled = Boolean(frm.doc.enable_panel_wise_consumption_matrix)
		const standard_fields = [
			"select_attributes_html", "get_cutting_combination", "cutting_items_html"
		]
		standard_fields.forEach(fieldname => {
			if(frm.fields_dict[fieldname]){
				const has_cloths = (frm.doc.cloth_detail || []).length > 0
				const visible = !enabled && (
					fieldname !== "get_cutting_combination" || has_cloths
				)
				frm.toggle_display(fieldname, visible)
			}
		})

		const field = frm.fields_dict.panel_wise_consumption_matrix_html
		if(!field){
			return
		}
		$(field.wrapper).empty()
		frm.panel_wise_consumption_matrix = null
		if(!enabled){
			return
		}
		if(!frm.doc.stiching_in_stage || !frm.doc.dependent_attribute){
			$(field.wrapper).html(
				'<div class="alert alert-warning">Set the stitching input stage and dependent attribute before using the panel-wise matrix.</div>'
			)
			return
		}

		const payload = await frappe.xcall(
			"essdee_yrp.panel_wise_consumption.get_panel_wise_consumption_matrix",
			{doc: frm.doc}
		)
		frm.panel_wise_consumption_matrix = new frappe.production.ui.PanelWiseConsumptionMatrix(field.wrapper)
		frm.panel_wise_consumption_matrix.load_data(
			payload,
			!frm.is_new() && frm.doc.approval_status === "Approved"
		)
	},
	async render_panel_wise_cloth_mapping(frm){
		const field = frm.fields_dict.cutting_cloths_html
		if(!field){
			return
		}
		if(!frm.doc.enable_panel_wise_consumption_matrix){
			frm.panel_wise_cloth_mapping = null
			return
		}
		$(field.wrapper).empty()
		frm.panel_wise_cloth_mapping = null
		if(!frm.doc.stiching_in_stage || !frm.doc.dependent_attribute){
			$(field.wrapper).html(
				'<div class="text-muted">Configure the Stitching input stage before using the Cloth Mapping matrix.</div>'
			)
			return
		}

		const stagedDoc = {...frm.doc}
		if(frm.panel_wise_consumption_matrix){
			stagedDoc.panel_wise_consumption_matrix_json =
				frm.panel_wise_consumption_matrix.get_data()
		}
		const payload = await frappe.xcall(
			"essdee_yrp.panel_wise_cloth_mapping.get_panel_wise_cloth_mapping_matrix",
			{doc: stagedDoc}
		)
		frm.panel_wise_cloth_mapping = new frappe.production.ui.PanelWiseClothMappingMatrix(field.wrapper)
		frm.panel_wise_cloth_mapping.load_data(
			payload,
			!frm.is_new() && frm.doc.approval_status === "Approved"
		)
	}
});

function showOrHideColumns(frm, fields, table, hidden) {
	if (!frm.fields_dict[table] || !frm.get_field(table).grid) {
		return
	}
	if (frappe.ui.form.editable_row) {
		frappe.ui.form.editable_row.toggle_editable_row(false)
	}
	let grid = frm.get_field(table).grid;
	for (let field of fields) {
		if (!grid.fields_map[field]) {
			continue
		}
		grid.fields_map[field].hidden = hidden;
	}
	grid.visible_columns = undefined;
	grid.setup_visible_columns();
	
	grid.header_row.wrapper.remove();
	delete grid.header_row;
	grid.make_head();
	
	for (let row of grid.grid_rows) {
		if (row.open_form_button) {
			row.open_form_button.parent().remove();
			delete row.open_form_button;
		}
		for (let field in row.columns) {
			if (row.columns[field] !== undefined) {
				row.columns[field].remove();
			}
		}
		for (let fieldname of fields) {
			let df = row.docfields.find(field => field.fieldname === fieldname)
			df && (df.hidden = hidden)
		}
		delete row.columns;
		row.columns = [];
		row.render_row();
	}
	frappe.ui.form.editable_row && frappe.ui.form.editable_row.toggle_editable_row(false)
}

function updateChildTableReqd(frm, fields, table, reqd) {
	if (!frm.fields_dict[table] || !frm.get_field(table).grid) {
		return
	}
    let grid = frm.get_field(table).grid;
    for (let row of grid.grid_rows) {
        if (row.open_form_button) {
            row.open_form_button.parent().remove();
            delete row.open_form_button;
        }
        for (let field in row.columns) {
            if (row.columns[field] !== undefined) {
                row.columns[field].remove();
            }
        }
        for (let fieldname of fields) {
			let df = row.docfields.find(field => field.fieldname === fieldname)
            df && (df.reqd = reqd)
        }
        delete row.columns;
        row.columns = [];
        row.render_row();
    }
    frappe.ui.form.editable_row && frappe.ui.form.editable_row.toggle_editable_row(false)
}

function clear_html_fields(frm, fields) {
	fields.forEach((fieldname) => {
		if (frm.fields_dict[fieldname]) {
			$(frm.fields_dict[fieldname].wrapper).html("");
		}
	})
}

function parse_json_value(value, fallback) {
	if (!value) {
		return fallback
	}
	if (typeof value === "string") {
		try {
			return JSON.parse(value)
		} catch (e) {
			return fallback
		}
	}
	return value
}

function render_packing_assortment(frm) {
	let $w = $(frm.fields_dict['packing_assortment_html'].wrapper).empty()
	let data = frm.doc.packing_assortment_json
	if (typeof data === 'string') {
		try { data = JSON.parse(data) } catch (e) { data = null }
	}
	if (!data || !data.boxes) { return }
	frm.doc.packing_assortment_json = data
	let assorted = data.assortment_attributes || []
	data.boxes.forEach((box, bi) => {
		let $card = $('<div style="margin-bottom:12px;"></div>').appendTo($w)
		$('<div style="font-weight:600;margin-bottom:4px;"></div>').text('Box: ' + box.box).appendTo($card)
		let $table = $('<table class="table table-bordered" style="margin-bottom:0;"></table>').appendTo($card)
		let $thead = $('<thead></thead>').appendTo($table)
		$('<tr></tr>')
			.append($('<th></th>').text(assorted.join(' / ')))
			.append($('<th style="width:120px;">Qty / Box</th>'))
			.appendTo($thead)
		let $tbody = $('<tbody></tbody>').appendTo($table)
		;(box.rows || []).forEach((row, ri) => {
			let label = assorted.map(a => row[a]).join(' / ')
			let $tr = $('<tr></tr>').appendTo($tbody)
			$('<td></td>').text(label).appendTo($tr)
			let $td = $('<td></td>').appendTo($tr)
			$('<input type="number" min="0" class="form-control input-sm">')
				.val(row.qty || 0)
				.on('input', function () {
					frm.doc.packing_assortment_json.boxes[bi].rows[ri].qty = parseFloat(this.value) || 0
					frm.dirty()
				})
				.appendTo($td)
		})
	})
}

async function get_stich_in_attributes(dependent_attribute_mapping, stiching_in_stage, item) {
    return new Promise((resolve, reject) => {
        frappe.call({
            method: 'essdee_yrp.ipd_ui.get_stiching_in_stage_attributes',
            args: {
                dependent_attribute_mapping: dependent_attribute_mapping,
                stiching_in_stage: stiching_in_stage,
                item: item,
            },
            callback: function(r) {
                resolve(r.message); 
            },
        });
    });
}

function make_select_attributes(frm, html_field, html_class, name, attrs, json_field, combination_type){
	let $wrapper = frm.get_field(html_field).$wrapper;
	$wrapper.empty();
	const select_attributes_wrapper = $(`<div class="${html_class}"></div>`).appendTo($wrapper);
	let cutting_attr_list = frm.doc[attrs]
	let check_list = []
	for(let i = 0; i < cutting_attr_list.length; i++){
		check_list.push(cutting_attr_list[i].attribute)
	}
	frm[name] = frappe.ui.form.make_control({
		parent: select_attributes_wrapper,
		df: {
			fieldname: "select_attributes_wrapper",
			fieldtype: "MultiCheck",
			// select_all: true,
			sort_options: false,
			columns: 4,
			get_data: () => {
				return frm.cutting_attrs.map(attr => {
					let check = 0
					if(check_list.includes(attr)){
						check = 1
					}
					return {
						label: attr,   
						value: attr,  
						checked: check   
					};
				});
			},
			on_change:()=> {
				frm.set_value(json_field,{});
				frm.trigger(combination_type)
			}
		},
		render_input: true,
	});
	frm[name].refresh_input();
}

function compacting_route_pairs(frm) {
	const seen = new Set();
	const pairs = [];
	const add_pair = (colour, input_dia) => {
		if (!colour || !input_dia) return;
		const key = `${colour}\u0000${input_dia}`;
		if (seen.has(key)) return;
		seen.add(key);
		pairs.push({ colour, input_dia });
	};
	(frm.doc.fabric_routes || []).forEach((row) => {
		add_pair(row.finished_colour || "", row.finished_dia || "");
	});
	if (!pairs.length) {
		const mappings = frm.doc.fabric_value_mappings || [];
		const introduced_dias = [...new Set(
			mappings
				.filter((row) => row.attribute === "Dia" && row.role === "Introduce")
				.map((row) => row.to_value)
				.filter(Boolean),
		)];
		const groups = new Map();
		mappings.forEach((row) => {
			const key = `${row.sequence || 0}\u0000${row.mapping_index || 0}`;
			if (!groups.has(key)) groups.set(key, []);
			groups.get(key).push(row);
		});
		groups.forEach((rows) => {
			const colour_entry = rows.find(
				(row) =>
					row.attribute === "Colour" &&
					["Change", "Introduce"].includes(row.role),
			);
			const dia_entry = rows.find(
				(row) =>
					row.attribute === "Dia" &&
					["Change", "Pin", "Introduce"].includes(row.role),
			);
			const colour = colour_entry?.to_value || colour_entry?.from_value || "";
			const dia = dia_entry?.to_value || dia_entry?.from_value || "";
			if (colour && dia) add_pair(colour, dia);
			else if (colour) introduced_dias.forEach((value) => add_pair(colour, value));
		});
		if (!pairs.length) {
			const recipe_colours = [...new Set(
				(frm.doc.colour_yarn_recipes || [])
					.map((row) => row.colour)
					.filter(Boolean),
			)];
			recipe_colours.forEach((colour) => {
				introduced_dias.forEach((dia) => add_pair(colour, dia));
			});
		}
	}
	return pairs.sort(
		(a, b) =>
			String(a.input_dia).localeCompare(String(b.input_dia), undefined, { numeric: true }) ||
			String(a.colour).localeCompare(String(b.colour), undefined, { numeric: true }),
	);
}

function compacting_targets(routes, scope, selected_colours) {
	if (scope === "All Colours") {
		return [...new Set(routes.map((row) => row.input_dia))].map((input_dia) => ({
			colour: "",
			input_dia,
		}));
	}
	if (scope === "Colour Group") {
		const selected = new Set(selected_colours || []);
		return routes.filter((row) => selected.has(row.colour));
	}
	return routes;
}

function open_compacting_generation_dialog(frm) {
	const routes = compacting_route_pairs(frm);
	if (!routes.length) {
		frappe.msgprint({
			title: __("No Fabric Process Combinations"),
			message: __(
				"Maintain the cloth Colour + Dia combinations in Fabric Processes first, then generate Compacting combinations.",
			),
			indicator: "orange",
		});
		return;
	}
	const colours = [...new Set(routes.map((row) => row.colour))].sort((a, b) =>
		String(a).localeCompare(String(b), undefined, { numeric: true }),
	);
	const selected_colours = new Set();
	let dialog;
	const render_colour_group = () => {
		const field = dialog?.fields_dict?.colour_group_html;
		if (!field) return;
		const $wrapper = $(field.$wrapper || field.wrapper).empty();
		$("<label class='control-label'></label>")
			.text(__("Colour Group"))
			.appendTo($wrapper);
		const $options = $(
			"<div class='compacting-colour-options' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px 16px;margin-top:8px;'></div>",
		).appendTo($wrapper);
		colours.forEach((colour) => {
			const $label = $(
				"<label class='checkbox' style='display:flex;align-items:center;gap:8px;margin:0;'></label>",
			).appendTo($options);
			$("<input type='checkbox'>")
				.prop("checked", selected_colours.has(colour))
				.on("change", function () {
					if (this.checked) selected_colours.add(colour);
					else selected_colours.delete(colour);
				})
				.appendTo($label);
			$("<span></span>").text(colour).appendTo($label);
		});
		$("<p class='text-muted small' style='margin:8px 0 0;'></p>")
			.text(
				__(
					"Selected colours sharing an input Dia are generated together; use the grid to fill their common compacting Dia.",
				),
			)
			.appendTo($wrapper);
	};
	dialog = new frappe.ui.Dialog({
		title: __("Generate Compacting Combinations"),
		fields: [
			{
				fieldname: "generation_scope",
				fieldtype: "Select",
				label: __("Generation Scope"),
				options: ["All Colours", "Separate Colours", "Colour Group"],
				default: "All Colours",
				reqd: 1,
				onchange() {
					const is_group = dialog.get_value("generation_scope") === "Colour Group";
					dialog.set_df_property("colour_group_html", "hidden", !is_group);
					if (!is_group) selected_colours.clear();
					else render_colour_group();
				},
			},
			{
				fieldname: "colour_group_html",
				fieldtype: "HTML",
				hidden: 1,
			},
			{
				fieldname: "preserve_note",
				fieldtype: "HTML",
				options: `<div class="small text-muted">${__(
					"Only missing combinations are added. Existing compacting Dias are never overwritten.",
				)}</div>`,
			},
		],
		primary_action_label: __("Generate Combinations"),
		primary_action(values) {
			const selected = [...selected_colours];
			if (values.generation_scope === "Colour Group" && !selected.length) {
				frappe.msgprint(__("Select at least one colour for the Compacting group."));
				return;
			}
			const targets = compacting_targets(routes, values.generation_scope, selected);
			const existing = new Set(
				(frm.doc.compacting_reference_details || []).map(
					(row) => `${row.colour || ""}\u0000${row.input_dia || ""}`,
				),
			);
			let added = 0;
			targets.forEach((target) => {
				const key = `${target.colour || ""}\u0000${target.input_dia || ""}`;
				if (existing.has(key)) return;
				existing.add(key);
				const row = frm.add_child("compacting_reference_details");
				row.colour = target.colour || "";
				row.input_dia = target.input_dia;
				row.compacting_dia = "";
				added += 1;
			});
			frm.refresh_field("compacting_reference_details");
			if (added) frm.dirty();
			dialog.hide();
			frappe.show_alert({
				message: added
					? __("{0} compacting combination(s) added. Enter the compacting Dia.", [added])
					: __("Every combination in this scope is already present."),
				indicator: added ? "green" : "blue",
			});
		},
	});
	dialog.show();
	render_colour_group();
}

function fill_selected_compacting_dia(frm) {
	const grid = frm.fields_dict.compacting_reference_details?.grid;
	const selected = grid?.get_selected_children() || [];
	if (!selected.length) {
		frappe.msgprint(
			__("Select the Compacting Detail rows whose compacting Dia should be filled together."),
		);
		return;
	}
	const input_dias = [...new Set(selected.map((row) => row.input_dia).filter(Boolean))];
	if (input_dias.length !== 1) {
		frappe.msgprint(
			__("Select rows sharing the same Knitting/Input Dia before filling a colour group."),
		);
		return;
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Fill Selected Compacting Dia"),
		fields: [
			{
				fieldname: "input_dia",
				fieldtype: "Data",
				label: __("Knitting/Input Dia"),
				default: input_dias[0],
				read_only: 1,
			},
			{
				fieldname: "compacting_dia",
				fieldtype: "Link",
				label: __("Compacting Dia"),
				options: "YRP Item Attribute Value",
				reqd: 1,
				get_query: () => ({ filters: { attribute_name: "Dia" } }),
			},
		],
		primary_action_label: __("Fill Selected Rows"),
		primary_action(values) {
			selected.forEach((row) => {
				row.compacting_dia = values.compacting_dia;
			});
			frm.refresh_field("compacting_reference_details");
			frm.dirty();
			dialog.hide();
			frappe.show_alert({
				message: __("{0} row(s) updated.", [selected.length]),
				indicator: "green",
			});
		},
	});
	dialog.show();
}

// ---------------------------------------------------------------------------
// Fabric swap-mapping widgets (dia-wise dyeing / colour-wise compacting).
// The checkbox picks the entry mode; the widget is just a faster editor for
// the SAME child table — rows carry dia/colour when entered dia-/colour-wise.
// ---------------------------------------------------------------------------

const FABRIC_SWAP_WIDGETS = {
	dyeing: {
		html_field: "dyeing_colour_matrix_html",
		checkbox_field: "dia_wise_colour_change",
		table_field: "dyeing_colour_details",
		pin_field: "dia", pin_attribute: "Dia", pin_label: "Dia",
		from_field: "from_colour", to_field: "to_colour",
		value_attribute: "Colour", value_label: "Colour",
	},
	compacting: {
		html_field: "compacting_dia_matrix_html",
		checkbox_field: "colour_wise_dia_change",
		table_field: "compacting_dia_details",
		pin_field: "colour", pin_attribute: "Colour", pin_label: "Colour",
		from_field: "from_dia", to_field: "to_dia",
		value_attribute: "Dia", value_label: "Dia",
	},
};

frappe.ui.form.on("YRP Item Production Detail", {
	setup(frm) {
		frm.set_query("dia", "dyeing_colour_details", () => ({ filters: { attribute_name: "Dia" } }));
		frm.set_query("colour", "compacting_dia_details", () => ({ filters: { attribute_name: "Colour" } }));
	},
	refresh(frm) {
		frm.trigger("render_fabric_swap_widgets");
		frm.trigger("apply_cloth_layout");
		frm.trigger("setup_compacting_reference_generator");
	},
	apply_cloth_layout(frm) {
		if (!frm.doc.is_cloth_item) return;
		// Cloth IPDs have no Item BOM (standing rule): hide the empty BOM grid
		// and relabel the section — it holds only the processes table, where
		// identity processes (Washing etc.) are declared with their Process Item.
		frm.toggle_display("item_bom", false);
		frm.toggle_display("bom_attribute_mapping_html", false);
		// set_df_property doesn't repaint an already-rendered section head.
		const section = frm.fields_dict.bill_of_materials_section;
		if (section && section.head) section.head.text(__("Processes"));
	},
	setup_compacting_reference_generator(frm) {
		if (!frm.doc.is_cloth_item) return;
		const field = frm.fields_dict.compacting_reference_details;
		if (!field?.grid) return;
		const button = field.grid.add_custom_button(
			__("Generate Combinations"),
			() => open_compacting_generation_dialog(frm),
			"top",
		);
		const fill_button = field.grid.add_custom_button(
			__("Fill Selected Compacting Dia"),
			() => fill_selected_compacting_dia(frm),
			"top",
		);
		const editable = frm.doc.approval_status !== "Approved";
		button.toggle(editable);
		fill_button.toggle(editable);
	},
	dia_wise_colour_change(frm) {
		frm.trigger("render_fabric_swap_widgets");
	},
	colour_wise_dia_change(frm) {
		frm.trigger("render_fabric_swap_widgets");
	},
	render_fabric_swap_widgets(frm) {
		if (!frm.doc.is_cloth_item) return;
		Object.values(FABRIC_SWAP_WIDGETS).forEach((cfg) => {
			const field = frm.fields_dict[cfg.html_field];
			if (!field) return;
			$(field.wrapper).empty();
			if (!frm.doc[cfg.checkbox_field]) return;
			const widget = new frappe.production.ui.FabricSwapDetail(field.wrapper, {
				on_change: (rows) => fabric_swap_write_back(frm, cfg, rows),
			});
			widget.load_data(fabric_swap_widget_data(frm, cfg));
			frm.fabric_swap_widgets = frm.fabric_swap_widgets || {};
			frm.fabric_swap_widgets[cfg.html_field] = widget;
		});
	},
});

function fabric_swap_widget_data(frm, cfg) {
	// Group existing rows by pin value; pre-seed cards for fast entry —
	// dyeing: every knitting dia; compacting: every dyeing to-colour.
	const groups = new Map();
	(frm.doc[cfg.table_field] || []).forEach((row) => {
		const pin = row[cfg.pin_field] || "";
		if (!groups.has(pin)) groups.set(pin, []);
		groups.get(pin).push({ from: row[cfg.from_field] || "", to: row[cfg.to_field] || "" });
	});
	// Seed suggestion cards ONLY on first entry (empty table). Once rows are
	// saved, the widget mirrors the stored rows exactly — otherwise a removed
	// empty card would reappear on every save/refresh.
	if (!groups.size) {
		const seeds = cfg.table_field === "dyeing_colour_details"
			? (frm.doc.knitting_dia_details || []).map((r) => r.dia)
			: (frm.doc.dyeing_colour_details || []).map((r) => r.to_colour);
		[...new Set(seeds)].filter(Boolean).forEach((pin) => {
			groups.set(pin, [{ from: "", to: "" }]);
		});
	}
	return {
		pin_label: cfg.pin_label,
		value_label: cfg.value_label,
		pin_attribute: cfg.pin_attribute,
		value_attribute: cfg.value_attribute,
		locked: !frm.is_new() && frm.doc.approval_status === "Approved",
		groups: [...groups.entries()].map(([pin, pairs]) => ({ pin, pairs })),
	};
}

function fabric_swap_write_back(frm, cfg, rows) {
	frm.clear_table(cfg.table_field);
	rows.forEach((r) => {
		const row = frm.add_child(cfg.table_field);
		row[cfg.pin_field] = r.pin;
		row[cfg.from_field] = r.from;
		row[cfg.to_field] = r.to;
	});
	frm.refresh_field(cfg.table_field);
	frm.dirty();
}

// ===========================================================================
// Generic Fabric Processes — view-integrated Vue entry (2026-07-07 UI rebuild).
//
// Replaces the two raw child-table grids (fabric_processes + the sibling
// fabric_value_mappings) with ONE comprehension-first Vue app (a card per
// process: shape badge, in -> out, and a labelled "what changes" area) plus a
// shape-driven add panel. The Vue OWNS entry; on every add/remove it writes BOTH
// sibling child tables back through frm so a normal Ctrl/Cmd+S persists them and
// sync_fabric_process_matrices regenerates the matrices. The grids stay in the
// doctype as the storage (hidden) -- the data model is unchanged.
// ===========================================================================

frappe.ui.form.on("YRP Item Production Detail", {
	refresh(frm) {
		fabric_processes_toggle_grids(frm);
		fabric_processes_mount(frm);
		colour_yarn_recipe_toggle_grid(frm);
		colour_yarn_recipe_mount(frm);
	},
	is_cloth_item(frm) {
		fabric_processes_toggle_grids(frm);
		fabric_processes_mount(frm);
		colour_yarn_recipe_toggle_grid(frm);
		colour_yarn_recipe_mount(frm);
	},
});

function fabric_processes_toggle_grids(frm) {
	// The Vue app is the UI; the two sibling grids + their section heads are the
	// hidden storage behind it. Hide them with CSS (NOT set_df_property hidden):
	// a Tab Break auto-hides when ALL its fields are df-hidden, which would hide
	// the whole Fabric Processes tab. CSS-hiding keeps df.hidden=0 so the tab (and
	// its HTML mount) stay visible while the raw grids disappear.
	if (!frm.doc.is_cloth_item) return;
	// Hide ONLY the two raw grids (their wrapper), never the section wrappers — the
	// HTML mount shares the first storage section, and hiding a section wrapper
	// collapses the mount. The two storage sections' labels + descriptions are
	// blanked on the Custom Fields, so with the grids gone only the Vue card view
	// reads as the UI.
	["fabric_processes", "fabric_value_mappings"].forEach((f) => {
		const fld = frm.fields_dict[f];
		if (fld && fld.wrapper) $(fld.wrapper).hide();
	});
}

async function fabric_processes_mount(frm) {
	const field = frm.fields_dict.fabric_processes_html;
	if (!field) return;
	const $w = $(field.wrapper);
	if (!frm.doc.is_cloth_item) {
		$w.empty();
		frm.__fabric_app = null;
		return;
	}
	// Rebuilt fresh each refresh (cur_frm reads aren't reactive -- same pattern as
	// the Lot fabric island).
	$w.empty();
	const all_processes = await fabric_processes_catalog();
	const app = new frappe.production.ui.FabricProcesses(field.wrapper, {
		on_change: (payload) => fabric_processes_write_back(frm, payload),
	});
	frm.__fabric_app = app;
	app.load_data(fabric_processes_payload(frm, all_processes));
}

let _fabric_process_catalog = null;
async function fabric_processes_catalog() {
	if (_fabric_process_catalog) return _fabric_process_catalog;
	const rows = await frappe.db.get_list("YRP Process", { fields: ["name"], limit: 0, order_by: "name asc" });
	_fabric_process_catalog = rows.map((r) => r.name);
	return _fabric_process_catalog;
}

function fabric_processes_payload(frm, all_processes) {
	const editable = frm.is_new() || frm.doc.approval_status !== "Approved";
	return {
		editable,
		item: frm.doc.item || null,
		// Conversion input defaults to the IPD's yarn (yarn → cloth); NEVER the
		// cloth item — a conversion's input and output must be distinct.
		default_input: frm.doc.yarn_item || null,
		attributes: [...new Set((frm.doc.item_attributes || []).map((a) => a.attribute).filter(Boolean))],
		all_processes: all_processes || [],
		processes: (frm.doc.fabric_processes || []).map((r) => ({
			sequence: r.sequence,
			fabric_process: r.fabric_process,
			input_item: r.input_item,
			output_item: r.output_item,
			quantity_ratio: r.quantity_ratio,
		})),
		mappings: (frm.doc.fabric_value_mappings || []).map((m) => ({
			sequence: m.sequence,
			mapping_index: m.mapping_index,
			attribute: m.attribute,
			role: m.role,
			from_value: m.from_value,
			to_value: m.to_value,
		})),
	};
}

function fabric_processes_write_back(frm, payload) {
	frm.clear_table("fabric_processes");
	(payload.processes || []).forEach((p) => Object.assign(frm.add_child("fabric_processes"), p));
	frm.clear_table("fabric_value_mappings");
	(payload.mappings || []).forEach((m) => Object.assign(frm.add_child("fabric_value_mappings"), m));
	frm.refresh_field("fabric_processes");
	frm.refresh_field("fabric_value_mappings");
	frm.dirty();
}

// ===========================================================================
// Colour-wise Yarn Recipes — grouped Desk editor.
//
// `colour_yarn_recipes` remains the internal child-table storage, while this
// Vue island is the only cloth-IPD entry surface. One card = one finished
// colour, with all yarns and the 100% total visible together. Fabric-route data
// is preserved in the payload for compatibility, but Dia/Colour conversions
// are intentionally entered and shown only in the Fabric Processes tab.
// ===========================================================================

function colour_yarn_recipe_toggle_grid(frm) {
	// Colour-wise cards are the single entry surface. The legacy global Yarn
	// Ratio is derived server-side from the first colour recipe for old readers.
	["yarn_ratio_details", "colour_yarn_recipes", "fabric_routes"].forEach((fieldname) => {
		const storage = frm.fields_dict[fieldname];
		if (storage && storage.wrapper && frm.doc.is_cloth_item) {
			$(storage.wrapper).hide();
		}
	});
}

function colour_yarn_recipe_mount(frm) {
	const field = frm.fields_dict.colour_yarn_recipe_editor;
	if (!field) return;
	const $wrapper = $(field.wrapper);
	if (frm.__colour_yarn_app && frm.__colour_yarn_app.app) {
		frm.__colour_yarn_app.app.unmount();
	}
	$wrapper.empty();
	frm.__colour_yarn_app = null;
	if (!frm.doc.is_cloth_item) return;

	const app = new frappe.production.ui.ColourYarnRecipeEditor(field.wrapper, {
		on_change: (payload) => colour_yarn_recipe_write_back(frm, payload),
	});
	frm.__colour_yarn_app = app;
	const can_write = (frm.perm || []).some((permission) => permission.write);
	app.load_data({
		cloth_item: frm.doc.item || "",
		locked: !can_write ||
			(!frm.is_new() && frm.doc.approval_status === "Approved"),
		rows: (frm.doc.colour_yarn_recipes || []).map((row) => ({
			cloth_item: row.cloth_item,
			colour: row.colour,
			yarn_item: row.yarn_item,
			ratio: row.ratio,
		})),
		routes: (frm.doc.fabric_routes || []).map((row) => ({
			finished_colour: row.finished_colour,
			finished_dia: row.finished_dia,
			knitting_output_colour: row.knitting_output_colour,
			knitting_output_dia: row.knitting_output_dia,
		})),
	});
}

function colour_yarn_recipe_write_back(frm, payload) {
	frm.clear_table("colour_yarn_recipes");
	(payload.rows || []).forEach((values) => {
		const row = frm.add_child("colour_yarn_recipes");
		row.cloth_item = frm.doc.item || values.cloth_item || "";
		row.colour = values.colour || "";
		row.yarn_item = values.yarn_item || "";
		row.ratio = Number(values.ratio || 0);
	});
	frm.refresh_field("colour_yarn_recipes");
	frm.clear_table("fabric_routes");
	(payload.routes || []).forEach((values) => {
		const row = frm.add_child("fabric_routes");
		row.finished_colour = values.finished_colour || "";
		row.finished_dia = values.finished_dia || "";
		row.knitting_output_colour = values.knitting_output_colour || "";
		row.knitting_output_dia = values.knitting_output_dia || "";
	});
	frm.refresh_field("fabric_routes");
	colour_yarn_recipe_toggle_grid(frm);
	frm.dirty();
}
