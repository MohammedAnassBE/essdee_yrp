# Copyright (c) 2026, anas@essdee.fit and contributors
"""Integration tests for the cross-bench GRN -> Material Receipt receiver.

Masters (Supplier+Warehouse, Item Variant, Lot, UOM, "Accepted" Received Type)
are always pre-synced in the real flow, so setUp BINDS to existing site masters
(skipTest if a fresh site lacks them) rather than fabricating a full variant/IPD.
receive_grn_transfer commits (it runs in its own HTTP request in production), so
tearDown cancels+deletes every Stock Entry it created for the test source_grns.
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.api.stock_transfer import cancel_grn_transfer, receive_grn_transfer

TEST_GRNS = ("GRN-TEST-0001", "GRN-NEVER-EXISTED", "GRN-TEST-DUP", "GRN-TEST-MULTI", "GRN-TEST-UIGRID")


class TestReceiveGrnTransfer(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The HTTP handlers commit in production by design. Suppress that
        # transaction boundary in tests so the class-level rollback owns every
        # Stock Entry, Stock Ledger Entry, and setup record created here.
        cls._commit_patcher = patch.object(frappe.db, "commit")
        cls._commit_patcher.start()
        cls.addClassCleanup(cls._commit_patcher.stop)

    def setUp(self):
        wh = frappe.get_all("Warehouse", filters={"supplier": ["is", "set"]},
                            fields=["name", "supplier"], limit=1)
        variants = frappe.get_all("Item Variant", limit=2, pluck="name")
        lots = frappe.get_all("Lot", limit=2, pluck="name")
        if not (wh and variants and lots and frappe.db.exists("Received Type", "Accepted")):
            self.skipTest("essdee_yrp.site missing a supplier-warehouse / variant / lot / Accepted")
        self.wh = wh[0].name
        self.supplier = wh[0].supplier
        self.variant = variants[0]
        self.lot = lots[0]
        # a 2nd distinct (variant, lot) for the multi-row parity test (may be None on a bare site)
        self.variant2 = variants[1] if len(variants) > 1 else None
        self.lot2 = lots[1] if len(lots) > 1 else None
        # yrp Item Variant carries no UOM; it lives on the parent Item.
        item = frappe.db.get_value("Item Variant", self.variant, "item")
        self.uom = frappe.db.get_value("Item", item, "default_unit_of_measure") \
            or (frappe.get_all("UOM", limit=1, pluck="name") or ["Nos"])[0]
        self._extra_ses = []            # non-source_grn SEs a test creates; cleaned in tearDown
        self._cleanup()

    def tearDown(self):
        for name in getattr(self, "_extra_ses", []):
            if frappe.db.exists("Stock Entry", name):
                doc = frappe.get_doc("Stock Entry", name)
                if doc.docstatus == 1:          # no source_grn -> guard does not block
                    doc.cancel()
                frappe.delete_doc("Stock Entry", name, force=True, ignore_permissions=True)
        self._cleanup()

    def _cleanup(self):
        for grn in TEST_GRNS:
            for name in frappe.get_all("Stock Entry", filters={"source_grn": grn}, pluck="name"):
                doc = frappe.get_doc("Stock Entry", name)
                if doc.docstatus == 1:
                    # source_grn SEs are guarded — cleanup takes the transfer-cancel path
                    doc.flags.from_grn_transfer = True
                    doc.cancel()
                frappe.delete_doc("Stock Entry", name, force=True, ignore_permissions=True)

    def _make_normal_se(self):
        """A plain Material Receipt with NO source_grn (mirrors receive_grn_transfer's
        SE construction minus the transfer marker) — the control for the cancel guard."""
        se = frappe.new_doc("Stock Entry")
        se.purpose = "Material Receipt"
        se.to_warehouse = self.wh
        se.to_supplier = self.supplier
        se.append("items", {"item": self.variant, "qty": 3.0, "uom": self.uom,
                            "lot": self.lot, "received_type": "Accepted",
                            "conversion_factor": 1.0, "rate": 1.0,
                            "row_index": 0, "table_index": 0})
        se.insert(ignore_permissions=True)
        se.submit()
        self._extra_ses.append(se.name)
        return se

    def _payload(self, **over):
        p = {"source_grn": "GRN-TEST-0001", "supplier": self.supplier,
             "items": [{"item_variant": self.variant, "qty": 5.0, "uom": self.uom,
                        "rate": 12.0, "lot": self.lot, "received_type": "Accepted"}]}
        p.update(over)
        return p

    def test_creates_and_submits_material_receipt(self):
        r = receive_grn_transfer(self._payload())
        self.assertTrue(r["ok"], r)
        se = frappe.get_doc("Stock Entry", r["stock_entry"])
        self.assertEqual(se.purpose, "Material Receipt")
        self.assertEqual(se.docstatus, 1)
        self.assertEqual(se.to_warehouse, self.wh)          # auto-resolved from supplier
        self.assertEqual(se.to_supplier, self.supplier)
        self.assertEqual(se.items[0].lot, self.lot)
        self.assertEqual(se.items[0].received_type, "Accepted")
        self.assertEqual(se.items[0].conversion_factor, 1.0)
        self.assertEqual(frappe.db.get_value("Stock Entry", se.name, "source_grn"), "GRN-TEST-0001")

    def test_multi_row_grn_makes_one_se_holding_all_rows(self):
        """A GRN with N item rows transfers as exactly ONE Material Receipt whose
        Stock Entry Detail rows equal all N rows — one detail per (item, lot), never
        dropped/merged (row-count parity: len(SE rows) == len(GRN item rows))."""
        if not (self.variant2 and self.lot2
                and (self.variant2, self.lot2) != (self.variant, self.lot)):
            self.skipTest("essdee_yrp.site lacks a 2nd distinct (variant, lot) for a multi-row test")
        expected = [
            {"item_variant": self.variant, "qty": 100.0, "uom": self.uom, "rate": 4.0,
             "lot": self.lot, "received_type": "Accepted"},
            {"item_variant": self.variant2, "qty": 650.0, "uom": self.uom, "rate": 7.0,
             "lot": self.lot2, "received_type": "Accepted"},
        ]
        r = receive_grn_transfer(self._payload(source_grn="GRN-TEST-MULTI", items=expected))
        self.assertTrue(r["ok"], r)
        self.assertFalse(r.get("duplicate"))
        # exactly ONE Stock Entry per GRN (not one-per-row)
        ses = frappe.get_all("Stock Entry",
                             filters={"source_grn": "GRN-TEST-MULTI", "docstatus": 1}, pluck="name")
        self.assertEqual(len(ses), 1, "there must be exactly ONE Stock Entry for the GRN")
        se = frappe.get_doc("Stock Entry", ses[0])
        # row-count parity + every (item, lot, qty) preserved inside that single SE
        self.assertEqual(len(se.items), len(expected),
                         "every GRN item row must be its own Stock Entry Detail row")
        got = sorted((row.item, row.lot, flt(row.qty)) for row in se.items)
        want = sorted((e["item_variant"], e["lot"], flt(e["qty"])) for e in expected)
        self.assertEqual(got, want)

    def test_multi_item_grn_renders_all_rows_in_desk_grid(self):
        """DISPLAY parity (the real reported bug): the yrp Stock Entry desk form
        renders its item grid from group_items_for_ui(items) — pushed via
        onload -> __onload.item_details — NOT from the flat child table. Two
        DIFFERENT parent items both stored with the Int-column default
        row_index=0 collapse into a SINGLE grouped entry (built from the first
        row's parent item), so the second item silently vanishes from the form
        even though the child table + total_amount are correct. Every transferred
        row must surface in the grouped grid (count + total qty preserved)."""
        from yrp.stock.save_stock_items import group_items_for_ui

        # The collapse only DROPS a row across DIFFERENT parent items, so the test
        # needs two variants whose parent Items differ (mirrors CS-46206 vs EC-46310).
        by_parent = {}
        for c in frappe.get_all("Item Variant", fields=["name", "item"], limit=80):
            by_parent.setdefault(c.item, c.name)
        if len(by_parent) < 2:
            self.skipTest("essdee_yrp.site needs Item Variants from >=2 distinct parent Items")
        (_p1, v1), (_p2, v2) = list(by_parent.items())[:2]
        lot_b = self.lot2 or self.lot
        items = [
            {"item_variant": v1, "qty": 100.0, "uom": self.uom, "rate": 4.0,
             "lot": self.lot, "received_type": "Accepted"},
            {"item_variant": v2, "qty": 650.0, "uom": self.uom, "rate": 4.0,
             "lot": lot_b, "received_type": "Accepted"},
        ]
        r = receive_grn_transfer(self._payload(source_grn="GRN-TEST-UIGRID", items=items))
        self.assertTrue(r["ok"], r)
        se = frappe.get_doc("Stock Entry", r["stock_entry"])
        self.assertEqual(len(se.items), 2, "child table (data) must hold both rows")

        # What the desk Vue grid actually receives on load:
        grouped = group_items_for_ui(se.items, "Stock Entry")
        rendered = []
        for group in grouped:
            for entry in group.get("items", []):
                for cell in (entry.get("values") or {}).values():
                    if flt((cell or {}).get("qty")):
                        rendered.append((entry["name"], flt(cell["qty"])))
        total_rendered = sum(q for _, q in rendered)
        self.assertEqual(len(rendered), 2,
                         f"desk grid must render BOTH item rows; got {rendered}")
        self.assertEqual(total_rendered, 750.0,
                         f"desk grid dropped a row: rendered {total_rendered} of 750 -> {rendered}")

    def test_missing_variant_hard_errors(self):
        r = receive_grn_transfer(self._payload(items=[{"item_variant": "NOPE-XYZ", "qty": 1,
            "uom": self.uom, "lot": self.lot, "received_type": "Accepted"}]))
        self.assertFalse(r["ok"])
        self.assertIn("NOPE-XYZ", r["error"])

    def test_missing_lot_hard_errors(self):
        r = receive_grn_transfer(self._payload(items=[{"item_variant": self.variant, "qty": 1,
            "uom": self.uom, "lot": "NO-SUCH-LOT", "received_type": "Accepted"}]))
        self.assertFalse(r["ok"])
        self.assertIn("NO-SUCH-LOT", r["error"])

    def test_missing_warehouse_for_supplier_hard_errors(self):
        r = receive_grn_transfer(self._payload(supplier="Supplier-With-No-Warehouse-ZZZ"))
        self.assertFalse(r["ok"])
        self.assertIn("warehouse", r["error"].lower())

    def test_duplicate_is_idempotent(self):
        first = receive_grn_transfer(self._payload(source_grn="GRN-TEST-DUP"))
        self.assertTrue(first["ok"], first)
        second = receive_grn_transfer(self._payload(source_grn="GRN-TEST-DUP"))
        self.assertTrue(second["ok"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["stock_entry"], first["stock_entry"])

    def test_cancel_cancels_the_receipt(self):
        created = receive_grn_transfer(self._payload())
        self.assertTrue(created["ok"], created)
        r = cancel_grn_transfer("GRN-TEST-0001")
        self.assertTrue(r["ok"], r)
        self.assertEqual(frappe.db.get_value("Stock Entry", created["stock_entry"], "docstatus"), 2)

    def test_cancel_missing_is_idempotent(self):
        r = cancel_grn_transfer("GRN-NEVER-EXISTED")
        self.assertTrue(r["ok"])                            # nothing to cancel = ok

    # --- Issue A: authorization gate (no ignore_permissions without an explicit check) ---
    def test_receive_blocked_without_stock_entry_create_permission(self):
        user = "yrp-noperm@test.local"
        if not frappe.db.exists("User", user):
            frappe.get_doc({"doctype": "User", "email": user, "first_name": "NoPerm",
                            "send_welcome_email": 0}).insert(ignore_permissions=True)
        # user has no roles -> no "create" permission on Stock Entry
        frappe.set_user(user)
        try:
            with self.assertRaises(frappe.PermissionError):
                receive_grn_transfer(self._payload())
        finally:
            frappe.set_user("Administrator")
        # nothing was created for this source_grn
        self.assertFalse(frappe.get_all("Stock Entry",
                                        filters={"source_grn": "GRN-TEST-0001"}, limit=1))

    # --- Issue D: check-then-insert serialized by a per-source_grn named lock ---
    def test_transfer_serialized_by_source_grn_lock(self):
        with patch("frappe.utils.synchronization.filelock",
                   return_value=MagicMock()) as mock_lock:
            r = receive_grn_transfer(self._payload())
        self.assertTrue(r["ok"], r)
        self.assertTrue(mock_lock.called, "receive_grn_transfer must serialize with a named lock")
        lock_name = mock_lock.call_args.args[0]
        self.assertIn("GRN-TEST-0001", lock_name)

    # --- Cancel guard: a transfer SE (source_grn set) may be cancelled ONLY by the
    #     mrp GRN-cancel flow (cancel_grn_transfer, which sets the from_grn_transfer flag) ---
    def test_direct_cancel_of_transfer_se_is_blocked(self):
        """Calling .cancel() directly on a transfer SE must raise — the before_cancel
        guard forbids it unless doc.flags.from_grn_transfer is set."""
        created = receive_grn_transfer(self._payload())
        self.assertTrue(created["ok"], created)
        se = frappe.get_doc("Stock Entry", created["stock_entry"])
        with self.assertRaises(frappe.ValidationError):
            se.cancel()
        self.assertEqual(
            frappe.db.get_value("Stock Entry", se.name, "docstatus"), 1,
            "a blocked direct cancel must leave the transfer SE submitted")

    def test_cancel_grn_transfer_still_cancels_transfer_se(self):
        """The legitimate mrp path (cancel_grn_transfer sets the flag) must still cancel
        the guarded transfer SE end-to-end (SE ends at docstatus 2)."""
        created = receive_grn_transfer(self._payload())
        self.assertTrue(created["ok"], created)
        r = cancel_grn_transfer("GRN-TEST-0001")
        self.assertTrue(r["ok"], r)
        self.assertEqual(
            frappe.db.get_value("Stock Entry", created["stock_entry"], "docstatus"), 2)

    def test_normal_stock_entry_cancel_is_unaffected(self):
        """A normal Stock Entry (no source_grn) is outside the guard and cancels normally."""
        se = self._make_normal_se()
        self.assertFalse(se.get("source_grn"))
        se.cancel()                                         # must NOT raise
        self.assertEqual(se.docstatus, 2)
