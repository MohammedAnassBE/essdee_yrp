// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.provide("essdee_yrp");

// Send-WhatsApp-to-supplier dialog. Mirrors the Send-SMS dialog
// (supplier_notification.js) for the WhatsApp hub-spoke: the user picks an
// APPROVED mirror template configured for this doctype, fills each positional
// {{n}} variable (body + text-header) EITHER from a document field OR a manual
// value, optionally attaches a media header (the document's print PDF for a
// DOCUMENT header, or a doc attachment/photo for an IMAGE header), previews the
// rendered body, then sends via yrp.whatsapp_notification.send_whatsapp_notification.
// Shared by the supplier-linked doctypes wired in essdee_yrp/hooks.py.
essdee_yrp.open_send_whatsapp_dialog = function (frm, supplier_key) {
	frappe.call({
		method: "yrp.whatsapp_notification.get_whatsapp_context",
		args: {
			doctype: frm.doc.doctype,
			docname: frm.doc.name,
			supplier_key: supplier_key,
		},
		callback(r) {
			if (!r.message) return;
			const ctx = r.message;
			if (!ctx.templates || !ctx.templates.length) {
				frappe.msgprint(__("No WhatsApp template configured for {0}", [frm.doc.doctype]));
				return;
			}
			const by_name = {};
			ctx.templates.forEach((t) => (by_name[t.name] = t));
			const template_options = ctx.templates.map((t) => t.name);
			const number_options = ctx.numbers && ctx.numbers.length ? ctx.numbers : [ctx.mobile];
			const default_number = number_options[0];

			const d = new frappe.ui.Dialog({
				// Dialog titles render as raw HTML (dialog.js set_title uses .html())
				title: __("Send WhatsApp to {0}", [frappe.utils.escape_html(ctx.supplier)]),
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
							essdee_yrp._on_template_change(d, by_name[d.get_value("template")], ctx, frm);
						},
					},
					{ fieldtype: "Section Break", label: __("Template Inputs") },
					{ fieldtype: "HTML", fieldname: "vars_area" },
					{ fieldtype: "Section Break", label: __("Media Header") },
					{ fieldtype: "HTML", fieldname: "header_area" },
					{ fieldtype: "Section Break", label: __("Preview") },
					{ fieldtype: "HTML", fieldname: "preview_area" },
				],
				primary_action_label: __("Send"),
				primary_action(values) {
					const template = by_name[values.template];
					const params = d._collect_params ? d._collect_params() : {};
					const header = d._collect_header
						? d._collect_header()
						: { header_source: null, print_format: null };
					d.hide();
					frappe.call({
						method: "yrp.whatsapp_notification.send_whatsapp_notification",
						// The hub round-trip + print-render/upload is slower than SMS.
						freeze: true,
						freeze_message: __("Sending WhatsApp…"),
						args: {
							doctype: frm.doc.doctype,
							docname: frm.doc.name,
							supplier_key: supplier_key,
							// The Select option value is t.name (the mirror autoname
							// "{template_name}-{language_code}", e.g. "yrp_wa_send-en"),
							// but the hub needs the BARE Meta template name — send the field.
							template_name: template.template_name,
							language_code: template.language_code,
							mobile_no: values.mobile_no,
							params: params,
							header_source: header.header_source,
							print_format: header.print_format,
						},
					});
				},
			});
			d.fields_dict.recipient.$wrapper.html(`
				<div class="mb-2 text-muted small">${__("Supplier")}: ${frappe.utils.escape_html(ctx.supplier)}</div>
			`);
			d.show();
			essdee_yrp._on_template_change(d, by_name[template_options[0]], ctx, frm);
		},
	});
};

// Re-render the three template-dependent sections when the template changes.
// Order matters: vars first (sets d._collect_params, which the preview reads),
// then the media-header control, then the preview.
essdee_yrp._on_template_change = function (d, template, ctx, frm) {
	essdee_yrp._render_whatsapp_vars(d, template, ctx.doc_fields, frm);
	essdee_yrp._render_header_control(d, template, ctx);
	essdee_yrp._render_preview(d, template);
};

