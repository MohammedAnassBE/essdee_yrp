frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Calculate Fabric Deliverables"), () => open_fabric_calculate(frm));
	},
});

function open_fabric_calculate(frm) {
	frappe.call({
		method: "essdee_yrp.api.work_order.get_fabric_deliverable_context",
		args: { work_order: frm.doc.name },
		callback(r) {
			const ctx = r.message || {};
			if (!ctx.is_fabric_process) {
				frappe.msgprint(__("{0} is not a fabric process for this Lot's fabrics.", [frm.doc.process_name || ""]));
				return;
			}
			render_fabric_dialog(frm, ctx);
		},
	});
}

function render_fabric_dialog(frm, ctx) {
	const fields = [];
	ctx.rows.forEach((row, i) => {
		fields.push({ fieldtype: "Section Break", label: `${row.cloth_item} (${row.production_detail})` });
		if (row.kind === "knitting") {
			fields.push({ fieldtype: "HTML", options: `<div class="text-muted small">${__("Yarn")}: ${frappe.utils.escape_html(row.yarn_item || "")}</div>` });
			(row.yarn_attributes || []).forEach((attr) => {
				fields.push({
					fieldtype: "Select", label: `${attr} (${__("yarn")})`, fieldname: `attr_${i}_${attr}`, reqd: 1,
					options: [""].concat((row.attribute_options || {})[attr] || []).join("\n"),
				});
			});
			fields.push({
				fieldtype: "Select", label: __("Cloth Dia"), fieldname: `target_dia_${i}`, reqd: 1,
				options: [""].concat(row.dia_options || []).join("\n"),
			});
			// create_variant needs EVERY cloth attribute -> collect the non-Dia ones too
			(row.cloth_attributes || []).filter((a) => a !== "Dia").forEach((attr) => {
				fields.push({
					fieldtype: "Select", label: `${attr} (${__("cloth")})`, fieldname: `cloth_attr_${i}_${attr}`, reqd: 1,
					options: [""].concat((row.attribute_options || {})[attr] || []).join("\n"),
				});
			});
		} else {
			(row.cloth_attributes || []).forEach((attr) => {
				const restrict = (row.kind === "dyeing" && attr === "Colour") ? row.colour_from_options
					: (row.kind === "compacting" && attr === "Dia") ? row.dia_from_options
					: (row.attribute_options || {})[attr];
				fields.push({
					fieldtype: "Select", label: attr, fieldname: `attr_${i}_${attr}`, reqd: 1,
					options: [""].concat(restrict || []).join("\n"),
				});
			});
		}
		fields.push({ fieldtype: "Float", label: __("Weight (deliverable qty)"), fieldname: `weight_${i}` });
	});

	const d = new frappe.ui.Dialog({
		title: __("Calculate Fabric Deliverables — {0}", [frm.doc.process_name]),
		fields,
		primary_action_label: __("Calculate"),
		primary_action(values) {
			const rows = [];
			ctx.rows.forEach((row, i) => {
				const weight = values[`weight_${i}`];
				if (!weight || weight <= 0) return;
				const attrs = {};
				const attr_list = row.kind === "knitting" ? row.yarn_attributes : row.cloth_attributes;
				(attr_list || []).forEach((attr) => {
					const v = values[`attr_${i}_${attr}`];
					if (v) attrs[attr] = v;
				});
				const cloth_attrs = {};
				if (row.kind === "knitting") {
					(row.cloth_attributes || []).filter((a) => a !== "Dia").forEach((attr) => {
						const v = values[`cloth_attr_${i}_${attr}`];
						if (v) cloth_attrs[attr] = v;
					});
				}
				rows.push({
					fabric_row: row.fabric_row,
					weight,
					attribute_values: attrs,
					cloth_attribute_values: cloth_attrs,
					target_dia: values[`target_dia_${i}`] || null,
				});
			});
			if (!rows.length) {
				frappe.msgprint(__("Enter a weight for at least one fabric."));
				return;
			}
			frappe.call({
				method: "essdee_yrp.api.work_order.calculate_fabric_deliverables",
				args: { work_order: frm.doc.name, rows },
				freeze: true,
				callback(res) {
					d.hide();
					const m = res.message || {};
					frappe.show_alert({ message: __("Calculated {0} deliverable(s) and {1} receivable(s).", [m.deliverables, m.receivables]), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}
