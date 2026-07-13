frappe.ui.form.on("Work Order", {
	setup(frm) {
		// Cloth process + lot selected -> the Item link offers ONLY the Lot's
		// fabric cloths; otherwise the standard full Item list.
		frm.set_query("item", () => {
			if (frm._fabric_cloth_items && frm._fabric_cloth_items.length) {
				return { filters: { name: ["in", frm._fabric_cloth_items] } };
			}
			return {};
		});
	},
	refresh(frm) {
		frm.trigger("apply_lot_item_behaviour");
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Calculate Fabric Deliverables"), () => open_fabric_calculate(frm));
	},
	lot(frm) {
		frm.trigger("apply_lot_item_behaviour");
	},
	process_name(frm) {
		frm.trigger("apply_lot_item_behaviour");
	},
	async apply_lot_item_behaviour(frm) {
		frm._fabric_cloth_items = null;
		if (!frm.doc.lot || !frm.doc.process_name) return;

		const proc = await frappe.db.get_value("Process", frm.doc.process_name, "is_cloth_process");
		if (proc && proc.message && proc.message.is_cloth_process) {
			// Cloth process: DON'T pre-fill — filter the Item to the Lot's fabrics.
			// Child tables can't be queried via client get_list in v16 —
			// dedicated whitelisted endpoint instead.
			const r = await frappe.call({
				method: "essdee_yrp.api.work_order.get_lot_fabric_items",
				args: { lot: frm.doc.lot },
			});
			frm._fabric_cloth_items = r.message || [];
			// mutate only drafts — a submitted WO whose item left the fabric
			// list must never be blanked into an unsaveable dirty form
			if (frm.doc.docstatus === 0) {
				if (frm.doc.item && !frm._fabric_cloth_items.includes(frm.doc.item)) {
					frm.set_value("item", "");
				}
				if (!frm._fabric_cloth_items.length) {
					frappe.show_alert({
						message: __("Lot {0} has no fabric rows — add them on the Lot first.", [frm.doc.lot]),
						indicator: "orange",
					});
				}
			}
		} else if (frm.doc.docstatus === 0) {
			// Standard process: pre-fill the Item from the Lot (production_api behaviour).
			const lot = await frappe.db.get_value("Lot", frm.doc.lot, "item");
			if (lot && lot.message && lot.message.item && frm.doc.item !== lot.message.item) {
				frm.set_value("item", lot.message.item);
			}
		}
	},
});

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

// One planning line under each qty input. null/undefined figures are hidden
// (e.g. "available" on bought-greige lots where knitting isn't managed).
function planning_description(kind, qr) {
	const kg = (v) => `${flt(v, 3)} kg`;
	const parts = [];
	if (kind === "knitting") {
		parts.push(`${__("Program")} ${kg(qr.program)}`);
		if (flt(qr.received)) parts.push(`${__("Received")} ${kg(qr.received)}`);
		parts.push(`${__("Ordered")} ${kg(qr.ordered)}`);
		parts.push(`${__("Balance")} ${kg(qr.balance)}`);
	} else if (kind === "dyeing" || kind === "compacting" || kind === "conversion") {
		if (flt(qr.plan)) parts.push(`${__("Plan")} ${kg(qr.plan)}`);
		parts.push(`${__("Ordered")} ${kg(qr.ordered)}`);
		if (qr.available != null) parts.push(`${__("Previous stage available")} ${kg(qr.available)}`);
	}
	return parts.length ? parts.join(" · ") : undefined;
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
			const limit_label = row.kind === "knitting" ? __("balance") : __("greige available");
			fields.forEach((m) => {
				const dia = (m.out_attrs || {}).Dia || m.label;
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
					overs.push(`${row.cloth_item} · ${m.label}: ${qty} > ${__("dyed available")} ${m.available}`);
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
// attrs. Knitting renders one COLUMN PER GREIGE COLOUR (multiple colours per
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
		const yarn = row.ratio ? total / row.ratio : total;
		d.set_value(`yarn_qty_${i}`, Math.round(yarn * 1000) / 1000);
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
		const multi_colour = row.kind === "knitting" && row.has_colour
			&& colour_options.length > 0 && colour_options.length <= MAX_COLOUR_COLUMNS;

		if (row.kind === "knitting") {
			fields.push({
				fieldtype: "HTML",
				options: `<div class="text-muted small">${__("Yarn")}: <b>${frappe.utils.escape_html(row.yarn_item || "")}</b>
					&nbsp;·&nbsp; 1 kg ${__("yarn")} &rarr; ${row.ratio} kg ${__("cloth")}</div>`,
			});
			if (row.has_colour && !multi_colour) {
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
			// one column per greige colour, one input per dia inside each
			fields.push({ fieldtype: "Section Break" });
			colour_options.forEach((colour, ci) => {
				if (ci > 0) fields.push({ fieldtype: "Column Break" });
				fields.push({
					fieldtype: "HTML",
					options: `<div style="font-weight:600;margin-bottom:4px;">${frappe.utils.escape_html(colour)}</div>`,
				});
				(row.qty_rows || []).forEach((qr, j) => {
					const fieldname = `qty_${i}_${j}_c${ci}`;
					const is_greige = colour === row.greige_colour;
					fields.push({
						fieldtype: "Float", label: qr.label, fieldname,
						default: is_greige && qr.prefill ? qr.prefill : undefined,
						description: ci === 0 ? planning_description(row.kind, qr) : undefined,
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
					description: planning_description(row.kind, qr),
					onchange: row.kind === "knitting" ? () => recompute_yarn(i) : undefined,
				});
				manifest.push({
					fieldname, row: i, key: qr.key, out_attrs: qr.out_attrs,
					colour: null, label: qr.label, balance: qr.balance, available: qr.available,
				});
			};

			// Colour-section layout (2026-07-08): big multi-row popups group by the
			// server's `section` (the Colour part of each rule) with the short
			// `row_label` (the Dia part) on each input. Never for the knitting
			// branch above, never for small/flat lists.
			const sections = [];
			const by_section = {};
			qty_rows.forEach((qr, j) => {
				const key = qr.section == null ? " null" : String(qr.section);
				if (!by_section[key]) {
					by_section[key] = { name: qr.section, items: [] };
					sections.push(by_section[key]);
				}
				by_section[key].items.push([qr, j]);
			});
			const sectionable = ["conversion", "dyeing", "compacting", "identity"].includes(row.kind)
				&& qty_rows.length > 6
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

		if (row.kind === "knitting") {
			fields.push({
				fieldtype: "Float", label: __("Yarn (deliverable) Kg"), fieldname: `yarn_qty_${i}`,
				description: __("Auto: total cloth ÷ {0}. Edit only if reality differs.", [row.ratio]),
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
					yarn_qty: values[`yarn_qty_${i}`] || null,
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
