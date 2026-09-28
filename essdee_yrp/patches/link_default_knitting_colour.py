"""Preserve the existing plain Colour setting when changing it to a scoped Link."""
import frappe
from yrp.attribute_values import ensure_value_master


def execute():
    frappe.reload_doc("essdee_yrp", "doctype", "sd_yrp_ipd_settings")
    value = frappe.db.get_single_value("SD YRP IPD Settings", "default_knitting_output_colour")
    if value:
        from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import get_knitting_colour
        if frappe.db.exists("YRP Item Attribute Value", value):
            get_knitting_colour(value)
            return
        link = ensure_value_master("Colour", value)
        frappe.db.set_single_value("SD YRP IPD Settings", "default_knitting_output_colour", link)
