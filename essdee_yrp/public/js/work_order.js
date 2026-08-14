frappe.ui.form.on("Work Order", {
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
		}, 0);
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Calculate Fabric Deliverables"), () => open_fabric_calculate(frm));
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
		update_work_order_header_controls(frm);
		if (!frm.doc.lot || !frm.doc.process_name) return;

		const r = await frappe.call({
			method: "essdee_yrp.api.work_order.get_work_order_selection_context",
			args: { lot: frm.doc.lot, process_name: frm.doc.process_name },
		});
		if (request_id !== frm._work_order_selection_request) return;

		const context = r.message || {};
		frm._work_order_selection_options = context.options || [];
		frm._work_order_item_options = context.item_options || [];

		if (frm.doc.docstatus === 0) {
			if (context.auto_item) {
				await set_if_changed(frm, "item", context.auto_item);
				await set_if_changed(
					frm, "production_detail", context.auto_production_detail || ""
				);
			} else if (
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
	},
});

function update_work_order_header_controls(frm) {
	const draft = frm.doc.docstatus === 0;
	const has_process = Boolean(frm.doc.process_name);
	const has_context = has_process && Boolean(frm.doc.lot);
	const items = frm._work_order_item_options || [];
	frm.toggle_enable("lot", draft && has_process);
	frm.toggle_enable("item", draft && has_context && items.length > 1);
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
				aggregateRouteFields: [
					"fabric_reference_variant",
					"fabric_reference_allocations",
				],
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
					options: "Item Attribute Value",
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
