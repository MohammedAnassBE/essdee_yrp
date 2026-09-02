frappe.ui.form.on("YRP Work Order", {
	setup(frm) {
		frm.set_df_property("production_detail", "read_only", 1);
		frm.set_query("item", () => {
			const items = frm._work_order_item_options || [];
			return {
				filters: {
					name: ["in", items.length ? items : ["__no_work_order_item__"]],
				},
			};
		});
	},
	refresh(frm) {
		frm._work_order_process_is_cloth = null;
		update_calculate_button(frm);
		frm.set_df_property("supplier", "label", __("Supplier"));
		frm.set_df_property("supplier_address", "label", __("Supplier Address"));
		frm.set_df_property("process_name", "label", __("Process"));
		frm.set_df_property("production_detail", "label", __("Item Production Detail"));
		frm.set_df_property("production_detail", "read_only", 1);
		frm.trigger("apply_lot_process_selection");
		// Base YRP also mounts these editors in its refresh handler. Defer one
		// tick so the Essdee calculated-only editor is deterministically last,
		// regardless of hook registration order.
		setTimeout(() => {
			arrange_work_order_header_fields(frm);
			mount_calculated_work_order_editors(frm);
			mount_work_order_summary(frm);
			setup_essdee_work_order_actions(frm);
		}, 0);
	},
	lot(frm) {
		if (frm.doc.docstatus === 0) {
			frm.set_value("item", "");
			frm.set_value("production_detail", "");
		}
		frm.trigger("apply_lot_process_selection");
	},
	process_name(frm) {
		if (frm.doc.docstatus === 0) {
			frm.set_value("item", "");
			frm.set_value("production_detail", "");
			if (!frm.doc.process_name) frm.set_value("lot", "");
		}
		frm.trigger("apply_lot_process_selection");
	},
	item(frm) {
		apply_selected_work_order_item(frm);
	},
	async apply_lot_process_selection(frm) {
		const request_id = (frm._work_order_selection_request || 0) + 1;
		frm._work_order_selection_request = request_id;
		frm._work_order_selection_options = [];
		frm._work_order_item_options = [];
		frm._work_order_process_is_cloth = null;
		update_work_order_header_controls(frm);
		update_calculate_button(frm);
		if (!frm.doc.lot || !frm.doc.process_name) return;

		const r = await frappe.call({
			method: "essdee_yrp.api.work_order.get_work_order_selection_context",
			args: { lot: frm.doc.lot, process_name: frm.doc.process_name },
		});
		if (request_id !== frm._work_order_selection_request) return;

		const context = r.message || {};
		frm._work_order_selection_options = context.options || [];
		frm._work_order_item_options = context.item_options || [];
		frm._work_order_process_is_cloth = Boolean(context.process_is_cloth_process);

		if (frm.doc.docstatus === 0) {
			if (
				frm.doc.item
				&& !frm._work_order_item_options.includes(frm.doc.item)
			) {
				await set_if_changed(frm, "item", "");
				await set_if_changed(frm, "production_detail", "");
			} else {
				await apply_selected_work_order_item(frm);
			}
			if (!frm._work_order_item_options.length) {
				frappe.show_alert({
					message: context.is_cloth_process
						? __("No Lot cloth IPD contains process {0}.", [frm.doc.process_name])
						: __("The Lot has no garment Item Production Detail."),
					indicator: "orange",
				});
			}
		}
		update_work_order_header_controls(frm);
		update_calculate_button(frm);
	},
});

function update_calculate_button(frm) {
	const fabric_label = __("Calculate Fabric Deliverables");
	const garment_label = __("Calculate Items");
	frm.remove_custom_button(fabric_label);
	frm.remove_custom_button(garment_label);
	if (
		frm.is_new()
		|| frm.doc.docstatus !== 0
		|| frm.doc.is_rework
		|| !frm.doc.lot
		|| !frm.doc.process_name
		|| frm._work_order_process_is_cloth === null
	) {
		return;
	}
	if (frm._work_order_process_is_cloth) {
		frm.add_custom_button(fabric_label, () => open_fabric_calculate(frm));
	} else {
		frm.add_custom_button(garment_label, () => open_garment_calculate(frm));
	}
}

const ESSDEE_WORK_ORDER_ACTIONS = [
	"Material Issue",
	"Make Cutting Plan",
	"Make DC",
	"Make GRN",
	"Create Recut",
	"Change Delivery Date",
	"Change Item",
	"Create Sewing Plan",
	"Open Sewing Plan",
	"Calculate Pieces",
];

function clear_essdee_work_order_actions(frm) {
	for (const label of ESSDEE_WORK_ORDER_ACTIONS) {
		frm.remove_custom_button(__(label));
		frm.remove_custom_button(__(label), __("Create"));
	}
}

