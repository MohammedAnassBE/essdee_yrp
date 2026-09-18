"""Reviewed Production API -> F16 naming and field rules.

Only decisions already approved in ``docs/MRP_MIGRATION_CONTEXT.md`` belong
here.  Unknown source fields remain blockers; the engine never silently drops
them.
"""

from __future__ import annotations

from essdee_yrp.migration.engine import DocTypeRule

DOCTYPE_RENAMES = {
	"Essdee Debit": 'YRP Debit',
	"Essdee Raw Print Format": 'YRP ZPL Raw Print Format',
	"Essdee Raw Print Format Detail": 'YRP ZPL Raw Print Format Detail',
	"GRN Item Type": 'YRP Received Type',
	"GRN Deliverable": 'SD YRP YRP GRN Deliverable',
	"Purchase Order Lot": 'SD YRP Lot MultiSelect',
	"Stock Settings": 'YRP YRP Stock Settings',
	"Vendor Bill Tracking": 'YRP Bill Tracking',
	"Vendor Bill Tracking Assignment Detail": 'YRP Bill Tracking Assignment Detail',
	"Bin": "YRP Bin",
	"Delivery Challan": "YRP Delivery Challan",
	"Delivery Challan Item": "YRP Delivery Challan Item",
	"FG Stock Entry": "SD YRP FG Stock Entry",
	"Finishing Plan Old Lot Item": "SD YRP Finishing Plan Old Lot Item",
	"Goods Received Note": "YRP Goods Received Note",
	"Goods Received Note Item": "YRP Goods Received Note Item",
	"GRN Rework Item": "SD YRP GRN Rework Item",
	"IPD Process": "YRP IPD Process",
	"Item": "Item",
	"Item Attribute": "Item Attribute",
	"Item Attribute Value": "Item Attribute Value",
	"Item Variant": "Item",
	"Item Variant Attribute": "Item Variant Attribute",
	"Item BOM": "YRP Item BOM",
	"Item BOM Attribute Mapping": "YRP Item BOM Attribute Mapping",
	"Item Conversion": "SD YRP Item Conversion",
	"Item Production Detail": "YRP Item Production Detail",
	"Lot Transfer Item": "SD YRP Lot Transfer Item",
	"Lotwise Item Profit": "SD YRP Lotwise Item Profit",
	"MRP Settings": "SD YRP MRP Settings",
	"Process": "YRP Process",
	"Product": "SD YRP Product",
	"Production Order Detail": "YRP Production Order Detail",
	"Purchase Invoice": "YRP Purchase Invoice",
	"Purchase Order": "Purchase Order",
	"Purchase Order Item": "Purchase Order Item",
	"Repost Item Valuation": "YRP Repost Item Valuation",
	"Stiching Item Detail": "SD YRP Stiching Item Detail",
	"Stock Entry": "YRP Stock Entry",
	"Stock Entry Detail": "YRP Stock Entry Detail",
	"Stock Ledger Entry": "YRP Stock Ledger Entry",
	"Stock Reconciliation": "YRP Stock Reconciliation",
	"Stock Reconciliation Item": "YRP Stock Reconciliation Item",
	"Stock Reservation Entry": "YRP Stock Reservation Entry",
	"Stock Update": "YRP Stock Update",
	"Work Order": "YRP Work Order",
	"Work Order Deliverables": "YRP Work Order Deliverables",
	"Work Order Receivables": "YRP Work Order Receivables",
	"Work Station": "YRP Work Station",
}


