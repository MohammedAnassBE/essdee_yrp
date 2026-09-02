frappe.ui.form.on("YRP Goods Received Note", {
	refresh(frm) {
		exclude_grn_cut_panel_movement_from_cancel_all(frm);
		configure_bundle_return(frm);
		configure_calculate_button(frm);
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
	},
});

function configure_calculate_button(frm) {
	frm.remove_custom_button(__("Calculate"));
	if (
		frm.is_new()
		|| frm.doc.docstatus !== 0
		|| frm.doc.against !== "YRP Work Order"
		|| !frm.doc.against_id
		|| frm.doc.is_return
		|| frm.doc.is_rework
		|| frm.doc.additional_grn
		|| frm.doc.includes_packing
		|| frm.doc.cutting_laysheet
		|| frm.doc.cut_panel_movement
		|| frm.doc.from_closed_wo_sewing_details
	) {
		return;
	}
	frm.add_custom_button(__("Calculate"), () => open_calculate_dialog(frm));
}

function open_calculate_dialog(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the Goods Received Note before calculating quantities."));
		return;
	}
	frappe.call({
		method: "essdee_yrp.garment_grn.get_grn_calculation_context",
		args: { goods_received_note: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading Work Order calculated items..."),
		callback(r) {
			const context = r.message || {};
			if (!(context.rows || []).length) {
				frappe.msgprint(__("The Work Order has no calculated quantities."));
				return;
			}
			render_calculate_dialog(frm, context);
		},
	});
}

