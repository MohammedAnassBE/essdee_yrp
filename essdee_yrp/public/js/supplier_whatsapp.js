// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.provide("essdee_yrp");

// Send-WhatsApp-to-supplier dialog. Mirrors the Send-SMS dialog
// (supplier_notification.js) for the WhatsApp hub-spoke's template-centric
// contract: the user picks an APPROVED template that yrp.whatsapp_notification
// has ALREADY filtered server-side to this doctype (via the template's own
// Applicable DocTypes), fills each positional {{n}} variable (body + text
// header) EITHER from a document field OR a manual value, optionally attaches
// a media header file when the template needs one, previews the rendered
// body, then sends via yrp.whatsapp_notification.send_whatsapp_notification.
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
			// Select options carry {value, label} so the Meta template_name
			// (the human-readable label) can differ from the mirror's own
			// autoname (the value) — see control_select.js's parse_option.
			const template_options = ctx.templates.map((t) => ({
				value: t.name,
				label: t.template_name,
			}));
			const default_template = template_options[0].value;
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
						default: default_template,
						reqd: 1,
						onchange() {
							essdee_yrp._on_whatsapp_template_change(
								d,
								by_name[d.get_value("template")],
								ctx,
								frm
							);
						},
					},
					{ fieldtype: "Section Break", label: __("Template Inputs") },
					{ fieldtype: "HTML", fieldname: "vars_area" },
					{ fieldtype: "Section Break", label: __("Preview") },
					{ fieldtype: "HTML", fieldname: "preview_area" },
					{
						fieldtype: "Section Break",
						fieldname: "media_section",
						label: __("Media Header"),
					},
					{
						fieldtype: "Attach",
						fieldname: "header_file",
						label: __("Header image/document"),
					},
				],
				primary_action_label: __("Send"),
				primary_action(values) {
					const template = by_name[values.template];
					const params = d._collect_params ? d._collect_params() : {};
					d.hide();
					frappe.call({
						method: "yrp.whatsapp_notification.send_whatsapp_notification",
						// The hub round-trip + (for media templates) the file
						// upload is slower than SMS.
						freeze: true,
						freeze_message: __("Sending WhatsApp…"),
						args: {
							doctype: frm.doc.doctype,
							docname: frm.doc.name,
							supplier_key: supplier_key,
							// The Select's value is t.name (the mirror autoname
							// "{template_name}-{language_code}"), but the hub
							// needs the BARE Meta template name + language.
							template_name: template.template_name,
							language_code: template.language_code,
							mobile_no: values.mobile_no,
							params: params,
							header_file: values.header_file || null,
						},
					});
				},
			});
			d.fields_dict.recipient.$wrapper.html(`
				<div class="mb-2 text-muted small">${__("Supplier")}: ${frappe.utils.escape_html(ctx.supplier)}</div>
			`);
			d.show();
			essdee_yrp._on_whatsapp_template_change(d, by_name[default_template], ctx, frm);
		},
	});
};

// Re-render the three template-dependent sections when the template changes.
// Order matters: vars first (sets d._collect_params, which the preview
// reads), then the media-attach control, then the preview.
essdee_yrp._on_whatsapp_template_change = function (d, template, ctx, frm) {
	essdee_yrp._render_whatsapp_vars(d, template, ctx.doc_fields, frm);
	essdee_yrp._render_whatsapp_media_control(d, template);
	essdee_yrp._render_whatsapp_preview(d, template);
};

