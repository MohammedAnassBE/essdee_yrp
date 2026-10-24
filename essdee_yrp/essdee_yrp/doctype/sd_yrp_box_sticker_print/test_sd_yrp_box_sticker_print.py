import unittest
import unittest.mock
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe import _dict

from essdee_yrp import lot_pricing
from essdee_yrp.essdee_yrp.doctype.sd_yrp_box_sticker_print import (
	sd_yrp_box_sticker_print as box_sticker_print,
)
from essdee_yrp.finishing.box_sticker import (
	auto_create_box_sticker_print,
	build_box_sticker_details,
	get_missing_box_sticker_prices,
)

BOX_STICKER = "essdee_yrp.finishing.box_sticker"


@contextmanager
def _auto_create_patches(fg_item):
	"""Patch auto_create_box_sticker_print collaborators around the FG Item Master lookup."""
	settings = _dict(non_set_box_sticker="BOX", non_set_piece_sticker=None)
	values = {
		("SD YRP FG Item Master", "FG-1", "pcs_per_box"): 6,
		("Item", "ITEM-1", "primary_attribute"): "Size",
	}
	new_doc = MagicMock()
	new_doc.return_value.name = "BSP-1"
	with ExitStack() as stack:
		enter = stack.enter_context
		enter(patch(f"{BOX_STICKER}.attribute_db.get_value", side_effect=["PPO-1", 0, None]))
		enter(patch(f"{BOX_STICKER}._lock_production_orders"))
		enter(patch(f"{BOX_STICKER}.frappe.db.get_value", side_effect=lambda *args: values.get(args)))
		enter(patch(f"{BOX_STICKER}.frappe.db.exists", return_value=False))
		enter(patch(f"{BOX_STICKER}.get_missing_box_sticker_prices", return_value=[]))
		enter(patch(f"{BOX_STICKER}.frappe.get_doc", return_value=_dict(production_order_details=[])))
		enter(patch(f"{BOX_STICKER}._quantity_by_size", return_value={"S": 10}))
		enter(patch(f"{BOX_STICKER}.get_effective_lot_price_map", return_value={"S": 125}))
		enter(patch(f"{BOX_STICKER}.frappe.get_cached_doc", return_value=settings))
		yield {
			"new_doc": enter(patch(f"{BOX_STICKER}.frappe.new_doc", new_doc)),
			"fg_lookup": enter(patch(f"{BOX_STICKER}.get_fg_item_master", return_value=fg_item)),
		}


