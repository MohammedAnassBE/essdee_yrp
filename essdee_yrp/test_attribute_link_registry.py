import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from yrp.attribute_links import attribute_for, fields

SNAPSHOT = Path(__file__).with_name("test_attribute_link_snapshot.json")
CONTEXT_FIELDS = (
	"dependent_attribute",
	"po_dependent_attribute",
	"set_item_attribute",
	"stiching_attribute",
	"packing_attribute",
	"primary_attribute",
	"attribute",
)


class TestAttributeLinkRegistry(IntegrationTestCase):
	"""Each registered field resolves to the attribute it resolved to before the registry moved to essdee_yrp."""

	def setUp(self):
		frappe.db.set_single_value("SD YRP IPD Settings", "default_packing_attribute", "Colour")
		frappe.db.set_single_value("SD YRP IPD Settings", "default_dia_attribute", "Dia")
		frappe.db.set_single_value("YRP Settings", "po_dependent_attribute", "Stage")

	def test_every_registered_field_keeps_its_resolved_attribute(self):
		expected = json.loads(SNAPSHOT.read_text())
		registered = {f"{doctype}|{field}" for doctype, names in fields().items() for field in names}
		self.assertEqual(registered, set(expected))
		context = {name: f"ctx-{name}" for name in CONTEXT_FIELDS}
		for key, (without_context, with_context) in expected.items():
			doctype, field = key.split("|")
			with self.subTest(field=key):
				self.assertEqual(attribute_for(frappe._dict(doctype=doctype), field), without_context)
				self.assertEqual(attribute_for(frappe._dict(doctype=doctype, **context), field), with_context)
