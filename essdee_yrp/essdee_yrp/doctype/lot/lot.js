// Copyright (c) 2021, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lot", {
	setup(frm) {
		frm.set_query('production_detail', (doc) => {
			return {
				filters: {
					'item': doc.item
				}
			}
		})
		frm.set_query("production_order", (doc) => {
			return {
				filters: {
					"item": doc.item,
					"docstatus": 1,
				}
			}
		})
		frm.set_query("cloth_item", "lot_fabric_details", function () {
			return { filters: { is_cloth_item: 1 } };
		});
		frm.set_query("production_detail", "lot_fabric_details", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return { filters: { item: row.cloth_item || "" } };
		});
	},
	refresh(frm) {
		$(".layout-side-section").css("display", "none");
		frm.page.add_menu_item(__("Calculate"), function () {
			calculate_all(frm);
		}, false, 'Ctrl+E', false);
		frappe.call({
			method: "essdee_yrp.essdee_yrp.doctype.lot.lot.check_enabled_po",
			callback: function (r) {
				let x = true
				if (!r.message) {
					x = false
				}
				frm.set_df_property("item", "read_only", x)
				frm.refresh_field("item")
				if (frm.doc.item && !frm.doc.production_order) {
					frm.set_df_property("production_order", "read_only", true)
				}
				else{
					frm.set_df_property("production_order", "read_only", !x)
				}
				frm.refresh_field("production_order")
			}
		})

		if (!frm.is_new()) {
			frm.add_custom_button(__('Purchase Summary'), function () {
				frappe.set_route("query-report", "Lot Purchase Summary", {
					lot: frm.doc.name
				});
			}, __("View"));
		}
		frm.set_df_property('bom_summary', 'cannot_add_rows', true)
		frm.set_df_property('bom_summary', 'cannot_delete_rows', true)
		frm.add_custom_button("Calculate Order Items", () => {
			let d = new frappe.ui.Dialog({
				title: "Confirm Calculation",
				primary_action_label: "Yes",
				secondary_action_label: "No",
				primary_action() {
					d.hide()
					frappe.call({
						method: "essdee_yrp.essdee_yrp.doctype.lot.lot.update_order_details",
						args: {
							doc_name: frm.doc.name,
						},
						freeze: true,
						freeze_message: __("Calculating Order Items..."),
						callback: function (r) {
							frm.reload_doc()
						}
					})
				},
				secondary_action() {
					d.hide()
				}
			})
			d.show()
		})
		if (!frm.is_new() && frm.doc.production_detail && !frm.doc.is_transferred) {
			frm.add_custom_button("Build Cloth Programs", () => {
				frappe.call({
					method: "essdee_yrp.api.cloth_program.get_cloth_program_context",
					args: { lot: frm.doc.name },
					freeze: true,
					freeze_message: __("Loading cloths..."),
					callback: function (r) {
						const cloths = (r.message && r.message.cloths) || [];
						const defaults = (r.message && r.message.defaults) || {};
						if (!cloths.length) {
							frappe.msgprint(__("This lot's garment has no cloth items to build."));
							return;
						}
						build_cloth_programs_dialog(frm, cloths, defaults);
					}
				});
			});
		}
		$(frm.fields_dict['items_html'].wrapper).html("")
		frm.item = new frappe.production.ui.LotOrder(frm.fields_dict['items_html'].wrapper)
		if (frm.doc.__onload && frm.doc.__onload.item_details) {
			frm.doc['item_details'] = JSON.stringify(frm.doc.__onload.item_details);
			frm.item.load_data(frm.doc.__onload.item_details);
		}
		else {
			if (frm.doc.item && frm.doc.production_detail) {
				frappe.call({
					method: 'essdee_yrp.essdee_yrp.doctype.lot.lot.get_item_details',
					args: {
						item_name: frm.doc.item,
						uom: frm.doc.uom,
						production_detail: frm.doc.production_detail,
						ppo: frm.doc.production_order,
					},
					callback: function (r) {
						frm.item.load_data(r.message)
						if (frm.doc.production_order) {
							frm.item.show_inputs()
							frm.item.load_data(r.message)
						}
						cur_frm.dirty()
					}
				})
			}
			else {
				frm.item.load_data([])
			}
		}
		if (frm.doc.lot_order_details.length > 0) {
			frappe.call({
				method: "essdee_yrp.essdee_yrp.doctype.lot.lot.get_packing_attributes",
				args: {
					ipd: frm.doc.production_detail,
				},
				callback: function (r) {
					frm.fields_dict['size_set_colour'].df.options = r.message.major_colours
					frm.refresh_field("size_set_colour")
				}
			})
		}
		frm.order_detail = new frappe.production.ui.CutPlanItems(frm.fields_dict['lot_item_order_detail_html'].wrapper)
		if (frm.doc.__onload && frm.doc.__onload.order_item_details) {
			frm.order_detail.load_data(frm.doc.__onload.order_item_details, 0);
		}
		else {
			frm.order_detail.load_data([], 0)
		}
		if (frm.doc.is_transferred) {
			frm.order_detail.update_status()
		}
		$(frm.fields_dict['fabric_program_html'].wrapper).html("")
		frm.fabric_program = new frappe.production.ui.FabricProgram(frm.fields_dict['fabric_program_html'].wrapper)
		frm.fabric_program.load_data((frm.doc.__onload && frm.doc.__onload.fabric_program_details) || [])
		// if(!frm.is_new()){
		// 	frm.cad_detail = new frappe.production.ui.CadDetail(frm.fields_dict['cad_detail_html'].wrapper)
		// 	if(frm.doc.__onload && frm.doc.__onload.cad_item_details) {
		// 		frm.cad_detail.load_data(frm.doc.__onload.cad_item_details);
		// 	}
		// 	else{
		// 		frm.cad_detail.load_data([])
		// 	}
		// }
		if (!frm.is_new() && frm.doc.item && frm.doc.production_detail) {
			$(frm.fields_dict['ocr_detail_html'].wrapper).html("")
			new frappe.production.ui.OCRDetail(frm.fields_dict['ocr_detail_html'].wrapper)
		}
		if (frm.doc.has_transferred) {
			new frappe.production.ui.AlternativeDetail(frm.fields_dict['alternative_html'].wrapper)
		}
	},
	production_order(frm) {
		if (frm.doc.production_order) {
			frappe.db.get_value("Production Order", frm.doc.production_order, "item").then((r) => {
				frm.set_value("item", r.message.item)
				frm.refresh_field("item")
			})
		}
		else{
			frm.set_value("production_detail", "")
			frm.set_value("item", "")
			frm.refresh_field("item")
			frm.refresh_field("production_detail")
		}
	},
	// fetch_cad_template(frm){
	// 	frm.cad_detail.load_data([])
	// 	if(!frm.is_dirty()){
	// 		frm.dirty()
	// 	}
	// },
	async validate(frm) {
		if (frm.item) {
			let items = frm.item.get_data()
			frm.doc['item_details'] = JSON.stringify(items)
		}
		let order_items = frm.order_detail.get_items()
		frm.doc['order_item_details'] = JSON.stringify(order_items)
		// Guarded: an unmounted island must leave the transient fields absent so
		// the server keeps the stored program/requirement rows untouched.
		if (frm.fabric_program) {
			frm.doc['fabric_program_details'] = JSON.stringify(frm.fabric_program.get_data())
			frm.doc['fabric_requirement_details'] = JSON.stringify(frm.fabric_program.get_requirement())
		}
		// if(frm.cad_detail){
		// 	let cad_data = frm.cad_detail.get_data()
		// 	frm.doc['cad_details'] = JSON.stringify(cad_data)
		// }
	},
	item(frm) {
		if (!frm.doc.item) {
			if (frm.item) {
				frm.item.load_data([])
			}
		}
	},
	async production_detail(frm) {
		if (frm.doc.production_detail) {
			await frappe.call({
				method: 'essdee_yrp.essdee_yrp.doctype.lot.lot.get_isfinal_uom',
				args: {
					item_production_detail: frm.doc.production_detail,
					get_pack_stage: true,
				},
				callback: function (r) {
					if (r.message) {
						frm.set_value('uom', r.message.uom)
						frm.set_value('pack_in_stage', r.message.pack_in_stage)
						frm.set_value('packing_uom', r.message.packing_uom)
						frm.set_value('pack_out_stage', r.message.pack_out_stage)
						frm.set_value('dependent_attribute_mapping', r.message.dependent_attr_mapping)
						frm.set_value('tech_pack_version', r.message.tech_pack_version)
						frm.set_value('pattern_version', r.message.pattern_version)
						frm.set_value('packing_combo', r.message.packing_combo)
					}
				}
			})
			frappe.call({
				method: 'essdee_yrp.essdee_yrp.doctype.lot.lot.get_item_details',
				args: {
					item_name: frm.doc.item,
					uom: frm.doc.uom,
					production_detail: frm.doc.production_detail,
					dependent_attr_mapping: frm.doc.dependent_attribute_mapping,
					ppo: frm.doc.production_order,
				},
				callback: function (r) {
					frm.item.load_data(r.message)
					if (frm.doc.production_order) {
						frm.item.show_inputs()
						frm.item.load_data(r.message)
					}
				}
			})
		}
		else{
			let fields = ['uom', 'pack_in_stage', 'packing_uom', 'pack_out_stage', 'dependent_attribute_mapping', 'tech_pack_version', 'pattern_version', 'packing_combo']
			fields.forEach(field => {
				frm.set_value(field, "")
				frm.refresh_field(field)
			})
			if (frm.item) {
				frm.item.load_data([])
			}
		}
	},
	calculate_bom: function (frm) {
		if (frm.is_dirty()) {
			frappe.msgprint("Save the document before calculate the BOM")
			return
		}
		if (frm.doc.item && frm.doc.production_detail) {
			frappe.call({
				method: "yrp.yrp.doctype.item_production_detail.item_production_detail.get_calculated_bom",
				args: {
					item_production_detail: frm.doc.production_detail,
					items: frm.doc.lot_order_details,
					lot_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __("Calculating BOM..."),
				callback: function (r) {
					frm.refresh()
				}
			});
		}
	}
});


