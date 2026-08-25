const QUALITY_METHOD =
	"essdee_yrp.essdee_yrp.doctype.essdee_quality_inspection.essdee_quality_inspection";

frappe.ui.form.on("Essdee Quality Inspection", {
	setup(frm) {
		frm.set_query("against_id", () => ({ filters: { docstatus: 1 } }));
	},

	async refresh(frm) {
		render_debit_details(frm);
		mount_colour_size_editor(frm);

		if (frm.is_new() && (!frm.doc.major_aql_level || !frm.doc.minor_aql_level)) {
			const { message = {} } = await frappe.call({
				method: `${QUALITY_METHOD}.get_default_aql_level`,
			});
			await frm.set_value({
				major_aql_level: frm.doc.major_aql_level || message.major,
				minor_aql_level: frm.doc.minor_aql_level || message.minor,
			});
		}

		if (frm.doc.docstatus === 1) {
			frm.set_df_property("result", "read_only", true);
			frm.add_custom_button(
				__("Create Debit"),
				() => open_inspection_debit_dialog(frm),
				__("Create"),
			);
			frm.add_custom_button(__("Share"), () => share_inspection(frm));
		}

		if (frm.doc.result === "Hold" && frm.perm?.[0]?.write) {
			frm.add_custom_button(__("Update Status"), () => open_result_dialog(frm));
		}
	},

	validate(frm) {
		if (frm.colour_and_size) {
			frm.doc.colour_and_size_data = frm.colour_and_size.get_data();
		}
	},

	offer_qty: fetch_major_minor_allowed,
	checking_level: fetch_major_minor_allowed,
	major_aql_level: fetch_major_minor_allowed,
	minor_aql_level: fetch_major_minor_allowed,

	async against_id(frm) {
		if (!frm.doc.against_id) {
			await frm.set_value({ item: null, lot: null, order_qty: 0, supplier: null });
			frm.colour_and_size?.load_data({ colours: [], sizes: [] }, frm.doc.docstatus);
			return;
		}

		const { message = {} } = await frappe.call({
			method: `${QUALITY_METHOD}.get_against_details`,
			args: {
				against: frm.doc.against,
				against_id: frm.doc.against_id,
			},
		});
		await frm.set_value({
			item: message.item,
			lot: message.lot,
			order_qty: message.order_qty,
			supplier: message.supplier,
		});
		frm.colour_and_size?.load_data(
			{ colours: message.colours || [], sizes: message.sizes || [] },
			frm.doc.docstatus,
		);
	},
});

function mount_colour_size_editor(frm) {
	frm.colour_and_size?.unmount?.();
	const wrapper = frm.fields_dict.size_and_colour_html?.wrapper;
	if (!wrapper || !frappe.production?.ui?.QualityInspection) {
		return;
	}
	wrapper.innerHTML = "";
	frm.colour_and_size = new frappe.production.ui.QualityInspection(wrapper);
	frm.colour_and_size.load_data(
		frm.doc.__onload?.colour_size_data || { colours: [], sizes: [] },
		frm.doc.docstatus,
	);
}

async function fetch_major_minor_allowed(frm) {
	if (
		!frm.doc.checking_level ||
		Number(frm.doc.offer_qty || 0) <= 0 ||
		!frm.doc.major_aql_level ||
		!frm.doc.minor_aql_level
	) {
		return;
	}
	const { message = {} } = await frappe.call({
		method: `${QUALITY_METHOD}.get_max_minor_defect_allowed`,
		args: {
			level: frm.doc.checking_level,
			offer_qty: frm.doc.offer_qty,
			major_aql_level: frm.doc.major_aql_level,
			minor_aql_level: frm.doc.minor_aql_level,
		},
	});
	await frm.set_value({
		sample_piece_count: message.sample,
		major_defect_maximum_allowed: message.major_allowed,
		minor_defect_maximum_allowed: message.minor_allowed,
	});
}

function open_inspection_debit_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Debit"),
		fields: [
			{
				fieldname: "debit_value",
				fieldtype: "Currency",
				label: __("Debit Value"),
				reqd: 1,
			},
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Reason"),
				reqd: 1,
			},
			{
				fieldname: "debit_document",
				fieldtype: "Attach",
				label: __("Debit Document"),
				reqd: 1,
			},
		],
		primary_action_label: __("Create"),
		async primary_action(values) {
			const { message } = await frappe.call({
				method: `${QUALITY_METHOD}.create_inspection_debit`,
				args: { quality_inspection: frm.doc.name, ...values },
				freeze: true,
				freeze_message: __("Creating Debit..."),
			});
			if (message) {
				frappe.show_alert({
					message: __("Debit {0} created", [message.name]),
					indicator: "green",
				});
				dialog.hide();
				await frm.reload_doc();
			}
		},
	});
	dialog.show();
}

function open_result_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select the Result"),
		fields: [
			{
				label: __("Result"),
				fieldname: "result",
				fieldtype: "Select",
				options: ["Pass", "Fail"],
				reqd: 1,
			},
		],
		async primary_action(values) {
			await frm.set_value("result", values.result);
			dialog.hide();
			await frm.save("Update");
		},
	});
	dialog.show();
}

