frappe.ui.form.on("Goods Received Note", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
		essdee_yrp.configure_actual_dia_button(frm);
		if (
			frm.doc.docstatus === 1
			&& frm.doc.against === "Work Order"
			&& !frm.doc.is_return
			&& !frm.doc.mrp_stock_entry_created
		) {
			frm.add_custom_button(__("Create Stock in MRP"), () => {
				frappe.confirm(
					__(
						"Transfer this GRN's finished-cloth stock to MRP? "
						+ "This creates a Material Issue in YRP and a Material Receipt in MRP."
					),
					() => frappe.call({
						method: "essdee_yrp.api.mrp_stock_transfer.create_mrp_stock",
						args: { grn_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Creating MRP Stock"),
						callback: (r) => {
							if (r.message?.ok) {
								frappe.msgprint({
									title: __("Transferred"),
									indicator: "green",
									message: __("MRP Stock Entry {0}", [r.message.mrp_stock_entry]),
								});
								frm.reload_doc();
							}
						},
					})
				);
			});
		}
	},
	validate(frm) {
		essdee_yrp.validate_actual_dia_pool(frm);
	},
});

essdee_yrp.configure_actual_dia_button = function (frm) {
	frm._essdee_actual_dia = null;
	if (
		frm.doc.docstatus !== 0
		|| frm.doc.against !== "Work Order"
		|| !frm.doc.against_id
		|| frm.doc.is_return
		|| frm.doc.is_rework
		|| frm.doc.additional_grn
		|| frm.doc.includes_packing
	) return;

	frappe.call({
		method: "essdee_yrp.fabric_grn.get_actual_dia_context",
		args: { work_order: frm.doc.against_id },
		callback(r) {
			if (!r.message?.enabled || !(r.message.dia_options || []).length) return;
			frm._essdee_actual_dia = r.message;
			frm.add_custom_button(
				__("Add Actual Dia"),
				() => essdee_yrp.open_actual_dia_dialog(frm),
				__("Actual Dia"),
			);
		},
	});
};

essdee_yrp.open_actual_dia_dialog = function (frm) {
	if (!frm.itemEditor || !frm._essdee_actual_dia?.enabled) {
		frappe.msgprint(__("Load the Work Order receivables first."));
		return;
	}
	const groups = frm.itemEditor.get_items() || [];
	const sources = essdee_yrp.actual_dia_sources(groups);
	if (!sources.length) {
		frappe.msgprint(__("No pending Work Order receivable is available."));
		return;
	}
	const byLabel = new Map(sources.map((source) => [source.label, source]));
	const dialog = new frappe.ui.Dialog({
		title: __("Add Actual Dia Receipt"),
		fields: [
			{
				fieldtype: "Select",
				fieldname: "source",
				label: __("Work Order Receivable"),
				options: sources.map((source) => source.label),
				reqd: 1,
			},
			{
				fieldtype: "Select",
				fieldname: "dia",
				label: __("Actual Dia"),
				options: frm._essdee_actual_dia.dia_options,
				reqd: 1,
			},
			{
				fieldtype: "Float",
				fieldname: "qty",
				label: __("Received Quantity"),
				precision: 3,
				reqd: 1,
			},
			{
				fieldtype: "HTML",
				fieldname: "availability",
			},
		],
		primary_action_label: __("Add Dia Row"),
		primary_action(values) {
			const source = byLabel.get(values.source);
			if (!source) frappe.throw(__("Select a Work Order receivable."));
			const quantity = flt(values.qty);
			const remaining = essdee_yrp.actual_dia_remaining(groups, source.reference);
			if (quantity <= 0) frappe.throw(__("Enter a quantity greater than zero."));
			if (quantity > remaining + 0.0001) {
				frappe.throw(
					__("Only {0} remains for this Work Order receivable.", [remaining]),
				);
			}
			if (essdee_yrp.actual_dia_exists(groups, source.reference, values.dia)) {
				frappe.throw(
					__("{0} already exists for this receivable. Enter its quantity in the table.", [values.dia]),
				);
			}

			const clone = JSON.parse(JSON.stringify(source.entry));
			clone.attributes = { ...(clone.attributes || {}), Dia: values.dia };
			clone.comments = "";
			delete clone.row_index;
			delete clone.table_index;
			clone.values = {};
			for (const [key, detail] of Object.entries(source.entry.values || {})) {
				clone.values[key] = { ...detail, qty: key === source.valueKey ? quantity : 0 };
			}
			source.group.items.push(clone);
			frm.itemEditor.load_data(groups);
			frm.doc.item_details = JSON.stringify(groups);
			frm.dirty();
			dialog.hide();
		},
	});

	const updateAvailability = () => {
		const source = byLabel.get(dialog.get_value("source"));
		const remaining = source
			? essdee_yrp.actual_dia_remaining(groups, source.reference)
			: 0;
		const wrapper = dialog.fields_dict.availability.$wrapper;
		wrapper.html(
			source
				? `<div class="alert alert-info mb-0">${__("Remaining receivable quantity")}: <b>${format_number(remaining)}</b></div>`
				: "",
		);
	};
	dialog.fields_dict.source.df.onchange = updateAvailability;
	dialog.set_value("source", sources[0].label);
	dialog.set_value(
		"dia",
		frm._essdee_actual_dia.dia_options.find(
			(dia) => !essdee_yrp.actual_dia_exists(groups, sources[0].reference, dia),
		) || "",
	);
	dialog.set_value("qty", essdee_yrp.actual_dia_remaining(groups, sources[0].reference));
	updateAvailability();
	dialog.show();
};

