import "./vue_plugins";
import "./supplier_notification";
import "./supplier_whatsapp";
import "./ipd_attributes";
import { install_json_formatter } from "./json_format";

frappe.provide("frappe.yrp.work_order");
frappe.provide("essdee_yrp");

// Register before any form is rendered, not in refresh after unsafe HTML ran.
install_json_formatter(frappe.form.formatters);

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
