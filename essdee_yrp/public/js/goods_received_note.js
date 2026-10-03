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
	against_id(frm) {
		if (frm.doc.against === "Work Order" && frm.doc.against_id) {
			setTimeout(() => essdee_yrp.configure_actual_dia_button(frm), 0);
		}
	},
});

essdee_yrp.configure_actual_dia_button = function (frm) {
	frm._essdee_actual_dia = null;
	if (
		frm.doc.against !== "Work Order"
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
			// Every standard fabric GRN records the actual physical receipt. The
			// Work Order plan remains visible as Pending/Allowed, but it is not an
			// input cap; normal Stock validation remains authoritative on submit.
			essdee_yrp.mount_physical_grn_editor(frm);
			if (!r.message?.enabled || !(r.message.dia_options || []).length) return;
			frm._essdee_actual_dia = r.message;
			if (frm.doc.docstatus === 0) {
				frm.add_custom_button(
					__("Add Actual Dia"),
					() => essdee_yrp.open_actual_dia_dialog(frm),
					__("Actual Dia"),
				);
			}
		},
	});
};

essdee_yrp.mount_physical_grn_editor = function (frm) {
	if (!frm.itemEditor || !frappe.yrp?.work_order?.ItemEditor || !frm.fields_dict.item_html) return;
	const data = essdee_yrp.compact_physical_grn_groups(frm.itemEditor.get_items() || []);
	frm.itemEditor.app.unmount();
	$(frm.fields_dict.item_html.wrapper).empty();
	frm.itemEditor = new frappe.yrp.work_order.ItemEditor(
		frm.fields_dict.item_html.wrapper,
		{
			title: frm.doc.is_return ? __("Return Items") : __("Receive Items"),
			editorType: "goods_received_note",
			sourceType: frm.doc.against || "Work Order",
			showDimensions: true,
			allowCreate: false,
			allowEdit: false,
			allowRemove: false,
			returnMode: Boolean(frm.doc.is_return),
			allowExcess: true,
			aggregatePhysicalRows: true,
		},
	);
	frm.itemEditor.load_data(data);
	frm.itemEditor.update_status();
};

essdee_yrp.compact_physical_grn_groups = function (groups) {
	const canonical = (value) => {
		if (Array.isArray(value)) return value.map(canonical);
		if (!value || typeof value !== "object") return value;
		return Object.fromEntries(
			Object.keys(value).sort().map((key) => [key, canonical(value[key])]),
		);
	};
	const physical = JSON.parse(JSON.stringify(groups || []));
	for (const group of physical) {
		const buckets = new Map();
		for (const entry of group.items || []) {
			const dimensions = Object.fromEntries(
				Object.entries(entry.dimensions || {}).filter(([key]) => key !== "received_type"),
			);
			const identity = JSON.stringify(canonical({
				name: entry.name,
				dimensions,
				attributes: entry.attributes || {},
				set_combination: entry.set_combination || {},
				columns: Object.keys(entry.values || {}).sort(),
			}));
			const type = entry.dimensions?.received_type || "";
			const key = `${identity}::${type}`;
			if (!buckets.has(key)) buckets.set(key, { identity, entries: [] });
			buckets.get(key).entries.push(entry);
		}
		const byIdentity = new Map();
		for (const { identity, entries } of buckets.values()) {
			const entry = entries[0];
			for (const valueKey of Object.keys(entry.values || {})) {
				const details = entries.map((candidate) => candidate.values?.[valueKey]).filter(Boolean);
				entry.values[valueKey].qty = flt(
					details.reduce((sum, detail) => sum + flt(detail.qty), 0), 3,
				);
				for (const fieldname of ["pending_quantity", "max_receivable_quantity"]) {
					if (details.some((detail) => detail[fieldname] != null)) {
						entry.values[valueKey][fieldname] = flt(
							details.reduce((sum, detail) => sum + flt(detail[fieldname]), 0), 3,
						);
					}
				}
			}
			entry.comments = entries.find((candidate) => candidate.comments)?.comments || "";
			if (!byIdentity.has(identity)) byIdentity.set(identity, []);
			byIdentity.get(identity).push(entry);
		}
		group.items = [];
		for (const entries of byIdentity.values()) {
			const positive = entries.filter((entry) => Object.values(entry.values || {}).some(
				(detail) => flt(detail.qty) > 0,
			));
			group.items.push(...(positive.length ? positive : entries.slice(0, 1)));
		}
	}
	return physical;
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
			if (quantity <= 0) frappe.throw(__("Enter a quantity greater than zero."));
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
				? `<div class="alert alert-info mb-0">${__("Planned remaining quantity")}: <b>${format_number(remaining)}</b> · ${__("excess receipt is allowed")}</div>`
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