RULES = {
	"Brand": DocTypeRule(
		target="Brand",
		field_map={"name1": "brand"},
	),
	"Bin": DocTypeRule(
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
		target='YRP Debit',
		ignored_fields={
			"against": "Validated as Work Order by the custom transformer",
		},
		custom_transformer="essdee_debit_to_debit",
	),
	"Essdee Raw Print Format": DocTypeRule(
		target='YRP ZPL Raw Print Format',
		field_map={"raw_print_format_details": "zpl_raw_print_format_details"},
	),
	"Essdee Raw Print Format Detail": DocTypeRule(target='YRP ZPL Raw Print Format Detail'),
	"FG Stock Entry": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Finishing Plan Old Lot Item": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Goods Received Note": DocTypeRule(
		post_transformer="derive_goods_received_note_fields",
	),
	"GRN Deliverable": DocTypeRule(
		target='SD YRP YRP GRN Deliverable',
		post_transformer="derive_grn_deliverable_dimensions",
	),
	"GRN Item Type": DocTypeRule(
		target='YRP Received Type',
		field_map={"grn_type": "received_type_name"},
	),
	"GRN Rework Item": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Item": DocTypeRule(
		target="Item",
		field_map={
			"name1": "item_name",
			"default_unit_of_measure": "stock_uom",
			"uom_conversion_details": "uoms",
			"over_delivery_receipt_allowance": "po_excess_allowed_percentage",
		},
		table_option_map={"attributes": "Item Variant Attribute"},
		allowed_type_changes=frozenset({("Small Text", "Text Editor")}),
		post_transformer="item_to_standard_item",
	),
	"Item Attribute": DocTypeRule(target="Item Attribute"),
	"Item Attribute Value": DocTypeRule(
		target="Item Attribute Value",
		extra_dependencies=frozenset({"Item Attribute"}),
		custom_transformer="item_attribute_value_to_standard_child",
	),
	"Item Variant": DocTypeRule(
		target="Item",
		custom_transformer="item_variant_to_standard_item",
	),
	"Item Variant Attribute": DocTypeRule(
		target="Item Variant Attribute",
		allowed_type_changes=frozenset({("Link", "Data")}),
		value_transformers={"attribute_value": "attribute_value_link_to_data"},
	),
	"Item Alternative": DocTypeRule(
		target="Item Alternative",
		field_map={
			"item": "item_code",
			"alternative_item": "alternative_item_code",
		},
	),
	"Item BOM": DocTypeRule(allowed_type_changes=frozenset({("Data", "Link")})),
	"Item BOM Attribute Mapping": DocTypeRule(
		allowed_type_changes=frozenset({("Data", "Link")})
	),
	"Item Production Detail": DocTypeRule(
		table_option_map={"item_attributes": 'YRP IPD Item Attribute'},
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
	"MRP Settings": DocTypeRule(),
	"Purchase Invoice": DocTypeRule(
		extra_dependencies=frozenset({"Goods Received Note", "Work Order"}),
		field_map={"vendor_bill_tracking": "bill_tracking"},
		allowed_type_changes=frozenset({("Data", "Link")}),
		post_transformer="derive_purchase_invoice_fields",
	),
	"Purchase Order Item": DocTypeRule(
		field_map={
			"item_variant": "item_code",
			"delivery_date": "schedule_date",
			"cancelled_qty": "cancelled_quantity",
			"pending_qty": "pending_quantity",
		},
		allowed_type_changes=frozenset({("Int", "Data"), ("Data", "Text Editor")}),
		post_transformer="derive_purchase_order_item_fields",
	),
	"Purchase Order": DocTypeRule(
		field_map={
			"po_date": "transaction_date",
			"supplier_address_display": "address_display",
			"delivery_address": "shipping_address",
			"delivery_address_display": "shipping_address_display",
		},
		value_transformers={
			"status": "purchase_order_status",
			"open_status": "purchase_order_open_status",
		},
		post_transformer="derive_purchase_order_fields",
	),
	"Production Order Detail": DocTypeRule(
		post_transformer="derive_production_order_detail_fields",
	),
	"Process": DocTypeRule(
		# F15/production_api used Additional Allowance for the percentage by
		# which a Work Order receipt may exceed its planned receivable.  Base
		# YRP now owns that contract under the explicit field below; retaining
		# both fields leaves migrated Processes strict at the base default 0%.
		field_map={"additional_allowance": "wo_excess_allowed_percentage"},
		post_transformer="derive_process_fields",
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
		target='YRP YRP Stock Settings',
		field_map={"default_rejected_type": "default_rejected_received_type"},
		value_transformers={"transit_warehouse": "supplier_to_warehouse"},
	),
	"Stock Update": DocTypeRule(
		value_transformers={"warehouse": "supplier_to_warehouse"}
	),
	"Stiching Item Detail": DocTypeRule(
		post_transformer="default_legacy_stitching_category"
	),
	"Vendor Bill Tracking": DocTypeRule(
		target='YRP Bill Tracking',
		field_map={
			"vendor_bill_tracking_history": "bill_tracking_history",
			"purchase_invoice": "erp_purchase_invoice",
			"mrp_purchase_invoice": "purchase_invoice",
		},
		allowed_type_changes=frozenset({("Select", "Link"), ("Data", "Link")}),
	),
	"Vendor Bill Tracking Assignment Detail": DocTypeRule(
		target='YRP Bill Tracking Assignment Detail'
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
