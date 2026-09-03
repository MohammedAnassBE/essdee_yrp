frappe.ui.form.on("YRP Purchase Invoice", {
	refresh(frm) {
		configure_essdee_process_items(frm);
		configure_erp_purchase_invoice_actions(frm);
		schedule_essdee_verification_details(frm);
	},

	against(frm) {
		configure_essdee_process_items(frm);
	},

	essdee_rate_table_source(frm) {
		configure_essdee_process_items(frm);
	},
});

frappe.ui.form.on("SD YRP Essdee Purchase Invoice Item", {
	rate(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
		refresh_commercial_preview(frm);
	},
});

const VERIFICATION_GRAND_TOTAL_ROWS = [
	["total_delivered", __("Total Delivered")],
	["total_received", __("Total Received")],
	["difference", __("Difference")],
	["total_billed", __("Total Billed")],
	["pending_for_bill", __("Pending For Bill")],
	["grn_quantity", __("GRN Quantity")],
];

function schedule_essdee_verification_details(frm) {
	if (frm.doc.against !== "YRP Work Order") return;
	const details = frm.doc.__onload && frm.doc.__onload.item_details;
	if (!details || !details.length || !details[0].colours) return;
	const token = (frm.__essdee_verification_render_token || 0) + 1;
	frm.__essdee_verification_render_token = token;

	// Base YRP renders its generic list through nested asynchronous calls. Wait
	// until those calls have settled, then replace only that presentation with
	// Essdee's garment matrix.
	frappe.after_ajax(() => {
		setTimeout(async () => {
			if (token !== frm.__essdee_verification_render_token || cur_frm !== frm) return;
			let controls = null;
			if (frm.doc.docstatus === 0 && !frm.doc.approved_by && !frm.is_new()) {
				try {
					const [permission, status] = await Promise.all([
						frappe.xcall("yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_close_permission"),
						frappe.xcall(
							"yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.check_all_wo_closed",
							{ purchase_invoice: frm.doc.name }
						),
					]);
					controls = { permission: permission || {}, status: status || {} };
				} catch (error) {
					console.warn("Could not load Work Order close controls", error);
				}
			}
			if (token !== frm.__essdee_verification_render_token || cur_frm !== frm) return;
			frm.__essdee_verification_controls = controls;
			render_essdee_verification_details(frm, controls);
		}, 0);
	});
}

function render_essdee_verification_details(frm, controls = null) {
	const wrapper =
		frm.fields_dict.work_order_details_html && frm.fields_dict.work_order_details_html.wrapper;
	const details = frm.doc.__onload && frm.doc.__onload.item_details;
	if (!wrapper || !details || !details.length || !details[0].colours) return;

	ensure_essdee_verification_styles();
	let html = '<div class="essdee-pi-verification">';
	for (const item of details) {
		html += render_verification_work_order(item);
	}
	html += render_verification_close_controls(frm, controls);
	html += "</div>";
	$(wrapper).html(html);
	$(wrapper)
		.find(".essdee-pi-close-wo")
		.on("click", function () {
			frappe.yrp.work_order.open_close_dialog(frm, $(this).data("wo"));
		});
}
function render_verification_work_order(item) {
	let html = `<section class="essdee-verification-work-order">
		<h4>${escape_html(item.work_order)}</h4>`;
	if ((item.bills || []).length) {
		html += `<h5>${__("Purchase Invoice List")}</h5>
			<table class="table table-sm essdee-bordered-table essdee-small-width">
			<thead><tr><th>${__("S.No")}</th><th>${__("Purchase Invoice")}</th></tr></thead><tbody>`;
		item.bills.forEach((bill, index) => {
			const name = bill.pi_name || "";
			html += `<tr><td>${
				index + 1
			}</td><td><a href="/app/yrp-purchase-invoice/${encodeURIComponent(name)}"
				target="_blank">${escape_html(name)}</a></td></tr>`;
		});
		html += "</tbody></table>";
	}
	html += `<h5>${escape_html(item.lot)} - ${escape_html(item.item_name)}</h5>
		<div class="table-responsive"><table class="table table-sm essdee-bordered-table essdee-verification-matrix">
		<thead class="essdee-dark-border"><tr><th>${__("S.No")}</th>
		<th>${escape_html(item.packing_attr)}</th>`;
	if (item.is_set_item) html += `<th>${escape_html(item.set_attr)}</th>`;
	html += `<th>${__("Type")}</th>`;
	for (const size of item.sizes || []) html += `<th>${escape_html(size)}</th>`;
	html += `<th>${__("Total")}</th></tr></thead><tbody class="essdee-dark-border">`;

	Object.keys(item.colours || {}).forEach((colour, index) => {
		const colour_data = item.colours[colour];
		const totals = item.total_qty[colour];
		const rows = [
			[__("Total Delivered"), "total_delivered", "total_delivered"],
			[__("Total Received"), "total_received", "total_received"],
			[__("Difference"), "difference", "difference"],
			[__("Total Billed"), "billed", "total_billed"],
			[__("Pending For Bill"), "pending", "pending"],
			[__("GRN Quantity"), "quantity", "total_quantity"],
		];
		rows.forEach(([label, cell_key, total_key], row_index) => {
			html += "<tr>";
			if (row_index === 0) {
				html += `<td rowspan="6">${index + 1}</td>
					<td rowspan="6">${escape_html(colour.split("@")[0].trim())}</td>`;
				if (item.is_set_item) {
					html += `<td rowspan="6">${escape_html(colour_data.part)}</td>`;
				}
			}
			html += `<td>${label}</td>`;
			for (const size of item.sizes || []) {
				const cell = colour_data.data[size] || {};
				let value = 0;
				if (cell_key === "difference") {
					value = flt(cell.total_delivered) - flt(cell.total_received);
				} else if (cell_key === "pending") {
					value = flt(cell.total_received) - flt(cell.billed);
				} else {
					value = flt(cell[cell_key]);
				}
				html += `<td>${display_number(value, 3)}</td>`;
			}
			let total = 0;
			if (total_key === "difference") {
				total = flt(totals.total_delivered) - flt(totals.total_received);
			} else if (total_key === "pending") {
				total = flt(totals.total_received) - flt(totals.total_billed);
			} else {
				total = flt(totals[total_key]);
			}
			html += `<th>${display_number(total, 3)}</th></tr>`;
		});
	});
	html += "</tbody>";
	if (item.grand_total) {
		html += '<tbody class="essdee-dark-border essdee-grand-total-section">';
		VERIFICATION_GRAND_TOTAL_ROWS.forEach(([key, label], index) => {
			html += "<tr>";
			if (index === 0) {
				html += `<th rowspan="${VERIFICATION_GRAND_TOTAL_ROWS.length}"
					colspan="${item.is_set_item ? 3 : 2}" class="essdee-grand-total-label">
					${__("Grand Total")}</th>`;
			}
			html += `<th>${label}</th>`;
			for (const size of item.sizes || []) {
				html += `<th>${display_number(item.grand_total.sizes[size][key], 3)}</th>`;
			}
			html += `<th>${display_number(item.grand_total.total[key], 3)}</th></tr>`;
		});
		html += "</tbody>";
	}
	return `${html}</table></div></section>`;
}

