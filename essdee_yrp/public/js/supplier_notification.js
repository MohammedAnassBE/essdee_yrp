frappe.provide("essdee_yrp");

// Send-SMS-to-supplier dialog (MSG91 template-id path). A DocType can have
// several configured templates in YRP SMS Settings; the user picks one, then
// for each {placeholder} in that template chooses EITHER a document field to
// pull the value from OR types a manual value. MSG91 renders the body from the
// template + these params. Shared by the supplier-linked doctypes in hooks.py.
essdee_yrp.open_send_sms_dialog = function (frm, supplier_key) {
	frappe.call({
		method: "yrp.notification.get_flow_sms_context",
		args: {
			doctype: frm.doc.doctype,
			docname: frm.doc.name,
			supplier_key: supplier_key,
		},
		callback(r) {
			if (!r.message) return;
			const ctx = r.message;
			if (!ctx.templates || !ctx.templates.length) {
				frappe.msgprint(__("No SMS template configured for {0}", [frm.doc.doctype]));
				return;
			}
			const by_name = {};
			ctx.templates.forEach((t) => (by_name[t.name] = t));
			const template_options = ctx.templates.map((t) => t.name);
			const number_options = ctx.numbers && ctx.numbers.length ? ctx.numbers : [ctx.mobile];
			const default_number = number_options[0];

			const d = new frappe.ui.Dialog({
				// Dialog titles render as raw HTML (dialog.js set_title uses .html())
				title: __("Send SMS to {0}", [frappe.utils.escape_html(ctx.supplier)]),
				size: "large",
				fields: [
					{ fieldtype: "HTML", fieldname: "recipient" },
					{
						fieldtype: "Select",
						fieldname: "number_pick",
						label: __("Number"),
						options: number_options.join("\n"),
						default: default_number,
						onchange() {
							d.set_value("mobile_no", d.get_value("number_pick"));
						},
					},
					{
						fieldtype: "Data",
						fieldname: "mobile_no",
						label: __("Send to"),
						reqd: 1,
						default: default_number,
						description: __("Pick a number above or type/edit one"),
					},
					{
						fieldtype: "Select",
						fieldname: "template",
						label: __("Template"),
						options: template_options,
						default: template_options[0],
						reqd: 1,
						onchange() {
							essdee_yrp._render_sms_vars(d, by_name[d.get_value("template")], ctx.doc_fields, frm);
						},
					},
					{ fieldtype: "Section Break", label: __("Template Inputs") },
					{ fieldtype: "HTML", fieldname: "vars_area" },
				],
				primary_action_label: __("Send"),
				primary_action(values) {
					const params = d._collect_params ? d._collect_params() : {};
					d.hide();
					frappe.call({
						method: "yrp.notification.send_flow_sms_notification",
						args: {
							doctype: frm.doc.doctype,
							docname: frm.doc.name,
							supplier_key: supplier_key,
							template_name: values.template,
							mobile_no: values.mobile_no,
							params: params,
						},
					});
				},
			});
			d.fields_dict.recipient.$wrapper.html(`
				<div class="mb-2 text-muted small">${__("Supplier")}: ${frappe.utils.escape_html(ctx.supplier)}</div>
			`);
			d.show();
			essdee_yrp._render_sms_vars(d, by_name[template_options[0]], ctx.doc_fields, frm);
		},
	});
};

// Render the 3-column placeholder table for the selected template:
//   Template Input | Map to Field | Manual Value
// For each {placeholder}: if a field is chosen, its live value on the document
// is used; otherwise the manual value is sent. A placeholder whose name matches
// a document field is pre-mapped to that field.
essdee_yrp._render_sms_vars = function (d, template, doc_fields, frm) {
	const esc = frappe.utils.escape_html;
	const wrapper = d.fields_dict.vars_area.$wrapper;
	const vars = (template && template.variables) || [];
	const fields = doc_fields || [];

	if (!vars.length) {
		wrapper.html(`<div class="text-muted small">${__("This template has no inputs.")}</div>`);
		d._collect_params = () => ({});
		return;
	}

	const field_values = new Set(fields.map((f) => f.value));
	const rows = vars
		.map((v) => {
			const opts = [`<option value="">${__("— manual —")}</option>`]
				.concat(
					fields.map(
						(f) =>
							`<option value="${esc(f.value)}"${f.value === v.name ? " selected" : ""}>${esc(f.label)}</option>`
					)
				)
				.join("");
			// Prefill manual with the server-resolved value only when it is NOT
			// auto-mapped to a field (avoids a stale duplicate of a live field).
			const manual = field_values.has(v.name) ? "" : esc(v.value || "");
			return `<tr>
				<td class="align-middle"><code>${esc(v.name)}</code></td>
				<td><select class="form-control ph-field">${opts}</select></td>
				<td><input type="text" class="form-control ph-manual" value="${manual}"></td>
			</tr>`;
		})
		.join("");

	wrapper.html(`
		<table class="table table-bordered" style="margin-bottom:0">
			<thead><tr>
				<th style="width:28%">${__("Template Input")}</th>
				<th style="width:40%">${__("Map to Field")}</th>
				<th style="width:32%">${__("Manual Value")}</th>
			</tr></thead>
			<tbody>${rows}</tbody>
		</table>
	`);

	d._collect_params = function () {
		const params = {};
		const trs = wrapper.find("tbody tr");
		vars.forEach((v, i) => {
			const tr = trs.eq(i);
			const field = tr.find(".ph-field").val();
			const manual = tr.find(".ph-manual").val();
			let value = "";
			if (field) {
				value = frm.doc[field];
				value = value === undefined || value === null ? "" : value;
			} else {
				value = manual || "";
			}
			params[v.name] = value;
		});
		return params;
	};
};

essdee_yrp.add_send_sms_button = function (frm, { hidden_statuses = [], supplier_key = "supplier" } = {}) {
	if (frm.is_new()) return;
	if (hidden_statuses.includes(frm.doc.status)) return;
	if (!frm.doc[supplier_key]) return;
	frm.add_custom_button(
		__("Send SMS"),
		() => essdee_yrp.open_send_sms_dialog(frm, supplier_key),
		__("Send Notification")
	);
};
