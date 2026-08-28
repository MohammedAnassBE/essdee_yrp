import "./vue_plugins";
import "./supplier_notification";
import "./supplier_whatsapp";

frappe.provide("frappe.yrp.work_order");
frappe.provide("essdee_yrp");

// Frappe v16's sidebar header currently sends divider and failed-condition
// definitions through add_app_item(). Those definitions have no icon URL, so
// the renderer creates <img src="undefined"> and every Desk load logs a 404.
// Apply the guard before frappe.start_app() runs; do not patch upstream code.
essdee_yrp.guard_sidebar_header_items = function () {
    const SidebarHeader = frappe.ui?.SidebarHeader;
    if (!SidebarHeader || SidebarHeader.prototype.__essdee_item_guard) return;

    const add_app_item = SidebarHeader.prototype.add_app_item;
    SidebarHeader.prototype.add_app_item = function (item) {
        if (!item || item.is_divider) return;
        if (typeof item.condition === "function" && !item.condition()) return;
        if (!item.icon && !item.icon_url) return;
        return add_app_item.call(this, item);
    };
    SidebarHeader.prototype.__essdee_item_guard = true;
};

essdee_yrp.guard_sidebar_header_items();

// The shared YRP quantity editors intentionally let their matrix tables size to
// their contents. On Essdee records with many sizes/quantity columns that width
// can extend beneath Desk's right sidebar. Keep the matrix inside the owning
// HTML field and expose its own horizontal scrollbar.
essdee_yrp.contain_item_editor_matrix = function (frm, fieldnames) {
    for (const fieldname of fieldnames || []) {
        const $wrapper = frm.fields_dict[fieldname]?.$wrapper;
        if (!$wrapper?.length) continue;
        $wrapper.css({
            "max-width": "100%",
            "overflow-x": "auto",
        });
    }
};

frappe.yrp.work_order.close_dialog_options = {
    reason_options: [
        "",
        "NA",
        "Cutting Shortage",
        "Printing Shortage",
        "Sewing Shortage",
        "Sewing Missing",
        "Others",
    ],
    other_reason_value: "Others",
};