async function share_inspection(frm) {
	const selected = (rows, key) =>
		(rows || [])
			.filter((row) => Number(row.selected) === 1)
			.map((row) => row[key])
			.join(", ");
	const caption = [
		frm.doc.inspection_type,
		`Supplier: ${frm.doc.supplier_name || ""}`,
		`Style: ${frm.doc.item || ""}`,
		`Lot: ${frm.doc.lot || ""}`,
		`Size: ${selected(frm.doc.essdee_quality_inspection_sizes, "size")}`,
		`Colour: ${selected(frm.doc.essdee_quality_inspection_colours, "colour")}`,
		`Description: ${frm.doc.description || ""}`,
		`Order Qty: ${frm.doc.order_qty || 0}`,
		`Offer Qty: ${frm.doc.offer_qty || 0}`,
		`AQL Sample: ${frm.doc.sample_piece_count || 0}`,
		`Allowed Major: ${frm.doc.major_defect_maximum_allowed || 0}`,
		`Found Major: ${frm.doc.major_defect_found || 0}`,
		`Allowed Minor: ${frm.doc.minor_defect_maximum_allowed || 0}`,
		`Found Minor: ${frm.doc.minor_defect_found || 0}`,
		`Result: ${frm.doc.result || ""}`,
	].join("\n");

	try {
		await navigator.clipboard.writeText(caption);
		if (!frm.doc.upload_quality_approval_sheet) {
			frappe.show_alert({ message: __("Inspection details copied"), indicator: "green" });
			return;
		}

		const url = `/api/method/frappe.utils.file_manager.download_file?file_url=${encodeURIComponent(
			frm.doc.upload_quality_approval_sheet,
		)}`;
		const response = await fetch(url, { credentials: "include" });
		if (!response.ok) {
			throw new Error(`Attachment download failed (${response.status})`);
		}
		const blob = await response.blob();
		const file = new File([blob], "inspection.jpg", { type: blob.type });
		const shareData = { text: caption, files: [file] };
		if (!navigator.share || (navigator.canShare && !navigator.canShare(shareData))) {
			frappe.show_alert({ message: __("Inspection details copied"), indicator: "green" });
			return;
		}
		await navigator.share(shareData);
	} catch (error) {
		console.error(error);
		frappe.msgprint(__("Sharing failed. The inspection details may still be on your clipboard."));
	}
}

function render_debit_details(frm) {
	const debits = frm.doc.__onload?.debit_details || [];
	const visible = debits.length > 0;
	frm.toggle_display(["debit_details_tab", "debit_details_html"], visible);
	(frm.layout.tabs || [])
		.find((tab) => tab.df.fieldname === "debit_details_tab")
		?.toggle(visible);
	if (!visible || !frm.fields_dict.debit_details_html) {
		return;
	}

	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const currency = (value) => format_currency(Number(value || 0));
	const total = debits.reduce((sum, debit) => sum + Number(debit.debit_value || 0), 0);
	const rows = debits
		.map((debit) => {
			const debitUrl = `/app/debit/${encodeURIComponent(debit.name)}`;
			const fileUrl = String(debit.debit_document || "");
			const documentLink =
				fileUrl.startsWith("/files/") || fileUrl.startsWith("/private/files/")
					? `<a href="${escape(fileUrl)}" target="_blank" rel="noopener noreferrer">${__("View Document")}</a>`
					: "—";
			const indicator = debit.status === "Approved" ? "green" : "orange";
			const created = debit.creation ? frappe.datetime.str_to_user(debit.creation) : "—";
			return `<tr>
				<td><a href="${debitUrl}">${escape(debit.name)}</a></td>
				<td>${escape(debit.debit_type || "—")}</td>
				<td class="text-right"><strong>${currency(debit.debit_value)}</strong></td>
				<td style="white-space: pre-line;">${escape(debit.reason || "—")}</td>
				<td>${documentLink}</td>
				<td><span class="indicator-pill ${indicator}">${escape(debit.status || "—")}</span></td>
				<td>${escape(debit.approved_by || "—")}</td>
				<td>${escape(created)}</td>
			</tr>`;
		})
		.join("");

	$(frm.fields_dict.debit_details_html.wrapper).html(`
		<div style="padding-top: 12px;">
			<div class="row" style="margin-bottom: 14px;">
				<div class="col-sm-6"><div class="text-muted small">${__("Number of Debits")}</div><div style="font-size:18px;font-weight:600;">${debits.length}</div></div>
				<div class="col-sm-6 text-right"><div class="text-muted small">${__("Total Debit Value")}</div><div style="font-size:18px;font-weight:600;">${currency(total)}</div></div>
			</div>
			<div class="table-responsive"><table class="table table-bordered table-hover">
				<thead><tr><th>${__("Debit")}</th><th>${__("Type")}</th><th class="text-right">${__("Debit Value")}</th><th>${__("Reason")}</th><th>${__("Document")}</th><th>${__("Status")}</th><th>${__("Approved By")}</th><th>${__("Created On")}</th></tr></thead>
				<tbody>${rows}</tbody>
				<tfoot><tr><th colspan="2" class="text-right">${__("Total")}</th><th class="text-right">${currency(total)}</th><th colspan="5"></th></tr></tfoot>
			</table></div>
		</div>`);
}
