# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
"""Unit tests for the ported cloth-demand math (Phase 1 SPLIT). Pure functions
over frappe._dict fakes mirroring the live 437765 (set-item) and AISHWARYA
(Size+Panel) garment-IPD data shapes — no DB writes, no frappe.db.commit()."""

import json

from frappe.tests import IntegrationTestCase

from essdee_yrp.fabric_requirement import (
    _apply_cloth_allowance,
    _aggregate_demand,
    _validate_garment_ipd,
    calculate_cloth,
    get_cloth_combination,
    get_stitching_combination,
)
import frappe


def _set_item_garment_ipd():
    """437765-style set-item garment IPD (Top+Bottom panels, one 60 Dia Main
    Fabric, one Colour). Panel == part so the set-item branch is deterministic."""
    return frappe._dict({
        "stiching_attribute": "Part",
        "packing_attribute": "Colour",
        "set_item_attribute": "Part",
        "is_set_item": 1,
        "is_same_packing_attribute": 0,
        "dependent_attribute": None,
        "cutting_attributes": [frappe._dict(attribute="Part")],
        "cloth_attributes": [frappe._dict(attribute="Part")],
        "accessory_attributes": [],
        "cutting_items_json": json.dumps({"attributes": ["Part", "Dia", "Weight"], "items": [
            {"Part": "Top", "Dia": "60 Dia", "Weight": 0.263},
            {"Part": "Bottom", "Dia": "60 Dia", "Weight": 0.246},
        ]}),
        "cutting_cloths_json": json.dumps({"attributes": ["Part", "Cloth"], "items": [
            {"Part": "Top", "Cloth": "Main Fabric"},
            {"Part": "Bottom", "Cloth": "Main Fabric"},
        ]}),
        "cloth_accessory_json": None,
        "accessory_clothtype_json": None,
        "stiching_item_details": [
            frappe._dict(stiching_attribute_value="Top", quantity=1, set_item_attribute_value="Top"),
            frappe._dict(stiching_attribute_value="Bottom", quantity=1, set_item_attribute_value="Bottom"),
        ],
        "stiching_item_combination_details": [
            frappe._dict(major_attribute_value="Red", set_item_attribute_value="Top", attribute_value="Red"),
            frappe._dict(major_attribute_value="Red", set_item_attribute_value="Bottom", attribute_value="Red"),
        ],
    })


def _aishwarya_garment_ipd():
    """AISHWARYA-style (Size, Panel)-keyed garment IPD (probe family F4, 33 live
    IPDs): NOT a set item; cutting keyed (Size, Panel) with dia varying BY SIZE
    and BY PANEL within a size; cloths keyed (Panel), every panel -> 'MAIN
    FABRIC'; Pouch is stitched TWICE (stiching_item_details quantity=2)."""
    return frappe._dict({
        "name": "_Test Aishwarya IPD",
        "stiching_attribute": "Panel",
        "packing_attribute": "Colour",
        "set_item_attribute": None,
        "is_set_item": 0,
        "is_same_packing_attribute": 1,
        "dependent_attribute": None,
        "cutting_attributes": [frappe._dict(attribute="Size"), frappe._dict(attribute="Panel")],
        "cloth_attributes": [frappe._dict(attribute="Panel")],
        "accessory_attributes": [],
        "cutting_items_json": json.dumps({"attributes": ["Size", "Panel", "Dia", "Weight"], "items": [
            {"Size": "75 cm", "Panel": "Front", "Dia": "13 Dia", "Weight": 0.009},
            {"Size": "75 cm", "Panel": "Back", "Dia": "13 Dia", "Weight": 0.008},
            {"Size": "75 cm", "Panel": "Pouch", "Dia": "14 Dia", "Weight": 0.005},
            {"Size": "80 cm", "Panel": "Front", "Dia": "14 Dia", "Weight": 0.010},
            {"Size": "80 cm", "Panel": "Back", "Dia": "14 Dia", "Weight": 0.009},
            {"Size": "80 cm", "Panel": "Pouch", "Dia": "14 Dia", "Weight": 0.005},
        ]}),
        "cutting_cloths_json": json.dumps({"attributes": ["Panel", "Cloth"], "items": [
            {"Panel": "Front", "Cloth": "MAIN FABRIC"},
            {"Panel": "Back", "Cloth": "MAIN FABRIC"},
            {"Panel": "Pouch", "Cloth": "MAIN FABRIC"},
        ]}),
        "cloth_accessory_json": None,
        "accessory_clothtype_json": None,
        "stiching_item_details": [
            frappe._dict(stiching_attribute_value="Front", quantity=1, set_item_attribute_value=None),
            frappe._dict(stiching_attribute_value="Back", quantity=1, set_item_attribute_value=None),
            frappe._dict(stiching_attribute_value="Pouch", quantity=2, set_item_attribute_value=None),
        ],
        "stiching_item_combination_details": [
            frappe._dict(major_attribute_value="Navy", set_item_attribute_value="Front", attribute_value="Navy"),
            frappe._dict(major_attribute_value="Navy", set_item_attribute_value="Back", attribute_value="Navy"),
            frappe._dict(major_attribute_value="Navy", set_item_attribute_value="Pouch", attribute_value="Navy"),
        ],
    })


