import json
from unittest.mock import MagicMock, patch

import frappe
from frappe import _dict
from frappe.tests import UnitTestCase

from essdee_yrp.cut_panel_store import box_sticker_workspace as workspace
from essdee_yrp.cut_panel_store.box_sticker_workspace import (
	BOX_STICKER_DOCTYPE,
	confirm_box_sticker_print,
	execute_box_sticker_command,
	get_box_sticker_editor,
	get_box_sticker_preview,
	get_box_sticker_print_recovery,
	get_configured_box_sticker_printers,
	preview_box_sticker_source,
	reserve_box_sticker_print,
	rollback_box_sticker_print,
	save_box_sticker,
)


MODULE = "essdee_yrp.cut_panel_store.box_sticker_workspace"


def detail(
	name,
	size,
	quantity,
	mrp,
	*,
	printed_quantity=0,
	allow_excess_quantity=0,
	allow_excess_percentage=5,
	parent="BSP-1",
):
	return _dict(
		name=name,
		parent=parent,
		size=size,
		quantity=quantity,
		mrp=mrp,
		printed_quantity=printed_quantity,
		allow_excess_quantity=allow_excess_quantity,
		allow_excess_percentage=allow_excess_percentage,
	)


def box_doc(*, name="BSP-1", docstatus=1, modified="M1", rows=None):
	doc = MagicMock()
	doc.doctype = BOX_STICKER_DOCTYPE
	doc.name = name
	doc.docstatus = docstatus
	doc.modified = modified
	doc.lot = "LOT-1"
	doc.fg_item = "FG-1"
	doc.size = None
	doc.use_item_name = 0
	doc.display_name = "FG One"
	doc.print_format = "BOX-FORMAT"
	doc.piece_per_box = 10
	doc.against = None
	doc.against_id = None
	doc.box_sticker_print_details = rows or []
	return doc


def reservation_row(*, state="Active", payload_rows=None, user="Administrator"):
	if payload_rows is None:
		payload_rows = [{"name": "ROW-S", "delta": 4, "before": 2, "after": 6}]
	return _dict(
		name="request-12345678",
		request_id="request-12345678",
		box_sticker_print="BSP-1",
		requested_by=user,
		state=state,
		fingerprint="FINGERPRINT",
		printer_type="300dpi",
		expected_modified="M1",
		payload_json=json.dumps(payload_rows),
		zpl="^XA-STORED^XZ",
	)