// frappe.ui.form.on('Lot', {
// 	setup: function(frm) {
// 		frm.set_query('lot_template', (doc) => {
// 			return {
// 				filters: {
// 					item: doc.item,
// 				}
// 			}
// 		});
// 		frm.set_query('size', 'planned_qty', (doc) => {
// 			return {
// 				filters: {
// 					attribute_name: 'Size',
// 				}
// 			}
// 		});
// 	},

// 	refresh: function(frm) {
// 		frm.page.add_menu_item(__("Calculate"), function() {
// 			calculate_all(frm);
// 		}, false, 'Ctrl+E', false);
// 		if (!frm.is_new()) {
// 			frm.add_custom_button(__('Purchase Summary'), function() {
// 				frappe.set_route("query-report", "Lot Purchase Summary", {
// 					lot: frm.doc.name
// 				});
// 			}, __("View"));
// 		}
// 	},

// 	item: function(frm) {
// 		if (frm.doc.item) {
// 			frm.set_value({"lot_template": ""});
// 			frappe.call({
// 				method: "yrp.yrp.doctype.item.item.get_attribute_values",
// 				args: {
// 					item: frm.doc.item,
// 				},
// 				callback: function(r) {
// 					if (r.message) {
// 						if (r.message['Size']) {
// 							let planned_qty = []
// 							for(let i = 0;i < r.message.Size.length; i++) {
// 								planned_qty.push({size: r.message.Size[i], qty: 0});
// 							}
// 							frm.set_value({'planned_qty': planned_qty});
// 						}
// 					}
// 				}
// 			});
// 		}
// 	},