function setup_essdee_work_order_actions(frm) {
	hide_unavailable_rework_action(frm);
	clear_essdee_work_order_actions(frm);
	const request = (frm._essdee_action_request || 0) + 1;
	frm._essdee_action_request = request;
	if (frm.is_new() || frm.doc.docstatus !== 1) {
		return;
	}
	frappe.call({
		method: "essdee_yrp.work_order_actions.get_work_order_action_context",
		args: { work_order: frm.doc.name },
		callback(r) {
			if (request !== frm._essdee_action_request) return;
			const context = r.message || {};
			if (context.can_calculate_pieces) {
				frm.add_custom_button(__("Calculate Pieces"), () => {
					rebuild_work_order_pieces(frm);
				});
			}
			if (!context.is_open) return;
			add_essdee_create_actions(frm, context);
			if (context.can_change_delivery_date) {
				frm.add_custom_button(__("Change Delivery Date"), () => {
					open_change_delivery_date_dialog(frm);
				});
			}
			if (context.can_change_item) {
				frm.add_custom_button(__("Change Item"), () => {
					open_change_item_dialog(frm);
				});
			}
			if (context.can_create_sewing_plan) {
				const label = context.sewing_plan
					? __("Open Sewing Plan")
					: __("Create Sewing Plan");
				frm.add_custom_button(label, () => {
					if (context.sewing_plan) {
						frappe.set_route("Form", "SD YRP Sewing Plan", context.sewing_plan);
						return;
					}
					create_sewing_plan(frm);
				});
			}
		},
	});
}

function hide_unavailable_rework_action(frm) {
	if (frappe.model.can_create("YRP Work Order")) return;
	frm.remove_custom_button(__("Create Rework"));
	frm.remove_custom_button(__("Create Rework"), __("Create"));
}