class TestFabricRequirement(IntegrationTestCase):
    def test_cloth_allowance_matches_excel_whole_kg_rounding(self):
        demand = {
            ("Thermal Fabric", "22 Dia", "Black"): 12.96,
            ("Thermal Fabric", "24 Dia", "Red"): 142.0,
            ("Thermal Fabric", "30 Dia", "A Mel"): 46.0,
        }
        self.assertEqual(
            _apply_cloth_allowance(demand, 8.4),
            {
                ("Thermal Fabric", "22 Dia", "Black"): 14.0,
                ("Thermal Fabric", "24 Dia", "Red"): 154.0,
                ("Thermal Fabric", "30 Dia", "A Mel"): 50.0,
            },
        )

    def test_blank_cloth_allowance_preserves_decimal_demand(self):
        demand = {("Thermal Fabric", "24 Dia", "Red"): 141.6}
        self.assertIs(_apply_cloth_allowance(demand, None), demand)

    def test_calculate_cloth_set_item_sums_parts(self):
        ipd = _set_item_garment_ipd()
        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        rows = calculate_cloth(ipd, {"Colour": "Red"}, 100, cc, sc)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(sum(r["quantity"] for r in rows), 50.9, places=3)
        self.assertTrue(all(
            r["cloth_type"] == "Main Fabric" and r["colour"] == "Red" and r["dia"] == "60 Dia"
            for r in rows
        ))

    def test_aggregate_maps_label_to_item_and_reorders_to_dia_colour(self):
        ipd = _set_item_garment_ipd()
        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        demand = _aggregate_demand(
            ipd, [({"Colour": "Red"}, 100)], cc, sc, {"Main Fabric": "Polyester Velour Fabric"})
        self.assertEqual(list(demand.keys()), [("Polyester Velour Fabric", "60 Dia", "Red")])
        self.assertAlmostEqual(demand[("Polyester Velour Fabric", "60 Dia", "Red")], 50.9, places=3)

    def test_aggregate_raises_on_unmapped_cloth_label(self):
        # Deliberate deviation from production_api: an unmapped cloth LABEL must
        # RAISE, never silently under-demand (live: UL-34807 SWEAT SHIRT-1's
        # 'Scuba' label with an empty cloth_detail, Lot F0624-48).
        ipd = _set_item_garment_ipd()
        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        with self.assertRaises(frappe.ValidationError):
            _aggregate_demand(ipd, [({"Colour": "Red"}, 100)], cc, sc, {})

    def test_calculate_cloth_simple_branch(self):
        ipd = frappe._dict({
            "stiching_attribute": "Part", "packing_attribute": "Colour",
            "set_item_attribute": "Part", "is_set_item": 0, "is_same_packing_attribute": 0,
            "dependent_attribute": None,
            "cutting_attributes": [frappe._dict(attribute="Colour")],
            "cloth_attributes": [frappe._dict(attribute="Colour")],
            "accessory_attributes": [],
            "cutting_items_json": json.dumps({"attributes": ["Colour", "Dia", "Weight"], "items": [
                {"Colour": "Red", "Dia": "30 Dia", "Weight": 0.5}]}),
            "cutting_cloths_json": json.dumps({"attributes": ["Colour", "Cloth"], "items": [
                {"Colour": "Red", "Cloth": "Main Fabric"}]}),
            "cloth_accessory_json": None, "accessory_clothtype_json": None,
            "stiching_item_details": [], "stiching_item_combination_details": [],
        })
        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        rows = calculate_cloth(ipd, {"Colour": "Red"}, 100, cc, sc)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 50.0)
        self.assertEqual(
            (rows[0]["cloth_type"], rows[0]["dia"], rows[0]["colour"]),
            ("Main Fabric", "30 Dia", "Red"))

    def test_aishwarya_size_panel_dia_split_and_pouch_double(self):
        # F4: dia varies by size AND by panel within a size; Pouch counts twice.
        ipd = _aishwarya_garment_ipd()
        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        cloth = "40's GL Dyed Fabric New"
        demand = _aggregate_demand(
            ipd,
            [({"Size": "75 cm", "Colour": "Navy"}, 100),
             ({"Size": "80 cm", "Colour": "Navy"}, 50)],
            cc, sc, {"MAIN FABRIC": cloth})
        self.assertEqual(
            set(demand.keys()),
            {(cloth, "13 Dia", "Navy"), (cloth, "14 Dia", "Navy")})
        # 13 Dia: 75 cm Front+Back = (0.009 + 0.008) * 100
        self.assertAlmostEqual(demand[(cloth, "13 Dia", "Navy")], 1.7, places=3)
        # 14 Dia: 75 cm Pouch x2 + 80 cm Front+Back + 80 cm Pouch x2
        #         = 0.005*2*100 + (0.010 + 0.009)*50 + 0.005*2*50
        self.assertAlmostEqual(demand[(cloth, "14 Dia", "Navy")], 2.45, places=3)

    def test_colour_keyed_cloth_mapping_under_panel_cutting(self):
        # The PRINT O.E-1 exception: cloths keyed by (Colour) while cutting stays
        # keyed (Size, Panel).
        ipd = _aishwarya_garment_ipd()
        ipd.cloth_attributes = [frappe._dict(attribute="Colour")]
        ipd.cutting_cloths_json = json.dumps({"attributes": ["Colour", "Cloth"], "items": [
            {"Colour": "Navy", "Cloth": "MAIN FABRIC"}]})
        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        rows = calculate_cloth(ipd, {"Size": "75 cm", "Colour": "Navy"}, 10, cc, sc)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["cloth_type"] == "MAIN FABRIC" for r in rows))

    def test_schema_two_cutting_uses_each_panels_fabric_colour(self):
        ipd = _aishwarya_garment_ipd()
        ipd.enable_panel_wise_consumption_matrix = 1
        ipd.panel_wise_consumption_matrix_json = {"schema_version": 2}
        ipd.cutting_attributes = [
            frappe._dict(attribute="Size"),
            frappe._dict(attribute="Panel"),
            frappe._dict(attribute="Colour"),
        ]
        ipd.cutting_items_json = json.dumps({
            "attributes": ["Size", "Panel", "Colour", "Dia", "Weight"],
            "items": [
                {"Size": "75 cm", "Panel": "Front", "Colour": "Navy",
                 "Dia": "13 Dia", "Weight": 0.009},
                {"Size": "75 cm", "Panel": "Back", "Colour": "Navy",
                 "Dia": "13 Dia", "Weight": 0.008},
                {"Size": "75 cm", "Panel": "Pouch", "Colour": "Red",
                 "Dia": "14 Dia", "Weight": 0.005},
            ],
        })
        ipd.stiching_item_combination_details[-1].attribute_value = "Red"

        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        rows = calculate_cloth(
            ipd, {"Size": "75 cm", "Colour": "Navy"}, 100, cc, sc
        )

        self.assertEqual([row["colour"] for row in rows], ["Navy", "Navy", "Red"])
        for row, expected in zip(rows, [0.9, 0.8, 1.0]):
            self.assertAlmostEqual(row["quantity"], expected, places=6)

    def test_incomplete_ipd_raises_clear_error(self):
        # 25 live empty-draft garment IPDs (10 with live Lots, e.g. 34178) must get
        # a clear message, not KeyError: 'items'.
        ipd = _aishwarya_garment_ipd()
        ipd.cutting_items_json = None
        ipd.cutting_cloths_json = None
        with self.assertRaises(frappe.ValidationError):
            _validate_garment_ipd(ipd)

    def test_accessory_demand_included(self):
        # Accessory demand (66% of live garment IPDs) is IN scope and lands in the
        # same rows the CPDs are seeded from.
        ipd = _aishwarya_garment_ipd()
        ipd.cloth_accessory_json = json.dumps({"attributes": [], "items": [
            {"Accessory": "Neck Tape", "Dia": "34 Dia", "Weight": 0.001}]})
        ipd.accessory_clothtype_json = json.dumps({"Neck Tape": "MAIN FABRIC"})
        ipd.stiching_accessory_json = json.dumps({"items": [
            {"accessory": "Neck Tape", "major_colour": "Navy",
             "accessory_colour": "Navy", "cloth_type": "MAIN FABRIC"}]})
        cc = get_cloth_combination(ipd)
        sc = get_stitching_combination(ipd)
        rows = calculate_cloth(ipd, {"Size": "75 cm", "Colour": "Navy"}, 10, cc, sc)
        acc = [r for r in rows if r["type"] == "accessory"]
        self.assertEqual(len(acc), 1)
        self.assertEqual((acc[0]["dia"], acc[0]["colour"]), ("34 Dia", "Navy"))
        self.assertAlmostEqual(acc[0]["quantity"], 0.01, places=4)