function render_verification_close_controls(frm, controls) {
	if (
		!controls ||
		frm.doc.docstatus !== 0 ||
		frm.doc.approved_by ||
		frm.doc.against !== "YRP Work Order"
	) {
		return "";
	}
	const permission = controls.permission || {};
	const status = controls.status || {};
	const open_work_orders = status.open_work_orders || [];
	const close_request_wos = status.close_request_wos || [];
	if (!open_work_orders.length && !close_request_wos.length) return "";
	let html = `<div class="essdee-verification-actions">
		<div class="text-warning mb-2">${__("Work Orders must be closed before manager approval.")}</div>`;
	if (!permission.approver_role) {
		html += `<div class="text-danger mb-2">${__(
			"Configure Work Order Closing Approver Role in YRP Settings."
		)}</div>`;
	}
	for (const work_order of open_work_orders) {
		if (!permission.approver_role) continue;
		const label = permission.is_close_manager ? __("Close") : __("Request Close");
		html += `<button class="btn btn-xs btn-warning essdee-pi-close-wo"
			data-wo="${escape_html(work_order)}">${label} ${escape_html(work_order)}</button> `;
	}
	for (const work_order of close_request_wos) {
		if (permission.is_close_manager) {
			html += `<button class="btn btn-xs btn-warning essdee-pi-close-wo"
				data-wo="${escape_html(work_order)}">${__("Approve Close")} ${escape_html(work_order)}</button> `;
		} else if (permission.approver_role) {
			html += `<span class="text-muted mr-2">${__("Close requested")}: ${escape_html(
				work_order
			)}</span>`;
		}
	}
	return `${html}</div>`;
}

function ensure_essdee_verification_styles() {
	if (document.getElementById("essdee-pi-verification-styles")) return;
	const style = document.createElement("style");
	style.id = "essdee-pi-verification-styles";
	style.textContent = `
		.essdee-pi-verification .essdee-bordered-table { width: 100%; border: 1px solid #ccc; border-collapse: collapse; }
		.essdee-pi-verification .essdee-small-width { width: 50%; }
		.essdee-pi-verification .essdee-bordered-table th,
		.essdee-pi-verification .essdee-bordered-table td { border: 1px solid #ccc; padding: 6px 8px; text-align: center; }
		.essdee-pi-verification .essdee-bordered-table thead { background-color: #f8f9fa; font-weight: bold; }
		.essdee-pi-verification .essdee-dark-border { border: 2px solid #000; }
		.essdee-pi-verification .essdee-grand-total-section { background-color: #f3f4f6; border-top: 3px double #000; }
		.essdee-pi-verification .essdee-grand-total-label { font-size: 1.05rem; vertical-align: middle; }
		.essdee-pi-verification .essdee-verification-work-order { margin-bottom: 24px; }
		.essdee-pi-verification .essdee-verification-actions { text-align: right; margin-top: 12px; }
	`;
	document.head.appendChild(style);
}