function rebuild_work_order_pieces(frm) {
	frappe.call({
		method: "essdee_yrp.work_order_piece_tracking.calculate_completed_pieces",
		args: { work_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Rebuilding Work Order piece quantities..."),
		callback(r) {
			const result = r.message || {};
			frappe.show_alert({
				message: __("Pieces rebuilt: {0} delivered, {1} received.", [
					flt(result.total_delivered, 3),
					flt(result.total_received, 3),
				]),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

function add_essdee_create_actions(frm, context) {
	if (context.can_make_material_issue) {
		frm.add_custom_button(__("Material Issue"), () => {
			frappe.new_doc("YRP Stock Entry", {
				purpose: "Material Issue",
				against: "YRP Work Order",
				against_id: frm.doc.name,
				from_warehouse: context.material_issue_warehouse || "",
				from_supplier: frm.doc.supplier || "",
				transfer_supplier: frm.doc.supplier || "",
			});
		}, __("Create"));
	}
	if (context.can_make_cutting_plan) {
		frm.add_custom_button(__("Make Cutting Plan"), () => {
			open_local_work_order_doc("SD YRP Cutting Plan", {
				work_order: frm.doc.name,
				lot: frm.doc.lot,
				item: frm.doc.item,
				maximum_no_of_plys: 100,
			});
		}, __("Create"));
	}
	if (context.can_make_delivery_challan) {
		frm.add_custom_button(__("Make DC"), () => {
			prepare_work_order_transaction(frm, "YRP Delivery Challan");
		}, __("Create"));
	}
	if (context.can_make_goods_received_note) {
		frm.add_custom_button(__("Make GRN"), () => {
			select_grn_delivery_challan(frm);
		}, __("Create"));
	}
	if (context.can_make_recut) {
		frm.add_custom_button(__("Create Recut"), () => {
			open_local_work_order_doc("SD YRP WO Recut", {
				work_order: frm.doc.name,
				lot: frm.doc.lot,
			});
		}, __("Create"));
	}
}

function open_local_work_order_doc(doctype, values) {
	frappe.model.with_doctype(doctype, () => {
		const doc = frappe.model.get_new_doc(doctype);
		for (const [fieldname, value] of Object.entries(values || {})) {
			if (frappe.meta.has_field(doctype, fieldname)) doc[fieldname] = value;
		}
		frappe.set_route("Form", doctype, doc.name);
	});
}

function select_grn_delivery_challan(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Delivery Challan"),
		fields: [
			{
				fieldname: "delivery_challan",
				fieldtype: "Link",
				options: "YRP Delivery Challan",
				label: __("Delivery Challan"),
				get_query: () => ({
					filters: { work_order: frm.doc.name, docstatus: 1 },
				}),
			},
		],
		primary_action(values) {
			dialog.hide();
			prepare_work_order_transaction(frm, "YRP Goods Received Note", {
				delivery_challan: values.delivery_challan || "",
			});
		},
	});
	dialog.show();
}

function prepare_work_order_transaction(frm, doctype, extra_args = {}) {
	const method = doctype === "YRP Delivery Challan"
		? "essdee_yrp.work_order_actions.get_delivery_challan_defaults"
		: "essdee_yrp.work_order_actions.get_goods_received_note_defaults";
	frappe.call({
		method,
		args: { work_order: frm.doc.name, ...extra_args },
		freeze: true,
		freeze_message: __(`Preparing ${doctype}...`),
		callback(r) {
			if (r.message) open_prepared_work_order_transaction(doctype, r.message);
		},
	});
}

function open_prepared_work_order_transaction(doctype, values) {
	frappe.model.with_doctype(doctype, () => {
		const doc = frappe.model.get_new_doc(doctype);
		const prepared_item_details = values?.item_details || [];
		const ignored = new Set(["items", "correction_items", "correction_item_details"]);
		for (const [fieldname, value] of Object.entries(values || {})) {
			if (ignored.has(fieldname)) continue;
			if (fieldname === "item_details") {
				doc.item_details = JSON.stringify(value || []);
				continue;
			}
			if (frappe.meta.has_field(doctype, fieldname)) doc[fieldname] = value;
		}
		if (!doc.posting_date) doc.posting_date = frappe.datetime.nowdate();
		if (!doc.posting_time) doc.posting_time = frappe.datetime.now_datetime().split(" ")[1];
		frappe.set_route("Form", doctype, doc.name).then(() => {
			if (doctype !== "YRP Goods Received Note") return;
			frappe.after_ajax(() => {
				if (cur_frm?.doctype !== doctype || cur_frm.doc.name !== doc.name) return;
				cur_frm.clear_table("items");
				cur_frm.refresh_field("items");
				cur_frm.doc.item_details = JSON.stringify(prepared_item_details);
				if (cur_frm.itemEditor) {
					cur_frm.itemEditor.load_data(prepared_item_details);
				}
				cur_frm.dirty();
			});
		});
	});
}

function open_change_delivery_date_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Change Delivery Date"),
		fields: [
			{
				fieldname: "expected_date",
				fieldtype: "Date",
				label: __("Delivery Date"),
				default: frm.doc.expected_delivery_date,
				reqd: 1,
			},
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Reason"),
				reqd: 1,
			},
		],
		primary_action_label: __("Submit"),
		primary_action(values) {
			frappe.call({
				method: "essdee_yrp.time_and_action.tracking.update_expected_date",
				args: {
					work_order: frm.doc.name,
					expected_date: values.expected_date,
					reason: values.reason,
					_return: 0,
				},
				freeze: true,
				freeze_message: __("Updating delivery date..."),
				callback() {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function create_sewing_plan(frm) {
	frappe.call({
		method: "essdee_yrp.sewing.plan.create_sewing_plan",
		args: { work_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating Sewing Plan..."),
		callback(r) {
			if (r.message) frappe.set_route("Form", "SD YRP Sewing Plan", r.message);
		},
	});
}

function open_change_item_dialog(frm) {
	frappe.call({
		method: "essdee_yrp.work_order_actions.get_wo_bom_accessory_items",
		args: { work_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading Item BOM rows..."),
		callback(r) {
			const result = r.message || {};
			if (!result.supported || !(result.items || []).length) {
				frappe.msgprint({
					title: __("Change Item"),
					message: result.message || __("No Item BOM rows are available."),
					indicator: "blue",
				});
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Change Item"),
				size: "large",
				fields: [{ fieldname: "items_html", fieldtype: "HTML" }],
				primary_action_label: __("Recalculate"),
				primary_action() {
					const selected = d.$wrapper
						.find(".essdee-change-item-row:checked")
						.map((_, element) => $(element).data("name"))
						.get();
					if (!selected.length) {
						frappe.msgprint(__("Select at least one Item BOM row to recalculate."));
						return;
					}
					d.hide();
					open_change_item_preview(frm, selected);
				},
			});
			d.fields_dict.items_html.$wrapper.html(render_change_item_rows(result.items));
			d.show();
		},
	});
}

function open_change_item_preview(frm, selected) {
	frappe.call({
		method: "essdee_yrp.work_order_actions.get_wo_bom_accessory_change_preview",
		args: { work_order: frm.doc.name, selected },
		freeze: true,
		freeze_message: __("Recalculating selected Item BOM rows..."),
		callback(r) {
			const changes = (r.message || {}).changes || [];
			const approvable = changes.filter(
				(change) => change.action === "replace" && change.eligible,
			);
			const d = new frappe.ui.Dialog({
				title: __("Approve Item BOM Change"),
				size: "large",
				fields: [{ fieldname: "preview_html", fieldtype: "HTML" }],
				primary_action_label: __("Approve"),
				primary_action() {
					if (!approvable.length) return;
					frappe.call({
						method: "essdee_yrp.work_order_actions.apply_bom_accessory_changes",
						args: { work_order: frm.doc.name, selected },
						freeze: true,
						freeze_message: __("Updating selected Item BOM rows..."),
						callback(res) {
							const output = res.message || {};
							frappe.msgprint({
								title: __("Change Item"),
								message: __("Updated {0} Item BOM row(s).", [(output.applied || []).length]),
								indicator: (output.applied || []).length ? "green" : "orange",
							});
							d.hide();
							frm.reload_doc();
						},
					});
				},
			});
			d.fields_dict.preview_html.$wrapper.html(render_change_item_preview(changes));
			d.show();
			d.get_primary_btn().toggle(approvable.length > 0);
		},
	});
}

function render_change_item_rows(items) {
	const escape = frappe.utils.escape_html;
	const rows = items.map((item) => `<tr>
		<td class="text-center"><input type="checkbox" class="essdee-change-item-row" data-name="${escape(item.row_name)}"></td>
		<td>${escape(item.branch || "")}</td>
		<td>${escape(item.item || "")}</td>
		<td>${escape(item.attributes || "")}</td>
		<td class="text-right">${flt(item.qty, 3)} ${escape(item.uom || "")}</td>
	</tr>`).join("");
	return `<div class="table-responsive"><table class="table table-bordered">
		<thead><tr><th></th><th>${__("Process")}</th><th>${__("Item BOM")}</th><th>${__("Mapping")}</th><th>${__("Qty")}</th></tr></thead>
		<tbody>${rows}</tbody>
	</table></div>`;
}

function render_change_item_preview(changes) {
	const escape = frappe.utils.escape_html;
	if (!changes.length) return `<p class="text-muted">${__("No recalculated changes were found.")}</p>`;
	const rows = changes.map((change) => {
		let status = change.eligible
			? `<span class="text-success">${__("Ready")}</span>`
			: `<span class="text-danger">${escape(change.reason || __("Not eligible"))}</span>`;
		if (change.action === "unchanged") status = `<span class="text-muted">${__("No change")}</span>`;
		return `<tr class="${change.eligible ? "" : "text-muted"}">
			<td>${escape(change.item || "")}</td>
			<td>${escape(change.old_variant || "")}<br><span class="text-muted">${__("Qty")}: ${flt(change.old_qty, 3)} ${escape(change.old_uom || "")}</span></td>
			<td class="text-center">&rarr;</td>
			<td>${escape(change.new_variant || "")}<br><span class="text-muted">${__("Calculated Qty")}: ${flt(change.new_qty, 3)} ${escape(change.new_uom || "")}</span></td>
			<td>${status}</td>
		</tr>`;
	}).join("");
	return `<div class="table-responsive"><table class="table table-bordered">
		<thead><tr><th>${__("Item BOM")}</th><th>${__("Current")}</th><th></th><th>${__("Recalculated")}</th><th>${__("Status")}</th></tr></thead>
		<tbody>${rows}</tbody>
	</table></div>`;
}

function update_work_order_header_controls(frm) {
	const draft = frm.doc.docstatus === 0;
	const has_process = Boolean(frm.doc.process_name);
	const has_context = has_process && Boolean(frm.doc.lot);
	const items = frm._work_order_item_options || [];
	frm.toggle_enable("lot", draft && has_process);
	frm.toggle_enable("item", draft && has_context && items.length > 0);
	frm.toggle_enable("production_detail", false);
}

function arrange_work_order_header_fields(frm) {
	const process = frm.fields_dict.process_name?.$wrapper;
	const lot = frm.fields_dict.lot?.$wrapper;
	const item = frm.fields_dict.item?.$wrapper;
	const production_detail = frm.fields_dict.production_detail?.$wrapper;
	if (!process?.length || !lot?.length || !item?.length || !production_detail?.length) return;
	lot.insertAfter(process);
	item.insertAfter(lot);
	production_detail.insertAfter(item);
}

async function set_if_changed(frm, fieldname, value) {
	if ((frm.doc[fieldname] || "") === (value || "")) return;
	await frm.set_value(fieldname, value || "");
}

async function apply_selected_work_order_item(frm) {
	if (frm.doc.docstatus !== 0) return;
	const matches = (frm._work_order_selection_options || []).filter(
		(option) => option.item === frm.doc.item
	);
	await set_if_changed(
		frm,
		"production_detail",
		matches.length === 1 ? matches[0].production_detail : ""
	);
}

function mount_calculated_work_order_editors(frm) {
	if (!frappe.yrp?.work_order?.ItemEditor) return;
	[
		{
			fieldname: "deliverable_items",
			editor_key: "deliverableEditor",
			payload_field: "deliverable_details",
			source_table: "deliverables",
			editor_type: "work_order_deliverables",
			title: __("Deliverables"),
		},
		{
			fieldname: "receivable_items",
			editor_key: "receivableEditor",
			payload_field: "receivable_details",
			source_table: "receivables",
			editor_type: "work_order_receivables",
			title: __("Receivables"),
		},
	].forEach((config) => {
		if (!frm.fields_dict[config.fieldname]) return;
		if (frm[config.editor_key]) frm[config.editor_key].app.unmount();
		frm.set_df_property(config.fieldname, "hidden", 0);
		frm.set_df_property(config.source_table, "hidden", 1);
		$(frm.fields_dict[config.fieldname].wrapper).empty();
		frm[config.editor_key] = new frappe.yrp.work_order.ItemEditor(
			frm.fields_dict[config.fieldname].wrapper,
			{
				title: config.title,
				editorType: config.editor_type,
				showDimensions: false,
				allowCreate: false,
				allowEdit: false,
				allowRemove: false,
				aggregateDisplay: true,
			},
		);
		let data = frm.doc.__onload?.[config.payload_field] || frm.doc[config.payload_field] || [];
		if (typeof data === "string") {
			try {
				data = JSON.parse(data);
			} catch (_) {
				data = [];
			}
		}
		frm[config.editor_key].load_data(data);
		frm[config.editor_key].update_status();
	});
	essdee_yrp.contain_item_editor_matrix(frm, ["deliverable_items", "receivable_items"]);
}

function mount_work_order_summary(frm) {
	const field = frm.fields_dict.wo_summary_html;
	if (!field) return;

	const $wrapper = $(field.wrapper);
	if (frm._essdee_work_order_summary?.app) {
		frm._essdee_work_order_summary.app.unmount();
	}
	frm._essdee_work_order_summary = null;
	$wrapper.empty();

	const request = (frm._essdee_summary_request || 0) + 1;
	frm._essdee_summary_request = request;
	if (frm.is_new() || frm.doc.docstatus !== 1 || frm.doc.is_rework) return;

	$wrapper.html(`<p class="text-muted" style="padding:12px 0;">${__("Loading Work Order summary...")}</p>`);
	frappe.call({
		method: "essdee_yrp.api.work_order.fetch_summary_details",
		args: {
			doc_name: frm.doc.name,
			production_detail: frm.doc.production_detail,
		},
		callback(r) {
			if (request !== frm._essdee_summary_request) return;
			const result = r.message || {};
			const rows = result.item_detail || [];
			$wrapper.empty();
			if (!rows.length) {
				$wrapper.html(
					`<div class="alert alert-info">${__("No Work Order Calculated Item rows are available for this summary.")}</div>`,
				);
				return;
			}
			if (!frappe.production?.ui?.WOSummary) {
				$wrapper.html(
					`<div class="alert alert-danger">${__("Work Order summary component is unavailable. Refresh after rebuilding Essdee assets.")}</div>`,
				);
				return;
			}
			frm._essdee_work_order_summary = new frappe.production.ui.WOSummary(
				$wrapper,
			);
			frm._essdee_work_order_summary.load_data(
				rows,
				result.deliverables || [],
				{ doctype: "YRP Work Order" },
			);
			$wrapper.css("overflow-x", "auto");
		},
		error() {
			if (request !== frm._essdee_summary_request) return;
			$wrapper.html(
				`<div class="alert alert-danger">${__("Could not load the Work Order summary.")}</div>`,
			);
		},
	});
}

function open_fabric_calculate(frm) {
	frappe.call({
		method: "essdee_yrp.api.work_order.get_fabric_deliverable_context",
		args: { work_order: frm.doc.name },
		callback(r) {
			const ctx = r.message || {};
			(ctx.warnings || []).forEach((w) => frappe.msgprint({ message: w, indicator: "orange" }));
			if (!(ctx.rows || []).length) {
				if (!ctx.is_fabric_process) {
					frappe.msgprint(__("{0} is not a fabric process for this Lot's fabrics.", [frm.doc.process_name || ""]));
				}
				return;
			}
			render_fabric_dialog(frm, ctx);
		},
	});
}

function open_garment_calculate(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the Work Order before calculating items."));
		return;
	}
	frappe.call({
		method: "essdee_yrp.garment_work_order.get_garment_work_order_context",
		args: { work_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading Lot items..."),
		callback(r) {
			const context = r.message || {};
			if (!(context.rows || []).length) {
				frappe.msgprint(__("The Lot has no items available for this process."));
				return;
			}
			render_garment_calculate_dialog(frm, context);
		},
	});
}

function render_garment_calculate_dialog(frm, context) {
	const rows = context.rows || [];
	const matrixRows = context.matrix_rows || [];
	const attributes = context.display_attributes || [];
	const primaryValues = context.primary_values || [];

	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const missing_matrices = context.missing_matrix_variants || [];
	const missing_preview = missing_matrices.slice(0, 5).map(escape).join(", ");
	const missing_suffix = missing_matrices.length > 5
		? __(", and {0} more", [missing_matrices.length - 5])
		: "";
	const matrix_warning = context.matrix_ready
		? ""
		: `<div class="alert alert-warning" style="margin-bottom:12px;">
			${__("Cutting matrices are missing for {0} selected variant(s): {1}{2}. Open {3} and use Generate / Regenerate IPD Process Matrix. If regeneration skips them, complete those variants' Cutting mappings in the IPD.", [
				missing_matrices.length,
				missing_preview,
				missing_suffix,
				`<a href="/app/yrp-item-production-detail/${encodeURIComponent(context.ipd)}"><b>${escape(context.ipd)}</b></a>`,
			])}
		</div>`;
	const attributeHeader = attributes
		.map((attribute) => `<th>${escape(__(attribute))}</th>`)
		.join("");
	const primaryHeader = primaryValues
		.map((value) => `<th style="min-width:92px;">${escape(value)}</th>`)
		.join("");
	const body = matrixRows.map((row, index) => {
		const attributeCells = attributes.map(
			(attribute) => `<td>${escape((row.attributes || {})[attribute] || "")}</td>`,
		).join("");
		const qtyCells = primaryValues.map((value) => {
			const cell = (row.values || {})[value];
			if (!cell) return '<td class="text-muted text-center">—</td>';
			return `<td style="min-width:92px;">
				<input class="form-control input-sm essdee-wo-calc-qty"
					type="number" min="0" max="${escape(flt(cell.available_qty))}" step="1"
					value="${escape(flt(cell.qty))}"
					data-source-row="${escape(cell.source_row)}"
					data-primary-value="${escape(value)}"
					title="${escape(cell.item_variant)}">
			</td>`;
		}).join("");
		return `<tr data-matrix-row="${index}">
			<td><input type="checkbox" class="essdee-wo-row-toggle" checked> ${index + 1}</td>
			${attributeCells}
			${qtyCells}
			<td class="text-right"><strong class="essdee-wo-row-total">0</strong></td>
		</tr>`;
	}).join("");
	const totals = primaryValues
		.map((value) => `<th class="text-right essdee-wo-column-total" data-primary-value="${escape(value)}">0</th>`)
		.join("");
	const html = `${matrix_warning}
		<h4 style="margin:0 0 10px;">${__("Order Items")}</h4>
		<div class="mb-2">
			<button class="btn btn-xs btn-default essdee-wo-select-all">${__("Select All")}</button>
			<button class="btn btn-xs btn-default essdee-wo-unselect-all" style="margin-left:5px;">${__("Unselect All")}</button>
		</div>
		<div style="max-height:55vh;overflow:auto;">
			<table class="table table-bordered table-sm">
				<thead><tr><th>${__("S.No.")}</th>${attributeHeader}${primaryHeader}<th class="text-right">${__("Total Qty")}</th></tr></thead>
				<tbody>${body}</tbody>
				<tfoot><tr><th>${__("Total")}</th>${attributes.map(() => "<th></th>").join("")}${totals}<th class="text-right essdee-wo-grand-total">0</th></tr></tfoot>
			</table>
		</div>`;

	const dialog = new frappe.ui.Dialog({
		title: __("Lot Items"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "items_html", options: html }],
		primary_action_label: __("Submit"),
		primary_action() {
			const selected = [];
			dialog.get_field("items_html").$wrapper.find(".essdee-wo-calc-qty").each(function () {
				const qty = flt($(this).val());
				if (qty > 0) selected.push({ source_row: $(this).data("source-row"), qty });
			});
			if (!selected.length) {
				frappe.msgprint(__("Enter a quantity greater than zero for at least one row."));
				return;
			}
			frappe.call({
				method: "essdee_yrp.garment_work_order.calculate_garment_work_order",
				args: {
					work_order: frm.doc.name,
					rows: selected,
					modified: frm.doc.modified,
				},
				freeze: true,
				freeze_message: __("Calculating Deliverables and Receivables..."),
				callback(res) {
					dialog.hide();
					const result = res.message || {};
					frappe.show_alert({
						message: __("Calculated {0} deliverable(s) and {1} receivable(s).", [
							result.deliverables || 0,
							result.receivables || 0,
						]),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
	const wrapper = dialog.get_field("items_html").$wrapper;
	const updateTotals = () => {
		const columnTotals = {};
		let grandTotal = 0;
		wrapper.find("tr[data-matrix-row]").each(function () {
			let rowTotal = 0;
			$(this).find(".essdee-wo-calc-qty").each(function () {
				const qty = flt($(this).val());
				const primaryValue = String($(this).data("primary-value"));
				rowTotal += qty;
				columnTotals[primaryValue] = (columnTotals[primaryValue] || 0) + qty;
			});
			$(this).find(".essdee-wo-row-total").text(rowTotal);
			grandTotal += rowTotal;
		});
		wrapper.find(".essdee-wo-column-total").each(function () {
			$(this).text(columnTotals[String($(this).data("primary-value"))] || 0);
		});
		wrapper.find(".essdee-wo-grand-total").text(grandTotal);
	};
	const setRowSelected = (row, selected) => {
		row.find(".essdee-wo-row-toggle").prop("checked", selected);
		row.find(".essdee-wo-calc-qty").each(function () {
			$(this).val(selected ? $(this).attr("max") : 0);
		});
	};
	wrapper.on("input", ".essdee-wo-calc-qty", updateTotals);
	wrapper.on("change", ".essdee-wo-row-toggle", function () {
		setRowSelected($(this).closest("tr"), $(this).prop("checked"));
		updateTotals();
	});
	wrapper.on("click", ".essdee-wo-select-all", () => {
		wrapper.find("tr[data-matrix-row]").each(function () {
			setRowSelected($(this), true);
		});
		updateTotals();
	});
	wrapper.on("click", ".essdee-wo-unselect-all", () => {
		wrapper.find("tr[data-matrix-row]").each(function () {
			setRowSelected($(this), false);
		});
		updateTotals();
	});
	updateTotals();
}

// Non-blocking (production_api stance): over-balance warns, never blocks —
// knitting can legitimately over-deliver. Knitting and dyeing check the
// per-dia SUM of the dialog's own inputs (colours share one dia's balance).
function warn_balance_overshoot(ctx, manifest, values) {
	const overs = [];
	ctx.rows.forEach((row, i) => {
		const fields = manifest.filter((m) => m.row === i);
		if (row.kind === "knitting" || row.kind === "dyeing") {
			const per_dia = {};
			const limit_label = row.kind === "knitting" ? __("balance") : __("previous stage available");
			fields.forEach((m) => {
				const dia = m.reference_item_variant || (m.out_attrs || {}).Dia || m.label;
				const limit = row.kind === "knitting" ? m.balance : m.available;
				if (!per_dia[dia]) per_dia[dia] = { sum: 0, limit };
				per_dia[dia].sum += flt(values[m.fieldname]) || 0;
			});
			Object.entries(per_dia).forEach(([dia, agg]) => {
				if (agg.limit != null && agg.sum > agg.limit + 0.001) {
					overs.push(`${row.cloth_item} · ${dia}: ${agg.sum} > ${limit_label} ${agg.limit}`);
				}
			});
		} else if (row.kind === "compacting") {
			fields.forEach((m) => {
				const qty = flt(values[m.fieldname]);
				if (qty && m.available != null && qty > m.available + 0.001) {
					overs.push(`${row.cloth_item} · ${m.label}: ${qty} > ${__("previous stage available")} ${m.available}`);
				}
			});
		}
	});
	if (overs.length) {
		frappe.show_alert({
			message: __("Exceeds balance:") + "<br>"
				+ overs.map((o) => frappe.utils.escape_html(o)).join("<br>"),
			indicator: "orange",
		}, 8);
	}
}

// The IPD derives every attribute; the user only enters quantities. Every
// input posts its matrix-group key so the server never resolves groups by
// attrs. Legacy knitting renders one column per physical output colour
// WO, 2026-07-04) — each (dia × colour) input becomes its own entry line.
const MAX_COLOUR_COLUMNS = 6;

function render_fabric_dialog(frm, ctx) {
	const fields = [];
	// one record per qty input: drives collection, yarn total, overshoot check
	const manifest = [];
	let d = null;

	const recompute_yarn = (i) => {
		const row = ctx.rows[i];
		let total = 0;
		manifest.forEach((m) => {
			if (m.row === i) total += flt(d.get_value(m.fieldname)) || 0;
		});
		const total_yarn = row.ratio ? total / row.ratio : total;
		const yarns = row.yarns || [];
		if (yarns.length > 1) {
			yarns.forEach((yarn, yi) => {
				const qty = total_yarn * flt(yarn.ratio) / 100;
				d.set_value(`yarn_qty_${i}_${yi}`, Math.round(qty * 1000) / 1000);
			});
			return;
		}
		d.set_value(`yarn_qty_${i}`, Math.round(total_yarn * 1000) / 1000);
	};

	ctx.rows.forEach((row, i) => {
		fields.push({ fieldtype: "Section Break", label: `${row.cloth_item} (${row.production_detail})` });
		if (row.kind === "identity" && row.treated_item && row.treated_item !== row.cloth_item) {
			fields.push({
				fieldtype: "HTML",
				options: `<div class="text-muted small">${__("Item")}: <b>${frappe.utils.escape_html(row.treated_item)}</b></div>`,
			});
		}
		if (row.kind === "conversion" && row.input_item) {
			// Rule-based conversion (Consume/Introduce): say what gets consumed —
			// each qty row below is one "consumed combo → produced combo" rule.
			fields.push({
				fieldtype: "HTML",
				options: `<div class="text-muted small">${__("Consumes")}: <b>${frappe.utils.escape_html(row.input_item)}</b> &rarr; ${__("produces")} <b>${frappe.utils.escape_html(row.cloth_item)}</b></div>`,
			});
		}

		const colour_options = row.colour_options || [];
		const reference_routed = Boolean(row.reference_routed);
		const multi_colour = row.kind === "knitting" && !reference_routed && row.has_colour
			&& colour_options.length > 0 && colour_options.length <= MAX_COLOUR_COLUMNS;
		const needs_colour_picker = row.kind === "knitting" && row.has_colour
			&& !multi_colour
			&& (!reference_routed || (row.qty_rows || []).some((qr) => !qr.knit_colour));

		if (row.kind === "knitting") {
			if (needs_colour_picker) {
				// too many colour choices for columns — single-colour fallback
				fields.push({
					fieldtype: "Link", label: __("Cloth Colour"), fieldname: `colour_${i}`,
					options: "YRP Item Attribute Value",
					default: row.greige_colour || undefined,
					get_query: () => {
						if (colour_options.length) {
							return { filters: { name: ["in", colour_options] } };
						}
						return row.colour_mapping
							? {
								query: "essdee_yrp.ipd_ui.get_attribute_detail_values",
								filters: { mapping: row.colour_mapping },
							}
							: { filters: { attribute_name: "Colour" } };
					},
				});
			}
		}

		if (multi_colour) {
			// Legacy route: one column per physical knitting-output colour.
			fields.push({ fieldtype: "Section Break" });
			colour_options.forEach((colour, ci) => {
				if (ci > 0) fields.push({ fieldtype: "Column Break" });
				fields.push({
					fieldtype: "HTML",
					options: `<div style="font-weight:600;margin-bottom:4px;">${frappe.utils.escape_html(colour)}</div>`,
				});
				(row.qty_rows || []).forEach((qr, j) => {
					const fieldname = `qty_${i}_${j}_c${ci}`;
					const is_default_output = colour === row.greige_colour;
					fields.push({
						fieldtype: "Float", label: qr.label, fieldname,
						default: is_default_output && qr.prefill ? qr.prefill : undefined,
						onchange: () => recompute_yarn(i),
					});
					manifest.push({
						fieldname, row: i, key: qr.key, out_attrs: qr.out_attrs,
						colour, label: qr.label, balance: qr.balance, available: qr.available,
					});
				});
			});
			fields.push({ fieldtype: "Section Break" });
		} else {
			const qty_rows = row.qty_rows || [];
			// The manifest entry is IDENTICAL in both layouts (fieldname keeps the
			// original qty_rows index j) — only the visual arrangement differs, so
			// the primary_action payload is unchanged.
			const push_qty_field = (qr, j, label) => {
				const fieldname = `qty_${i}_${j}`;
				fields.push({
					fieldtype: "Float", label, fieldname,
					default: qr.prefill || undefined,
					onchange: row.kind === "knitting" ? () => recompute_yarn(i) : undefined,
				});
				manifest.push({
					fieldname, row: i, key: qr.key, out_attrs: qr.out_attrs,
					colour: qr.knit_colour || null,
					label: qr.label,
					balance: qr.balance,
					available: qr.available,
					reference_item_variant: qr.reference_item_variant || null,
				});
			};

			// Colour-section layout (2026-07-08): big multi-row popups group by the
			// server's `section` (the Colour part of each rule) with the short
			// `row_label` (the Dia part) on each input. Never for the knitting
			// branch above, never for small/flat lists.
			const sections = [];
			const by_section = {};
			qty_rows.forEach((qr, j) => {
				const key = qr.section == null ? "null" : String(qr.section);
				if (!by_section[key]) {
					by_section[key] = { name: qr.section, items: [] };
					sections.push(by_section[key]);
				}
				by_section[key].items.push([qr, j]);
			});
			const sectionable = (
				["conversion", "dyeing", "compacting", "identity"].includes(row.kind)
				|| reference_routed
			)
				&& (reference_routed || qty_rows.length > 6)
				&& sections.length > 1
				&& qty_rows.every((qr) => qr.section != null);

			if (sectionable) {
				const as_columns = sections.length <= MAX_COLOUR_COLUMNS;
				if (as_columns) fields.push({ fieldtype: "Section Break" });
				sections.forEach((sec, si) => {
					if (as_columns && si > 0) fields.push({ fieldtype: "Column Break" });
					if (!as_columns) fields.push({ fieldtype: "Section Break" });
					fields.push({
						fieldtype: "HTML",
						options: `<div style="font-weight:600;margin-bottom:4px;">${frappe.utils.escape_html(sec.name)}</div>`,
					});
					sec.items.forEach(([qr, j]) => push_qty_field(qr, j, qr.row_label || qr.label));
				});
				if (as_columns) fields.push({ fieldtype: "Section Break" });
			} else {
				qty_rows.forEach((qr, j) => push_qty_field(qr, j, qr.label));
			}
		}

		if (row.kind === "knitting" && !reference_routed && (row.yarns || []).length <= 1) {
			fields.push({
				fieldtype: "Float", label: __("Yarn (deliverable) Kg"), fieldname: `yarn_qty_${i}`,
			});
		} else if (row.kind === "knitting" && !reference_routed) {
			fields.push({
				fieldtype: "Section Break",
				label: __("Calculated Yarn Deliverables"),
			});
			(row.yarns || []).forEach((yarn, yi) => {
				fields.push({
					fieldtype: "Float",
					label: `${yarn.yarn_item} (${flt(yarn.ratio, 3)}%)`,
					fieldname: `yarn_qty_${i}_${yi}`,
					read_only: 1,
				});
			});
		}
	});

	d = new frappe.ui.Dialog({
		title: __("Calculate Fabric Deliverables — {0}", [frm.doc.process_name]),
		size: "large",
		fields,
		primary_action_label: __("Calculate"),
		primary_action(values) {
			const rows = [];
			let missing_colour = null;
			ctx.rows.forEach((row, i) => {
				const entries = [];
				manifest.forEach((m) => {
					if (m.row !== i) return;
					const qty = flt(values[m.fieldname]);
					if (!qty || qty <= 0) return;
					const line = { key: m.key, out_attrs: m.out_attrs, qty };
					if (m.colour) line.colour = m.colour;
					entries.push(line);
				});
				if (!entries.length) return;
				const fallback_colour = values[`colour_${i}`] || null;
				if (row.kind === "knitting" && row.has_colour) {
					if (entries.some((line) => !line.colour) && !fallback_colour) {
						missing_colour = row.cloth_item;
						return;
					}
				}
				rows.push({
					fabric_row: row.fabric_row,
					colour: fallback_colour,
					yarn_qty: !row.reference_routed && (row.yarns || []).length <= 1
						? values[`yarn_qty_${i}`] || null
						: null,
					entries,
				});
			});
			if (missing_colour) {
				frappe.msgprint(__("Select the cloth Colour for {0}.", [missing_colour]));
				return;
			}
			if (!rows.length) {
				frappe.msgprint(__("Enter a quantity for at least one row."));
				return;
			}
			warn_balance_overshoot(ctx, manifest, values);
			frappe.call({
				method: "essdee_yrp.api.work_order.calculate_fabric_deliverables",
				args: { work_order: frm.doc.name, rows },
				freeze: true,
				callback(res) {
					d.hide();
					const m = res.message || {};
					frappe.show_alert({
						message: __("Calculated {0} deliverable(s) and {1} receivable(s).", [m.deliverables, m.receivables]),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
	// Pre-filled balances must reflect in the auto yarn figure immediately,
	// not only after the first manual edit.
	ctx.rows.forEach((row, i) => {
		if (row.kind === "knitting") recompute_yarn(i);
	});
}
