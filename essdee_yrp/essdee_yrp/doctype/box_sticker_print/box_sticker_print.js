// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

const BOX_STICKER_METHOD =
	"essdee_yrp.essdee_yrp.doctype.box_sticker_print.box_sticker_print";

frappe.ui.form.on("Box Sticker Print", {
	setup(frm) {
		frm.set_query("size", "box_sticker_print_details", () => ({
			filters: { attribute_name: "Size" },
		}));
		frm.set_query("fg_item", () => ({
			filters: { is_temp_item: 0, disabled: 0 },
		}));
	},

	refresh(frm) {
		disable_browser_print_shortcut();
		hide_standard_print_actions();
		if (frm.doc.docstatus === 1 && frm.perm?.[0]?.write) {
			frm.add_custom_button(__("Print Labels"), () => open_print_dialog(frm));
		}
		render_preview(frm);
	},

	lot(frm) {
		if (!frm.doc.lot) {
			frm.set_value("box_sticker_print_details", []);
		} else if (frm.doc.fg_item) {
			load_fg_details(frm);
		}
	},

	fg_item(frm) {
		if (frm.doc.fg_item) {
			load_fg_details(frm);
		} else {
			frm.set_value("box_sticker_print_details", []);
		}
	},
});

async function load_fg_details(frm) {
	const rows = await frappe.xcall(`${BOX_STICKER_METHOD}.get_fg_details`, {
		fg_item: frm.doc.fg_item,
		lot: frm.doc.lot,
	});
	await frm.set_value("box_sticker_print_details", rows || []);
}

async function open_print_dialog(frm) {
	try {
		await frappe.ui.form.qz_connect();
		const detected = await frappe.ui.form.qz_get_printer_list();
		const printers = await frappe.xcall(`${BOX_STICKER_METHOD}.get_printer`, {
			printers: detected,
		});
		if (!printers?.length) {
			frappe.throw(__("No configured label printer is available."));
		}
		const printer_dialog = new frappe.ui.Dialog({
			title: __("Select Printer"),
			fields: [
				{
					fieldname: "printer",
					fieldtype: "Select",
					label: __("Printer"),
					options: printers,
					reqd: 1,
				},
				{
					fieldname: "printer_type",
					fieldtype: "Select",
					label: __("Printer Resolution"),
					options: ["200dpi", "300dpi"],
					default: "300dpi",
					reqd: 1,
				},
			],
			primary_action_label: __("Next"),
			primary_action(values) {
				printer_dialog.hide();
				open_quantity_dialog(frm, values.printer, values.printer_type);
			},
		});
		printer_dialog.show();
	} catch (error) {
		frappe.ui.form.qz_fail(error);
	}
}

function open_quantity_dialog(frm, printer, printer_type) {
	const data = (frm.doc.box_sticker_print_details || []).map((row) => ({
		doc_name: row.name,
		size: row.size,
		mrp: row.mrp,
		total_quantity: row.quantity,
		printed_quantity: row.printed_quantity,
		print_quantity: 0,
	}));
	const dialog = new frappe.ui.Dialog({
		title: __("Enter Label Quantities"),
		size: "large",
		fields: [
			{
				fieldname: "items",
				fieldtype: "Table",
				label: __("Items"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				data,
				fields: [
					{
						fieldname: "doc_name",
						fieldtype: "Data",
						hidden: 1,
					},
					{
						fieldname: "size",
						fieldtype: "Data",
						label: __("Size"),
						in_list_view: 1,
						read_only: 1,
					},
					{
						fieldname: "mrp",
						fieldtype: "Currency",
						label: __("MRP"),
						in_list_view: 1,
						read_only: 1,
					},
					{
						fieldname: "total_quantity",
						fieldtype: "Int",
						label: __("Total"),
						in_list_view: 1,
						read_only: 1,
					},
					{
						fieldname: "printed_quantity",
						fieldtype: "Int",
						label: __("Printed"),
						in_list_view: 1,
						read_only: 1,
					},
					{
						fieldname: "print_quantity",
						fieldtype: "Int",
						label: __("Print Quantity"),
						in_list_view: 1,
					},
				],
			},
		],
		primary_action_label: __("Print"),
		async primary_action(values) {
			const items = (values.items || [])
				.filter((row) => cint(row.print_quantity) > 0)
				.map((row) => ({
					doc_name: row.doc_name,
					quantity: cint(row.print_quantity),
				}));
			if (!items.length) {
				frappe.throw(__("Enter at least one print quantity."));
			}
			dialog.get_primary_btn().prop("disabled", true);
			let raw;
			try {
				raw = await frappe.xcall(`${BOX_STICKER_METHOD}.get_print_format`, {
					doc: frm.doc.name,
					print_items: items,
					printer_type,
				});
			} catch (error) {
				dialog.get_primary_btn().prop("disabled", false);
				throw error;
			}
			try {
				await qz.print(qz.configs.create(printer), [raw]);
				dialog.hide();
				await frm.reload_doc();
			} catch (error) {
				await frappe.xcall(`${BOX_STICKER_METHOD}.override_print_quantity`, {
					print_items: items,
					print_format: frm.doc.print_format,
				});
				throw error;
			} finally {
				dialog.get_primary_btn().prop("disabled", false);
			}
		},
	});
	dialog.show();
}

async function render_preview(frm) {
	const wrapper = frm.fields_dict.preview?.$wrapper;
	if (!wrapper) return;
	wrapper.empty();
	if (!frm.doc.print_format || frm.doc.__islocal) return;
	try {
		const result = await frappe.xcall(`${BOX_STICKER_METHOD}.get_raw_code`, {
			doc_name: frm.doc.name,
		});
		const url = `https://api.labelary.com/v1/printers/12dpmm/labels/${encodeURIComponent(
			result.width
		)}x${encodeURIComponent(result.height)}/0/${encodeURIComponent(result.code)}`;
		$("<img>", {
			src: url,
			alt: __("Label Preview"),
			css: { border: "2px solid #000", maxWidth: "100%" },
		}).appendTo(wrapper);
	} catch (error) {
		wrapper.text(__("Preview unavailable"));
	}
}

function disable_browser_print_shortcut() {
	$(document)
		.off("keydown.essdee_box_sticker")
		.on("keydown.essdee_box_sticker", (event) => {
			if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "p") {
				event.preventDefault();
				event.stopImmediatePropagation();
			}
		});
}

function hide_standard_print_actions() {
	$("[data-original-title='Print']").hide();
	$("li:has(a:has(span[data-label='Print']))").remove();
}