class TestCutPanelStoreBoxStickerWorkspace(UnitTestCase):
	def test_editor_returns_authoritative_totals_and_permissions(self):
		doc = box_doc(
			rows=[detail("ROW-S", "S", 10, 125, printed_quantity=4, allow_excess_percentage=10)]
		)
		with patch(f"{MODULE}.frappe.get_doc", return_value=doc):
			payload = get_box_sticker_editor("BSP-1")

		row = payload["record"]["rows"][0]
		self.assertEqual(row["allowed_quantity"], 11)
		self.assertEqual(row["remaining_quantity"], 7)
		self.assertEqual(row["printed_quantity"], 4)
		self.assertTrue(payload["permissions"]["can_print"])
		self.assertEqual(payload["context"]["display_name"], "FG One")
		doc.check_permission.assert_called_with("read")

	def test_source_preview_keeps_server_size_and_mrp(self):
		lot = MagicMock()
		fg_item = MagicMock()
		fg_item.display_name = "New Shirt"
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", side_effect=[lot, fg_item]),
			patch(
				f"{MODULE}.get_fg_details",
				return_value=[{"size": "S", "mrp": 125}, {"size": "M", "mrp": 135}],
			),
		):
			payload = preview_box_sticker_source(
				"LOT-1",
				"FG-1",
				{
					"rows": [
						{"size": "S", "mrp": 1, "quantity": 8, "allow_excess_percentage": 10},
						{"size": "M", "mrp": 2, "quantity": 0, "allow_excess_percentage": 5},
					]
				},
			)

		self.assertEqual([row["size"] for row in payload["rows"]], ["S", "M"])
		self.assertEqual([row["mrp"] for row in payload["rows"]], [125.0, 135.0])
		self.assertEqual([row["quantity"] for row in payload["rows"]], [8, 0])
		self.assertEqual([row["allow_excess_quantity"] for row in payload["rows"]], [0, 0])
		self.assertEqual(payload["context"]["display_name"], "New Shirt")
		lot.check_permission.assert_called_with("read")
		fg_item.check_permission.assert_called_with("read")

	def test_source_preview_rejects_missing_or_forged_sizes(self):
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=MagicMock()),
			patch(
				f"{MODULE}.get_fg_details",
				return_value=[{"size": "S", "mrp": 125}, {"size": "M", "mrp": 135}],
			),
			self.assertRaises(frappe.ValidationError),
		):
			preview_box_sticker_source(
				"LOT-1",
				"FG-1",
				{"rows": [{"size": "XL", "quantity": 8}]},
			)

	def test_save_rejects_stale_existing_document(self):
		doc = box_doc(docstatus=0, modified="NEW")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
			):
			save_box_sticker({"rows": []}, name="BSP-1", expected_modified="OLD")

	def test_existing_save_requires_expected_modified(self):
		doc = box_doc(docstatus=0, modified="M1")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			save_box_sticker({"rows": []}, name="BSP-1")

	def test_save_uses_server_row_identity_and_mrp(self):
		doc = box_doc(name="BSP-NEW", docstatus=0, rows=[])
		lot = MagicMock()
		fg_item = MagicMock()
		print_format = MagicMock()
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.new_doc", return_value=doc),
			patch(f"{MODULE}.frappe.get_doc", side_effect=[lot, fg_item, print_format]),
			patch(f"{MODULE}.get_fg_details", return_value=[{"size": "S", "mrp": 125}]),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-NEW"}),
		):
			payload = save_box_sticker(
				{
					"lot": "LOT-1",
					"fg_item": "FG-1",
					"print_format": "BOX-FORMAT",
					"use_item_name": 1,
					"rows": [{"size": "S", "mrp": 1, "quantity": 10, "allow_excess_percentage": 7}],
				},
			)

		self.assertEqual(payload["name"], "BSP-NEW")
		rows = doc.set.call_args.args[1]
		self.assertEqual(rows[0]["size"], "S")
		self.assertEqual(rows[0]["mrp"], 125.0)
		self.assertEqual(rows[0]["quantity"], 10)
		self.assertEqual(rows[0]["allow_excess_percentage"], 7)
		doc.save.assert_called_once()

	def test_new_manual_document_rejects_all_zero_quantities(self):
		doc = box_doc(name="BSP-NEW", docstatus=0, rows=[])
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.new_doc", return_value=doc),
			patch(f"{MODULE}.frappe.get_doc", return_value=MagicMock()),
			patch(f"{MODULE}.get_fg_details", return_value=[{"size": "S", "mrp": 125}]),
			self.assertRaises(frappe.ValidationError),
		):
			save_box_sticker(
				{
					"lot": "LOT-1",
					"fg_item": "FG-1",
					"print_format": "BOX-FORMAT",
					"rows": [{"size": "S", "quantity": 0}],
				}
			)

	def test_save_rejects_forged_existing_child_name(self):
		doc = box_doc(
			docstatus=0,
			rows=[detail("ROW-S", "S", 10, 125)],
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, MagicMock(), MagicMock(), MagicMock()]),
			patch(f"{MODULE}.get_fg_details", return_value=[{"size": "S", "mrp": 125}]),
			self.assertRaises(frappe.ValidationError),
		):
			save_box_sticker(
				{
					"lot": "LOT-1",
					"fg_item": "FG-1",
					"print_format": "BOX-FORMAT",
					"rows": [{"name": "FORGED", "size": "S", "quantity": 10}],
				},
				name="BSP-1",
				expected_modified="M1",
			)

	def test_save_preserves_server_mrp_snapshot_for_an_unchanged_source(self):
		doc = box_doc(
			docstatus=0,
			rows=[detail("ROW-S", "S", 10, 150)],
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, MagicMock(), MagicMock(), MagicMock()]),
			patch(f"{MODULE}.get_fg_details", return_value=[{"size": "S", "mrp": 125}]),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1"}),
		):
			save_box_sticker(
				{
					"lot": "LOT-1",
					"fg_item": "FG-1",
					"print_format": "BOX-FORMAT",
					"rows": [{"name": "ROW-S", "size": "S", "mrp": 1, "quantity": 10}],
				},
				name="BSP-1",
				expected_modified="M1",
			)

		rows = doc.set.call_args.args[1]
		self.assertEqual(rows[0]["mrp"], 150.0)

	def test_partial_existing_save_preserves_optional_server_fields(self):
		doc = box_doc(
			docstatus=0,
			rows=[detail("ROW-S", "S", 10, 150)],
		)
		doc.size = "PACK-SIZE"
		doc.use_item_name = 1
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, MagicMock(), MagicMock(), MagicMock()]),
			patch(f"{MODULE}.get_fg_details", return_value=[{"size": "S", "mrp": 125}]),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1"}),
		):
			save_box_sticker(
				{"rows": [{"name": "ROW-S", "size": "S", "quantity": 10}]},
				name="BSP-1",
				expected_modified="M1",
			)

		self.assertEqual(doc.size, "PACK-SIZE")
		self.assertEqual(doc.use_item_name, 1)

	def test_lifecycle_rechecks_permission_state_and_staleness(self):
		doc = box_doc(docstatus=0, modified="M1")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._revalidate_saved_draft"),
			patch(f"{MODULE}._record_payload", return_value={"docstatus": 1}),
		):
			result = execute_box_sticker_command("BSP-1", "submit", expected_modified="M1")

		self.assertEqual(result["docstatus"], 1)
		doc.check_permission.assert_called_with("submit")
		doc.submit.assert_called_once()

		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.ValidationError),
		):
			execute_box_sticker_command("BSP-1", "cancel", expected_modified="M1")

	def test_lifecycle_checks_permission_before_disclosing_staleness(self):
		doc = box_doc(docstatus=0, modified="NEW")
		doc.check_permission.side_effect = frappe.PermissionError
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.PermissionError),
		):
			execute_box_sticker_command("BSP-1", "submit", expected_modified="OLD")

	def test_lifecycle_requires_expected_modified(self):
		doc = box_doc(docstatus=0, modified="M1")
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			execute_box_sticker_command("BSP-1", "submit")

	def test_unsupported_lifecycle_command_does_not_load_the_named_record(self):
		with (
			patch(f"{MODULE}.frappe.get_doc") as get_doc,
			self.assertRaises(frappe.ValidationError),
		):
			execute_box_sticker_command("BSP-SECRET", "delete", expected_modified="M1")

		get_doc.assert_not_called()

	def test_combined_save_submit_checks_submit_permission_before_saving(self):
		doc = box_doc(name="BSP-NEW", docstatus=0, rows=[])

		def permission(permission):
			if permission == "submit":
				raise frappe.PermissionError

		doc.check_permission.side_effect = permission
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.new_doc", return_value=doc),
			patch(f"{MODULE}._canonical_source_rows", return_value=[{"size": "S", "quantity": 1, "allow_excess_quantity": 0}]),
			patch(f"{MODULE}._validate_print_format"),
			self.assertRaises(frappe.PermissionError),
		):
			save_box_sticker(
				{"lot": "LOT-1", "fg_item": "FG-1", "print_format": "BOX-FORMAT"},
				submit=True,
			)

		doc.save.assert_not_called()

	def test_preview_is_read_checked_and_returns_zpl_aliases(self):
		doc = box_doc(docstatus=0, rows=[detail("ROW-S", "S", 10, 125)])
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._validate_print_format", return_value=_dict(labels_per_row=2)),
			patch(
				f"{MODULE}.get_raw_code",
				return_value={"code": "^XA^XZ", "height": 4, "width": 6},
			),
		):
			payload = get_box_sticker_preview("BSP-1")

		self.assertEqual(payload["code"], "^XA^XZ")
		self.assertEqual(payload["zpl"], "^XA^XZ")
		self.assertEqual(payload["raw"], "^XA^XZ")
		doc.check_permission.assert_called_with("read")

	def test_preview_rejects_an_invalid_label_count_with_a_safe_validation_error(self):
		doc = box_doc(docstatus=0, rows=[detail("ROW-S", "S", 10, 125)])
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._validate_print_format", return_value=_dict(labels_per_row=0)),
			patch(f"{MODULE}.get_raw_code") as renderer,
			self.assertRaises(frappe.ValidationError),
		):
			get_box_sticker_preview("BSP-1")

		renderer.assert_not_called()

	def test_configured_printers_are_filtered_after_read_permission(self):
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True) as permission,
			patch(f"{MODULE}.get_printer", return_value=["Zebra-A"]),
		):
			printers = get_configured_box_sticker_printers(["Zebra-A", "Office"])

		self.assertEqual(printers, ["Zebra-A"])
		permission.assert_called_once_with(BOX_STICKER_DOCTYPE, ptype="read", throw=True)

	def test_print_lock_order_is_production_order_then_box_sticker_parent(self):
		doc = box_doc()
		events = []
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._lock_linked_production_order", side_effect=lambda lot: events.append("production-order")),
			patch(f"{MODULE}.frappe.db.sql", side_effect=lambda *args, **kwargs: events.append("box-sticker")),
		):
			workspace._lock_box_sticker("BSP-1", expected_modified="M1")

		self.assertEqual(events, ["production-order", "box-sticker"])

	def test_reservation_requires_expected_modified(self):
		doc = box_doc()
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			workspace._lock_box_sticker("BSP-1")

	def test_reservation_claim_is_inserted_and_locked_in_sql(self):
		row = reservation_row(state="Preparing")
		with (
			patch(f"{MODULE}.now_datetime", return_value="2026-10-07 12:00:00"),
			patch(
				f"{MODULE}.frappe.db.sql",
				side_effect=[[], [(1,)], [row]],
			) as sql,
		):
			claimed, inserted = workspace._claim_reservation(
				request_id="request-12345678",
				box_sticker="BSP-1",
				user="Administrator",
				fingerprint="FINGERPRINT",
				printer_type="300dpi",
				expected_modified="M1",
			)

		self.assertTrue(inserted)
		self.assertEqual(claimed.request_id, "request-12345678")
		self.assertIn("INSERT IGNORE", sql.call_args_list[0].args[0])
		self.assertIn("FOR UPDATE", sql.call_args_list[2].args[0])

	def test_reservation_claim_does_not_disclose_a_foreign_owner(self):
		foreign = reservation_row(state="Active", user="other@example.com")
		with (
			patch(f"{MODULE}.now_datetime", return_value="2026-10-07 12:00:00"),
			patch(f"{MODULE}.frappe.db.sql", side_effect=[[], [(0,)]]),
			patch(f"{MODULE}._lock_reservation", return_value=foreign),
			self.assertRaises(frappe.PermissionError) as error,
		):
			workspace._claim_reservation(
				request_id="request-12345678",
				box_sticker="BSP-1",
				user="Administrator",
				fingerprint="FINGERPRINT",
				printer_type="300dpi",
				expected_modified="M1",
			)

		self.assertEqual(str(error.exception), "The print reservation is not available.")

	def test_reservation_claim_and_state_participate_in_the_database_transaction(self):
		request_id = f"test-request-{frappe.generate_hash(length=16)}"
		try:
			claimed, inserted = workspace._claim_reservation(
				request_id=request_id,
				box_sticker="BSP-TRANSACTION-TEST",
				user="Administrator",
				fingerprint="TRANSACTION-FINGERPRINT",
				printer_type="300dpi",
				expected_modified="2026-10-07 12:00:00",
			)
			self.assertTrue(inserted)
			self.assertEqual(claimed.state, "Preparing")
			workspace._update_reservation(
				request_id,
				state="Active",
				payload_json='[{"name":"ROW-S","delta":4,"before":2,"after":6}]',
				zpl="^XA-TRANSACTION^XZ",
			)

			frappe.db.savepoint("box_sticker_reservation_state")
			workspace._update_reservation(request_id, state="Confirmed")
			self.assertEqual(
				frappe.db.get_value(workspace.RESERVATION_DOCTYPE, request_id, "state"),
				"Confirmed",
			)
			frappe.db.rollback(save_point="box_sticker_reservation_state")
			self.assertEqual(
				frappe.db.get_value(workspace.RESERVATION_DOCTYPE, request_id, "state"),
				"Active",
			)

			replayed, replay_inserted = workspace._claim_reservation(
				request_id=request_id,
				box_sticker="BSP-TRANSACTION-TEST",
				user="Administrator",
				fingerprint="TRANSACTION-FINGERPRINT",
				printer_type="300dpi",
				expected_modified="2026-10-07 12:00:00",
			)
			self.assertFalse(replay_inserted)
			self.assertEqual(replayed.state, "Active")
			self.assertEqual(replayed.zpl, "^XA-TRANSACTION^XZ")
		finally:
			frappe.db.delete(workspace.RESERVATION_DOCTYPE, {"name": request_id})

	def test_requested_rows_normalises_one_input_exactly_once(self):
		self.assertEqual(
			workspace._requested_rows([{"doc_name": "ROW-S", "quantity": 3}]),
			[{"name": "ROW-S", "quantity": 3}],
		)

	def test_same_request_retry_returns_durable_result_without_incrementing_again(self):
		doc = box_doc(rows=[detail("ROW-S", "S", 10, 125, printed_quantity=6)])
		stored = reservation_row(state="Active")
		with (
			patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._claim_reservation", return_value=(stored, False)),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1", "rows": []}),
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
		):
			payload = reserve_box_sticker_print(
				"BSP-1",
				[{"doc_name": "ROW-S", "quantity": 3}],
				"300dpi",
				request_id="request-12345678",
				expected_modified="M1",
			)

		self.assertTrue(payload["already_reserved"])
		self.assertEqual(payload["reservation_state"], "active")
		self.assertEqual(payload["zpl"], "^XA-STORED^XZ")
		set_value.assert_not_called()

	def test_confirmed_request_id_cannot_be_replayed_for_zpl(self):
		doc = box_doc(rows=[detail("ROW-S", "S", 10, 125, printed_quantity=6)])
		stored = reservation_row(state="Confirmed")
		with (
			patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._claim_reservation", return_value=(stored, False)),
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			self.assertRaises(frappe.ValidationError),
		):
			reserve_box_sticker_print(
				"BSP-1",
				[{"doc_name": "ROW-S", "quantity": 3}],
				"300dpi",
				request_id="request-12345678",
				expected_modified="M1",
			)

		set_value.assert_not_called()

	def test_reservation_rejects_zero_duplicate_forged_and_over_limit_rows(self):
		doc = box_doc(rows=[])
		format_doc = _dict(labels_per_row=2, zpl_raw_print_format_details=[])
		locked = [detail("ROW-S", "S", 10, 125, printed_quantity=8, allow_excess_percentage=10)]
		with patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc):
			for rows in (
			[{"doc_name": "ROW-S", "quantity": 0}],
			[{"doc_name": "ROW-S", "quantity": 1}, {"doc_name": "ROW-S", "quantity": 1}],
			):
				with self.subTest(rows=rows), self.assertRaises(frappe.ValidationError):
					reserve_box_sticker_print(
						"BSP-1",
						rows,
						"300dpi",
						request_id="request-invalid1",
						expected_modified="M1",
					)

		preparing = reservation_row(state="Preparing")
		for rows in (
			[{"doc_name": "FORGED", "quantity": 1}],
			[{"doc_name": "ROW-S", "quantity": 4}],
		):
			with (
				self.subTest(rows=rows),
				patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc),
				patch(f"{MODULE}._claim_reservation", return_value=(preparing, True)),
				patch(f"{MODULE}._lock_box_sticker", return_value=doc),
				patch(f"{MODULE}._get_print_format_doc", return_value=(format_doc, "RAW", 2)),
				patch(f"{MODULE}._locked_detail_rows", return_value=locked),
				self.assertRaises(frappe.ValidationError),
			):
				reserve_box_sticker_print(
					"BSP-1",
					rows,
					"300dpi",
					request_id="request-invalid2",
					expected_modified="M1",
				)

	def test_reservation_locks_rows_uses_server_values_and_updates_actual_label_total(self):
		doc = box_doc(rows=[])
		doc.size = "PACK-SIZE"
		format_doc = _dict(name="BOX-FORMAT", labels_per_row=2, zpl_raw_print_format_details=[])
		locked = [detail("ROW-S", "S", 10, 125, printed_quantity=2)]
		reservation = reservation_row(state="Preparing", payload_rows=[])

		def update_reservation(request_id, **values):
			for key, value in values.items():
				reservation[key] = value

		with (
			patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc),
			patch(f"{MODULE}._claim_reservation", return_value=(reservation, True)),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._get_print_format_doc", return_value=(format_doc, "RAW", 2)),
			patch(f"{MODULE}._locked_detail_rows", return_value=locked),
			patch(f"{MODULE}.get_template", return_value="^XA-SERVER^XZ") as render,
			patch(f"{MODULE}._update_reservation", side_effect=update_reservation) as update,
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1", "rows": []}),
		):
			payload = reserve_box_sticker_print(
				"BSP-1",
				[{"doc_name": "ROW-S", "quantity": 3, "mrp": 1, "size": "FORGED"}],
				"300dpi",
				request_id="request-12345678",
				expected_modified="M1",
			)

		self.assertEqual(payload["reservation"], "request-12345678")
		self.assertEqual(payload["reservation_id"], "request-12345678")
		self.assertEqual(payload["zpl"], "^XA-SERVER^XZ")
		self.assertEqual(payload["raw"], "^XA-SERVER^XZ")
		set_value.assert_called_once_with(
			"SD YRP Box Sticker Print Detail", "ROW-S", "printed_quantity", 6
		)
		rendered_item = render.call_args.args[1]
		self.assertEqual(rendered_item["size"], "PACK-SIZE")
		self.assertEqual(rendered_item["mrp"], 125)
		self.assertEqual(render.call_args.kwargs["dpi"], 300)
		self.assertEqual(json.loads(reservation.payload_json)[0]["delta"], 4)
		update.assert_called_once()

	def test_requested_quantity_uses_authoritative_excess_rule_but_tracks_padded_total(self):
		doc = box_doc(rows=[])
		format_doc = _dict(name="BOX-FORMAT", labels_per_row=2)
		locked = [detail("ROW-S", "S", 10, 125, printed_quantity=8, allow_excess_percentage=10)]
		reservation = reservation_row(state="Preparing", payload_rows=[])

		def update_reservation(request_id, **values):
			reservation.update(values)

		with (
			patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc),
			patch(f"{MODULE}._claim_reservation", return_value=(reservation, True)),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._get_print_format_doc", return_value=(format_doc, "RAW", 2)),
			patch(f"{MODULE}._locked_detail_rows", return_value=locked),
			patch(f"{MODULE}.get_template", return_value="^XA^XZ"),
			patch(f"{MODULE}._update_reservation", side_effect=update_reservation),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1"}),
		):
			reserve_box_sticker_print(
				"BSP-1",
				[{"doc_name": "ROW-S", "quantity": 3}],
				"300dpi",
				request_id="request-padding1",
				expected_modified="M1",
			)

		set_value.assert_called_once_with(
			"SD YRP Box Sticker Print Detail", "ROW-S", "printed_quantity", 12
		)

	def test_reservation_checks_record_permission_before_inspecting_print_rows(self):
		with (
			patch(f"{MODULE}._authorise_box_sticker_print", side_effect=frappe.PermissionError),
			self.assertRaises(frappe.PermissionError),
		):
			reserve_box_sticker_print(
				"BSP-1",
				[{"doc_name": "ROW-S", "quantity": 0}],
				"300dpi",
				request_id="request-denied1",
				expected_modified="M1",
			)

	def test_reservation_does_not_increment_if_the_durable_claim_fails(self):
		doc = box_doc(rows=[])
		with (
			patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._claim_reservation", side_effect=frappe.ValidationError),
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			self.assertRaises(frappe.ValidationError),
		):
			reserve_box_sticker_print(
				"BSP-1",
				[{"doc_name": "ROW-S", "quantity": 2}],
				"300dpi",
				request_id="request-db-fail",
				expected_modified="M1",
			)

		set_value.assert_not_called()

	def test_reservation_locks_parent_before_claiming_the_request_id(self):
		doc = box_doc(rows=[])
		events = []

		def fail_claim(**kwargs):
			events.append("reservation")
			raise frappe.ValidationError

		with (
			patch(f"{MODULE}._authorise_box_sticker_print", return_value=doc),
			patch(
				f"{MODULE}._lock_box_sticker",
				side_effect=lambda *args, **kwargs: events.append("parent") or doc,
			),
			patch(f"{MODULE}._claim_reservation", side_effect=fail_claim),
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			self.assertRaises(frappe.ValidationError),
		):
			reserve_box_sticker_print(
				"BSP-1",
				[{"doc_name": "ROW-S", "quantity": 2}],
				"300dpi",
				request_id="request-lock-order",
				expected_modified="M1",
			)

		self.assertEqual(events, ["parent", "reservation"])
		set_value.assert_not_called()

	def test_rollback_is_user_bound_exact_once_and_confirmation_blocks_it(self):
		reservation = reservation_row(state="Active")
		doc = box_doc()
		locked = [detail("ROW-S", "S", 10, 125, printed_quantity=6)]

		def update_reservation(request_id, **values):
			reservation.update(values)

		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._reserved_printed_floors", return_value={"ROW-S": 6}),
			patch(f"{MODULE}._locked_detail_rows", return_value=locked),
			patch(f"{MODULE}._update_reservation", side_effect=update_reservation) as update,
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1", "rows": []}),
		):
			first = rollback_box_sticker_print("request-12345678")
			second = rollback_box_sticker_print({"reservation_id": "request-12345678"})

		self.assertTrue(first["rolled_back"])
		self.assertTrue(second["already_rolled_back"])
		set_value.assert_called_once_with(
			"SD YRP Box Sticker Print Detail", "ROW-S", "printed_quantity", 2
		)
		update.assert_called_once_with("request-12345678", state="Rolled Back")

		reservation.state = "Active"
		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._update_reservation", side_effect=update_reservation),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1"}),
		):
			confirmed = confirm_box_sticker_print("request-12345678")
		self.assertTrue(confirmed["confirmed"])
		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			self.assertRaises(frappe.ValidationError),
		):
			rollback_box_sticker_print("request-12345678")

	def test_rollback_rejects_a_reservation_owned_by_another_user(self):
		reservation = reservation_row(user="other@example.com")
		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			self.assertRaises(frappe.PermissionError),
		):
			rollback_box_sticker_print("request-12345678")

	def test_confirmation_acknowledges_active_and_confirmed_reservations_after_cancel(self):
		reservation = reservation_row(state="Active")
		doc = box_doc(docstatus=2)

		def update_reservation(_request_id, **values):
			reservation.update(values)

		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._update_reservation", side_effect=update_reservation) as update,
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1", "docstatus": 2}),
		):
			first = confirm_box_sticker_print("request-12345678")
			second = confirm_box_sticker_print("request-12345678")

		self.assertTrue(first["confirmed"])
		self.assertFalse(first["already_confirmed"])
		self.assertTrue(second["already_confirmed"])
		update.assert_called_once_with("request-12345678", state="Confirmed")
		doc.check_permission.assert_called_with("read")

	def test_print_recovery_returns_owned_state_and_hides_missing_or_foreign_tokens(self):
		doc = box_doc()
		active = reservation_row(state="Active")
		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=active),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1"}),
		):
			payload = get_box_sticker_print_recovery("request-12345678")

		self.assertEqual(payload["state"], "Active")
		self.assertEqual(payload["zpl"], "^XA-STORED^XZ")
		self.assertEqual(payload["printer_type"], "300dpi")
		self.assertTrue(payload["can_resume"])
		doc.check_permission.assert_called_once_with("read")

		for stored in (None, reservation_row(user="other@example.com")):
			with (
				self.subTest(stored=stored),
				patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
				patch(f"{MODULE}._lock_reservation", return_value=stored),
			):
				self.assertEqual(
					get_box_sticker_print_recovery("request-12345678"),
					{"state": "Missing", "reservation": "request-12345678"},
				)

	def test_active_print_recovery_withholds_zpl_after_cancel(self):
		active = reservation_row(state="Active")
		doc = box_doc(docstatus=2)
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=active),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1", "docstatus": 2}),
		):
			payload = get_box_sticker_print_recovery("request-12345678")

		self.assertFalse(payload["can_resume"])
		self.assertTrue(payload["release_required"])
		self.assertNotIn("zpl", payload)

	def test_read_access_is_enough_to_print_and_resume(self):
		def read_only(_doctype, ptype="read", **_kwargs):
			return ptype == "read"

		doc = box_doc()
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=read_only),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
		):
			self.assertTrue(workspace._permissions(doc)["can_print"])
			workspace._authorise_box_sticker_print("BSP-1", "M1")
		doc.check_permission.assert_called_with("read")

		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=read_only),
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation_row(state="Active")),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1", "docstatus": 1}),
		):
			payload = get_box_sticker_print_recovery("request-12345678")
		self.assertTrue(payload["can_resume"])
		self.assertEqual(payload["zpl"], "^XA-STORED^XZ")

	def test_missing_and_wrong_owner_reservations_use_the_same_non_disclosing_error(self):
		errors = []
		for stored in (None, reservation_row(user="other@example.com")):
			with self.subTest(stored=stored):
				with (
					patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
					patch(f"{MODULE}._lock_reservation", return_value=stored),
					self.assertRaises(frappe.PermissionError) as error,
				):
					workspace._owned_reservation("request-12345678")
				errors.append(str(error.exception))

		self.assertEqual(errors[0], errors[1])

	def test_overlapping_active_reservations_can_rollback_in_either_order(self):
		for order in (
			("request-a1234567", "request-b1234567"),
			("request-b1234567", "request-a1234567"),
		):
			with self.subTest(order=order):
				reservations = {
					"request-a1234567": reservation_row(
						state="Active",
						payload_rows=[{"name": "ROW-S", "delta": 4, "before": 0, "after": 4}],
					),
					"request-b1234567": reservation_row(
						state="Active",
						payload_rows=[{"name": "ROW-S", "delta": 4, "before": 4, "after": 8}],
					),
				}
				for request_id, reservation in reservations.items():
					reservation.name = request_id
					reservation.request_id = request_id
				printed = {"value": 8}
				doc = box_doc()

				def lock_reservation(request_id, **kwargs):
					return reservations[request_id]

				def locked_rows(parent, names):
					return [detail("ROW-S", "S", 10, 125, printed_quantity=printed["value"])]

				def printed_floors(parent, names):
					baselines = [
						json.loads(reservation.payload_json)[0]["before"]
						for reservation in reservations.values()
					]
					return {
						"ROW-S": min(baselines)
						+ sum(
							json.loads(reservation.payload_json)[0]["delta"]
							for reservation in reservations.values()
							if reservation.state in {"Active", "Confirmed"}
						)
					}

				def set_value(doctype, name, fieldname, value):
					printed["value"] = value

				def update_reservation(request_id, **values):
					reservations[request_id].update(values)

				with (
					patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
					patch(f"{MODULE}._lock_reservation", side_effect=lock_reservation),
					patch(f"{MODULE}._lock_box_sticker", return_value=doc),
					patch(f"{MODULE}._locked_detail_rows", side_effect=locked_rows),
					patch(f"{MODULE}._reserved_printed_floors", side_effect=printed_floors),
					patch(f"{MODULE}._update_reservation", side_effect=update_reservation),
					patch(f"{MODULE}.attribute_db.set_value", side_effect=set_value),
					patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1"}),
				):
					rollback_box_sticker_print(order[0])
					self.assertEqual(printed["value"], 4)
					rollback_box_sticker_print(order[1])

				self.assertEqual(printed["value"], 0)
				self.assertEqual(reservations["request-a1234567"].state, "Rolled Back")
				self.assertEqual(reservations["request-b1234567"].state, "Rolled Back")

	def test_rollback_rejects_total_below_all_reservations_still_in_effect(self):
		reservation = reservation_row(
			state="Active",
			payload_rows=[{"name": "ROW-S", "delta": 4, "before": 0, "after": 4}],
		)
		doc = box_doc()
		locked = [detail("ROW-S", "S", 10, 125, printed_quantity=5)]
		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._locked_detail_rows", return_value=locked),
			patch(f"{MODULE}._reserved_printed_floors", return_value={"ROW-S": 8}),
			patch(f"{MODULE}._update_reservation") as update,
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			self.assertRaises(frappe.ValidationError),
		):
			rollback_box_sticker_print("request-12345678")

		set_value.assert_not_called()
		update.assert_not_called()

	def test_rollback_rejects_counter_below_the_reserved_after_total(self):
		reservation = reservation_row(state="Active")
		doc = box_doc()
		locked = [detail("ROW-S", "S", 10, 125, printed_quantity=5)]
		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._reserved_printed_floors", return_value={"ROW-S": 6}),
			patch(f"{MODULE}._locked_detail_rows", return_value=locked),
			patch(f"{MODULE}._update_reservation") as update,
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			self.assertRaises(frappe.ValidationError),
		):
			rollback_box_sticker_print("request-12345678")

		set_value.assert_not_called()
		update.assert_not_called()

	def test_active_reservation_can_be_rolled_back_after_concurrent_cancel(self):
		reservation = reservation_row(state="Active")
		doc = box_doc(docstatus=2)
		locked = [detail("ROW-S", "S", 10, 125, printed_quantity=6)]
		with (
			patch(f"{MODULE}.frappe.session", _dict(user="Administrator")),
			patch(f"{MODULE}._lock_reservation", return_value=reservation),
			patch(f"{MODULE}._lock_box_sticker", return_value=doc),
			patch(f"{MODULE}._reserved_printed_floors", return_value={"ROW-S": 6}),
			patch(f"{MODULE}._locked_detail_rows", return_value=locked),
			patch(f"{MODULE}._update_reservation"),
			patch(f"{MODULE}.attribute_db.set_value") as set_value,
			patch(f"{MODULE}._record_payload", return_value={"name": "BSP-1"}),
		):
			payload = rollback_box_sticker_print("request-12345678")

		self.assertTrue(payload["rolled_back"])
		set_value.assert_called_once_with(
			"SD YRP Box Sticker Print Detail", "ROW-S", "printed_quantity", 2
		)
