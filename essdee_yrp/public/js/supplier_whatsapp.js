// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.provide("essdee_yrp");

// Send-WhatsApp-to-supplier dialog: pick the supplier number and the Relay
// Document Action, check the filled message and PDF name, then send.
essdee_yrp.open_send_whatsapp_dialog = function (frm, supplier_key) {
	frappe.call({
		method: "yrp.whatsapp_notification.get_whatsapp_context",
		args: { doctype: frm.doc.doctype, docname: frm.doc.name, supplier_key },
		callback(r) {
			const ctx = r.message;
			if (!ctx) return;
			const by_name = Object.fromEntries(ctx.templates.map((t) => [t.name, t]));
			// One message per dialog: a double click sends once, a new dialog sends again.
			const request_key = frappe.utils.get_random(20);
			const d = new frappe.ui.Dialog({
				// Dialog titles render as raw HTML.
				title: __("Send WhatsApp to {0}", [frappe.utils.escape_html(ctx.supplier)]),
				fields: [
					{
						fieldtype: "Select",
						fieldname: "mobile_no",
						label: __("Send to"),
						options: ctx.numbers.join("\n"),
						default: ctx.mobile,
						reqd: 1,
					},
					{
						fieldtype: "Select",
						fieldname: "template",
						label: __("Message"),
						options: ctx.templates.map((t) => t.name).join("\n"),
						default: ctx.templates[0].name,
						reqd: 1,
						onchange: () => render(),
					},
					{ fieldtype: "HTML", fieldname: "preview_area" },
				],
				primary_action_label: __("Send"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "yrp.whatsapp_notification.send_whatsapp_notification",
						freeze: true,
						freeze_message: __("Sending WhatsApp…"),
						args: {
							doctype: frm.doc.doctype,
							docname: frm.doc.name,
							supplier_key,
							template_name: values.template,
							mobile_no: values.mobile_no,
							request_key,
						},
					});
				},
			});
			const render = () => {
				const esc = frappe.utils.escape_html;
				const template = by_name[d.get_value("template")] || {};
				const file = template.file_name
					? `<div class="text-muted small mt-2">${__("PDF")}: ${esc(template.file_name)}</div>`
					: "";
				d.fields_dict.preview_area.$wrapper.html(`
					<div style="background:#dcf8c6;color:#000;border-radius:8px;padding:10px 12px;white-space:pre-wrap">${esc(template.body_text || "")}</div>${file}
				`);
			};
			d.show();
			render();
		},
	});
};

// Every doctype enabled to send WhatsApp (+ its configured supplier_key),
// fetched once per page load and cached as a promise on essdee_yrp itself so
// every add_send_whatsapp_button call shares the same round-trip.
essdee_yrp._get_enabled_whatsapp_doctypes = function () {
	if (!essdee_yrp._wa_enabled_doctypes) {
		essdee_yrp._wa_enabled_doctypes = frappe
			.xcall("yrp.whatsapp_notification.get_enabled_whatsapp_doctypes")
			.catch(() => ({ doctypes: {} }));
	}
	return essdee_yrp._wa_enabled_doctypes;
};

essdee_yrp.add_send_whatsapp_button = function (
	frm,
	{ hidden_statuses = [], supplier_key = "supplier" } = {}
) {
	if (frm.is_new()) return;
	if (hidden_statuses.includes(frm.doc.status)) return;

	essdee_yrp._get_enabled_whatsapp_doctypes().then((r) => {
		const enabled = (r && r.doctypes) || {};
		if (!(frm.doc.doctype in enabled)) return;
		// The Relay Document Action names the supplier field of the doctype.
		const key = enabled[frm.doc.doctype] || supplier_key;
		if (!frm.doc[key]) return;
		frm.add_custom_button(
			__("Send WhatsApp"),
			() => essdee_yrp.open_send_whatsapp_dialog(frm, key),
			__("Send Notification")
		);
	});
};
