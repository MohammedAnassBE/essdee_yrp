// Copyright (c) 2021, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP Lot", {
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
		mount_cloth_program(frm);
		frappe.call({
			method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.check_enabled_po",
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
				frappe.set_route("query-report", "SD YRP Lot Purchase Summary", {
					lot: frm.doc.name
				});
			}, __("View"));
			if (frm.has_perm("write")) {
				add_purchase_order_link_actions(frm);
			}
		}
		frm.set_df_property('bom_summary', 'cannot_add_rows', true)
		frm.set_df_property('bom_summary', 'cannot_delete_rows', true)
		if (
			!frm.is_new()
			&& frm.has_perm("write")
			&& !(frm.doc.lot_time_and_action_details || []).length
		) {
			frm.add_custom_button("Calculate Order Items", () => {
				let d = new frappe.ui.Dialog({
					title: "Confirm Calculation",
					primary_action_label: "Yes",
					secondary_action_label: "No",
					primary_action() {
						d.hide()
						frappe.call({
							method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.update_order_details",
							args: {
								doc_name: frm.doc.name,
							},
							freeze: true,
							freeze_message: __("Calculating Order Items..."),
							callback: function () {
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
		}
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
		if (!frm.is_new() && frm.doc.production_detail && !frm.doc.is_transferred
			&& frm.doc.docstatus !== 2 && frm.has_perm("write")
			&& (frm.doc.lot_fabric_details || []).length) {
			frm.add_custom_button(__("Recalculate Cloth Program"), () => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save the Lot before recalculating the Cloth Program."));
					return;
				}
				frappe.call({
					method: "essdee_yrp.api.cloth_program.recalculate_cloth_program",
					args: { lot: frm.doc.name, modified: frm.doc.modified },
					freeze: true,
					freeze_message: __("Recalculating Cloth Program..."),
					callback: (r) => {
						if (!r.exc) frm.reload_doc();
					},
				});
			});
		}
		if (!frm.is_new() && (frm.doc.lot_fabric_programs || []).length) {
			frm.add_custom_button(__("Cloth Program"), () => {
				const url = frappe.urllib.get_full_url(
					`/printview?doctype=Lot&name=${encodeURIComponent(frm.doc.name)}` +
					`&trigger_print=1&format=${encodeURIComponent("Essdee Lot Cloth Program")}` +
					"&no_letterhead=1"
				);
				if (!window.open(url)) {
					frappe.msgprint(__("Please enable pop-ups"));
				}
			}, __("Print"));
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
					method: 'essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_item_details',
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
				method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_packing_attributes",
				args: {
					ipd: frm.doc.production_detail,
				},
				callback: function (r) {
					frm.fields_dict['size_set_colour'].df.options = r.message.major_colours
					frm.refresh_field("size_set_colour")
				}
			})
		}
		setup_time_and_action(frm)
		frm.order_detail = new frappe.production.ui.CutPlanItems(frm.fields_dict['lot_item_order_detail_html'].wrapper)
		if (frm.doc.__onload && frm.doc.__onload.order_item_details) {
			frm.order_detail.load_data(frm.doc.__onload.order_item_details, frm.doc.lot_time_and_action_details.length);
		}
		else {
			frm.order_detail.load_data([], 0)
		}
		if (frm.doc.is_transferred) {
			frm.order_detail.update_status()
		}
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
			frappe.db.get_value("YRP Production Order", frm.doc.production_order, "item").then((r) => {
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
		if (frm.fabric_program && frm._cloth_program_ready) {
			frm.doc['fabric_program_details'] = JSON.stringify(frm.fabric_program.get_data())
			frm.doc['fabric_requirement_details'] = JSON.stringify(frm.fabric_program.get_requirement())
		} else {
			delete frm.doc.fabric_program_details;
			delete frm.doc.fabric_requirement_details;
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
				method: 'essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_isfinal_uom',
				args: {
					item_production_detail: frm.doc.production_detail,
					get_pack_stage: true,
				},
				callback: function (r) {
					if (r.message) {
						frm.set_value('uom', r.message.uom)
						frm.set_value('pack_in_stage', frappe.yrp.attribute_value(r.message.pack_in_stage))
						frm.set_value('packing_uom', r.message.packing_uom)
						frm.set_value('pack_out_stage', frappe.yrp.attribute_value(r.message.pack_out_stage))
						frm.set_value('dependent_attribute_mapping', r.message.dependent_attr_mapping)
						frm.set_value('tech_pack_version', r.message.tech_pack_version)
						frm.set_value('pattern_version', r.message.pattern_version)
						frm.set_value('packing_combo', r.message.packing_combo)
					}
				}
			})
			frappe.call({
				method: 'essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_item_details',
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
				method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.calculate_bom",
				args: {
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

function add_purchase_order_link_actions(frm) {
	frm.add_custom_button(__("Link to PO"), () => {
		new frappe.ui.form.MultiSelectDialog({
			doctype: "Purchase Order",
			target: frm,
			date_field: "po_date",
			get_query() {
				return { filters: { docstatus: 1, open_status: "Open" } };
			},
			primary_action_label: __("Link"),
			action(selections) {
				if (!(selections || []).length) {
					frappe.show_alert({
						message: __("Select at least one Purchase Order"),
						indicator: "red",
					});
					return;
				}
				prompt_purchase_order_link_reason(frm, {
					add_pos: selections,
					title: __("Reason for Linking"),
					action_label: __("Link"),
					freeze_message: __("Linking lot to Purchase Orders..."),
				});
			},
		});
	}, __("Actions"));

	frm.add_custom_button(__("Unlink from PO"), () => {
		frappe.call({
			method: "essdee_yrp.purchase_order_lots.get_purchase_orders_for_lot",
			args: { lot: frm.doc.name },
			callback(r) {
				const linked = r.message || [];
				if (!linked.length) {
					frappe.show_alert({
						message: __("This lot is not linked to any submitted PO"),
						indicator: "blue",
					});
					return;
				}
				new frappe.ui.form.MultiSelectDialog({
					doctype: "Purchase Order",
					target: frm,
					date_field: "po_date",
					get_query() {
						return {
							filters: { name: ["in", linked], docstatus: 1 },
						};
					},
					primary_action_label: __("Unlink"),
					action(selections) {
						if (!(selections || []).length) {
							frappe.show_alert({
								message: __("Select at least one Purchase Order"),
								indicator: "red",
							});
							return;
						}
						prompt_purchase_order_link_reason(frm, {
							remove_pos: selections,
							title: __("Reason for Unlinking"),
							action_label: __("Unlink"),
							freeze_message: __("Unlinking lot from Purchase Orders..."),
						});
					},
				});
			},
		});
	}, __("Actions"));
}

function prompt_purchase_order_link_reason(frm, options) {
	frappe.prompt(
		[
			{
				fieldname: "comment",
				fieldtype: "Small Text",
				label: __("Reason"),
				reqd: 1,
			},
		],
		(values) => {
			frappe.call({
				method: "essdee_yrp.purchase_order_lots.update_lot_po_links",
				args: {
					lot: frm.doc.name,
					add_pos: options.add_pos || [],
					remove_pos: options.remove_pos || [],
					comment: values.comment,
				},
				freeze: true,
				freeze_message: options.freeze_message,
				callback() {
					frm.reload_doc();
				},
			});
		},
		options.title,
		options.action_label,
	);
}

function setup_time_and_action(frm) {
	if (!frm.fields_dict.time_and_action_html || !frm.fields_dict.time_and_action_report_html) {
		return
	}
	const links = frm.doc.lot_time_and_action_details || []
	if (links.length) {
		$(frm.fields_dict.time_and_action_html.wrapper).empty()
		frm.time_action = new frappe.production.ui.TimeAction(
			frm.fields_dict.time_and_action_html.wrapper
		)
		frm.time_action.load_data(frm.doc.__onload?.action_details || [])
		$(frm.fields_dict.time_and_action_report_html.wrapper).empty()
		frm.time_action_report = new frappe.production.ui.TimeActionReport(
			frm.fields_dict.time_and_action_report_html.wrapper
		)
		if (frappe.user.has_role("T & A Admin")) {
			frm.add_custom_button(__("Revert T & A"), () => {
				frappe.confirm(__("Revert this Lot's Time and Action schedule?"), () => {
					frappe.call({
						method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_time_and_action.sd_yrp_time_and_action.revert_t_and_a",
						args: { doc_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Reverting Time and Action..."),
						callback: () => frm.reload_doc(),
					})
				})
			}, __("Time and Action"))
		}
		return
	}
	if (frm.is_new() || !frm.doc.assigned_person || !frm.doc.size_set_colour) {
		return
	}
	frm.add_custom_button(__("Create T&A"), () => open_time_and_action_dialog(frm), __("Time and Action"))
}

function open_time_and_action_dialog(frm) {
	frappe.call({
		method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_packing_attributes",
		args: { ipd: frm.doc.production_detail },
		callback: (response) => {
			const packing = response.message || {}
			const rows = (packing.colour_combo || []).map((row) => ({
				major_colour: row.major_colour,
				colour: frappe.yrp.attribute_value(row.colour),
				master: null,
			}))
			if (!rows.length) {
				frappe.msgprint(__("No packing colour combinations are available."))
				return
			}
			const label = frm.doc.is_set_item
				? __("Colours - {0}", [frm.doc.set_item_attribute])
				: __("Colours")
			const dialog = new frappe.ui.Dialog({
				title: __("Create Time and Action"),
				size: "extra-large",
				fields: [
					{
						label,
						fieldname: "table",
						fieldtype: "Table",
						cannot_add_rows: true,
						in_place_edit: false,
						data: rows,
						fields: [
							{ fieldname: "major_colour", fieldtype: "Data", in_list_view: 1, label: __("Major Colour"), read_only: 1 },
							{ fieldname: "colour", fieldtype: "Data", in_list_view: 1, label: __("Colour"), read_only: 1 },
							{
								fieldname: "master",
								fieldtype: "Link",
								in_list_view: 1,
								options: "SD YRP Action Master",
								label: __("Master"),
								reqd: 1,
								filters: { workflow_state: "Approved", disable: 0 },
							},
						],
					},
					{ label: __("Start Date"), fieldname: "start_date", fieldtype: "Date", reqd: 1 },
				],
				primary_action_label: __("Create"),
				primary_action: (values) => open_work_station_dialog(frm, dialog, packing, values),
				secondary_action_label: __("Preview"),
				secondary_action: () => preview_time_and_action(dialog),
			})
			dialog.show()
		},
	})
}

function validate_time_and_action_values(values) {
	for (const row of values.table || []) {
		if (!row.master) frappe.throw(__("Select an Action Master for colour {0}.", [frappe.yrp.attribute_value(row.colour)]))
	}
	if (!values.start_date) frappe.throw(__("Select the Start Date."))
}

function open_work_station_dialog(frm, parentDialog, packing, values) {
	validate_time_and_action_values(values)
	frappe.call({
		method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_action_master.sd_yrp_action_master.get_action_master_details",
		args: { master_list: values.table },
		callback: async (response) => {
			const dialog = new frappe.ui.Dialog({
				title: __("Work Station List"),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "work_station_html" }],
				primary_action_label: __("Create"),
				primary_action: () => {
					const items = editor.get_items()
					dialog.disable_primary_action()
					frappe.call({
						method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_time_and_action.sd_yrp_time_and_action.create_time_and_action",
						args: {
							lot: frm.doc.name,
							item_name: frm.doc.item,
							args: packing,
							values,
							total_qty: frm.doc.total_order_quantity,
							items,
						},
						freeze: true,
						freeze_message: __("Creating Time and Action..."),
						callback: () => {
							dialog.hide()
							parentDialog.hide()
							frm.reload_doc()
						},
						always: () => dialog.enable_primary_action(),
					})
				},
			})
			dialog.show()
			const editor = new frappe.production.ui.WorkStation(
				dialog.fields_dict.work_station_html.wrapper
			)
			await editor.load_data(response.message, "create")
			editor.set_attributes()
		},
	})
}

function preview_time_and_action(dialog) {
	const values = dialog.get_values()
	validate_time_and_action_values(values)
	frappe.call({
		method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_time_and_action.sd_yrp_time_and_action.get_t_and_a_preview_data",
		args: { start_date: values.start_date, table: values.table },
		callback: (response) => {
			const preview = new frappe.ui.Dialog({
				title: __("Time and Action Preview"),
				size: "extra-large",
				fields: [{ fieldname: "preview_html", fieldtype: "HTML" }],
				primary_action_label: __("Close"),
				primary_action: () => preview.hide(),
			})
			const view = new frappe.production.ui.TimeActionPreview(
				preview.fields_dict.preview_html.wrapper
			)
			view.load_data(response.message, values.start_date)
			preview.show()
		},
	})
}

function mount_cloth_program(frm) {
	const field = frm.fields_dict.fabric_program_html;
	if (!field) return;
	frm.fabric_program?.app?.unmount();
	const request = (frm._cloth_program_request || 0) + 1;
	frm._cloth_program_request = request;
	frm._cloth_program_ready = false;
	const wrapper = $(field.wrapper).empty();
	const status = $('<div class="text-muted mb-2" role="status"></div>').appendTo(wrapper);
	const content = $('<div></div>').appendTo(wrapper);
	frm.fabric_program = new frappe.production.ui.FabricProgram(content[0]);
	frm.fabric_program.load_data(frm.doc.__onload?.fabric_program_details || []);
	if (frm.is_new()) {
		frm._cloth_program_ready = true;
		return;
	}
	const lot = frm.doc.name;
	const editor = frm.fabric_program;
	const current = () => frm.doc.name === lot && frm._cloth_program_request === request
		&& frm.fabric_program === editor;
	const load = () => {
		status.text(__('Loading Cloth Program…'));
		content.css('pointer-events', 'none').attr('inert', '');
		frappe.call({
			method: 'essdee_yrp.fabric_program.get_fabric_program_details',
			args: {lot},
			callback(r) {
				if (!current()) return;
				editor.load_data(r.message || []);
				frm._cloth_program_ready = true;
				status.empty();
				content.css('pointer-events', '').removeAttr('inert');
			},
			error() {
				if (!current()) return;
				status.text(__('Could not load Cloth Program. '));
				$('<button type="button" class="btn btn-xs btn-default"></button>')
					.text(__('Retry')).on('click', load).appendTo(status);
			},
		});
	};
	load();
}


// frappe.ui.form.on('SD YRP Lot', {
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
// 				frappe.set_route("query-report", "SD YRP Lot Purchase Summary", {
// 					lot: frm.doc.name
// 				});
// 			}, __("View"));
// 		}
// 	},

// 	item: function(frm) {
// 		if (frm.doc.item) {
// 			frm.set_value({"lot_template": ""});
// 			frappe.call({
// 				method: "yrp.yrp.doctype.yrp_item.yrp_item.get_attribute_values",
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
// 				method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_template.sd_yrp_lot_template.get_attribute_values",
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
// 				method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_template.sd_yrp_lot_template.get_calculated_bom",
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

// frappe.ui.form.on('SD YRP Lot Planned Qty', {
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
	const colour_selections = {};
	const fields = [{
		label: __("Cloth Excess Percentage"),
		fieldname: "excess_percentage",
		fieldtype: "Float",
		default: Number(frm.doc.cloth_excess_percentage || 0),
	}];
	cloths.forEach((c, i) => {
		const item_yarns = c.item_yarns || [];
		const profile = c.profile || {};
		const required_colours = (c.required_colours || []).filter(Boolean);
		const stored_dyed_colours = new Set(c.dyed_yarn_colours || []);
		const stored_same_finished_colours = new Set(
			c.same_finished_colours || []
		);
		fields.push({ fieldtype: "Section Break", label: __(frappe.utils.escape_html(`${c.label} — ${c.cloth_item}`)) });
		fields.push({ fieldtype: "Data", fieldname: `cloth_item_${i}`, hidden: 1, default: c.cloth_item });
		fields.push({ fieldtype: "Data", fieldname: `production_detail_${i}`, hidden: 1, default: c.production_detail || "" });
		fields.push({
			fieldtype: "HTML",
			fieldname: `item_yarn_recipe_${i}`,
			options: item_yarns.length
				? `<div class="text-muted small" style="margin-bottom:10px">${__(
					"Item Yarn Recipe"
				)}: <strong>${item_yarns.map((row) =>
					`${frappe.utils.escape_html(row.yarn_item)} ${Number(row.ratio || 0)}%`
				).join(" + ")}</strong></div>`
				: `<div class="text-danger small" style="margin-bottom:10px">${__(
					"Configure a Yarn Ratio totalling 100% on Cloth Item {0} before building.",
					[frappe.utils.escape_html(c.cloth_item)]
				)}</div>`,
		});

		if (required_colours.length) {
			colour_selections[i] = required_colours.map((colour) => ({
				colour,
				use_dyed_yarn: stored_dyed_colours.has(colour) ? 1 : 0,
				same_finished_colour: (
					!stored_dyed_colours.has(colour)
					&& stored_same_finished_colours.has(colour)
				) ? 1 : 0,
			}));
			fields.push({
				fieldname: `colour_selection_${i}`,
				fieldtype: "HTML",
				options: cloth_program_colour_table(i, colour_selections[i]),
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
			options: "YRP Process",
			reqd: 1,
			default: profile.knitting_process || defaults.knitting_process || "",
		});
		fields.push({ fieldtype: "Column Break" });
		fields.push({
			label: "Dyeing Process", fieldname: `dyeing_process_${i}`,
			fieldtype: "Link",
			options: "YRP Process",
			reqd: 0,
			default: profile.dyeing_process || defaults.dyeing_process || "",
		});
	});

	const d = new frappe.ui.Dialog({
		title: "Build Cloth Programs",
		size: "large",
		fields: fields,
		primary_action_label: "Build",
		primary_action(values) {
			if (Number(values.excess_percentage) < 0) {
				frappe.msgprint(__("Knitting program excess percentage cannot be negative."));
				return;
			}
			const selections = cloths.map((c, i) => {
				const profile = c.profile || {};
				const required_colours = (c.required_colours || []).filter(Boolean);
				const colour_rows = colour_selections[i] || [];
				const dyed_yarn_colours = colour_rows
					.filter((row) => Number(row.use_dyed_yarn || 0))
					.map((row) => frappe.yrp.attribute_value(row.colour))
					.filter(Boolean);
				const dyed_colour_set = new Set(dyed_yarn_colours);
				const same_finished_colours = colour_rows
					.filter((row) => Number(row.same_finished_colour || 0))
					.map((row) => frappe.yrp.attribute_value(row.colour))
					.filter(Boolean);
				const same_finished_set = new Set(same_finished_colours);
				const non_dyed_colour = frappe.yrp.attribute_value(defaults.knitting_output_colour) || "";
				const fabric_routes = [];
				required_colours.forEach((colour) => {
					(c.required_routes || [])
						.filter((route) => frappe.yrp.attribute_value(route.colour) === colour)
						.sort((a, b) => dia_sort_value(frappe.yrp.attribute_value(a.dia)) - dia_sort_value(frappe.yrp.attribute_value(b.dia)))
						.forEach((route) => {
							const stored_route = (profile.fabric_routes || []).find(
								(row) => frappe.yrp.attribute_value(row.finished_colour) === colour && frappe.yrp.attribute_value(row.finished_dia) === frappe.yrp.attribute_value(route.dia)
							) || {};
							fabric_routes.push({
								finished_colour: colour,
								finished_dia: frappe.yrp.attribute_value(route.dia),
								knitting_output_dia:
									frappe.yrp.attribute_value(stored_route.knitting_output_dia) || frappe.yrp.attribute_value(route.dia) || null,
								knitting_output_colour:
									(
										dyed_colour_set.has(colour)
										|| same_finished_set.has(colour)
									)
										? colour
										: non_dyed_colour,
								use_dyed_yarn: dyed_colour_set.has(colour) ? 1 : 0,
							});
						});
				});
				const recipe = c.item_yarns || [];
				return {
					cloth_item: values[`cloth_item_${i}`],
					production_detail: values[`production_detail_${i}`] || null,
					dyed_yarn_colours: dyed_yarn_colours,
					same_finished_colours: same_finished_colours,
					fabric_routes: fabric_routes,
					non_dyed_colour: non_dyed_colour,
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
			const issues = [];
			selections.forEach((s) => {
				const add_issue = (message) => issues.push(`${frappe.utils.escape_html(s.cloth_item)}: ${message}`);
				const invalid_recipe = !s.yarns.length
					|| s.yarns.some((row) => !row.yarn_item || !(Number(row.ratio) > 0))
					|| frappe.yrp.attribute_value(new Set(s.yarns.map((row) => row.yarn_item)).size) !== s.yarns.length
					|| Math.abs(s.yarns.reduce((sum, row) => sum + Number(row.ratio), 0) - 100) > 0.001;
				if (invalid_recipe) add_issue(__("Configure unique Yarn Items with positive ratios totaling 100% on the Cloth Item."));
				const needs_default = s.required_colours.some((colour) =>
					!s.dyed_yarn_colours.includes(colour) && !s.same_finished_colours.includes(colour));
				if (needs_default && !s.non_dyed_colour) {
					add_issue(__("Set Default Knitting Yarn Colour in SD YRP IPD Settings for colours without Is Dyed Yarn or Same Finished Colour selected."));
				}
				if (!s.knitting_process) add_issue(__("Select a Knitting Process."));
				if (!(s.cloth_per_kg_yarn > 0)) add_issue(__("Cloth Kgs / 1 Kg Yarn must be greater than zero."));
				if (s.fabric_routes.some((row) => !frappe.yrp.attribute_value(row.knitting_output_dia))) {
					add_issue(__("Configure the missing Knitting Output Dia in the cloth IPD."));
				}
				if (s.fabric_routes.some((row) => frappe.yrp.attribute_value(row.knitting_output_colour) && frappe.yrp.attribute_value(row.knitting_output_colour) !== frappe.yrp.attribute_value(row.finished_colour))
					&& !s.dyeing_process) add_issue(__("Select a Dyeing Process for routes that change Colour."));
				if (s.fabric_routes.some((row) => frappe.yrp.attribute_value(row.knitting_output_dia) && frappe.yrp.attribute_value(row.knitting_output_dia) !== frappe.yrp.attribute_value(row.finished_dia))
					&& !s.compacting_process) add_issue(__("Set Default Dia-change Process in SD YRP IPD Settings for routes that change Dia."));
			});
			if (issues.length) {
				frappe.msgprint({ title: __("Cloth Program Settings Required"), message: issues.join("<br>"), indicator: "orange" });
				return;
			}
			frappe.call({
				method: "essdee_yrp.api.cloth_program.build_cloth_programs",
				args: {
					lot: frm.doc.name,
					selections: JSON.stringify(selections),
					modified: frm.doc.modified,
					excess_percentage: values.excess_percentage || 0,
				},
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
		const profile_yarn = c.item_yarns?.[0]?.yarn_item;
		if (!c.profile?.knitting_process && profile_yarn) {
			apply_yarn_profile(d, i, profile_yarn, c);
		}
	});
	d.show();
	mount_cloth_program_colour_controls(d, colour_selections);
}

function cloth_program_colour_table(cloth_index, rows) {
	const header_style = [
		"display:grid",
		"grid-template-columns:minmax(170px,5fr) minmax(120px,3fr) minmax(180px,4fr)",
		"gap:12px",
		"align-items:center",
		"padding:8px 12px",
		"background:var(--subtle-fg)",
		"border-bottom:1px solid var(--border-color)",
		"font-size:12px",
		"font-weight:600",
	].join(";");
	const row_style = [
		"display:grid",
		"grid-template-columns:minmax(170px,5fr) minmax(120px,3fr) minmax(180px,4fr)",
		"gap:12px",
		"align-items:center",
		"min-height:48px",
		"padding:6px 12px",
		"border-bottom:1px solid var(--border-color)",
	].join(";");
	return `
		<div class="small text-muted" style="margin-bottom:6px">${__("Colours")}</div>
		<div class="cloth-program-colour-table"
			style="position:relative;overflow:visible;border:1px solid var(--border-color);border-radius:8px">
			<div style="${header_style}">
				<span>${__("Finished Colour")}</span>
				<span>${__("Is Dyed Yarn")}</span>
				<span>${__("Same Finished Colour")}</span>
			</div>
			${rows.map((row, row_index) => `
				<div style="${row_style}">
					<strong>${frappe.utils.escape_html(frappe.yrp.attribute_value(row.colour))}</strong>
					<label style="display:flex;align-items:center;gap:7px;margin:0;cursor:pointer">
						<input type="checkbox"
							data-cloth-program-dyed="${cloth_index}:${row_index}"
							${row.use_dyed_yarn ? "checked" : ""}>
					</label>
					<label style="display:flex;align-items:center;gap:7px;margin:0;cursor:pointer">
						<input type="checkbox"
							data-cloth-program-same="${cloth_index}:${row_index}"
							${row.same_finished_colour ? "checked" : ""}
							${row.use_dyed_yarn ? "disabled" : ""}>
					</label>
				</div>
			`).join("")}
		</div>`;
}

function mount_cloth_program_colour_controls(dialog, selections) {
	dialog.$wrapper.on("change", "[data-cloth-program-dyed]", function () {
		const [cloth_index, row_index] = $(this)
			.attr("data-cloth-program-dyed")
			.split(":");
		const row = selections[cloth_index][Number(row_index)];
		const checked = $(this).is(":checked");
		row.use_dyed_yarn = checked ? 1 : 0;
		if (checked) {
			row.same_finished_colour = 0;
		}
		const $same = dialog.$wrapper.find(
			`[data-cloth-program-same="${cloth_index}:${row_index}"]`
		);
		$same.prop("checked", Boolean(row.same_finished_colour));
		$same.prop("disabled", checked);
	});

	dialog.$wrapper.on("change", "[data-cloth-program-same]", function () {
		const [cloth_index, row_index] = $(this)
			.attr("data-cloth-program-same")
			.split(":");
		const row = selections[cloth_index][Number(row_index)];
		row.same_finished_colour = $(this).is(":checked") ? 1 : 0;
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
			cloth.profile = { ...(cloth.profile || {}), ...p };
			if (p.knitting_process && !dialog.get_value(`knitting_process_${i}`)) {
				dialog.set_value(`knitting_process_${i}`, p.knitting_process);
			}
			if (p.dyeing_process && !dialog.get_value(`dyeing_process_${i}`)) {
				dialog.set_value(`dyeing_process_${i}`, p.dyeing_process);
			}
			if (p.cloth_per_kg_yarn && !dialog.get_value(`cloth_per_kg_yarn_${i}`)) {
				dialog.set_value(`cloth_per_kg_yarn_${i}`, p.cloth_per_kg_yarn);
			}
		}
	});
}