// 	lot_template: function(frm) {
// 		if (frm.doc.lot_template) {
// 			frappe.call({
// 				method: "essdee_yrp.essdee_yrp.doctype.lot_template.lot_template.get_attribute_values",
// 				args: {
// 					lot_template: frm.doc.lot_template,
// 				},
// 				callback: function(r) {
// 					if (r.message) {
// 						if (r.message['Size']) {
// 							let planned_qty = []
// 							for(let i = 0;i < r.message.Size.length; i++) {
// 								planned_qty.push({size: r.message.Size[i], qty: 0});
// 							}
// 							frm.set_value({'planned_qty': planned_qty});
// 						}
// 					}
// 				}
// 			});
// 		}s
// 	},

// 	calculate_bom: function(frm) {
// 		if (frm.doc.item && frm.doc.lot_template && frm.doc.planned_qty.length > 0) {
// 			frappe.call({
// 				method: "essdee_yrp.essdee_yrp.doctype.lot_template.lot_template.get_calculated_bom",
// 				args: {
// 					lot_template: frm.doc.lot_template,
// 					planned_qty: frm.doc.planned_qty,
// 				},
// 				callback: function(r) {
// 					console.log(r.message);
// 					if (r.message) {
// 						if (r.message['items']) {
// 							let items = r.message.items || [];
// 							for (let i = 0; i < items.length; i++) {
// 								let bom = frm.doc.bom_summary;
// 								let found = false;
// 								for (let j = 0; j < bom.length; j++) {
// 									if (bom[j].item_name == items[i].item) {
// 										bom[j].required_qty = items[i].required_qty;
// 										found = true;
// 										break;
// 									}
// 								}
// 								if (!found) {
// 									var childTable = frm.add_child("bom_summary");
// 									childTable.item_name = items[i].item;
// 									childTable.required_qty = items[i].required_qty;
// 								}
// 							}
// 							frm.refresh_field('bom_summary');
// 						}
// 					}
// 				}
// 			});
// 		}
// 	}
// });

