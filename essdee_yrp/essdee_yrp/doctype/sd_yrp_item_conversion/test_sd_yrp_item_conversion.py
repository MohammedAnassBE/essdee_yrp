import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate, nowtime

DOCTYPE = "SD YRP Item Conversion"
SLE = "YRP Stock Ledger Entry"


def find_stocked_variant(min_qty=2):
	"""Return one positive, valued Bin of an enabled stock template variant, or None."""
	rows = frappe.db.sql(
		"""
		SELECT bin.item_code, bin.warehouse, bin.lot, bin.received_type, bin.stock_uom, item.variant_of
		FROM `tabYRP Bin` bin
		JOIN `tabItem` item ON item.name = bin.item_code
		JOIN `tabItem` template ON template.name = item.variant_of
		WHERE bin.actual_qty >= %s AND bin.valuation_rate > 0
			AND bin.lot IS NOT NULL AND bin.received_type IS NOT NULL
			AND template.is_stock_item = 1 AND template.disabled = 0
		ORDER BY bin.modified DESC
		LIMIT 1
		""",
		(min_qty,),
		as_dict=True,
	)
	return rows[0] if rows else None


def make_conversion(source, from_qty=1, to_qty=2):
	row = {
		"item": source.item_code,
		"lot": source.lot,
		"received_type": source.received_type,
		"uom": source.stock_uom,
	}
	return frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"naming_series": "IC-.YYYY.-",
			"warehouse": source.warehouse,
			"from_item": source.variant_of,
			"to_item": source.variant_of,
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"from_items": [{**row, "qty": from_qty}],
			"to_items": [{**row, "qty": to_qty}],
		}
	)


class TestSDYRPItemConversion(IntegrationTestCase):
	def test_requires_exactly_one_from_and_one_to_row(self):
		doc = frappe.new_doc(DOCTYPE)
		doc.append("from_items", {"item": "FROM-1"})
		doc.append("from_items", {"item": "FROM-2"})
		doc.append("to_items", {"item": "TO-1"})
		with self.assertRaisesRegex(frappe.ValidationError, "exactly one From Item row"):
			doc.validate_single_item_rows()

		doc.set("from_items", [{"item": "FROM-1"}])
		doc.append("to_items", {"item": "TO-2"})
		with self.assertRaisesRegex(frappe.ValidationError, "exactly one To Item row"):
			doc.validate_single_item_rows()

	def test_submit_issues_from_and_receives_to_then_cancel_reverses(self):
		source = find_stocked_variant()
		if not source:
			self.skipTest("Item Conversion ledger test needs a valued stock Bin")
		bin_filters = {key: source[key] for key in ("item_code", "warehouse", "lot", "received_type")}
		qty_before = flt(frappe.db.get_value("YRP Bin", bin_filters, "actual_qty"))
		doc = make_conversion(source)
		doc.insert()
		self.assertAlmostEqual(doc.to_items[0].rate * 2, doc.from_items[0].rate, places=6)
		self.assertEqual(doc.difference_amount, 0)
		doc.submit()

		entries = frappe.get_all(
			SLE,
			filters={"voucher_type": DOCTYPE, "voucher_no": doc.name, "is_cancelled": 0},
			fields=[
				"item",
				"warehouse",
				"lot",
				"received_type",
				"qty",
				"stock_value_difference",
				"voucher_detail_no",
			],
		)
		by_row = {entry.voucher_detail_no: entry for entry in entries}
		self.assertEqual(len(entries), 2)
		outgoing = by_row[doc.from_items[0].name]
		incoming = by_row[doc.to_items[0].name]
		self.assertEqual(flt(outgoing.qty), -flt(doc.from_items[0].stock_qty))
		self.assertEqual(flt(incoming.qty), flt(doc.to_items[0].stock_qty))
		for entry in (outgoing, incoming):
			self.assertEqual(
				(entry.item, entry.warehouse, entry.lot, entry.received_type),
				(source.item_code, source.warehouse, source.lot, source.received_type),
			)
		self.assertLess(flt(outgoing.stock_value_difference), 0)
		self.assertAlmostEqual(
			flt(outgoing.stock_value_difference) + flt(incoming.stock_value_difference), 0, places=2
		)
		doc.reload()
		self.assertEqual(doc.from_total_amount, doc.to_total_amount)
		self.assertEqual(
			flt(frappe.db.get_value("YRP Bin", bin_filters, "actual_qty")),
			qty_before + flt(incoming.qty) + flt(outgoing.qty),
		)

		doc.cancel()
		self.assertFalse(
			frappe.db.exists(SLE, {"voucher_type": DOCTYPE, "voucher_no": doc.name, "is_cancelled": 0})
		)
		self.assertEqual(flt(frappe.db.get_value("YRP Bin", bin_filters, "actual_qty")), qty_before)
