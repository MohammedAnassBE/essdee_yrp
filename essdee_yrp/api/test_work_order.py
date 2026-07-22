# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
"""Regression tests for the fabric WO Calculate backend (owner bug 2026-07-22,
lot C0625-39/2-220 / WO-00029): a knitting yarn whose Item master declares
Colour (TT-YARN-GREY) is consumed ATTR-LESS by the knitting matrix, and
Calculate blew up with "Please mention Colour attribute in TT-YARN-GREY".
Owner ruling: a yarn must never be forced to take a Colour — the minted
deliverable resolves WITHOUT a Colour-stamped variant.

Fixtures follow test_cloth_program's pattern — everything created inside the
rolled-back test transaction, no frappe.db.commit()."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from essdee_yrp.api import cloth_program
from essdee_yrp.api.cloth_program import build_cloth_programs
from essdee_yrp.api.test_cloth_program import (
    _ensure_iav,
    _ensure_item,
    _ensure_process,
    _reset_cpd,
)
from essdee_yrp.api.work_order import (
    calculate_fabric_deliverables,
    get_fabric_deliverable_context,
)


def _ensure_attributed_item(name1, attributes):
    """An Item that DECLARES the given attributes (like live TT-YARN-GREY,
    which declares Colour while the knitting matrix consumes it attr-less)."""
    name = _ensure_item(name1)
    doc = frappe.get_doc("Item", name)
    have = {r.attribute for r in doc.get("attributes") or []}
    missing = [a for a in attributes if a not in have]
    if missing:
        for attr in missing:
            doc.append("attributes", {"attribute": attr})
        doc.save(ignore_permissions=True)
    return name


def _ensure_address(title="_Test WO Calc Sup"):
    existing = frappe.db.get_value("Address", {"address_title": title}, "name")
    if existing:
        return existing
    return frappe.get_doc({
        "doctype": "Address", "address_title": title, "address_type": "Billing",
        "address_line1": "1 Test Street", "city": "Tiruppur", "country": "India",
    }).insert(ignore_permissions=True).name


def _ensure_default_received_type():
    if frappe.db.get_single_value("YRP Stock Settings", "default_received_type"):
        return
    if not frappe.db.exists("Received Type", "Accepted"):
        rt = frappe.new_doc("Received Type")
        for f in frappe.get_meta("Received Type").fields:
            if f.reqd and f.fieldtype == "Data":
                rt.set(f.fieldname, "Accepted")
        rt.insert(ignore_permissions=True)
    frappe.db.set_single_value("YRP Stock Settings", "default_received_type", "Accepted")


class TestCalculateFabricDeliverables(IntegrationTestCase):
    def setUp(self):
        self.dia = _ensure_iav("Dia", "_Test 60 Dia CPD")
        self.greige = _ensure_iav("Colour", "_Test Greige CPD")
        self.red = _ensure_iav("Colour", "_Test Red CPD")
        # The bug shape: yarn Item DECLARES Colour, matrix input carries no attrs.
        self.yarn = _ensure_attributed_item("_Test Grey Yarn WOCalc", ["Colour"])
        # Cloth mirrors live Thermal Rib: declares Dia + Colour.
        self.cloth = _ensure_attributed_item("_Test Cloth WOCalc", ["Dia", "Colour"])
        frappe.db.set_value("Item", self.cloth, "is_cloth_item", 1)
        _reset_cpd(self.cloth)
        self.k_proc = _ensure_process("_Test Knit CPD", is_item_conversion=1)
        self.d_proc = _ensure_process("_Test Dye CPD")
        _ensure_default_received_type()

        selection = {
            "cloth_item": self.cloth, "yarn_item": self.yarn,
            "knitting_process": self.k_proc, "dyeing_process": self.d_proc,
            "compacting_process": None, "cloth_per_kg_yarn": 3.0,
            "greige_colour": self.greige,
        }
        # The class shares ONE uncommitted transaction (see _reset_cpd's note) —
        # a Lot inserted by an earlier test's setUp is still visible here.
        if frappe.db.exists("Lot", "_Test WOCalc Lot"):
            self.lot = frappe.get_doc("Lot", "_Test WOCalc Lot")
        else:
            self.lot = frappe.get_doc({
                "doctype": "Lot", "lot_name": "_Test WOCalc Lot",
            }).insert(ignore_permissions=True)
        demand = {(self.cloth, self.dia, self.red): 48.05}
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(self.lot.name, [selection])

        addr = _ensure_address()
        self.wo = frappe.get_doc({
            "doctype": "Work Order", "naming_series": "WO-",
            "wo_date": nowdate(), "process_name": self.k_proc,
            "item": self.cloth, "lot": self.lot.name,
            "planned_start_date": nowdate(), "planned_end_date": nowdate(),
            "supplier_address": addr, "delivery_address": addr,
        }).insert(ignore_permissions=True)

    def _calculate(self):
        ctx = get_fabric_deliverable_context(self.wo.name)
        self.assertEqual(ctx["kind"], "knitting")
        self.assertEqual(len(ctx["rows"]), 1)
        row = ctx["rows"][0]
        self.assertEqual(row["yarn_item"], self.yarn)
        payload = [{
            "fabric_row": row["fabric_row"],
            "colour": row["greige_colour"],
            "entries": [
                {"key": qr["key"], "qty": qr["balance"] or 48.05}
                for qr in row["qty_rows"]
            ],
        }]
        return calculate_fabric_deliverables(self.wo.name, payload)

    def test_colour_declaring_yarn_calculates_without_colour_demand(self):
        """WO-00029 regression: Calculate must NOT throw "Please mention Colour
        attribute in <yarn>" when the yarn Item declares Colour but the knitting
        matrix input is attr-less. The yarn deliverable resolves to a variant
        WITHOUT a Colour attribute row."""
        res = self._calculate()
        self.assertEqual(res["deliverables"], 1)
        self.assertEqual(res["receivables"], 1)

        wo = frappe.get_doc("Work Order", self.wo.name)
        delivs = [d for d in wo.get("deliverables") if d.is_calculated]
        self.assertEqual(len(delivs), 1)
        variant = frappe.get_doc("Item Variant", delivs[0].item_variant)
        self.assertEqual(variant.item, self.yarn)
        # Owner ruling: NOT Colour-stamped — no attribute rows at all.
        self.assertEqual([r.attribute for r in variant.get("attributes") or []], [])
        # 48.05 kg cloth / 3.0 cloth-per-kg-yarn ≈ 16.017 kg yarn
        self.assertAlmostEqual(delivs[0].qty, 48.05 / 3.0, places=2)

        # The receivable keeps its FULL attribute set (cloth declares Dia+Colour;
        # knitting stamps the greige colour) — declared attrs are never dropped.
        recvs = wo.get("receivables")
        self.assertEqual(len(recvs), 1)
        recv_variant = frappe.get_doc("Item Variant", recvs[0].item_variant)
        self.assertEqual(recv_variant.item, self.cloth)
        self.assertEqual(
            {r.attribute: r.attribute_value for r in recv_variant.attributes},
            {"Dia": self.dia, "Colour": self.greige},
        )

    def test_calculate_is_idempotent_for_partial_variant(self):
        """Second Calculate must REUSE the minted attr-less yarn variant (no
        DuplicateEntryError, no second variant on the yarn Item)."""
        self._calculate()
        self._calculate()
        variants = frappe.get_all("Item Variant", filters={"item": self.yarn}, pluck="name")
        self.assertEqual(len(variants), 1)

    def test_resolve_variant_keeps_declared_drops_undeclared(self):
        """_resolve_variant: attrs the Item DECLARES are always kept (full-set
        path); attrs it does NOT declare are dropped instead of poisoning the
        tuple lookup into a duplicate-name insert."""
        from essdee_yrp.api.work_order import _resolve_variant

        v = _resolve_variant(self.yarn, {"Colour": self.red, "Dia": self.dia})
        doc = frappe.get_doc("Item Variant", v)
        self.assertEqual(
            {r.attribute: r.attribute_value for r in doc.attributes},
            {"Colour": self.red},
        )