// frappe.ui.form.on('Lot Planned Qty', {
// 	qty: function(frm, cdt, cdn) {
// 		let row = frappe.get_doc(cdt, cdn)
// 		row.qty = parseInt(row.qty);
// 		calculate_all(frm);
// 	},
// 	cut_qty: function(frm, cdt, cdn) {
// 		let row = frappe.get_doc(cdt, cdn)
// 		row.cut_qty = parseInt(row.cut_qty);
// 		calculate_all(frm);
// 	},
// 	final_qty: function(frm, cdt, cdn) {
// 		let row = frappe.get_doc(cdt, cdn)
// 		row.final_qty = parseInt(row.final_qty);
// 		calculate_all(frm);
// 	},
// });

// function calculate_all(frm) {
// 	calculate_planned_qty(frm);
// 	frm.refresh_field("total_planned_qty")
// 	frm.refresh_field("total_final_qty")
// 	frm.refresh_field("total_cutting_qty")
// 	frm.dirty();
// }

// function calculate_planned_qty(frm) {
// 	let total_qty = 0, total_cut_qty = 0, total_final_qty = 0;
// 	$.each(frm.doc.planned_qty || [], function(i, v) {
// 		total_cut_qty += (v.cut_qty || 0)
// 		total_qty += (v.qty || 0);
// 		total_final_qty += (v.final_qty || 0);
//     })
// 	frm.doc.total_planned_qty = total_qty;
// 	frm.doc.total_final_qty = total_final_qty;
// 	frm.doc.total_cutting_qty = total_cut_qty;
// }

