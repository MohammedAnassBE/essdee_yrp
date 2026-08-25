"""Reviewed Production API -> F16 naming and field rules.

Only decisions already approved in ``docs/MRP_MIGRATION_CONTEXT.md`` belong
here.  Unknown source fields remain blockers; the engine never silently drops
them.
"""

from __future__ import annotations

from essdee_yrp.migration.engine import DocTypeRule


DOCTYPE_RENAMES = {
	"Essdee Debit": "Debit",
	"Essdee Raw Print Format": "ZPL Raw Print Format",
	"Essdee Raw Print Format Detail": "ZPL Raw Print Format Detail",
	"GRN Item Type": "Received Type",
	"GRN Deliverable": "YRP GRN Deliverable",
	"Purchase Order Lot": "Lot MultiSelect",
	"Stock Settings": "YRP Stock Settings",
	"Vendor Bill Tracking": "Bill Tracking",
	"Vendor Bill Tracking Assignment Detail": "Bill Tracking Assignment Detail",
}


RULES = {
	"Bin": DocTypeRule(
		ignored_fields={
			"reserved_qty": "Derived from migrated Stock Reservation Entry rows in F16",
		},
		value_transformers={"warehouse": "supplier_to_warehouse"},
	),
	"Delivery Challan": DocTypeRule(
		post_transformer="derive_delivery_challan_fields",
	),
	"Delivery Challan Item": DocTypeRule(
		field_map={"item_type": "received_type"},
		allowed_type_changes=frozenset({("Int", "Data")}),
	),
	"Essdee Debit": DocTypeRule(
		target="Debit",
		ignored_fields={
			"against": "Validated as Work Order by the custom transformer",
		},
		custom_transformer="essdee_debit_to_debit",
	),
	"Essdee Raw Print Format": DocTypeRule(
		target="ZPL Raw Print Format",
		field_map={"raw_print_format_details": "zpl_raw_print_format_details"},
	),
	"Essdee Raw Print Format Detail": DocTypeRule(target="ZPL Raw Print Format Detail"),
	"FG Stock Entry": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Finishing Plan Old Lot Item": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Goods Received Note": DocTypeRule(
		ignored_fields={
			"essdee_yrp_stock_entry": "Obsolete cross-site stock-entry reference",
			"essdee_yrp_stock_entry_created": "Obsolete cross-site stock-entry flag",
		},
		post_transformer="derive_goods_received_note_fields",
	),
	"GRN Deliverable": DocTypeRule(
		target="YRP GRN Deliverable",
		post_transformer="derive_grn_deliverable_dimensions",
	),
	"GRN Item Type": DocTypeRule(
		target="Received Type",
		field_map={"grn_type": "received_type_name"},
	),
	"GRN Rework Item": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Item": DocTypeRule(
		field_map={"over_delivery_receipt_allowance": "po_excess_allowed_percentage"}
	),
	"Item BOM": DocTypeRule(allowed_type_changes=frozenset({("Data", "Link")})),
	"Item BOM Attribute Mapping": DocTypeRule(
		allowed_type_changes=frozenset({("Data", "Link")})
	),
	"Item Production Detail": DocTypeRule(
		table_option_map={"item_attributes": "IPD Item Attribute"},
		post_transformer="remove_empty_ipd_process_placeholders",
	),
	"IPD Process": DocTypeRule(custom_transformer="ipd_process_to_f16"),
	"Item Conversion": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Lot Transfer Item": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Lotwise Item Profit": DocTypeRule(
		post_transformer="default_legacy_lot_costing_type"
	),
	"MRP Settings": DocTypeRule(
		ignored_fields={
			"auto_send_notifications": "Notification automation is not installed on the target",
			"yrp_api_key": "Obsolete F15 remote-site credential",
			"yrp_api_secret": "Obsolete F15 remote-site credential",
			"yrp_site_url": "Obsolete F15 remote-site credential",
		}
	),
	"Purchase Invoice": DocTypeRule(
		field_map={"vendor_bill_tracking": "bill_tracking"},
		allowed_type_changes=frozenset({("Data", "Link")}),
		post_transformer="derive_purchase_invoice_fields",
	),
	"Purchase Order Item": DocTypeRule(
		field_map={
			"cancelled_qty": "cancelled_quantity",
			"pending_qty": "pending_quantity",
		},
		allowed_type_changes=frozenset({("Int", "Data")}),
	),
	"Purchase Order": DocTypeRule(
		value_transformers={
			"status": "purchase_order_status",
			"open_status": "purchase_order_open_status",
		},
		post_transformer="derive_purchase_order_fields",
	),
	"Production Order Detail": DocTypeRule(
		post_transformer="derive_production_order_detail_fields",
	),
	"Product": DocTypeRule(post_transformer="derive_product_item_name"),
	"Repost Item Valuation": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Goods Received Note Item": DocTypeRule(
		allowed_type_changes=frozenset({("Int", "Data")})
	),
	"Stock Entry": DocTypeRule(
		allowed_type_changes=frozenset({("Select", "Link")}),
		value_transformers={
			"from_warehouse": "supplier_to_warehouse",
			"to_warehouse": "supplier_to_warehouse",
		},
	),
	"Stock Entry Detail": DocTypeRule(
		allowed_type_changes=frozenset({("Data", "Dynamic Link")})
	),
	"Stock Ledger Entry": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Stock Reconciliation": DocTypeRule(
		value_transformers={"default_warehouse": "supplier_to_warehouse"}
	),
	"Stock Reconciliation Item": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Stock Reservation Entry": DocTypeRule(
		allowed_type_changes=frozenset(
			{
				("Data", "Select"),
			}
		),
		value_transformers={"warehouse": "supplier_to_warehouse"},
	),
	"Stock Settings": DocTypeRule(
		target="YRP Stock Settings",
		field_map={"default_rejected_type": "default_rejected_received_type"},
		ignored_fields={
			"sms_old_database_host": "Obsolete legacy database credential",
			"sms_old_database_name": "Obsolete legacy database credential",
			"sms_old_database_port": "Obsolete legacy database credential",
			"sms_old_database_user": "Obsolete legacy database credential",
			"sms_old_database_password": "Obsolete legacy database credential",
			"location_mapping": "One-time legacy warehouse mapping, replaced by Warehouse.supplier",
		},
		custom_transformer="stock_settings_to_yrp_stock_settings",
	),
	"Stock Update": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Stiching Item Detail": DocTypeRule(
		post_transformer="default_legacy_stitching_category"
	),
	"Vendor Bill Tracking": DocTypeRule(
		target="Bill Tracking",
		field_map={
			"vendor_bill_tracking_history": "bill_tracking_history",
			"purchase_invoice": "erp_purchase_invoice",
			"mrp_purchase_invoice": "purchase_invoice",
		},
		allowed_type_changes=frozenset({("Select", "Link"), ("Data", "Link")}),
	),
	"Vendor Bill Tracking Assignment Detail": DocTypeRule(
		target="Bill Tracking Assignment Detail"
	),
	"Work Order": DocTypeRule(field_map={"close_reason": "sd_close_reason"}),
	"Work Order Deliverables": DocTypeRule(field_map={"item_type": "received_type"}),
	"Work Order Receivables": DocTypeRule(),
	"Work Station": DocTypeRule(post_transformer="derive_workstation_fields"),
}


def get_rule(source_doctype: str) -> DocTypeRule:
	"""Return an explicit rule or the safe default identity rule."""

	rule = RULES.get(source_doctype)
	if rule:
		return rule
	return DocTypeRule(target=DOCTYPE_RENAMES.get(source_doctype, source_doctype))