class TestBoxStickerPrint(unittest.TestCase):
	def test_explicit_price_map_does_not_treat_ppo_default_as_lot_price(self):
		pricing = {
			"locked": False,
			"prices": {
				"S": {"has_override": False, "override_mrp": None, "effective_mrp": 100},
				"M": {"has_override": True, "override_mrp": 125, "effective_mrp": 125},
			},
		}
		with patch.object(lot_pricing, "get_lot_pricing", return_value=pricing):
			price_map = lot_pricing.get_explicit_lot_price_map("LOT-1", "PPO-TEST")

		self.assertNotIn("S", price_map)
		self.assertEqual(price_map["M"], 125)

	def test_explicit_price_map_accepts_printed_lot_snapshot(self):
		pricing = {
			"locked": True,
			"prices": {
				"S": {"has_override": False, "override_mrp": None, "effective_mrp": 100},
			},
		}
		with patch.object(lot_pricing, "get_lot_pricing", return_value=pricing):
			price_map = lot_pricing.get_explicit_lot_price_map("LOT-1", "PPO-TEST")

		self.assertEqual(price_map, {"S": 100})

	def test_packing_requires_explicit_price_for_each_used_lot_size(self):
		work_order = _dict(
			lot="LOT-1",
			item="ITEM-1",
			work_order_calculated_items=[
				_dict(item_variant="ITEM-S", quantity=10),
				_dict(item_variant="ITEM-M", quantity=12),
			],
		)
		with (
			patch(
				"essdee_yrp.finishing.box_sticker.attribute_db.get_value",
				side_effect=["PPO-TEST", 0],
			),
			patch(
				"essdee_yrp.finishing.box_sticker.frappe.db.get_value",
				return_value="Size",
			),
			patch(
				"essdee_yrp.finishing.box_sticker.get_variant_attr_details",
				side_effect=lambda item: {"Size": item.removeprefix("ITEM-")},
			),
			patch(
				"essdee_yrp.finishing.box_sticker.get_explicit_lot_price_map",
				return_value={"M": 125},
			) as explicit_prices,
			patch("essdee_yrp.finishing.box_sticker._lock_production_orders") as lock_production_orders,
		):
			missing = get_missing_box_sticker_prices(work_order, for_update=True)

		self.assertEqual(missing, ["S"])
		lock_production_orders.assert_called_once_with("PPO-TEST")
		explicit_prices.assert_called_once_with("LOT-1", "PPO-TEST", for_update=True)

	def test_preview_posts_zpl_in_the_request_body(self):
		client = Path(box_sticker_print.__file__).with_suffix(".js").read_text(encoding="utf-8")
		self.assertIn('method: "POST"', client)
		self.assertIn("body: result.code", client)
		self.assertNotIn("encodeURIComponent(result.code)", client)

	def test_template_uses_the_selected_printer_dpi(self):
		doc = SimpleNamespace(piece_per_box=10, use_item_name=1, lot="LOT-1")
		with patch.object(box_sticker_print.frappe, "render_template", return_value="ZPL") as render:
			result = box_sticker_print.get_template(
				doc,
				{"quantity": 2, "mrp": 125, "size": "M"},
				"{{ dpi }}",
				1,
				"FG-1",
				dpi=300,
			)

		self.assertEqual(result, "ZPL")
		self.assertEqual(render.call_args.args[1]["dpi"], 300)

	def test_desk_print_needs_only_read_permission(self):
		client = Path(box_sticker_print.__file__).with_suffix(".js").read_text(encoding="utf-8")
		self.assertNotIn("perm?.[0]?.write", client)
		doc = MagicMock(docstatus=1, lot="LOT-1", print_format="FMT", fg_item="FG-1", size=None)
		with (
			patch.object(box_sticker_print.frappe, "get_doc", return_value=doc),
			patch.object(box_sticker_print, "_lock_linked_production_order"),
			patch.object(box_sticker_print, "_raw_code", return_value="RAW"),
		):
			box_sticker_print.get_print_format("BSP-1", "[]", "300dpi")
		doc.check_permission.assert_any_call("read")
		self.assertNotIn(unittest.mock.call("write"), doc.check_permission.call_args_list)

	def test_desk_print_rollback_needs_only_read_permission(self):
		parent = MagicMock(lot="LOT-1")
		format_doc = MagicMock(labels_per_row=1)
		with (
			patch.object(box_sticker_print.frappe, "get_doc", side_effect=[format_doc, parent]),
			patch.object(
				box_sticker_print.frappe.db, "sql", return_value=[_dict(printed_quantity=3, parent="BSP-1")]
			),
			patch.object(box_sticker_print, "_lock_linked_production_order"),
			patch.object(box_sticker_print.attribute_db, "set_value") as set_value,
		):
			box_sticker_print.override_print_quantity('[{"doc_name": "ROW-1", "quantity": 2}]', "FMT")
		parent.check_permission.assert_called_once_with("read")
		set_value.assert_called_once_with("SD YRP Box Sticker Print Detail", "ROW-1", "printed_quantity", 1)

	def test_save_does_not_refetch_or_overwrite_mrp(self):
		doc = SimpleNamespace(
			box_sticker_print_details=[_dict(size="S", quantity=1, allow_excess_quantity=0, mrp=999)]
		)
		frappe_mock = MagicMock()
		with patch.object(box_sticker_print, "frappe", frappe_mock):
			box_sticker_print.BoxStickerPrint.before_validate(doc)
		self.assertEqual(doc.box_sticker_print_details[0].mrp, 999)
		frappe_mock.db.get_value.assert_not_called()

	def test_work_order_builds_sticker_rows_from_resolved_price_map(self):
		self.assertEqual(
			build_box_sticker_details(["S", "M"], {"S": 100, "M": 0}, {"S": 125, "M": 135}),
			[
				{
					"size": "S",
					"quantity": 100.0,
					"mrp": 125.0,
					"allow_excess_quantity": 0,
					"allow_excess_percentage": 5,
				},
				{
					"size": "M",
					"quantity": 0.0,
					"mrp": 135.0,
					"allow_excess_quantity": 1,
					"allow_excess_percentage": 5,
				},
			],
		)

	def test_work_order_without_fg_item_master_skips_with_message(self):
		with (
			_auto_create_patches(fg_item=None) as mocks,
			patch(f"{BOX_STICKER}.frappe.msgprint") as msgprint,
		):
			self.assertEqual(auto_create_box_sticker_print(_dict(lot="LOT-1", item="ITEM-1")), [])
		self.assertIn("ITEM-1", msgprint.call_args.args[0])
		mocks["new_doc"].assert_not_called()

	def test_work_order_box_sticker_links_the_resolved_fg_item_master(self):
		with _auto_create_patches(fg_item="FG-1") as mocks:
			created = auto_create_box_sticker_print(_dict(lot="LOT-1", item="ITEM-1", name="WO-1"))
		self.assertEqual(created, ["BSP-1"])
		values = mocks["new_doc"].return_value.update.call_args.args[0]
		self.assertEqual((values["fg_item"], values["piece_per_box"]), ("FG-1", 6))
		mocks["fg_lookup"].assert_called_once_with("ITEM-1")

	def test_work_order_box_sticker_rows_take_the_production_order_lot_price(self):
		with _auto_create_patches(fg_item="FG-1") as mocks:
			auto_create_box_sticker_print(_dict(lot="LOT-1", item="ITEM-1", name="WO-1"))
		rows = mocks["new_doc"].return_value.set.call_args.args[1]
		self.assertEqual([(row["size"], row["mrp"]) for row in rows], [("S", 125.0)])

	def test_effective_lot_price_is_production_order_mrp_unless_lot_override(self):
		production_order = _dict(
			doctype="YRP Production Order",
			item="ITEM-1",
			production_order_details=[_dict(item_variant="V-S", mrp=110), _dict(item_variant="V-M", mrp=120)],
			lot_price_overrides=[_dict(lot="LOT-1", size="M", mrp=135)],
		)
		with (
			patch.object(lot_pricing.attribute_db, "get_value", return_value="PPO-1"),
			patch.object(lot_pricing.frappe, "get_doc", return_value=production_order),
			patch.object(lot_pricing.frappe, "get_value", return_value="Size"),
			patch.object(
				lot_pricing, "get_variant_attr_details", side_effect=lambda variant: {"Size": variant[-1]}
			),
			patch.object(
				lot_pricing,
				"get_lot_print_state",
				return_value={"locked": False, "documents": [], "prices": {}},
			),
		):
			price_map = lot_pricing.get_effective_lot_price_map("LOT-1", "PPO-1")
		self.assertEqual(price_map, {"S": 110.0, "M": 135.0})

	def test_migrated_packing_work_order_has_complete_price_scope(self):
		work_order = "WO-2627-00839"
		if not frappe.db.exists("YRP Work Order", work_order):
			self.skipTest("Migrated packing Work Order oracle is unavailable")
		self.assertEqual(get_missing_box_sticker_prices(work_order), [])
