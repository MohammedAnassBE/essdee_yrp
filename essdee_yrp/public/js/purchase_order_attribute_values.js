const PO_ATTRIBUTE_METHOD = "essdee_yrp.purchase_order_attribute_values";

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (
			frm.is_new() ||
			frm.doc.docstatus !== 1 ||
			!frm.doc.is_yrp_managed ||
			!frappe.user.has_role("System Manager")
		) {
			return;
		}
		frappe
			.xcall(`${PO_ATTRIBUTE_METHOD}.can_update_purchase_order_attribute_values`, { name: frm.doc.name })
			.then((allowed) => {
				if (allowed) frm.add_custom_button(__("Update Attribute Values"), () => open_po_attribute_dialog(frm));
			});
	},
});

function po_attribute_fieldname(row, attribute) {
	return `${row.name}__${frappe.scrub(attribute)}`;
}

function po_attribute_dialog_fields(rows) {
	const fields = [];
	for (const row of rows) {
		fields.push({
			fieldtype: "Section Break",
			label: __("Row #{0}: {1}", [row.idx, row.item_code]),
		});
		fields.push({
			fieldtype: "HTML",
			fieldname: `${row.name}__summary`,
			options: `<div class="text-muted small">${__("Qty")}: ${frappe.format(row.qty, { fieldtype: "Float" })} ${frappe.utils.escape_html(row.uom || "")} · ${__("Rate")}: ${frappe.format(row.rate, { fieldtype: "Currency" })} · ${__("Amount")}: ${frappe.format(row.amount, { fieldtype: "Currency" })}</div>`,
		});
		for (const entry of row.attributes) {
			fields.push({
				fieldtype: entry.options.length ? "Autocomplete" : "Data",
				fieldname: po_attribute_fieldname(row, entry.attribute),
				label: entry.attribute,
				options: entry.options,
				default: entry.value,
				reqd: 1,
				read_only: entry.editable ? 0 : 1,
			});
		}
	}
	return fields;
}

function po_attribute_changes(rows, values) {
	const changes = [];
	for (const row of rows) {
		const attributes = {};
		for (const entry of row.attributes) {
			const value = values[po_attribute_fieldname(row, entry.attribute)];
			if (entry.editable && value !== entry.value) attributes[entry.attribute] = value;
		}
		if (Object.keys(attributes).length) {
			changes.push({ name: row.name, item_code: row.item_code, qty: row.qty, attributes });
		}
	}
	return changes;
}

async function open_po_attribute_dialog(frm) {
	const data = await frappe.xcall(`${PO_ATTRIBUTE_METHOD}.get_purchase_order_attribute_rows`, {
		name: frm.doc.name,
	});
	const rows = (data.rows || []).filter((row) => row.attributes.length);
	if (!rows.length) {
		frappe.msgprint(__("No item row on this Purchase Order has variant attributes."));
		return;
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Update Attribute Values"),
		size: "large",
		fields: po_attribute_dialog_fields(rows),
		primary_action_label: __("Save"),
		async primary_action(values) {
			const changes = po_attribute_changes(rows, values);
			if (!changes.length) {
				dialog.hide();
				return;
			}
			await frappe.xcall(
				`${PO_ATTRIBUTE_METHOD}.update_purchase_order_attribute_values`,
				{ name: frm.doc.name, rows: changes },
				"POST",
				{ freeze: true },
			);
			dialog.hide();
			frappe.show_alert({ message: __("Attribute values updated"), indicator: "green" });
			frm.reload_doc();
		},
	});
	dialog.show();
}