// Render the positional-variable table for the selected template — one row
// per {{n}} placeholder (body + text header): Template Input | Map to Field |
// Manual Value. Each row's value comes from a chosen document field OR the
// manual box (pre-filled with the server-resolved value from the template's
// own Sample Values). A body {{1}} and a header {{1}} are DISTINCT variables,
// so params are keyed "<type>:<n>" (e.g. "body:1", "header:1") to avoid
// collision — this is the exact flat shape send_whatsapp_notification expects.
essdee_yrp._render_whatsapp_vars = function (d, template, doc_fields, frm) {
	const esc = frappe.utils.escape_html;
	const wrapper = d.fields_dict.vars_area.$wrapper;
	const vars = (template && template.variables) || [];
	const fields = doc_fields || [];
	const num = (token) => (token || "").replace(/[^0-9]/g, "");

	if (!vars.length) {
		wrapper.html(`<div class="text-muted small">${__("This template has no inputs.")}</div>`);
		d._collect_params = () => ({});
		if (d._refresh_whatsapp_preview) d._refresh_whatsapp_preview();
		return;
	}

	const rows = vars
		.map((v) => {
			const opts = [`<option value="">${__("— manual —")}</option>`]
				.concat(fields.map((f) => `<option value="${esc(f.value)}">${esc(f.label)}</option>`))
				.join("");
			return `<tr>
				<td class="align-middle"><code>${esc(v.name)}</code> <span class="text-muted small">(${esc(v.type)})</span></td>
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
			params[`${v.type}:${num(v.name)}`] = value;
		});
		return params;
	};

	// Live-refresh the preview as the user edits any mapping/manual input.
	wrapper.find(".ph-field, .ph-manual").on("change keyup", () => {
		if (d._refresh_whatsapp_preview) d._refresh_whatsapp_preview();
	});
	if (d._refresh_whatsapp_preview) d._refresh_whatsapp_preview();
};

// Toggle the Attach field for the template's media header. Only templates
// whose header needs a file (needs_media: IMAGE/DOCUMENT/VIDEO) show it — a
// headerless or TEXT-header template hides + clears it. Marked reqd only
// while shown, so frappe.ui.Dialog's built-in get_values() validation (which
// does not consult `hidden`) blocks Send on a missing attachment only when
// one is actually required.
essdee_yrp._render_whatsapp_media_control = function (d, template) {
	const needs_media = !!(template && template.needs_media);
	const header_type = (template && template.header_type) || "";

	d.set_df_property("media_section", "hidden", !needs_media);
	d.set_df_property("header_file", "hidden", !needs_media);
	d.set_df_property("header_file", "reqd", needs_media ? 1 : 0);
	d.set_df_property(
		"header_file",
		"description",
		needs_media
			? __("This template requires a {0} attachment for its header.", [header_type])
			: ""
	);
	if (!needs_media && d.get_value("header_file")) {
		d.set_value("header_file", "");
	}
};

// Render a read-only WhatsApp-style preview bubble: the body with each {{n}}
// substituted by the currently chosen value (unfilled placeholders stay as
// {{n}}), plus the static footer if the template has one. Only the body is
// substituted — the hub contract has no separate header-preview text.
// Refreshes live via d._refresh_whatsapp_preview().
essdee_yrp._render_whatsapp_preview = function (d, template) {
	const esc = frappe.utils.escape_html;
	const wrapper = d.fields_dict.preview_area.$wrapper;

	const render = () => {
		const params = d._collect_params ? d._collect_params() : {};
		const body = (template && template.body_text) || "";
		const sub = body.replace(/\{\{\s*(\d+)\s*\}\}/g, (m, n) => {
			const val = params[`body:${n}`];
			return val === undefined || val === null || val === "" ? m : String(val);
		});
		const parts = [`<div>${esc(sub).replace(/\n/g, "<br>")}</div>`];
		if (template && template.footer_text) {
			parts.push(
				`<div class="text-muted small" style="margin-top:6px">${esc(template.footer_text)}</div>`
			);
		}
		wrapper.html(`
			<div style="background:#dcf8c6;color:#000;border-radius:8px;padding:10px 12px;max-width:80%">
				${parts.join("")}
			</div>
		`);
	};

	d._refresh_whatsapp_preview = render;
	render();
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
		// The hub settings row may configure a different supplier_key for
		// this doctype (e.g. Stock Entry's to_supplier/from_supplier split)
		// — prefer it over the caller's default when given.
		const key = enabled[frm.doc.doctype] || supplier_key;
		if (!frm.doc[key]) return;
		frm.add_custom_button(
			__("Send WhatsApp"),
			() => essdee_yrp.open_send_whatsapp_dialog(frm, key),
			__("Send Notification")
		);
	});
};
