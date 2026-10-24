import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from essdee_yrp.fabric_store.documents.goods_received_note import (
	get_goods_received_note_workspace,
	save_goods_received_note,
)

HEADER_FIELDS = (
	"posting_date",
	"posting_time",
	"delivery_location",
	"from_warehouse",
	"to_warehouse",
	"supplier_address",
	"delivery_address",
)


def _work_order_with_pending_receivables():
	names = frappe.db.sql(
		"""
		SELECT wo.name
		FROM `tabYRP Work Order` wo
		INNER JOIN `tabYRP Work Order Receivables` receivable ON receivable.parent = wo.name
		WHERE wo.docstatus = 1 AND wo.open_status != 'Close' AND COALESCE(wo.is_rework, 0) = 0
			AND COALESCE(wo.includes_packing, 0) = 0 AND wo.process_name NOT LIKE '%%Cutting%%'
			AND receivable.pending_quantity > 0
		GROUP BY wo.name
		ORDER BY wo.creation DESC
		LIMIT 1
		""",
		pluck=True,
	)
	return names[0] if names else None


def _cells(groups):
	for group in groups or []:
		for entry in group.get("items") or []:
			yield from (entry.get("values") or {}).values()


def _zeroed(groups):
	for cell in _cells(groups):
		cell["qty"] = 0
		cell["secondary_qty"] = 0
	return groups


def _pending_quantities(work_order):
	return frappe.get_all(
		"YRP Work Order Receivables",
		filters={"parent": work_order},
		fields=["name", "pending_quantity"],
		order_by="name",
	)


class TestGoodsReceivedNoteDraftWithoutQuantity(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.work_order = _work_order_with_pending_receivables()
		if not self.work_order:
			self.skipTest("No open Work Order with pending receivables on this site.")

	def tearDown(self):
		frappe.db.rollback()

	def save_empty(self, additional_grn=0):
		source = {"work_order": self.work_order, "additional_grn": additional_grn}
		workspace = get_goods_received_note_workspace(source=source)
		values = {**source, **{key: workspace["values"].get(key) for key in HEADER_FIELDS}}
		values["item_details"] = _zeroed(workspace["matrices"]["items"])
		values["correction_item_details"] = _zeroed(workspace["matrices"]["correction_items"])
		return save_goods_received_note(values)

	def test_empty_normal_draft_saves_and_reopens_with_source_rows(self):
		pending_before = _pending_quantities(self.work_order)
		workspace = self.save_empty()
		doc = frappe.get_doc("YRP Goods Received Note", workspace["record"]["name"])
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(doc.items, [])
		self.assertEqual(flt(doc.total_received_quantity), 0)
		cells = list(_cells(workspace["matrices"]["items"]))
		self.assertTrue(cells)
		self.assertFalse(any(flt(cell.get("qty")) for cell in cells))
		self.assertEqual(_pending_quantities(self.work_order), pending_before)

	def test_empty_additional_draft_saves(self):
		workspace = self.save_empty(additional_grn=1)
		doc = frappe.get_doc("YRP Goods Received Note", workspace["record"]["name"])
		self.assertEqual(doc.additional_grn, 1)
		self.assertEqual(doc.items, [])
		self.assertTrue(list(_cells(workspace["matrices"]["items"])))

	def test_empty_draft_accepts_quantity_on_next_save(self):
		workspace = self.save_empty()
		groups = workspace["matrices"]["items"]
		next(iter(_cells(groups)))["qty"] = 1
		save_goods_received_note(
			{"item_details": groups},
			name=workspace["record"]["name"],
			expected_modified=workspace["record"]["modified"],
		)
		doc = frappe.get_doc("YRP Goods Received Note", workspace["record"]["name"])
		self.assertEqual(len(doc.items), 1)
		self.assertEqual(flt(doc.total_received_quantity), 1)

	def test_normal_save_keeps_entered_quantities(self):
		source = {"work_order": self.work_order}
		workspace = get_goods_received_note_workspace(source=source)
		entered = sum(flt(cell.get("qty")) for cell in _cells(workspace["matrices"]["items"]))
		values = {**source, **{key: workspace["values"].get(key) for key in HEADER_FIELDS}}
		values["item_details"] = workspace["matrices"]["items"]
		saved = save_goods_received_note(values)
		doc = frappe.get_doc("YRP Goods Received Note", saved["record"]["name"])
		self.assertGreater(entered, 0)
		self.assertTrue(doc.items)
		self.assertAlmostEqual(flt(doc.total_received_quantity), entered, places=3)

	def test_submit_empty_draft_requires_a_quantity(self):
		workspace = self.save_empty()
		with self.assertRaisesRegex(frappe.ValidationError, "at least one row before submitting"):
			save_goods_received_note(
				{},
				name=workspace["record"]["name"],
				submit=True,
				expected_modified=workspace["record"]["modified"],
			)
		self.assertEqual(
			frappe.db.get_value("YRP Goods Received Note", workspace["record"]["name"], "docstatus"), 0
		)
