# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from essdee_yrp.sewing.entry import (
	cancel_sewing_plan_entry,
	get_data_entry_data,
	submit_data_entry_log,
	update_sewing_plan_data,
)
from essdee_yrp.sewing.plan import create_sewing_plan
from essdee_yrp.sewing.read_models import (
	get_consumption_mapping_data,
	get_dashboard_data,
	get_fi_updates_data,
	get_item_summary_data,
	get_item_summary_options,
	get_monthly_summary_data,
	get_monthly_summary_print_data,
	get_scr_data,
	get_sewing_consumption_print_data,
	get_sewing_plan_dpr_data,
	get_sewing_plan_entries,
	get_sp_status_summary,
	get_supplier_lots,
	get_the_lot,
	save_consumption_data,
	update_fi_dates,
)
from essdee_yrp.sewing.strength import get_worker_strength_report


class SDYRPSewingPlan(Document):
	pass


__all__ = [
	"SewingPlan",
	"cancel_sewing_plan_entry",
	"create_sewing_plan",
	"get_data_entry_data",
	"get_consumption_mapping_data",
	"get_dashboard_data",
	"get_fi_updates_data",
	"get_item_summary_data",
	"get_item_summary_options",
	"get_monthly_summary_data",
	"get_monthly_summary_print_data",
	"get_scr_data",
	"get_sewing_consumption_print_data",
	"get_sewing_plan_dpr_data",
	"get_sewing_plan_entries",
	"get_sp_status_summary",
	"get_supplier_lots",
	"get_the_lot",
	"save_consumption_data",
	"submit_data_entry_log",
	"update_sewing_plan_data",
	"update_fi_dates",
]


SewingPlan = SDYRPSewingPlan
