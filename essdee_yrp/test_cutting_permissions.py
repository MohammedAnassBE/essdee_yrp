from unittest import TestCase
from unittest.mock import MagicMock, patch

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
	_get_web_cutting_plan_permissions,
	get_recut_print_panel_details,
)


class TestCuttingPermissions(TestCase):
	def test_plan_workspace_exposes_effective_read_permissions(self):
		plan = MagicMock()
		plan.docstatus = 1
		plan.cp_status = "Ready to Cut"
		plan.has_permission.side_effect = lambda ptype: ptype in {"read", "write", "print"}

		def has_permission(doctype, ptype):
			if ptype == "read":
				return doctype in {"SD YRP Cutting LaySheet", "YRP Stock Update"}
			return False

		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.has_permission",
				side_effect=has_permission,
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.has_cls_grammage_approval_role",
				return_value=False,
			),
		):
			permissions = _get_web_cutting_plan_permissions(plan)

		self.assertFalse(permissions["can_read_marker"])
		self.assertTrue(permissions["can_read_laysheet"])
		self.assertFalse(permissions["can_read_movement"])
		self.assertTrue(permissions["can_read_stock_transfers"])
		self.assertFalse(permissions["can_read_recut"])

	def test_recut_summary_requires_child_doctype_read_permission(self):
		plan = MagicMock()
		plan.check_permission = MagicMock()

		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.get_doc",
				return_value=plan,
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.has_permission"
			) as has_permission,
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.get_all"
			) as get_all,
		):
			has_permission.side_effect = PermissionError("not permitted")
			with self.assertRaises(PermissionError):
				get_recut_print_panel_details("CP-TEST", "Recut")

		has_permission.assert_called_once_with(
			"SD YRP Recut and Print Panel", "read", throw=True
		)
		get_all.assert_not_called()
