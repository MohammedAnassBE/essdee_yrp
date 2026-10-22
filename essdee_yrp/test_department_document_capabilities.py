from unittest import TestCase
from unittest.mock import patch

from essdee_yrp.fabric_store import web_workspace as fabric_store
from essdee_yrp.finishing import web_workspace as finishing
from essdee_yrp.merch import web_workspace as merch
from essdee_yrp.merch_purchase import web_workspace as merch_purchase
from essdee_yrp.planning import web_workspace as planning
from essdee_yrp.quality import web_workspace as quality
from essdee_yrp.sewing import web_workspace as sewing

DOCUMENT_SECTIONS = {
	"delivery_challans": "YRP Delivery Challan",
	"goods_received_notes": "YRP Goods Received Note",
}
DEPARTMENTS = {
	"fabric_store": fabric_store,
	"sewing": sewing,
	"finishing": finishing,
	"quality": quality,
	"merch": merch,
	"planning": planning,
	"merch_purchase": merch_purchase,
}


def _sections(module, denied=()):
	def has_permission(doctype=None, ptype="read", *_args, **_kwargs):
		return doctype not in denied

	with patch("frappe.has_permission", side_effect=has_permission):
		return module.get_capabilities()["sections"]


class TestDepartmentDocumentCapabilities(TestCase):
	def test_work_order_departments_expose_delivery_challan_and_grn_sections(self):
		for name, module in DEPARTMENTS.items():
			sections = _sections(module)
			self.assertTrue(sections["work_orders"]["can_read"], name)
			for key, doctype in DOCUMENT_SECTIONS.items():
				with self.subTest(department=name, section=key):
					self.assertTrue(sections[key]["can_read"])
					if name not in {"merch", "merch_purchase"}:
						self.assertEqual(sections[key]["doctype"], doctype)

	def test_document_sections_follow_their_doctype_read_permission(self):
		for name, module in DEPARTMENTS.items():
			sections = _sections(module, denied={"YRP Delivery Challan"})
			with self.subTest(department=name):
				self.assertFalse(sections.get("delivery_challans", {}).get("can_read"))
				self.assertTrue(sections["goods_received_notes"]["can_read"])

	def test_quality_document_sections_are_read_only_and_need_inspection_access(self):
		sections = _sections(quality)
		for key in DOCUMENT_SECTIONS:
			self.assertFalse(sections[key]["can_create"])
		denied = _sections(quality, denied={quality.DOCTYPE})
		for key in DOCUMENT_SECTIONS:
			self.assertFalse(denied[key]["can_read"])