function render_calculate_dialog(frm, context) {
	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const attributes = context.display_attributes || [];
	const primaryValues = context.primary_values || [];
	const attributeHeader = attributes
		.map((attribute) => `<th>${escape(__(attribute))}</th>`)
		.join("");
	const primaryHeader = primaryValues
		.map((value) => `<th style="min-width:92px;">${escape(value)}</th>`)
		.join("");
	const body = (context.matrix_rows || []).map((row, index) => {
		const attributeCells = attributes.map(
			(attribute) => `<td>${escape((row.attributes || {})[attribute] || "")}</td>`,
		).join("");
		const quantityCells = primaryValues.map((value) => {
			const cell = (row.values || {})[value];
			if (!cell) return '<td class="text-muted text-center">—</td>';
			return `<td style="min-width:92px;">
				<input class="form-control input-sm essdee-grn-calc-qty"
					type="number" min="0" max="${escape(flt(cell.available_qty))}"
					step="0.001" value="${escape(flt(cell.qty))}"
					data-source-row="${escape(cell.source_row)}"
					data-primary-value="${escape(value)}"
					title="${escape(cell.item_variant)}">
			</td>`;
		}).join("");
		return `<tr data-matrix-row="${index}">
			<td><input type="checkbox" class="essdee-grn-row-toggle" checked> ${index + 1}</td>
			${attributeCells}${quantityCells}
			<td class="text-right"><strong class="essdee-grn-row-total">0</strong></td>
		</tr>`;
	}).join("");
	const totals = primaryValues.map(
		(value) => `<th class="text-right essdee-grn-column-total" data-primary-value="${escape(value)}">0</th>`,
	).join("");
	const html = `<h4 style="margin:0 0 10px;">${__("Work Order Items")}</h4>
		<div class="mb-2">
			<button class="btn btn-xs btn-default essdee-grn-select-all">${__("Select All")}</button>
			<button class="btn btn-xs btn-default essdee-grn-unselect-all" style="margin-left:5px;">${__("Unselect All")}</button>
		</div>
		<div style="max-height:55vh;overflow:auto;">
			<table class="table table-bordered table-sm">
				<thead><tr><th>${__("S.No.")}</th>${attributeHeader}${primaryHeader}<th class="text-right">${__("Total Qty")}</th></tr></thead>
				<tbody>${body}</tbody>
				<tfoot><tr><th>${__("Total")}</th>${attributes.map(() => "<th></th>").join("")}${totals}<th class="text-right essdee-grn-grand-total">0</th></tr></tfoot>
			</table>
		</div>`;

	const dialog = new frappe.ui.Dialog({
		title: __("Calculate Receivables"),
		size: "extra-large",
		fields: [
			{
				fieldname: "received_type",
				fieldtype: "Link",
				options: "YRP Received Type",
				label: __("Received Type"),
				default: context.default_received_type || "",
				reqd: 1,
			},
			{ fieldname: "calculated_items_html", fieldtype: "HTML", options: html },
		],
		primary_action_label: __("Calculate"),
		primary_action(values) {
			const selected = [];
			const wrapper = dialog.get_field("calculated_items_html").$wrapper;
			wrapper.find(".essdee-grn-calc-qty").each(function () {
				const quantity = flt($(this).val());
				if (quantity > 0) {
					selected.push({
						source_row: $(this).attr("data-source-row"),
						qty: quantity,
					});
				}
			});
			if (!selected.length) {
				frappe.msgprint(__("Enter a quantity greater than zero for at least one row."));
				return;
			}
			frappe.call({
				method: "essdee_yrp.garment_grn.calculate_grn_receivables",
				args: {
					goods_received_note: frm.doc.name,
					rows: selected,
					received_type: values.received_type,
					modified: context.modified,
				},
				freeze: true,
				freeze_message: __("Calculating receivable quantities..."),
				callback(r) {
					dialog.hide();
					const result = r.message || {};
					frappe.show_alert({
						message: __("Updated {0} received row(s).", [result.received_rows || 0]),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
	const wrapper = dialog.get_field("calculated_items_html").$wrapper;
	const updateTotals = () => {
		const columnTotals = {};
		let grandTotal = 0;
		wrapper.find("tr[data-matrix-row]").each(function () {
			let rowTotal = 0;
			$(this).find(".essdee-grn-calc-qty").each(function () {
				const quantity = flt($(this).val());
				const primaryValue = String($(this).attr("data-primary-value"));
				rowTotal += quantity;
				columnTotals[primaryValue] = (columnTotals[primaryValue] || 0) + quantity;
			});
			$(this).find(".essdee-grn-row-total").text(rowTotal);
			grandTotal += rowTotal;
		});
		wrapper.find(".essdee-grn-column-total").each(function () {
			$(this).text(columnTotals[String($(this).attr("data-primary-value"))] || 0);
		});
		wrapper.find(".essdee-grn-grand-total").text(grandTotal);
	};
	const setRowSelected = (row, selected) => {
		row.find(".essdee-grn-row-toggle").prop("checked", selected);
		row.find(".essdee-grn-calc-qty").each(function () {
			$(this).val(selected ? $(this).attr("max") : 0);
		});
	};
	wrapper.on("input", ".essdee-grn-calc-qty", updateTotals);
	wrapper.on("change", ".essdee-grn-row-toggle", function () {
		setRowSelected($(this).closest("tr"), $(this).prop("checked"));
		updateTotals();
	});
	wrapper.on("click", ".essdee-grn-select-all", () => {
		wrapper.find("tr[data-matrix-row]").each(function () {
			setRowSelected($(this), true);
		});
		updateTotals();
	});
	wrapper.on("click", ".essdee-grn-unselect-all", () => {
		wrapper.find("tr[data-matrix-row]").each(function () {
			setRowSelected($(this), false);
		});
		updateTotals();
	});
	updateTotals();
}

function exclude_grn_cut_panel_movement_from_cancel_all(frm) {
	if (frm.doc.docstatus !== 1 || !frm.doc.cut_panel_movement) return;
	const ignored = new Set(frm.ignore_doctypes_on_cancel_all || []);
	ignored.add("SD YRP Cut Panel Movement");
	frm.ignore_doctypes_on_cancel_all = [...ignored];
}

function configure_bundle_return(frm) {
	if (!frm.fields_dict.cut_panel_movement) return;
	const editable_return = frm.doc.docstatus === 0 && Boolean(frm.doc.is_return);
	frm.set_df_property("cut_panel_movement", "hidden", editable_return ? 0 : 1);
	if (!editable_return) return;

	frm.set_df_property(
		"cut_panel_movement",
		"description",
		__(
			"Select the submitted Cut Panel Movement for an exact whole-bundle return. Leave this empty to return the entered quantity as collapsed-bundle stock.",
		),
	);
	frm.set_query("cut_panel_movement", () => {
		const filters = {
			docstatus: 1,
			against_id: ["is", "not set"],
		};
		if (frm.doc.supplier) filters.from_warehouse = frm.doc.supplier;
		if (frm.doc.lot) filters.lot = frm.doc.lot;
		return { filters };
	});
}