essdee_yrp.actual_dia_sources = function (groups) {
	const byReference = new Map();
	let sequence = 0;
	for (const group of groups || []) {
		for (const entry of group.items || []) {
			for (const [valueKey, detail] of Object.entries(entry.values || {})) {
				const reference = detail.ref_docname || entry.ref_docname;
				if (!reference || byReference.has(reference)) continue;
				const attrs = Object.values(entry.attributes || {}).filter(Boolean).join(" · ");
				const label = `${++sequence}. ${entry.name}${attrs ? ` · ${attrs}` : ""}`;
				byReference.set(reference, { group, entry, valueKey, reference, label });
			}
		}
	}
	return Array.from(byReference.values());
};

essdee_yrp.actual_dia_cells = function (groups, reference) {
	const cells = [];
	for (const group of groups || []) {
		for (const entry of group.items || []) {
			for (const [valueKey, detail] of Object.entries(entry.values || {})) {
				if ((detail.ref_docname || entry.ref_docname) === reference) {
					cells.push({ entry, valueKey, detail });
				}
			}
		}
	}
	return cells;
};

essdee_yrp.actual_dia_remaining = function (groups, reference) {
	const cells = essdee_yrp.actual_dia_cells(groups, reference);
	const allowed = Math.max(
		0,
		...cells.map(({ detail }) => flt(
			detail.max_receivable_quantity ?? detail.pending_quantity ?? 0,
		)),
	);
	const used = cells.reduce((total, { detail }) => total + flt(detail.qty), 0);
	return Math.max(flt(allowed - used, 3), 0);
};

essdee_yrp.actual_dia_exists = function (groups, reference, dia) {
	return essdee_yrp.actual_dia_cells(groups, reference).some(
		({ entry }) => (entry.attributes || {}).Dia === dia,
	);
};

essdee_yrp.validate_actual_dia_pool = function (frm) {
	if (!frm._essdee_actual_dia?.enabled || !frm.itemEditor) return;
	const groups = frm.itemEditor.get_items() || [];
	const references = new Set(
		essdee_yrp.actual_dia_sources(groups).map((source) => source.reference),
	);
	for (const reference of references) {
		const cells = essdee_yrp.actual_dia_cells(groups, reference);
		const allowed = Math.max(
			0,
			...cells.map(({ detail }) => flt(
				detail.max_receivable_quantity ?? detail.pending_quantity ?? 0,
			)),
		);
		const total = cells.reduce((sum, { detail }) => sum + flt(detail.qty), 0);
		if (total > allowed + 0.0001) {
			frappe.throw(
				__("Actual Dia split total {0} exceeds the allowed quantity {1}.", [total, allowed]),
			);
		}
	}
};