function build_cloth_programs_dialog(frm, cloths, defaults = {}) {
	const fields = [];
	cloths.forEach((c, i) => {
		const colour_recipes = c.colour_yarn_recipes || [];
		const fallback_yarns = (c.default_yarns && c.default_yarns.length)
			? c.default_yarns
			: [{ yarn_item: c.default_yarn || "", ratio: 100 }];
		const profile = c.profile || {};
		const required_colours = (c.required_colours || []).filter(Boolean);
		const required_routes = c.required_routes || [];
		const output_colours = profile.knitting_output_colours || {};
		const stored_routes = profile.fabric_routes || [];
		fields.push({ fieldtype: "Section Break", label: __(frappe.utils.escape_html(`${c.label} — ${c.cloth_item}`)) });
		fields.push({ fieldtype: "Data", fieldname: `cloth_item_${i}`, hidden: 1, default: c.cloth_item });
		fields.push({ fieldtype: "Data", fieldname: `production_detail_${i}`, hidden: 1, default: c.production_detail || "" });

		if (required_colours.length) {
			if (i > 0) {
				fields.push({
					label: __("Use Main Fabric Yarn Recipes"),
					fieldname: `use_main_yarn_recipes_${i}`,
					fieldtype: "Check",
					default: 0,
					description: __(
						"Reuse the Main Fabric recipe for each matching finished colour. Changes made to Main Fabric are used when Build is clicked."
					),
					onchange() {
						if (d.get_value(`use_main_yarn_recipes_${i}`)) {
							copy_main_fabric_recipes(d, cloths, i);
						}
					},
				});
			}
			fields.push({
				fieldtype: "HTML",
				fieldname: `route_help_${i}`,
				options: `<div class="text-muted small" style="margin-bottom:8px">${__(
					"Maintain one grouped yarn recipe and the physical Knitting output colour for every finished-colour route. Each recipe must total exactly 100%."
				)}</div>`,
			});
			required_colours.forEach((colour, colour_index) => {
				const colour_routes = required_routes
					.filter((route) => route.colour === colour)
					.sort((a, b) => dia_sort_value(a.dia) - dia_sort_value(b.dia));
				const stored = colour_recipes.filter((row) => row.colour === colour);
				const recipe = stored.length ? stored : fallback_yarns;
				const signature = JSON.stringify(
					recipe.map((row) => [row.yarn_item, Number(row.ratio || 0)]).sort()
				);
				const recipe_source = required_colours.slice(0, colour_index).find((candidate) => {
					const candidate_stored = colour_recipes.filter((row) => row.colour === candidate);
					const candidate_recipe = candidate_stored.length ? candidate_stored : fallback_yarns;
					return JSON.stringify(
						candidate_recipe.map((row) => [row.yarn_item, Number(row.ratio || 0)]).sort()
					) === signature;
				}) || "";
				const colour_total = colour_routes.reduce(
					(total, route) => total + Number(route.weight || 0), 0);
				fields.push({
					fieldtype: "HTML",
					fieldname: `route_title_${i}_${colour_index}`,
					depends_on: i > 0
						? `eval:!doc.use_main_yarn_recipes_${i}`
						: undefined,
					options: `<div style="margin:12px 0 5px;font-weight:650">${__(
						"Finished Colour: {0}", [frappe.utils.escape_html(colour)]
					)}</div><div class="text-muted small" style="margin-bottom:6px">${__(
						"{0} routes · {1} kg total",
						[colour_routes.length, colour_total]
					)}</div>`,
				});
				if (colour_index) {
					fields.push({
						label: __("Reuse Yarn Recipe From"),
						fieldname: `recipe_source_${i}_${colour_index}`,
						fieldtype: "Select",
						options: ["", ...required_colours.slice(0, colour_index)],
						default: recipe_source,
						depends_on: i > 0
							? `eval:!doc.use_main_yarn_recipes_${i}`
							: undefined,
						description: __(
							"Select an earlier colour to share its recipe, or leave blank to maintain a separate recipe."
						),
					});
				}
				fields.push({
					label: __("Yarn Recipe — {0}", [colour]),
					fieldname: `colour_yarns_${i}_${colour_index}`,
					fieldtype: "Table",
					cannot_add_rows: false,
					cannot_delete_rows: false,
					in_place_edit: true,
					reqd: colour_index === 0,
					depends_on: i > 0
						? (
							colour_index
								? `eval:!doc.use_main_yarn_recipes_${i} && !doc.recipe_source_${i}_${colour_index}`
								: `eval:!doc.use_main_yarn_recipes_${i}`
						)
						: (
							colour_index
								? `eval:!doc.recipe_source_${i}_${colour_index}`
								: undefined
						),
					data: recipe.map((row) => ({
						yarn_item: row.yarn_item,
						ratio: Number(row.ratio || 0),
					})),
					fields: yarn_recipe_fields(),
				});
				const route_defaults = colour_routes.map((route) => {
					const stored_route = stored_routes.find(
						(row) => row.finished_colour === colour && row.finished_dia === route.dia
					) || {};
					return stored_route.knitting_output_colour
						|| output_colours[colour]
						|| profile.greige_colour
						|| "";
				});
				const common_output_colours = [...new Set(route_defaults.filter(Boolean))];
				const bulk_colour_fieldname = `bulk_knitting_output_colour_${i}_${colour_index}`;
				fields.push({
					label: __("Apply Knitting Output Colour to All {0} Dias", [colour]),
					fieldname: bulk_colour_fieldname,
					fieldtype: "Link",
					options: "Item Attribute Value",
					default: common_output_colours.length === 1 ? common_output_colours[0] : "",
					description: __(
						"Select once to fill every Dia route for this finished colour. Individual routes remain editable."
					),
					get_query: () => ({ filters: { attribute_name: "Colour" } }),
					onchange() {
						const value = d.get_value(bulk_colour_fieldname) || "";
						colour_routes.forEach((_route, route_index) => {
							d.set_value(
								`knitting_output_colour_${i}_${colour_index}_${route_index}`,
								value
							);
						});
					},
				});
				colour_routes.forEach((route, route_index) => {
					const stored_route = stored_routes.find(
						(row) => row.finished_colour === colour && row.finished_dia === route.dia
					) || {};
					fields.push({
						fieldtype: "HTML",
						fieldname: `physical_route_title_${i}_${colour_index}_${route_index}`,
						options: `<div style="margin:9px 0 4px;font-weight:600">${__(
							"{0} · {1} kg finished",
							[
								frappe.utils.escape_html(route.dia || ""),
								Number(route.weight || 0),
							]
						)}</div>`,
					});
					fields.push({
						label: __("Knitting Output Dia"),
						fieldname: `knitting_output_dia_${i}_${colour_index}_${route_index}`,
						fieldtype: "Link",
						options: "Item Attribute Value",
						reqd: 1,
						default: stored_route.knitting_output_dia || route.dia || "",
						description: __("Physical Dia received from Knitting."),
						get_query: () => ({ filters: { attribute_name: "Dia" } }),
					});
					fields.push({
						label: __("Knitting Output Colour"),
						fieldname: `knitting_output_colour_${i}_${colour_index}_${route_index}`,
						fieldtype: "Link",
						options: "Item Attribute Value",
						reqd: 1,
						default: stored_route.knitting_output_colour
							|| output_colours[colour]
							|| profile.greige_colour
							|| "",
						description: __(
							"Select the Finished Colour itself to bypass Dyeing for this route."
						),
						get_query: () => ({ filters: { attribute_name: "Colour" } }),
					});
				});
			});
		} else {
			fields.push({
				label: __("Yarn Recipe"),
				fieldname: `yarns_${i}`,
				fieldtype: "Table",
				cannot_add_rows: false,
				cannot_delete_rows: false,
				in_place_edit: true,
				reqd: 1,
				description: __("List every yarn used for this cloth. The Ratio total must be exactly 100%."),
				data: fallback_yarns,
				fields: yarn_recipe_fields(),
			});
		}
		fields.push({ fieldtype: "Section Break", label: __("Process Settings") });
		fields.push({
			label: "Cloth Kgs / 1 Kg Yarn", fieldname: `cloth_per_kg_yarn_${i}`,
			fieldtype: "Float",
			reqd: 1,
			default: profile.cloth_per_kg_yarn || defaults.cloth_per_kg_yarn || 1,
		});
		fields.push({ fieldtype: "Column Break" });
		fields.push({
			label: "Knitting Process", fieldname: `knitting_process_${i}`,
			fieldtype: "Link",
			options: "Process",
			reqd: 1,
			default: profile.knitting_process || defaults.knitting_process || "",
		});
		fields.push({
			label: "Dyeing Process", fieldname: `dyeing_process_${i}`,
			fieldtype: "Link",
			options: "Process",
			reqd: 0,
			default: profile.dyeing_process || defaults.dyeing_process || "",
			description: __(
				"Required only when at least one Knitting Output Colour differs from its Finished Colour."
			),
		});
	});

	const d = new frappe.ui.Dialog({
		title: "Build Cloth Programs",
		size: "large",
		fields: fields,
		primary_action_label: "Build",
		primary_action(values) {
			const recipes_by_cloth = [];
			const selections = cloths.map((c, i) => {
				const required_colours = (c.required_colours || []).filter(Boolean);
				const colour_yarn_recipes = [];
				const fabric_routes = [];
				const resolved_recipes = {};
				required_colours.forEach((colour, colour_index) => {
					const source = values[`recipe_source_${i}_${colour_index}`];
					const use_main = i > 0 && values[`use_main_yarn_recipes_${i}`];
					const rows = use_main
						? ((recipes_by_cloth[0] && recipes_by_cloth[0][colour]) || [])
						: (
							source
								? (resolved_recipes[source] || [])
								: (values[`colour_yarns_${i}_${colour_index}`] || [])
						);
					resolved_recipes[colour] = rows.map((row) => ({
						yarn_item: row.yarn_item,
						ratio: Number(row.ratio || 0),
					}));
					resolved_recipes[colour].forEach((row) => {
						colour_yarn_recipes.push({
							colour: colour,
							yarn_item: row.yarn_item,
							ratio: row.ratio,
						});
					});
					(c.required_routes || [])
						.filter((route) => route.colour === colour)
						.sort((a, b) => dia_sort_value(a.dia) - dia_sort_value(b.dia))
						.forEach((route, route_index) => {
							fabric_routes.push({
								finished_colour: colour,
								finished_dia: route.dia,
								knitting_output_dia:
									values[`knitting_output_dia_${i}_${colour_index}_${route_index}`] || null,
								knitting_output_colour:
									values[`knitting_output_colour_${i}_${colour_index}_${route_index}`] || null,
							});
						});
				});
				recipes_by_cloth[i] = resolved_recipes;
				const recipe = required_colours.length
					? colour_yarn_recipes
						.filter((row) => row.colour === required_colours[0])
						.map((row) => ({ yarn_item: row.yarn_item, ratio: row.ratio }))
					: (values[`yarns_${i}`] || []).map((row) => ({
						yarn_item: row.yarn_item,
						ratio: Number(row.ratio || 0),
					}));
				return {
					cloth_item: values[`cloth_item_${i}`],
					production_detail: values[`production_detail_${i}`] || null,
					colour_yarn_recipes: colour_yarn_recipes,
					fabric_routes: fabric_routes,
					yarns: recipe,
					yarn_item: recipe[0] && recipe[0].yarn_item,
					cloth_per_kg_yarn: values[`cloth_per_kg_yarn_${i}`],
					knitting_process: values[`knitting_process_${i}`],
					dyeing_process: values[`dyeing_process_${i}`] || null,
					compacting_process:
						profile.compacting_process
						|| defaults.compacting_process
						|| null,
					required_colours: required_colours,
				};
			});
			const incomplete = selections.some((s) => {
				const groups = {};
				(s.colour_yarn_recipes.length ? s.colour_yarn_recipes : s.yarns).forEach((row) => {
					const key = row.colour || "__uncoloured__";
					if (!groups[key]) groups[key] = [];
					groups[key].push(row);
				});
				const invalid_recipe = Object.values(groups).some((rows) =>
					!rows.length ||
					rows.some((row) => !row.yarn_item || !(row.ratio > 0)) ||
					new Set(rows.map((row) => row.yarn_item)).size !== rows.length ||
					Math.abs(rows.reduce((sum, row) => sum + row.ratio, 0) - 100) > 0.001
				);
				const needs_dyeing = s.fabric_routes.some(
					(row) => row.knitting_output_colour && row.knitting_output_colour !== row.finished_colour
				);
				const needs_compacting = s.fabric_routes.some(
					(row) => row.knitting_output_dia && row.knitting_output_dia !== row.finished_dia
				);
				return (
					invalid_recipe ||
					!s.knitting_process ||
					!(s.cloth_per_kg_yarn > 0) ||
					s.fabric_routes.some(
						(row) => !row.knitting_output_colour || !row.knitting_output_dia
					) ||
					(needs_dyeing && !s.dyeing_process) ||
					(needs_compacting && !s.compacting_process)
				);
			});
			if (incomplete) {
				frappe.msgprint(__(
					"Complete every colour's Yarn Recipe (total 100%), Knitting Output Colour, required process, and cloth-per-kg before building. Dyeing is required for colour-changing routes. Configure the default Dia-change Process in IPD Settings when a route changes Dia."
				));
				return;
			}
			frappe.call({
				method: "essdee_yrp.api.cloth_program.build_cloth_programs",
				args: { lot: frm.doc.name, selections: JSON.stringify(selections), modified: frm.doc.modified },
				freeze: true,
				freeze_message: __("Building cloth programs..."),
				callback: function (r) {
					d.hide();
					const n = (r.message && r.message.cloths_built) || 0;
					frappe.show_alert({ message: __("Built {0} cloth program(s)", [n]), indicator: "green" });
					frm.reload_doc();
				}
			});
		}
	});
	// Existing cloth CPD values are already in context. Only legacy/new cloths
	// without a direct profile need the reverse-yarn convenience prefill.
	cloths.forEach((c, i) => {
		const profile_yarn = c.colour_yarn_recipes?.[0]?.yarn_item || c.default_yarn;
		if (!c.profile?.knitting_process && profile_yarn) {
			apply_yarn_profile(d, i, profile_yarn, c);
		}
	});
	d.show();
}

