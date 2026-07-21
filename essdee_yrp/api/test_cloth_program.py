# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
"""Integration tests for the CPD auto-builder (Phases 2-4). All fixtures are
created inside the per-test transaction (IntegrationTestCase rolls it back) — no
frappe.db.commit(). compute_cloth_demand is monkeypatched with a controlled
demand so the CPD-build / matrix / reachability / plan flow is exercised without
a full garment IPD (that path is covered by test_fabric_requirement)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api import cloth_program
from essdee_yrp.api.cloth_program import (
    _ensure_lot_fabric_detail,
    _find_or_create_cpd,
    _requirement_payload,
    build_cloth_programs,
)
from essdee_yrp.fabric_chain import final_combos


def _ensure_item_group(name="_Test CPD Group"):
    if not frappe.db.exists("Item Group", name):
        frappe.get_doc({
            "doctype": "Item Group", "item_group_name": name,
            "is_group": 0, "parent_item_group": "All Item Groups",
        }).insert(ignore_permissions=True)
    return name


def _ensure_uom(name="Kg"):
    if not frappe.db.exists("UOM", name):
        frappe.get_doc({"doctype": "UOM", "uom_name": name}).insert(ignore_permissions=True)
    return name


def _ensure_item(name1):
    if frappe.db.exists("Item", name1):
        return name1
    return frappe.get_doc({
        "doctype": "Item", "name1": name1, "item_group": _ensure_item_group(),
        "default_unit_of_measure": _ensure_uom(), "is_stock_item": 1,
    }).insert(ignore_permissions=True).name


def _ensure_item_attribute(name):
    if not frappe.db.exists("Item Attribute", name):
        frappe.get_doc({"doctype": "Item Attribute", "attribute_name": name}).insert(
            ignore_permissions=True)
    return name


def _ensure_iav(attribute, value):
    _ensure_item_attribute(attribute)
    if not frappe.db.exists("Item Attribute Value", value):
        frappe.get_doc({
            "doctype": "Item Attribute Value", "attribute_name": attribute,
            "attribute_value": value,
        }).insert(ignore_permissions=True)
    return value


def _ensure_process(process_name, is_item_conversion=0):
    if not frappe.db.exists("Process", process_name):
        frappe.get_doc({
            "doctype": "Process", "process_name": process_name,
            "is_item_conversion": is_item_conversion,
        }).insert(ignore_permissions=True)
    return process_name


def _reset_cpd(cloth_item):
    """IntegrationTestCase only rolls back at CLASS teardown (addClassCleanup),
    NOT per test method — every test in this class shares one uncommitted
    transaction, so a CPD built by an earlier test method is still visible to a
    later one. _find_or_create_cpd's additive seeding is exactly what makes this
    dangerous here: a test asserting a single fresh dia row would silently see a
    prior test's union-merged rows. Drop any leftover CPD (+ its matrices) for the
    shared test cloth Item so each test starts from a known-empty state."""
    name = frappe.db.get_value("Item Production Detail", {"item": cloth_item, "is_cloth_item": 1}, "name")
    if name:
        frappe.db.delete("IPD Process Matrix", {"ipd": name})
        frappe.delete_doc("Item Production Detail", name, force=True, ignore_permissions=True)


class TestClothProgram(IntegrationTestCase):
    def setUp(self):
        self.dia = _ensure_iav("Dia", "_Test 60 Dia CPD")
        self.greige = _ensure_iav("Colour", "_Test Greige CPD")
        self.red = _ensure_iav("Colour", "_Test Red CPD")
        self.yarn = _ensure_item("_Test Yarn CPD")
        self.cloth = _ensure_item("_Test Cloth CPD")
        # Item Production Detail.is_cloth_item is `fetch_from: item.is_cloth_item`
        # (read-only, fetch_if_empty=0) — every IPD save re-pulls it from the linked
        # Item regardless of what the CPD builder stamps in memory, so the cloth
        # Item master itself must carry the flag for is_cloth_ipd() to route the
        # IPD through the cloth-validation path instead of the garment one.
        frappe.db.set_value("Item", self.cloth, "is_cloth_item", 1)
        _reset_cpd(self.cloth)
        self.k_proc = _ensure_process("_Test Knit CPD", is_item_conversion=1)
        self.d_proc = _ensure_process("_Test Dye CPD")
        self.selection = {
            "cloth_item": self.cloth, "yarn_item": self.yarn,
            "knitting_process": self.k_proc, "dyeing_process": self.d_proc,
            "compacting_process": None, "cloth_per_kg_yarn": 3.0,
            "greige_colour": self.greige,
        }
        self.tuples = {(self.dia, self.red): 50.9}

    def test_find_or_create_cpd_seeds_tabs_matrices_and_reachability(self):
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual(cpd.is_cloth_item, 1)
        self.assertEqual(cpd.yarn_item, self.yarn)
        self.assertEqual(cpd.cloth_per_kg_yarn, 3.0)
        self.assertEqual(cpd.approval_status, "Approved")
        self.assertEqual([r.dia for r in cpd.knitting_dia_details], [self.dia])
        self.assertEqual(
            [(r.dia, r.from_colour, r.to_colour) for r in cpd.dyeing_colour_details],
            [(self.dia, self.greige, self.red)])
        matrices = frappe.get_all("IPD Process Matrix", filters={"ipd": cpd_name})
        self.assertGreaterEqual(len(matrices), 2)
        want = frozenset({("Dia", self.dia), ("Colour", self.red)})
        self.assertIn(want, final_combos(cpd))

    def test_find_or_create_cpd_is_idempotent(self):
        first = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        second = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        self.assertEqual(first, second)
        cpd = frappe.get_doc("Item Production Detail", second)
        self.assertEqual(len(cpd.knitting_dia_details), 1)
        self.assertEqual(len(cpd.dyeing_colour_details), 1)
        # Additive seeding: a sibling lot demanding a NEW dia on the SAME shared
        # cloth must UNION into the CPD, never wipe the earlier lot's rows.
        dia2 = _ensure_iav("Dia", "_Test 70 Dia CPD")
        third = _find_or_create_cpd(
            self.cloth, self.selection,
            {(self.dia, self.red): 1.0, (dia2, self.red): 1.0})
        self.assertEqual(third, first)
        cpd = frappe.get_doc("Item Production Detail", third)
        self.assertEqual({r.dia for r in cpd.knitting_dia_details}, {self.dia, dia2})
        self.assertIn(
            (self.dia, self.greige, self.red),
            [(r.dia, r.from_colour, r.to_colour) for r in cpd.dyeing_colour_details])

    def test_ensure_lot_fabric_detail_find_or_append(self):
        lot = frappe.new_doc("Lot")
        _ensure_lot_fabric_detail(lot, self.cloth, "CPD-X")
        _ensure_lot_fabric_detail(lot, self.cloth, "CPD-Y")  # same cloth -> update, no dup
        self.assertEqual(len(lot.lot_fabric_details), 1)
        self.assertEqual(lot.lot_fabric_details[0].production_detail, "CPD-Y")

    def test_requirement_payload_shape(self):
        payload = _requirement_payload({self.cloth: {(self.dia, self.red): 50.9}})
        self.assertEqual(payload, [{
            "cloth_item": self.cloth,
            "requirement": [{"dia": self.dia, "colour": self.red, "weight": 50.9}],
        }])

    def test_build_cloth_programs_writes_requirements_and_plan(self):
        lot = frappe.get_doc({"doctype": "Lot", "lot_name": "_Test CPD Lot"}).insert(
            ignore_permissions=True)
        demand = {(self.cloth, self.dia, self.red): 50.9}
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            res = build_cloth_programs(lot.name, [self.selection])
        self.assertEqual(res["cloths_built"], 1)
        lot.reload()
        fab = [f for f in lot.lot_fabric_details if f.cloth_item == self.cloth]
        self.assertEqual(len(fab), 1)
        self.assertEqual(fab[0].plan_status, "Built")
        reqs = [r for r in lot.lot_fabric_requirements if r.cloth_item == self.cloth]
        self.assertEqual(len(reqs), 1)
        self.assertEqual((reqs[0].dia, reqs[0].colour), (self.dia, self.red))
        self.assertAlmostEqual(reqs[0].weight, 50.9, places=3)
        self.assertTrue(lot.lot_fabric_programs)       # WO knitting pre-seed
        self.assertTrue(lot.lot_fabric_step_ledger)    # CPD chain plan

    def test_build_cloth_programs_requires_dyeing_for_coloured_demand(self):
        # A colour-bearing demand with no dyeing_process must fail FAST with a clear
        # message (not the opaque downstream "No chain path produces" from Phase 4).
        lot = frappe.get_doc({"doctype": "Lot", "lot_name": "_Test CPD Lot NoDye"}).insert(
            ignore_permissions=True)
        demand = {(self.cloth, self.dia, self.red): 50.9}
        sel = dict(self.selection, dyeing_process=None)
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            with self.assertRaises(frappe.ValidationError):
                build_cloth_programs(lot.name, [sel])

    def test_build_cloth_programs_is_idempotent(self):
        lot = frappe.get_doc({"doctype": "Lot", "lot_name": "_Test CPD Lot Idem"}).insert(
            ignore_permissions=True)
        demand = {(self.cloth, self.dia, self.red): 50.9}
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(lot.name, [self.selection])
            build_cloth_programs(lot.name, [self.selection])
        lot.reload()
        self.assertEqual(
            len([f for f in lot.lot_fabric_details if f.cloth_item == self.cloth]), 1)
        cpd_name = frappe.db.get_value(
            "Item Production Detail", {"item": self.cloth, "is_cloth_item": 1}, "name")
        self.assertEqual(
            len(frappe.get_all(
                "Item Production Detail", filters={"item": self.cloth, "is_cloth_item": 1})), 1)
        self.assertGreaterEqual(
            len(frappe.get_all("IPD Process Matrix", filters={"ipd": cpd_name})), 2)