// Render the positional-variable table for the selected template — one row per
// {{n}} placeholder (body + text header): Template Input | Map to Field |
// Manual Value. Each row's value comes from a chosen document field OR the
// manual box (pre-filled with the server-resolved value from variable_mapping).
// A body {{1}} and a header {{1}} are DISTINCT variables, so params are keyed
// "<type>:<n>" (e.g. "body:1", "header:1") to avoid collision.
essdee_yrp._render_whatsapp_vars = function (d, template, doc_fields, frm) {
	const esc = frappe.utils.escape_html;
	const wrapper = d.fields_dict.vars_area.$wrapper;
	const vars = (template && template.variables) || [];
	const fields = doc_fields || [];
	const num = (token) => (token || "").replace(/[^0-9]/g, "");

	if (!vars.length) {
		wrapper.html(`<div class="text-muted small">${__("This template has no inputs.")}</div>`);
		d._collect_params = () => ({});
		if (d._refresh_preview) d._refresh_preview();
		return;
	}

	const rows = vars
		.map((v) => {
			const opts = [`<option value="">${__("— manual —")}</option>`]
				.concat(
					fields.map(
						(f) => `<option value="${esc(f.value)}">${esc(f.label)}</option>`
					)
				)
				.join("");
			return `<tr>
				<td class="align-middle"><code>${esc(v.token)}</code> <span class="text-muted small">(${esc(v.type)})</span></td>
				<td><select class="form-control ph-field">${opts}</select></td>
				<td><input type="text" class="form-control ph-manual" value="${esc(v.value || "")}"></td>
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
			params[`${v.type}:${num(v.token)}`] = value;
		});
		return params;
	};

	// Live-refresh the preview as the user edits any mapping/manual input.
	wrapper.find(".ph-field, .ph-manual").on("change keyup", () => {
		if (d._refresh_preview) d._refresh_preview();
	});
	if (d._refresh_preview) d._refresh_preview();
};

// Render the media-header control. Only IMAGE / DOCUMENT header templates get a
// control: DOCUMENT attaches the document's print PDF (pick a Print Format),
// IMAGE attaches a file already on the document (pick an attachment / photo).
// Anything else (no header, TEXT header) sends no media. Exposes d._collect_header().
essdee_yrp._render_header_control = function (d, template, ctx) {
	const esc = frappe.utils.escape_html;
	const wrapper = d.fields_dict.header_area.$wrapper;
	const header_type = (template && template.header_type) || "";

	if (header_type === "DOCUMENT") {
		const formats = ctx.print_formats || [];
		const opts = formats
			.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`)
			.join("");
		wrapper.html(`
			<div class="text-muted small mb-2">${__("The document's print PDF will be attached as the header.")}</div>
			<label class="control-label">${__("Print Format")}</label>
			<select class="form-control wa-print-format">${opts}</select>
		`);
		d._collect_header = () => ({
			header_source: "print",
			print_format: wrapper.find(".wa-print-format").val() || null,
		});
	} else if (header_type === "IMAGE") {
		const atts = ctx.attachments || [];
		const opts = [`<option value="">${__("— none —")}</option>`]
			.concat(
				atts.map(
					(a) => `<option value="${esc(a.file_url)}">${esc(a.file_name || a.file_url)}</option>`
				)
			)
			.join("");
		wrapper.html(`
			<div class="text-muted small mb-2">${__("Pick a photo attached to this document to send as the header.")}</div>
			<label class="control-label">${__("Image Attachment")}</label>
			<select class="form-control wa-image-file">${opts}</select>
		`);
		d._collect_header = () => ({
			header_source: wrapper.find(".wa-image-file").val() || null,
			print_format: null,
		});
	} else {
		wrapper.html(`<div class="text-muted small">${__("This template has no media header.")}</div>`);
		d._collect_header = () => ({ header_source: null, print_format: null });
	}
};

// Render a read-only WhatsApp-style preview bubble: the TEXT header (if any) and
// the body with each {{n}} substituted by the currently chosen value.
// Unfilled placeholders stay as {{n}}. Refreshes live via d._refresh_preview().
essdee_yrp._render_preview = function (d, template) {
	const esc = frappe.utils.escape_html;
	const wrapper = d.fields_dict.preview_area.$wrapper;

	const render = () => {
		const params = d._collect_params ? d._collect_params() : {};
		const sub = (text, type) =>
			(text || "").replace(/\{\{\s*(\d+)\s*\}\}/g, (m, n) => {
				const val = params[`${type}:${n}`];
				return val === undefined || val === null || val === "" ? m : String(val);
			});
		const parts = [];
		if (template && template.header_type === "TEXT" && template.header_content) {
			parts.push(`<div style="font-weight:600">${esc(sub(template.header_content, "header"))}</div>`);
		}
		parts.push(`<div>${esc(sub((template && template.body_text) || "", "body")).replace(/\n/g, "<br>")}</div>`);
		wrapper.html(`
			<div style="background:#dcf8c6;color:#000;border-radius:8px;padding:10px 12px;max-width:80%">
				${parts.join("")}
			</div>
		`);
	};

	d._refresh_preview = render;
	render();
};

essdee_yrp.add_send_whatsapp_button = function (
	frm,
	{ hidden_statuses = [], supplier_key = "supplier" } = {}
) {
	if (frm.is_new()) return;
	if (hidden_statuses.includes(frm.doc.status)) return;
	if (!frm.doc[supplier_key]) return;
	frm.add_custom_button(
		__("Send WhatsApp"),
		() => essdee_yrp.open_send_whatsapp_dialog(frm, supplier_key),
		__("Send Notification")
	);
};
