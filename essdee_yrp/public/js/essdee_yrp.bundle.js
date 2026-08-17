import "./vue_plugins";
import "./supplier_notification";
import "./supplier_whatsapp";

frappe.provide("frappe.yrp.work_order");
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
