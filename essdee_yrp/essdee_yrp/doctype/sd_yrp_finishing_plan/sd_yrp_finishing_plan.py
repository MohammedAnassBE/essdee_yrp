# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from essdee_yrp.finishing.ocr import (
	get_fp_ocr_details,
	get_ocr_details,
	get_ocr_percentage,
	get_ocr_style,
)
from essdee_yrp.finishing.old_lot import create_lot_transfer, fetch_from_old_lot
from essdee_yrp.finishing.alternative import (
	check_is_alternative_item,
	create_alternative_fp,
	get_alternative_details,
	get_fp_alternate_lots,
	get_unconfigured_lots,
	update_alternative_lot_quantity,
)
from essdee_yrp.finishing.insights import (
	fetch_rejected_quantity,
	get_fp_consumption_details,
	get_fp_stock_balance_details,
)
from essdee_yrp.finishing.closure import (
	add_p_and_l_document,
	approve_ocr_request,
	complete_ocr,
	delete_p_and_l_document,
	get_p_and_l_documents,
)
from essdee_yrp.finishing.inward import (
	cache_selected_size,
	get_finishing_plan_inward_details,
	get_part_value,
)
from essdee_yrp.finishing.packing import (
	get_dynamic_packed_qty,
	get_finishing_packing_summary,
	get_ipd_packing_config,
	prepare_dynamic_batch_dispatch,
	rebuild_finishing_packing_quantities,
)
from essdee_yrp.finishing.reports import (
	get_finishing_dispatch_report,
	get_finishing_packed_details,
)
from essdee_yrp.finishing.rebuild import (
	fetch_quantity,
	get_incomplete_transfer_docs,
)
from essdee_yrp.finishing.status import (
	apply_auto_fp_status,
	cancel_finishing_dispatch_log,
	compute_received_status,
	get_finishing_dispatch_totals,
	get_finishing_plan_total_cutting,
	get_set_item_parts_count,
	record_finishing_dispatch_log,
)
from essdee_yrp.finishing.transactions import (
	cancel_document,
	convert_to_loose_piece_items,
	create_delivery_challan,
	create_grn,
	create_material_receipt,
	create_stock_entry,
	get_primary_values,
	get_delivery_challan_item_list,
	return_items,
)
from essdee_yrp.finishing.views import (
	before_save as prepare_detail_state,
	build_plan_views,
	get_packed_qty,
)


class SDYRPFinishingPlan(Document):
	def onload(self):
		views = build_plan_views(self)
		self.set_onload(
			"finishing_plan_data",
			{
				"primary_values": views["primary_values"],
				"data": views["finishing_inward"],
				"is_set_item": views["is_set_item"],
				"set_attr": views["set_attr"],
			},
		)
		self.set_onload(
			"finishing_qty_data",
			{
				"primary_values": views["primary_values"],
				"data": views["finishing_qty"],
				"rework_details": views["rework_details"],
				"is_set_item": views["is_set_item"],
				"set_attr": views["set_attr"],
			},
		)
		self.set_onload(
			"inward_details",
			{
				"primary_values": views["primary_values"],
				"data": views["inward_details"],
				"is_set_item": views["is_set_item"],
				"set_attr": views["set_attr"],
			},
		)
		self.set_onload("pack_items", views["packed_qty"])
		self.set_onload(
			"finishing_ironing",
			{
				"primary_values": views["primary_values"],
				"data": views["finishing_ironing"],
				"is_set_item": views["is_set_item"],
				"set_attr": views["set_attr"],
			},
		)
		self.set_onload(
			"pack_return",
			{
				"primary_values": views["primary_values"],
				"data": views["pack_return"],
				"is_set_item": views["is_set_item"],
				"set_attr": views["set_attr"],
			},
		)
		self.set_onload(
			"ocr_details",
			{
				"ocr_data": get_ocr_details(self),
				"primary_values": views["primary_values"],
			},
		)
		self.set_onload("finishing_rejection_data", views["rejection_details"])
		self.set_onload("old_lot_data", views["old_lot_data"])
		self.set_onload("old_lot_given_matrix", views["old_lot_given_matrix"])
		self.set_onload("old_lot_received_matrix", views["old_lot_received_matrix"])

	def before_save(self):
		prepare_detail_state(self)

	def get_finishing_plans(self):
		return build_plan_views(self)

	def get_inward_details(self):
		return build_plan_views(self)["inward_details"]

	def get_rework_item_details(self):
		return build_plan_views(self)["rework_details"]

	def get_rejection_details(self, **_kwargs):
		return build_plan_views(self)["rejection_details"]

	def get_packed_qty(self):
		return get_packed_qty(self)

	def get_dynamic_packed_qty(self, grn_names):
		return get_dynamic_packed_qty(self, grn_names)


FinishingPlan = SDYRPFinishingPlan