function yarn_recipe_fields() {
	return [
		{
			label: __("Yarn Item"),
			fieldname: "yarn_item",
			fieldtype: "Link",
			options: "Item",
			in_list_view: 1,
			columns: 7,
			reqd: 1,
		},
		{
			label: __("Ratio %"),
			fieldname: "ratio",
			fieldtype: "Float",
			in_list_view: 1,
			columns: 3,
			reqd: 1,
		},
	];
}

function dialog_colour_recipes(dialog, cloth, cloth_index) {
	const resolved = {};
	((cloth && cloth.required_colours) || []).filter(Boolean).forEach((colour, colour_index) => {
		const source = dialog.get_value(`recipe_source_${cloth_index}_${colour_index}`);
		const rows = source
			? (resolved[source] || [])
			: (dialog.get_value(`colour_yarns_${cloth_index}_${colour_index}`) || []);
		resolved[colour] = rows.map((row) => ({
			yarn_item: row.yarn_item || "",
			ratio: Number(row.ratio || 0),
		}));
	});
	return resolved;
}

function copy_main_fabric_recipes(dialog, cloths, target_index) {
	const main = cloths[0];
	const target = cloths[target_index];
	if (!main || !target) return;

	const main_recipes = dialog_colour_recipes(dialog, main, 0);
	(target.required_colours || []).filter(Boolean).forEach((colour, colour_index) => {
		if (!main_recipes[colour]) return;
		dialog.set_value(`recipe_source_${target_index}_${colour_index}`, "");
		dialog.set_value(
			`colour_yarns_${target_index}_${colour_index}`,
			main_recipes[colour].map((row) => ({ ...row }))
		);
	});
}

