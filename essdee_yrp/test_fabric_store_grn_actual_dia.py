from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.fabric_store.documents import goods_received_note as service


class TestFabricStoreGRNActualDia(TestCase):
	def setUp(self):
		self.enterContext(patch.object(service, "_dimension_fieldnames", return_value=("lot", "received_type")))
		self.enterContext(patch.object(service, "_", side_effect=lambda text: text))
		self.enterContext(patch("essdee_yrp.fabric_grn._", side_effect=lambda text: text))
		self.enterContext(patch("frappe.throw", side_effect=lambda message: self.fail_validation(message)))
		self.enterContext(patch("essdee_yrp.fabric_grn.get_parent_item", return_value="Fabric"))
		self.enterContext(patch("essdee_yrp.fabric_grn.get_dia_attribute", return_value="Dia"))
		self.enterContext(patch("essdee_yrp.fabric_grn._configured_dia_values", return_value=["14", "14.25", "14.5", "15", "15.5", "19"]))
		self.enterContext(patch("essdee_yrp.fabric_grn._variant_attrs", side_effect=self.variant_attrs))
		self.db = self.enterContext(patch("frappe.db", MagicMock()))
		self.db.get_value.side_effect = lambda doctype, name, field: {"A": "Greige-19", "B": "Greige-14"}[name]
		self.rows = [
			self.saved("one", "19", 40, "A", 0),
			self.saved("two", "14", 30, "B", 1),
			self.saved("three", "15", 5, "B", 2),
			self.saved("four", "14.5", 20, "B", 3),
		]

	@staticmethod
	def fail_validation(message):
		raise frappe.ValidationError(message)

	@staticmethod
	def variant_attrs(variant):
		colour, dia = variant.split("-")
		return {"Colour": colour, "Dia": dia}

	@staticmethod
	def saved(name, dia, qty, reference, index):
		return {
			"name": name, "item_variant": f"Greige-{dia}", "quantity": qty,
			"ref_doctype": "YRP Work Order Receivables", "ref_docname": reference,
			"received_type": "Accepted", "lot": "ZZ TEST U4", "row_index": index,
			"rate": 20, "uom": "Kg",
		}

	def browser(self):
		return [
			{**{key: value for key, value in row.items() if key != "name"},
			 "grn_item_name": row["name"], "original_item_variant": row["item_variant"]}
			for row in self.rows
		]

	def merge(self, browser):
		return service._merge_authoritative_rows(self.rows, browser, actual_dia_context={"enabled": True})

	def test_changed_saved_dia_replaces_child_and_preserves_total(self):
		browser = self.browser()
		browser[2].update(item_variant="Greige-15.5", row_index=99, rate=999)
		merged = self.merge(browser)
		self.assertEqual([(row["item_variant"], row["quantity"]) for row in merged], [
			("Greige-19", 40), ("Greige-14", 30), ("Greige-15.5", 5), ("Greige-14.5", 20),
		])
		self.assertEqual(sum(row["quantity"] for row in merged), 95)
		self.assertEqual((merged[2]["name"], merged[2]["row_index"], merged[2]["rate"]), ("three", 2, 20))

	def test_original_variant_fallback_and_child_name_identity(self):
		for identity in ("original_item_variant", "name"):
			with self.subTest(identity=identity):
				browser = self.browser()
				for row in browser:
					name = row.pop("grn_item_name")
					if identity == "name":
						row["name"] = name
						row.pop("original_item_variant")
				browser[2].update(item_variant="Greige-15.5", row_index=99)
				merged = self.merge(browser)
				self.assertEqual(merged[2]["name"], "three")
				self.assertEqual(merged[2]["item_variant"], "Greige-15.5")
				self.assertEqual(sum(row["quantity"] for row in merged), 95)

	def test_changed_saved_dia_and_added_original_dia_have_separate_identities(self):
		for identity in ("grn_item_name", "name"):
			for addition_first in (False, True):
				with self.subTest(identity=identity, addition_first=addition_first):
					browser = self.browser()
					browser[2].update(item_variant="Greige-15.5", quantity=4)
					added = {
						key: value for key, value in browser[2].items()
						if key not in ("grn_item_name", "original_item_variant")
					}
					added.update(item_variant="Greige-15", quantity=1, rate=999)
					if identity == "name":
						for row in browser:
							row["name"] = row.pop("grn_item_name")
							row.pop("original_item_variant")
					browser.insert(0 if addition_first else len(browser), added)
					merged = self.merge(browser)
					self.assertEqual(len(merged), 5)
					replaced = next(row for row in merged if row.get("name") == "three")
					self.assertEqual((replaced["item_variant"], replaced["quantity"], replaced["row_index"]),
						("Greige-15.5", 4, 2))
					addition = next(row for row in merged if row["item_variant"] == "Greige-15")
					self.assertNotIn("name", addition)
					self.assertEqual((addition["quantity"], addition["row_index"], addition["rate"]), (1, 4, 20))
					self.assertEqual(sum(row["quantity"] for row in merged), 95)

	def test_removed_or_zeroed_saved_actual_dia_is_dropped(self):
		for remove in (True, False):
			with self.subTest(remove=remove):
				browser = self.browser()
				if remove:
					browser.pop(2)
				else:
					browser[2]["quantity"] = 0
				merged = self.merge(browser)
				self.assertEqual(len(merged), 3)
				self.assertNotIn("Greige-15", [row["item_variant"] for row in merged])
				self.assertEqual(sum(row["quantity"] for row in merged), 90)

	def test_changed_planned_dia_replaces_planned_row(self):
		browser = self.browser()
		browser[1]["item_variant"] = "Greige-14.25"
		merged = self.merge(browser)
		self.assertNotIn("Greige-14", [row["item_variant"] for row in merged])
		self.assertEqual(merged[1]["name"], "two")
		self.assertEqual(merged[1]["quantity"], 30)
		self.assertEqual(sum(row["quantity"] for row in merged), 95)

	def test_colour_change_on_saved_new_or_zero_row_throws(self):
		for saved in (True, False):
			for qty in (0, 20):
				with self.subTest(saved=saved, qty=qty):
					browser = self.browser()
					changed = browser[3]
					changed.update(item_variant="White-14.5", quantity=qty)
					if not saved:
						changed.pop("grn_item_name")
						changed.pop("original_item_variant")
					with self.assertRaisesRegex(frappe.ValidationError, "only Dia may differ.*Colour changed"):
						self.merge(browser)

	def test_added_dia_has_new_identity_and_inherits_trusted_fields(self):
		browser = self.browser()
		browser[1]["quantity"] = 25
		browser.append({**{key: value for key, value in browser[1].items() if key not in ("grn_item_name", "original_item_variant")},
			"item_variant": "Greige-14.25", "quantity": 5, "rate": 999})
		merged = self.merge(browser)
		self.assertEqual(len(merged), 5)
		self.assertNotIn("name", merged[-1])
		self.assertEqual((merged[-1]["row_index"], merged[-1]["rate"]), (4, 20))
		self.assertEqual(sum(row["quantity"] for row in merged), 95)

	def test_forged_or_duplicate_identity_is_rejected(self):
		for change in ("unknown", "lineage", "duplicate"):
			with self.subTest(change=change):
				browser = self.browser()
				if change == "unknown":
					browser[2]["grn_item_name"] = "unknown"
				elif change == "lineage":
					browser[2]["lot"] = "another lot"
				else:
					browser.append(dict(browser[2]))
				with self.assertRaises(frappe.ValidationError):
					self.merge(browser)

	def groups(self):
		return [{"primary_attribute": "Dia", "items": [
			{"name": "Fabric", "primary_attribute": "Dia", "row_index": 100 + index,
			 "dimensions": {"lot": row["lot"], "received_type": row["received_type"]},
			 "attributes": {"Colour": "Greige"}, "values": {
				 row["item_variant"].split("-")[1]: {
					 "qty": row["quantity"], "ref_doctype": row["ref_doctype"], "ref_docname": row["ref_docname"],
				 },
			 } }
			for index, row in enumerate(self.rows)
		]}]

	def test_display_identity_survives_primary_and_default_cell_ungrouping(self):
		for primary in (True, False):
			with self.subTest(primary=primary):
				groups = self.groups()
				doc = frappe._dict(items=self.rows, correction_items=[])
				doc.run_method = MagicMock()
				doc.get_onload = MagicMock(return_value={"item_details": groups})
				with patch.object(service, "_actual_dia_context", return_value={"enabled": True}):
					groups, _corrections = service._onload_matrices(doc)
				for row, saved in zip(groups[0]["items"], self.rows, strict=True):
					cell = next(iter(row["values"].values()))
					self.assertEqual(cell["grn_item_name"], saved["name"])
					self.assertEqual(cell["original_item_variant"], saved["item_variant"])
					self.assertEqual(cell["is_saved_actual_dia"], saved["name"] in ("three", "four"))
					if not primary:
						row["attributes"]["Dia"] = next(iter(row["values"]))
						row["primary_attribute"] = None
						row["values"] = {"default": cell}
				self.assert_roundtrip(groups)

	def ungroup(self, groups):
		with (
			patch("yrp.stock.save_stock_items.frappe.get_hooks", return_value=[]),
			patch("yrp.stock.save_stock_items.frappe.get_meta", return_value=MagicMock()),
			patch("yrp.stock.save_stock_items.get_dimension_fieldnames", return_value=["lot", "received_type"]),
			patch("yrp.stock.save_stock_items._resolve_or_create_variant", side_effect=lambda template, attrs: f"{attrs['Colour']}-{attrs['Dia']}"),
		):
			flat, present = service._browser_rows({"item_details": deepcopy(groups)}, corrections=False, fallback_rows=[])
		self.assertTrue(present)
		return flat

	def assert_roundtrip(self, groups):
		flat = self.ungroup(groups)
		self.assertEqual([row["grn_item_name"] for row in flat], [row["name"] for row in self.rows])
		self.assertEqual([row["original_item_variant"] for row in flat], [row["item_variant"] for row in self.rows])
		flat[2]["item_variant"] = "Greige-15.5"
		merged = self.merge(flat)
		self.assertEqual(merged[2]["name"], "three")
		self.assertEqual(sum(row["quantity"] for row in merged), 95)

	def test_saved_colour_tampering_in_default_payload_throws(self):
		groups = self.groups()
		service._add_actual_dia_row_identity(groups, self.rows)
		for row in groups[0]["items"]:
			dia, cell = next(iter(row["values"].items()))
			row["attributes"]["Dia"] = dia
			row["primary_attribute"] = None
			row["values"] = {"default": cell}
		groups[0]["items"][3]["attributes"]["Colour"] = "White"
		flat = self.ungroup(groups)
		self.assertEqual(flat[3]["item_variant"], "White-14.5")
		with self.assertRaisesRegex(frappe.ValidationError, "only Dia may differ.*Colour changed"):
			self.merge(flat)

	def test_web_save_routes_saved_dia_replacement_through_merge_owner(self):
		doc = frappe._dict(name="GRN-1", docstatus=0, against="YRP Work Order", against_id="WO-1", items=self.rows, correction_items=[])
		doc.set = lambda key, value: doc.update({key: value})
		doc.save = MagicMock()
		browser = self.browser()
		browser[2]["item_variant"] = "Greige-15.5"
		with (
			patch.object(service, "_get_grn", return_value=doc),
			patch.object(service, "assert_expected_modified"),
			patch.object(service, "_actual_dia_context", return_value={"enabled": True}),
			patch.object(service, "_browser_rows", side_effect=[(browser, True), ([], False)]),
			patch.object(service, "get_goods_received_note_workspace", return_value={}),
			patch("essdee_yrp.fabric_grn.validate_actual_dia_rows") as validate_rows,
		):
			service.save_goods_received_note({"item_details": []}, name=doc.name)
		self.assertEqual(len(doc["items"]), 4)
		self.assertEqual(doc["items"][2]["item_variant"], "Greige-15.5")
		self.assertEqual(sum(row["quantity"] for row in doc["items"]), 95)
		validate_rows.assert_called_once_with(doc)
		doc.save.assert_called_once()