function escape_html(value) {
	return frappe.utils.escape_html(String(value ?? ""));
}

function display_number(value, precision) {
	const number = flt(value, precision);
	if (Number.isInteger(number)) return String(number);
	return number.toFixed(precision).replace(/\.?0+$/, "");
}

function configure_essdee_process_items(frm) {
	const is_work_order = frm.doc.against === "YRP Work Order";
	const is_purchase_order = frm.doc.against === "YRP Purchase Order";
	const uses_grouped_items =
		is_work_order ||
		(is_purchase_order &&
			((frm.doc.essdee_items || []).length ||
				["yrp_grn_v1", "production_api"].includes(frm.doc.essdee_rate_table_source)));
	const grouped_label = is_work_order ? __("Process Items") : __("Grouped Items");
	frm.set_df_property("items_section", "label", uses_grouped_items ? grouped_label : __("Items"));
	frm.set_df_property("essdee_items", "label", grouped_label);
	// Operators edit only the grouped commercial projection. The exact GRN
	// variants remain server-owned inputs for stock valuation adjustment.
	frm.toggle_display("items", !uses_grouped_items);
	frm.toggle_display("essdee_items", uses_grouped_items);
	if (!uses_grouped_items || !frm.fields_dict.essdee_items) return;

	const grid = frm.fields_dict.essdee_items.grid;
	grid.cannot_add_rows = true;
	grid.cannot_delete_rows = true;
	grid.only_sortable = false;
	const editable_rate =
		frm.doc.docstatus === 0 &&
		["yrp_grn_v1", "production_api"].includes(frm.doc.essdee_rate_table_source);
	for (const fieldname of [
		"item",
		"lot",
		"item_group",
		"expense_head",
		"qty",
		"uom",
		"source_rate",
		"amount",
		"tax",
	]) {
		grid.update_docfield_property(fieldname, "read_only", 1);
	}
	grid.update_docfield_property("rate", "read_only", editable_rate ? 0 : 1);
	frm.refresh_field("essdee_items");
}

function configure_erp_purchase_invoice_actions(frm) {
	const sync_enabled = Boolean(
		frm.doc.__onload && frm.doc.__onload.erp_purchase_invoice_sync_enabled
	);
	if (frm.doc.docstatus === 1 && frm.doc.erp_inv_name) {
		frm.add_custom_button(
			__("Show Bill"),
			() => {
				frappe.call({
					method: "essdee_yrp.erp_purchase_invoice.get_erp_inv_link",
					args: { name: frm.doc.name },
					callback(r) {
						if (r.message) window.open(r.message, "_blank");
					},
				});
			},
			__("ERP")
		);
	}
	if (
		sync_enabled &&
		frm.doc.docstatus === 1 &&
		frm.doc.erp_inv_name &&
		flt(frm.doc.erp_inv_docstatus) === 0
	) {
		frm.add_custom_button(
			__("Submit Bill"),
			() => {
				frappe.call({
					method: "essdee_yrp.erp_purchase_invoice.submit_erp_invoice",
					args: { name: frm.doc.name },
					freeze: true,
					freeze_message: __("Submitting Bill..."),
					callback() {
						frm.reload_doc();
					},
				});
			},
			__("ERP")
		);
	}
	if (sync_enabled && frm.doc.docstatus === 0 && get_erp_items(frm).length) {
		frm.add_custom_button(__("Fetch Expense Head"), () => fetch_expense_heads(frm), __("ERP"));
	}
}

function get_erp_items(frm) {
	if ((frm.doc.essdee_items || []).length) {
		return frm.doc.essdee_items;
	}
	return frm.doc.items || [];
}

function fetch_expense_heads(frm) {
	const fieldname =
		(frm.doc.essdee_items || []).length ? "essdee_items" : "items";
	frappe.call({
		method: "essdee_yrp.erp_purchase_invoice.fetch_items_expense_head",
		args: { items: get_erp_items(frm) },
		freeze: true,
		freeze_message: __("Fetching Expense Heads..."),
		callback(r) {
			if (r.message) frm.set_value(fieldname, r.message);
		},
	});
}

function refresh_commercial_preview(frm) {
	const total = (frm.doc.essdee_items || []).reduce(
		(value, row) => value + flt(row.qty) * flt(row.rate),
		0
	);
	frm.set_value("total", total);
	const request_id = (frm.__essdee_tax_preview_request =
		(frm.__essdee_tax_preview_request || 0) + 1);
	Promise.all(
		(frm.doc.essdee_items || []).map(async (row) => {
			if (!row.tax) return 0;
			const result = await frappe.db.get_value("YRP Tax Slab", row.tax, "percentage");
			return flt(result.message && result.message.percentage);
		})
	).then((tax_rates) => {
		if (request_id !== frm.__essdee_tax_preview_request) return;
		const tax_total = (frm.doc.essdee_items || []).reduce(
			(value, row, index) =>
				value + (flt(row.qty) * flt(row.rate) * flt(tax_rates[index])) / 100,
			0
		);
		frm.set_value("total_tax", tax_total);
		frm.set_value("grand_total", total + tax_total);
	});
}
