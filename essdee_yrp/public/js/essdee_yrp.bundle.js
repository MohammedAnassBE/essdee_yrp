import "./vue_plugins";
import "./supplier_notification";
import "./supplier_whatsapp";

frappe.provide("frappe.yrp.work_order");
frappe.provide("essdee_yrp");

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
