// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP WO Recut", {
	setup(frm) {
		frm.set_query("work_order", () => ({
			filters: {
				docstatus: 1,
				open_status: "Open",
				is_rework: 0,
			},
		}));
	},

	refresh(frm) {
		if (!frm.fields_dict.recut_items) {
			return;
		}
		const current_items = frm.recut_items_editor?.get_items() || [];
		if (frm.recut_items_editor) {
			frm.recut_items_editor.app.unmount();
		}
		$(frm.fields_dict.recut_items.wrapper).empty();
		frm.recut_items_editor = new frappe.yrp.work_order.ItemEditor(
			frm.fields_dict.recut_items.wrapper,
			{
				editorType: "work_order_deliverables",
				title: __("Recut Items"),
				showDimensions: false,
				allowCreate: true,
				allowEdit: true,
				allowRemove: true,
			},
		);
		const items = current_items.length
			? current_items
			: (frm.doc.__onload && frm.doc.__onload.recut_item_details) ||
				parse_item_details(frm.doc.recut_item_details);
		frm.recut_items_editor.load_data(items);
		frm.recut_items_editor.update_status();
		bind_dirty_event(frm);
		if (frm.is_new() && frm.doc.work_order && !current_items.length) {
			load_new_recut_items(frm);
		}
	},

	work_order(frm) {
		if (!frm.is_new()) return;
		frm._wo_recut_seeded_work_order = null;
		frm._wo_recut_seed_request = (frm._wo_recut_seed_request || 0) + 1;
		if (!frm.doc.work_order) {
			frm.recut_items_editor?.load_data([]);
			frm.set_value("lot", "");
			return;
		}
		load_new_recut_items(frm);
	},

	validate(frm) {
		if (frm.doc.docstatus === 0 && frm.recut_items_editor) {
			frm.doc.recut_item_details = JSON.stringify(
				frm.recut_items_editor.get_items() || [],
			);
		}
	},
});

function load_new_recut_items(frm) {
	const work_order = frm.doc.work_order;
	if (!work_order || frm._wo_recut_seeded_work_order === work_order) return;
	const request = (frm._wo_recut_seed_request || 0) + 1;
	frm._wo_recut_seed_request = request;
	frappe.call({
		method: "essdee_yrp.work_order_actions.get_wo_recut_defaults",
		args: { work_order },
		freeze: true,
		freeze_message: __("Loading Work Order SKUs..."),
		callback(r) {
			if (
				request !== frm._wo_recut_seed_request
				|| work_order !== frm.doc.work_order
			) return;
			const defaults = r.message || {};
			frm._wo_recut_seeded_work_order = work_order;
			frm.recut_items_editor?.load_data(defaults.item_details || []);
			if (defaults.lot && frm.doc.lot !== defaults.lot) {
				frm.set_value("lot", defaults.lot);
			}
		},
	});
}

function parse_item_details(value) {
	if (!value) return [];
	try {
		return typeof value === "string" ? JSON.parse(value) : value;
	} catch (error) {
		return [];
	}
}

function bind_dirty_event(frm) {
	if (!frappe.yrp.eventBus || frm._wo_recut_dirty_handler) return;
	frm._wo_recut_dirty_handler = () => frm.dirty();
	frappe.yrp.eventBus.$on("work_order_items_updated", frm._wo_recut_dirty_handler);
}