function dia_sort_value(value) {
	const match = String(value || "").match(/-?\d+(?:\.\d+)?/);
	return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER;
}

function apply_yarn_profile(dialog, i, yarn, cloth) {
	if (!yarn) return;
	frappe.call({
		method: "essdee_yrp.api.cloth_program.get_yarn_profile",
		args: { yarn_item: yarn },
		callback: function (r) {
			const p = r.message || {};
			if (p.knitting_process && !dialog.get_value(`knitting_process_${i}`)) {
				dialog.set_value(`knitting_process_${i}`, p.knitting_process);
			}
			if (p.dyeing_process && !dialog.get_value(`dyeing_process_${i}`)) {
				dialog.set_value(`dyeing_process_${i}`, p.dyeing_process);
			}
			if (p.cloth_per_kg_yarn && !dialog.get_value(`cloth_per_kg_yarn_${i}`)) {
				dialog.set_value(`cloth_per_kg_yarn_${i}`, p.cloth_per_kg_yarn);
			}
			const outputs = p.knitting_output_colours || {};
			(cloth.required_colours || []).forEach((colour, colour_index) => {
				(cloth.required_routes || [])
					.filter((route) => route.colour === colour)
					.sort((a, b) => dia_sort_value(a.dia) - dia_sort_value(b.dia))
					.forEach((route, route_index) => {
						const stored = (p.fabric_routes || []).find(
							(row) => row.finished_colour === colour && row.finished_dia === route.dia
						) || {};
						const colour_field = `knitting_output_colour_${i}_${colour_index}_${route_index}`;
						const dia_field = `knitting_output_dia_${i}_${colour_index}_${route_index}`;
						if (!dialog.get_value(colour_field)) {
							dialog.set_value(
								colour_field,
								stored.knitting_output_colour || outputs[colour] || p.greige_colour || ""
							);
						}
						if (!dialog.get_value(dia_field)) {
							dialog.set_value(dia_field, stored.knitting_output_dia || route.dia || "");
						}
					});
			});
		}
	});
}
