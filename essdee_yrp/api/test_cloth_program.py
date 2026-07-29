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
from frappe.utils import flt

from essdee_yrp.api import cloth_program
from essdee_yrp.api.cloth_program import (
    _ensure_lot_fabric_detail,
    _find_or_create_cpd,
    _normalize_knitting_output_colours,
    _normalize_yarns,
    _requirement_payload,
    build_cloth_programs,
)
from essdee_yrp.fabric_chain import final_combos, get_fabric_steps
from essdee_yrp.fabric_plan import solve_chain_backward
from essdee_yrp.fabric_program import (
    fetch_fabric_program_details,
    get_knitting_output_colour,
    get_knitting_output_colour_map,
)


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
        frappe.db.delete(
            "Item Yarn Ratio",
            {
                "parent": self.cloth,
                "parenttype": "Item",
                "parentfield": "yarn_ratio_details",
            },
        )
        frappe.clear_document_cache("Item", self.cloth)
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

    def test_multi_yarn_recipe_persists_and_builds_matrix_inputs(self):
        yarn_b = _ensure_item("_Test Yarn B CPD")
        selection = dict(
            self.selection,
            yarns=[
                {"yarn_item": self.yarn, "ratio": 60},
                {"yarn_item": yarn_b, "ratio": 40},
            ],
            colour_yarn_recipes=[
                {"colour": self.red, "yarn_item": self.yarn, "ratio": 60},
                {"colour": self.red, "yarn_item": yarn_b, "ratio": 40},
            ],
        )
        cpd_name = _find_or_create_cpd(self.cloth, selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual(
            [(row.yarn_item, flt(row.ratio)) for row in cpd.yarn_ratio_details],
            [(self.yarn, 60.0), (yarn_b, 40.0)],
        )
        self.assertEqual(cpd.yarn_item, self.yarn)

        knit = frappe.get_doc(
            "IPD Process Matrix",
            {"ipd": cpd_name, "process_name": self.k_proc},
        )
        group = next(iter(knit.get_combinations_grouped().values()))
        self.assertEqual(
            [(row["item"], flt(row["qty"])) for row in group["input"]],
            [(self.yarn, 0.6), (yarn_b, 0.4)],
        )

        # Colour recipes are the user-facing source. Clearing the legacy global
        # snapshot must rebuild it automatically on save.
        cpd.set("yarn_ratio_details", [])
        cpd.yarn_item = None
        cpd.save(ignore_permissions=True)
        cpd.reload()
        self.assertEqual(
            [(row.yarn_item, flt(row.ratio)) for row in cpd.yarn_ratio_details],
            [(self.yarn, 60.0), (yarn_b, 40.0)],
        )
        knit = frappe.get_doc(
            "IPD Process Matrix",
            {"ipd": cpd_name, "process_name": self.k_proc},
        )
        self.assertIsNone(
            knit.input_item,
            "A multi-yarn knitting matrix must not mislabel its first yarn as the only input.",
        )

    def test_cloth_attribute_values_are_generated_from_routes(self):
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        mapping_values = {}
        for row in cpd.item_attributes:
            mapping = frappe.get_doc("Item Item Attribute Mapping", row.mapping)
            mapping_values[row.attribute] = [
                value.attribute_value for value in mapping.values
            ]

        self.assertIn(self.dia, mapping_values["Dia"])
        self.assertIn(self.red, mapping_values["Colour"])
        self.assertIn(self.greige, mapping_values["Colour"])

    def test_all_colour_compacting_details_are_data_only(self):
        compacted_dia = _ensure_iav("Dia", "_Test 62 Dia CPD")
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        cpd.append("compacting_reference_details", {
            "colour": None,
            "input_dia": self.dia,
            "compacting_dia": compacted_dia,
            "notes": "Applies to all colours",
        })
        cpd.save(ignore_permissions=True)

        cpd.reload()
        row = cpd.compacting_reference_details[0]
        self.assertFalse(row.colour)
        self.assertEqual((row.input_dia, row.compacting_dia), (self.dia, compacted_dia))
        self.assertFalse(
            frappe.db.exists(
                "IPD Process Matrix",
                {"ipd": cpd_name, "process_name": "Compacting"},
            ),
            "Compacting Details must not create a calculation matrix or Work Order process.",
        )

    def test_yarn_recipe_requires_unique_positive_rows_totalling_100(self):
        self.assertEqual(
            _normalize_yarns({"yarn_item": self.yarn}),
            [{"yarn_item": self.yarn, "ratio": 100.0}],
        )
        with self.assertRaisesRegex(frappe.ValidationError, "exactly 100"):
            _normalize_yarns({
                "yarns": [
                    {"yarn_item": self.yarn, "ratio": 60},
                    {"yarn_item": _ensure_item("_Test Yarn B Ratio CPD"), "ratio": 30},
                ],
            })
        with self.assertRaisesRegex(frappe.ValidationError, "duplicate"):
            _normalize_yarns({
                "yarns": [
                    {"yarn_item": self.yarn, "ratio": 60},
                    {"yarn_item": self.yarn, "ratio": 40},
                ],
            })

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

    # ------------------------------------------------------------------
    # Persisted generic Fabric Processes rows (2026-07-22 fix). The legacy
    # Knitting/Dyeing/Compacting tabs were REMOVED from the IPD form
    # (patches/remove_cloth_ipd_fabric_tabs.py) — the generic Fabric
    # Processes tab is the ONLY authoring/inspection UI, and it reads the
    # persisted `fabric_processes` + `fabric_value_mappings` child tables.
    # An auto-built CPD that fills only the hidden tab fields renders an
    # EMPTY tab (owner bug, lot F0426-79/3), and the first step a user adds
    # there flips get_fabric_process_rows to persisted-only — silently
    # DROPPING knitting/dyeing from the chain and breaking the WO popup.
    # ------------------------------------------------------------------

    def test_find_or_create_cpd_persists_generic_fabric_rows(self):
        """The auto-built CPD must carry the SAME persisted rows manual
        authoring writes: knitting (seq 10, yarn->cloth, ratio) then dyeing
        (seq 20, cloth->cloth, 1) with their value mappings — Introduce Dia
        per knitting dia; Change Colour + Pin Dia per dyeing row."""
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual(
            [(r.sequence, r.fabric_process, r.input_item, r.output_item, flt(r.quantity_ratio))
             for r in sorted(cpd.fabric_processes, key=lambda r: r.sequence)],
            [(10, self.k_proc, self.yarn, self.cloth, 3.0),
             (20, self.d_proc, self.cloth, self.cloth, 1.0)])
        self.assertEqual(
            [(r.sequence, r.mapping_index, r.attribute, r.role, r.from_value or None, r.to_value or None)
             for r in sorted(cpd.fabric_value_mappings,
                             key=lambda r: (r.sequence, r.mapping_index, r.role))],
            [(10, 0, "Dia", "Introduce", None, self.dia),
             (20, 0, "Colour", "Change", self.greige, self.red),
             (20, 0, "Dia", "Pin", self.dia, self.dia)])

    def test_persisted_generic_rows_idempotent_and_chain_equivalent(self):
        """A re-build must NOT duplicate persisted rows, and the chain read
        from the PERSISTED rows (adapter now bypassed) must be identical to
        the adapter's: same steps, same reachable final combos."""
        _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual(len(cpd.fabric_processes), 2)
        self.assertEqual(len(cpd.fabric_value_mappings), 3)
        self.assertEqual(
            [(s["position"], s["process_name"], s["shape"]) for s in get_fabric_steps(cpd)],
            [(0, self.k_proc, "conversion"), (1, self.d_proc, "swap")])
        self.assertIn(frozenset({("Dia", self.dia), ("Colour", self.red)}), final_combos(cpd))

    def test_manual_generic_cloth_ipd_builds_colour_reference_matrices(self):
        """Manual Desk//web entry uses only the generic Fabric Processes tables.

        Saving/approving that document must build the same exact colour-reference
        knitting matrices as the Lot popup path; hidden legacy tab rows are not a
        prerequisite.
        """
        blue = _ensure_iav("Colour", "_Test Manual Blue CPD")
        grey_melange = _ensure_iav("Colour", "_Test Manual Grey Melange CPD")
        dia2 = _ensure_iav("Dia", "_Test Manual 20 Dia CPD")
        yarn_b = _ensure_item("_Test Manual Yarn B CPD")

        cpd = frappe.new_doc("Item Production Detail")
        cpd.item = self.cloth
        cpd.is_cloth_item = 1
        cpd.approval_status = "Approved"
        cpd.yarn_item = self.yarn
        cpd.append("yarn_ratio_details", {
            "yarn_item": self.yarn,
            "ratio": 100,
        })
        for colour, yarn in ((self.red, self.yarn), (blue, yarn_b)):
            cpd.append("colour_yarn_recipes", {
                "cloth_item": self.cloth,
                "colour": colour,
                "yarn_item": yarn,
                "ratio": 100,
            })
        cpd.append("fabric_processes", {
            "sequence": 10,
            "fabric_process": self.k_proc,
            "input_item": self.yarn,
            "output_item": self.cloth,
            "quantity_ratio": 3,
        })
        cpd.append("fabric_processes", {
            "sequence": 20,
            "fabric_process": self.d_proc,
            "input_item": self.cloth,
            "output_item": self.cloth,
            "quantity_ratio": 1,
        })
        for mapping_index, dia in enumerate((self.dia, dia2)):
            cpd.append("fabric_value_mappings", {
                "sequence": 10,
                "mapping_index": mapping_index,
                "attribute": "Dia",
                "role": "Introduce",
                "to_value": dia,
            })
        for mapping_index, (dia, source, target) in enumerate((
            (self.dia, self.greige, self.red),
            (dia2, grey_melange, blue),
        )):
            cpd.append("fabric_value_mappings", {
                "sequence": 20,
                "mapping_index": mapping_index,
                "attribute": "Colour",
                "role": "Change",
                "from_value": source,
                "to_value": target,
            })
            cpd.append("fabric_value_mappings", {
                "sequence": 20,
                "mapping_index": mapping_index,
                "attribute": "Dia",
                "role": "Pin",
                "from_value": dia,
                "to_value": dia,
            })
        cpd.insert(ignore_permissions=True)
        cpd.reload()

        self.assertEqual(cpd.get("knitting_dia_details"), [])
        self.assertEqual(cpd.get("dyeing_colour_details"), [])
        self.assertEqual(
            get_knitting_output_colour_map(cpd),
            {self.red: self.greige, blue: grey_melange},
        )
        knit_matrices = frappe.get_all(
            "IPD Process Matrix",
            filters={"ipd": cpd.name, "process_name": self.k_proc},
            fields=["name", "reference_item_variant"],
        )
        self.assertEqual(len(knit_matrices), 2)
        references = {
            frozenset(
                (row.attribute, row.attribute_value)
                for row in frappe.get_doc(
                    "Item Variant", matrix.reference_item_variant
                ).attributes
            )
            for matrix in knit_matrices
        }
        self.assertEqual(references, {
            frozenset({("Dia", self.dia), ("Colour", self.red)}),
            frozenset({("Dia", dia2), ("Colour", blue)}),
        })
        self.assertTrue(
            frappe.db.exists(
                "IPD Process Matrix",
                {"ipd": cpd.name, "process_name": self.d_proc},
            )
        )

    def test_manual_generic_exact_route_changes_dia_without_fake_dyeing(self):
        """Manual Desk/web data can express final 22 Dia cloth that is received
        from knitting as 18 Dia in its final colour.

        The exact route must build a direct knitting reference, bypass Dyeing,
        and reach the finished Dia through a real data-configured Dia process.
        """
        amel = _ensure_iav("Colour", "_Test Manual Direct AMEL CPD")
        knitting_dia = _ensure_iav("Dia", "_Test Manual Direct 18 Dia CPD")
        final_dia = _ensure_iav("Dia", "_Test Manual Direct 22 Dia CPD")
        amel_yarn = _ensure_item("_Test Manual Direct AMEL Yarn CPD")
        compacting = _ensure_process("_Test Manual Direct Compact CPD")

        cpd = frappe.new_doc("Item Production Detail")
        cpd.item = self.cloth
        cpd.is_cloth_item = 1
        cpd.approval_status = "Approved"
        cpd.yarn_item = self.yarn
        cpd.append("yarn_ratio_details", {
            "yarn_item": self.yarn,
            "ratio": 100,
        })
        for colour, yarn in (
            (self.red, self.yarn),
            (amel, amel_yarn),
        ):
            cpd.append("colour_yarn_recipes", {
                "cloth_item": self.cloth,
                "colour": colour,
                "yarn_item": yarn,
                "ratio": 100,
            })
        for route in (
            {
                "finished_colour": self.red,
                "finished_dia": self.dia,
                "knitting_output_colour": self.greige,
                "knitting_output_dia": self.dia,
            },
            {
                "finished_colour": amel,
                "finished_dia": final_dia,
                "knitting_output_colour": amel,
                "knitting_output_dia": knitting_dia,
            },
        ):
            cpd.append("fabric_routes", route)
        for sequence, process in (
            (10, self.k_proc),
            (20, self.d_proc),
            (30, compacting),
        ):
            cpd.append("fabric_processes", {
                "sequence": sequence,
                "fabric_process": process,
                "input_item": self.yarn if sequence == 10 else self.cloth,
                "output_item": self.cloth,
                "quantity_ratio": 3 if sequence == 10 else 1,
            })
        for mapping_index, dia in enumerate((self.dia, knitting_dia)):
            cpd.append("fabric_value_mappings", {
                "sequence": 10,
                "mapping_index": mapping_index,
                "attribute": "Dia",
                "role": "Introduce",
                "to_value": dia,
            })
        cpd.append("fabric_value_mappings", {
            "sequence": 20,
            "mapping_index": 0,
            "attribute": "Colour",
            "role": "Change",
            "from_value": self.greige,
            "to_value": self.red,
        })
        cpd.append("fabric_value_mappings", {
            "sequence": 20,
            "mapping_index": 0,
            "attribute": "Dia",
            "role": "Pin",
            "from_value": self.dia,
            "to_value": self.dia,
        })
        cpd.append("fabric_value_mappings", {
            "sequence": 30,
            "mapping_index": 0,
            "attribute": "Dia",
            "role": "Change",
            "from_value": knitting_dia,
            "to_value": final_dia,
        })
        cpd.append("fabric_value_mappings", {
            "sequence": 30,
            "mapping_index": 0,
            "attribute": "Colour",
            "role": "Pin",
            "from_value": amel,
            "to_value": amel,
        })
        cpd.insert(ignore_permissions=True)
        cpd.reload()

        knit_references = {
            frozenset(
                (row.attribute, row.attribute_value)
                for row in frappe.get_doc(
                    "Item Variant", matrix.reference_item_variant
                ).attributes
            )
            for matrix in frappe.get_all(
                "IPD Process Matrix",
                filters={"ipd": cpd.name, "process_name": self.k_proc},
                fields=["reference_item_variant"],
            )
        }
        self.assertEqual(
            knit_references,
            {
                frozenset({("Dia", self.dia), ("Colour", self.red)}),
                frozenset({("Dia", final_dia), ("Colour", amel)}),
            },
        )
        dye_references = frappe.get_all(
            "IPD Process Matrix",
            filters={"ipd": cpd.name, "process_name": self.d_proc},
            pluck="reference_item_variant",
        )
        self.assertEqual(len(dye_references), 1)
        self.assertEqual(
            {
                row.attribute: row.attribute_value
                for row in frappe.get_doc(
                    "Item Variant", dye_references[0]
                ).attributes
            },
            {"Dia": self.dia, "Colour": self.red},
        )
        compact_matrix = frappe.get_doc(
            "IPD Process Matrix",
            {"ipd": cpd.name, "process_name": compacting},
        )
        compact_group = next(
            iter(compact_matrix.get_combinations_grouped().values())
        )
        self.assertEqual(
            compact_group["input"][0]["attrs"],
            {"Colour": amel, "Dia": knitting_dia},
        )
        self.assertEqual(
            compact_group["output"][0]["attrs"],
            {"Colour": amel, "Dia": final_dia},
        )

    def test_rebuild_preserves_custom_fabric_steps(self):
        """A manually-added generic step OUTSIDE the managed tab sequences
        (10/20/30) — e.g. an in-chain Washing at seq 40 — must survive a
        re-build; the managed rows are refreshed (new dia appears)."""
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        wash = _ensure_process("_Test Wash CPD")
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        cpd.append("fabric_processes", {
            "sequence": 40, "fabric_process": wash,
            "input_item": self.cloth, "output_item": self.cloth, "quantity_ratio": 1})
        cpd.save(ignore_permissions=True)

        dia2 = _ensure_iav("Dia", "_Test 70 Dia CPD")
        _find_or_create_cpd(self.cloth, self.selection,
                            {(self.dia, self.red): 1.0, (dia2, self.red): 1.0})
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        by_seq = {r.sequence: r for r in cpd.fabric_processes}
        self.assertEqual(set(by_seq), {10, 20, 40})
        self.assertEqual(by_seq[40].fabric_process, wash)
        knit_dias = {r.to_value for r in cpd.fabric_value_mappings
                     if r.sequence == 10 and r.role == "Introduce"}
        self.assertEqual(knit_dias, {self.dia, dia2})

    def test_blank_yarn_rebuild_clears_stale_managed_rows(self):
        """Review follow-up (Important #1): a REBUILD with a blank yarn on a CPD
        whose managed rows were persisted earlier must CLEAR them — leaving them
        would serve a stale chain (old yarn input, new dias missing from the
        Introduce mappings -> opaque reachability failure). With the table
        emptied the adapter serves the fresh tabs, pre-fix behavior exactly."""
        _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        dia2 = _ensure_iav("Dia", "_Test 70 Dia CPD")
        cpd_name = _find_or_create_cpd(
            self.cloth, dict(self.selection, yarn_item=None),
            {(self.dia, self.red): 1.0, (dia2, self.red): 1.0})
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual(cpd.get("fabric_processes"), [])
        self.assertEqual(cpd.get("fabric_value_mappings"), [])
        self.assertEqual(
            [s["process_name"] for s in get_fabric_steps(cpd)],
            [self.k_proc, self.d_proc])
        self.assertIn(frozenset({("Dia", dia2), ("Colour", self.red)}), final_combos(cpd))

    def test_blank_yarn_rebuild_throws_when_custom_steps_present(self):
        """Review follow-up (Important #1): when the CPD ALSO carries custom
        unmanaged steps, clearing only the managed rows would leave a partial
        table that drops knitting/dyeing from the chain — refuse loudly."""
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        wash = _ensure_process("_Test Wash CPD")
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        cpd.append("fabric_processes", {
            "sequence": 40, "fabric_process": wash,
            "input_item": self.cloth, "output_item": self.cloth, "quantity_ratio": 1})
        cpd.save(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "[Yy]arn"):
            _find_or_create_cpd(
                self.cloth, dict(self.selection, yarn_item=None), self.tuples)

    def test_rebuild_renumbers_child_idx(self):
        """Review follow-up (Important #2): kept rows retain their old idx while
        appended rows get idx=len(table) — a preserve-rebuild would persist
        DUPLICATE idx values and the Desk grid (ordered by idx) could render
        the chain out of order. After a rebuild the fabric_processes idx must
        be unique, gapless and sequence-ordered."""
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        wash = _ensure_process("_Test Wash CPD")
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        cpd.append("fabric_processes", {
            "sequence": 40, "fabric_process": wash,
            "input_item": self.cloth, "output_item": self.cloth, "quantity_ratio": 1})
        cpd.save(ignore_permissions=True)
        _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        rows = sorted(cpd.fabric_processes, key=lambda r: r.idx)
        self.assertEqual([r.idx for r in rows], [1, 2, 3])
        self.assertEqual([r.sequence for r in rows], [10, 20, 40])
        vm_rows = sorted(cpd.fabric_value_mappings, key=lambda r: r.idx)
        self.assertEqual([r.idx for r in vm_rows],
                         list(range(1, len(vm_rows) + 1)))

    def test_blank_yarn_skips_persisting_but_keeps_chain(self):
        """input_item is REQD on IPD Fabric Process, and a PARTIAL persist
        would disable the tab adapter and drop steps from the chain. With a
        blank yarn nothing is persisted — the CPD still saves and the chain
        still resolves through the adapter."""
        sel = dict(self.selection, yarn_item=None)
        cpd_name = _find_or_create_cpd(self.cloth, sel, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual(cpd.get("fabric_processes"), [])
        self.assertEqual(cpd.get("fabric_value_mappings"), [])
        self.assertEqual(
            [s["process_name"] for s in get_fabric_steps(cpd)],
            [self.k_proc, self.d_proc])

    # ------------------------------------------------------------------
    # Multi-colour fan-out (piece-dyed: ONE greige at ONE dia dyed into
    # SEVERAL colours) — the owner-approved relaxation of the old
    # one-colour-per-(dia, greige) validate_swap_rows rule (task-6 Finding #1).
    # ------------------------------------------------------------------

    def test_multicolour_fanout_seeds_one_dyeing_row_per_colour(self):
        """(a) A cloth CPD with dyeing rows {dia, greige->Red} + {dia, greige->Blue}
        must VALIDATE and SAVE — one dyeing_colour_details row per demanded
        (dia, colour), all fanned out from the same greige."""
        blue = _ensure_iav("Colour", "_Test Blue CPD")
        tuples = {(self.dia, self.red): 30.0, (self.dia, blue): 20.5}
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual([r.dia for r in cpd.knitting_dia_details], [self.dia])
        self.assertEqual(
            {(r.dia, r.from_colour, r.to_colour) for r in cpd.dyeing_colour_details},
            {(self.dia, self.greige, self.red), (self.dia, self.greige, blue)})

    def test_multicolour_fanout_matrices_and_final_combos_cover_both(self):
        """(b) The dyeing matrix must emit ONE group per (dia, to_colour) —
        distinct outputs — and final_combos must contain both fan-out combos."""
        blue = _ensure_iav("Colour", "_Test Blue CPD")
        tuples = {(self.dia, self.red): 30.0, (self.dia, blue): 20.5}
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)

        combos = final_combos(cpd)
        self.assertIn(frozenset({("Dia", self.dia), ("Colour", self.red)}), combos)
        self.assertIn(frozenset({("Dia", self.dia), ("Colour", blue)}), combos)

        dye_matrix = frappe.get_doc("IPD Process Matrix", {
            "ipd": cpd_name, "process_name": self.d_proc})
        outputs = set()
        for _idx, group in dye_matrix.get_combinations_grouped().items():
            out = (group.get("output") or [{}])[0]
            outputs.add(frozenset((out.get("attrs") or {}).items()))
        # one group per (dia, to_colour); no duplicate output projections, so the
        # backward solver never sees AMBIGUOUS for fan-out demand
        self.assertEqual(outputs, {
            frozenset({("Dia", self.dia), ("Colour", self.red)}),
            frozenset({("Dia", self.dia), ("Colour", blue)}),
        })

    def test_duplicate_exact_dyeing_rows_still_rejected(self):
        """(c) The relaxation keeps the REAL invariant: an exact duplicate
        (dia, from_colour, to_colour) row is meaningless and would build two
        identical matrix groups (AMBIGUOUS at solve time) — still rejected."""
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        cpd.append("dyeing_colour_details", {
            "dia": self.dia, "from_colour": self.greige, "to_colour": self.red})
        with self.assertRaisesRegex(frappe.ValidationError, "duplicate mapping"):
            cpd.save(ignore_permissions=True)

    def test_changed_knitting_output_creates_new_cpd_version(self):
        """An output-colour change never mutates a CPD referenced by an earlier
        Lot. The builder creates a second operational profile and preserves both
        exact routes."""
        first = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        other_greige = _ensure_iav("Colour", "_Test Other Greige CPD")
        drift_selection = dict(self.selection, greige_colour=other_greige)
        second = _find_or_create_cpd(self.cloth, drift_selection, self.tuples)

        self.assertNotEqual(first, second)
        first_doc = frappe.get_doc("Item Production Detail", first)
        second_doc = frappe.get_doc("Item Production Detail", second)
        self.assertEqual(first_doc.dyeing_colour_details[0].from_colour, self.greige)
        self.assertEqual(second_doc.dyeing_colour_details[0].from_colour, other_greige)

    def test_linked_cpd_is_versioned_when_a_new_exact_route_is_added(self):
        """Adding a Dia route for a later Lot must not widen the matrices used
        by an earlier Lot or its Work Orders."""
        other_dia = _ensure_iav("Dia", "_Test 22 Dia Version CPD")
        recipe = [{
            "colour": self.red,
            "yarn_item": self.yarn,
            "ratio": 100,
        }]
        first_route = {
            "finished_dia": self.dia,
            "finished_colour": self.red,
            "knitting_output_dia": self.dia,
            "knitting_output_colour": self.greige,
        }
        first_selection = {
            **self.selection,
            "colour_yarn_recipes": recipe,
            "fabric_routes": [first_route],
        }
        first = _find_or_create_cpd(
            self.cloth, first_selection, {(self.dia, self.red): 50.9}
        )
        lot = frappe.get_doc({
            "doctype": "Lot",
            "lot_name": "_Test CPD Versioned Route Lot",
            "lot_fabric_details": [{
                "cloth_item": self.cloth,
                "production_detail": first,
            }],
        }).insert(ignore_permissions=True)
        self.assertTrue(lot.name)

        second_route = {
            "finished_dia": other_dia,
            "finished_colour": self.red,
            "knitting_output_dia": other_dia,
            "knitting_output_colour": self.greige,
        }
        second_selection = {
            **first_selection,
            "fabric_routes": [first_route, second_route],
        }
        second = _find_or_create_cpd(
            self.cloth,
            second_selection,
            {
                (self.dia, self.red): 50.9,
                (other_dia, self.red): 12.0,
            },
        )

        self.assertNotEqual(first, second)
        self.assertEqual(
            len(frappe.get_doc("Item Production Detail", first).fabric_routes),
            1,
        )
        self.assertEqual(
            len(frappe.get_doc("Item Production Detail", second).fabric_routes),
            2,
        )

    def test_knitting_output_mapping_requires_every_finished_colour(self):
        blue = _ensure_iav("Colour", "_Test Blue Output CPD")
        grey = _ensure_iav("Colour", "_Test Grey Output CPD")
        rows = _normalize_knitting_output_colours(
            {
                "knitting_output_colours": [
                    {"colour": self.red, "knitting_output_colour": self.greige},
                    {"colour": blue, "knitting_output_colour": grey},
                ]
            },
            [self.red, blue],
        )
        self.assertEqual(rows, [
            {"colour": self.red, "knitting_output_colour": self.greige},
            {"colour": blue, "knitting_output_colour": grey},
        ])
        with self.assertRaisesRegex(frappe.ValidationError, "Missing"):
            _normalize_knitting_output_colours(
                {
                    "knitting_output_colours": [
                        {"colour": self.red, "knitting_output_colour": self.greige},
                    ]
                },
                [self.red, blue],
            )

    def test_multiple_knitting_output_colours_build_exact_routes(self):
        blue = _ensure_iav("Colour", "_Test Blue Routed CPD")
        grey_melange = _ensure_iav("Colour", "_Test Grey Melange CPD")
        yarn_b = _ensure_item("_Test Routed Yarn B CPD")
        selection = dict(
            self.selection,
            greige_colour=None,
            yarns=[{"yarn_item": self.yarn, "ratio": 100}],
            colour_yarn_recipes=[
                {"colour": self.red, "yarn_item": self.yarn, "ratio": 100},
                {"colour": blue, "yarn_item": yarn_b, "ratio": 100},
            ],
            knitting_output_colours=[
                {"colour": self.red, "knitting_output_colour": self.greige},
                {"colour": blue, "knitting_output_colour": grey_melange},
            ],
        )
        cpd_name = _find_or_create_cpd(
            self.cloth,
            selection,
            {(self.dia, self.red): 30.0, (self.dia, blue): 20.0},
        )
        cpd = frappe.get_doc("Item Production Detail", cpd_name)

        self.assertEqual(
            {(row.from_colour, row.to_colour) for row in cpd.dyeing_colour_details},
            {(self.greige, self.red), (grey_melange, blue)},
        )
        self.assertEqual(
            get_knitting_output_colour_map(cpd),
            {self.red: self.greige, blue: grey_melange},
        )
        self.assertEqual(
            get_knitting_output_colour(cpd, blue, self.dia),
            grey_melange,
        )
        knit_matrices = frappe.get_all(
            "IPD Process Matrix",
            filters={"ipd": cpd_name, "process_name": self.k_proc},
            fields=["name", "reference_item_variant"],
        )
        self.assertEqual(len(knit_matrices), 2)
        self.assertTrue(all(row.reference_item_variant for row in knit_matrices))

    def test_mixed_direct_colour_route_bypasses_dyeing(self):
        """A single CPD can branch: Greige -> Red needs dyeing, while AMEL is
        already final at knitting and must create no dyeing plan/matrix row."""
        amel = _ensure_iav("Colour", "_Test AMEL Direct CPD")
        knitting_dia = _ensure_iav("Dia", "_Test 18 Dia Direct CPD")
        final_dia = _ensure_iav("Dia", "_Test 22 Dia Direct CPD")
        amel_yarn = _ensure_item("_Test AMEL Yarn CPD")
        compacting = _ensure_process("_Test Compact CPD")
        selection = dict(
            self.selection,
            greige_colour=None,
            compacting_process=compacting,
            yarns=[{"yarn_item": self.yarn, "ratio": 100}],
            colour_yarn_recipes=[
                {"colour": self.red, "yarn_item": self.yarn, "ratio": 100},
                {"colour": amel, "yarn_item": amel_yarn, "ratio": 100},
            ],
            fabric_routes=[
                {
                    "finished_colour": self.red,
                    "finished_dia": self.dia,
                    "knitting_output_colour": self.greige,
                    "knitting_output_dia": self.dia,
                },
                {
                    "finished_colour": amel,
                    "finished_dia": final_dia,
                    "knitting_output_colour": amel,
                    "knitting_output_dia": knitting_dia,
                },
            ],
        )
        demand = {
            (self.cloth, self.dia, self.red): 30.0,
            (self.cloth, final_dia, amel): 20.0,
        }
        lot = frappe.get_doc({
            "doctype": "Lot",
            "lot_name": "_Test CPD Lot Direct Colour",
        }).insert(ignore_permissions=True)
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(lot.name, [selection])

        lot.reload()
        fabric = next(
            row for row in lot.lot_fabric_details
            if row.cloth_item == self.cloth
        )
        self.assertEqual(fabric.plan_status, "Built")
        cpd = frappe.get_doc("Item Production Detail", fabric.production_detail)
        self.assertEqual(
            {
                (row.dia, row.from_colour, row.to_colour)
                for row in cpd.dyeing_colour_details
            },
            {
                (self.dia, self.greige, self.red),
                (knitting_dia, amel, amel),
            },
        )
        self.assertEqual(
            {
                (row.colour, row.from_dia, row.to_dia)
                for row in cpd.compacting_dia_details
            },
            {(amel, knitting_dia, final_dia)},
        )
        self.assertEqual(
            get_knitting_output_colour_map(cpd),
            {self.red: self.greige, amel: amel},
        )

        dye_matrix = frappe.get_doc(
            "IPD Process Matrix",
            {"ipd": cpd.name, "process_name": self.d_proc},
        )
        dye_groups = list(dye_matrix.get_combinations_grouped().values())
        self.assertEqual(len(dye_groups), 1)
        self.assertEqual(
            dye_groups[0]["output"][0]["attrs"],
            {"Colour": self.red, "Dia": self.dia},
        )
        self.assertEqual(
            final_combos(cpd),
            {
                frozenset({("Dia", self.dia), ("Colour", self.red)}),
                frozenset({("Dia", final_dia), ("Colour", amel)}),
            },
        )

        dye_outputs = {
            (row.dia, row.colour): flt(row.planned_weight)
            for row in lot.lot_fabric_step_ledger
            if row.cloth_item == self.cloth
            and row.process_name == self.d_proc
            and row.side == "Output"
        }
        self.assertEqual(dye_outputs, {(self.dia, self.red): 30.0})
        knit_outputs = {
            (row.dia, row.colour): flt(row.planned_weight)
            for row in lot.lot_fabric_step_ledger
            if row.cloth_item == self.cloth
            and row.process_name == self.k_proc
            and row.side == "Output"
        }
        self.assertEqual(
            knit_outputs,
            {
                (self.dia, self.greige): 30.0,
                (knitting_dia, amel): 20.0,
            },
        )
        compact_outputs = {
            (row.dia, row.colour): flt(row.planned_weight)
            for row in lot.lot_fabric_step_ledger
            if row.cloth_item == self.cloth
            and row.process_name == compacting
            and row.side == "Output"
        }
        self.assertEqual(compact_outputs, {(final_dia, amel): 20.0})

        display = fetch_fabric_program_details(lot)[0]
        displayed_routes = {
            (row["finished_colour"], row["finished_dia"]): (
                row["knitting_output_colour"],
                row["knitting_output_dia"],
                flt(row["weight"]),
            )
            for row in display["program"]
        }
        self.assertEqual(
            displayed_routes,
            {
                (self.red, self.dia): (
                    self.greige, self.dia, 30.0,
                ),
                (amel, final_dia): (
                    amel, knitting_dia, 20.0,
                ),
            },
        )

    def test_solve_chain_backward_splits_kg_per_colour(self):
        """Fan-out demand solves without ambiguity: dyeing outputs stay split per
        colour, the greige (dyeing input / knitting output) SUMS the colours, and
        the yarn figure scales by cloth_per_kg_yarn."""
        blue = _ensure_iav("Colour", "_Test Blue CPD")
        tuples = {(self.dia, self.red): 30.0, (self.dia, blue): 20.5}
        cpd_name = _find_or_create_cpd(self.cloth, self.selection, tuples)
        cpd = frappe.get_doc("Item Production Detail", cpd_name)

        red_key = frozenset({("Dia", self.dia), ("Colour", self.red)})
        blue_key = frozenset({("Dia", self.dia), ("Colour", blue)})
        step_plans, unreachable = solve_chain_backward(
            cpd, {red_key: 30.0, blue_key: 20.5})
        self.assertEqual(unreachable, [])
        self.assertEqual([p["process_name"] for p in step_plans],
                         [self.k_proc, self.d_proc])
        knit, dye = step_plans
        self.assertAlmostEqual(dye["outputs"][red_key], 30.0, places=3)
        self.assertAlmostEqual(dye["outputs"][blue_key], 20.5, places=3)
        greige_key = frozenset({("Dia", self.dia), ("Colour", self.greige)})
        self.assertAlmostEqual(dye["inputs"][greige_key], 50.5, places=3)
        self.assertAlmostEqual(knit["outputs"][greige_key], 50.5, places=3)
        # yarn (attr-less conversion input) = greige kg / cloth_per_kg_yarn (3.0)
        self.assertAlmostEqual(knit["inputs"][frozenset()], 50.5 / 3.0, places=3)

    def test_build_cloth_programs_multicolour_end_to_end(self):
        """(d) The whitelisted orchestrator on multi-colour demand: requirements
        SPLIT per (dia, colour) (not collapsed), plan Built, knitting program per
        dia sums the colours, ledger carries one dyeing output per colour."""
        blue = _ensure_iav("Colour", "_Test Blue CPD")
        lot = frappe.get_doc({"doctype": "Lot", "lot_name": "_Test CPD Lot Multi"}).insert(
            ignore_permissions=True)
        demand = {
            (self.cloth, self.dia, self.red): 30.0,
            (self.cloth, self.dia, blue): 20.5,
        }
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            res = build_cloth_programs(lot.name, [self.selection])
        self.assertEqual(res["cloths_built"], 1)
        lot.reload()

        fab = [f for f in lot.lot_fabric_details if f.cloth_item == self.cloth]
        self.assertEqual(len(fab), 1)
        self.assertEqual(fab[0].plan_status, "Built")

        reqs = {(r.dia, r.colour): flt(r.weight)
                for r in lot.lot_fabric_requirements if r.cloth_item == self.cloth}
        self.assertEqual(set(reqs), {(self.dia, self.red), (self.dia, blue)})
        self.assertAlmostEqual(reqs[(self.dia, self.red)], 30.0, places=3)
        self.assertAlmostEqual(reqs[(self.dia, blue)], 20.5, places=3)

        programs = {(r.dia, r.colour): flt(r.weight)
                    for r in lot.lot_fabric_programs if r.cloth_item == self.cloth}
        self.assertEqual(set(programs), {
            (self.dia, self.red),
            (self.dia, blue),
        })
        self.assertAlmostEqual(programs[(self.dia, self.red)], 30.0, places=3)
        self.assertAlmostEqual(programs[(self.dia, blue)], 20.5, places=3)

        dye_out = {(r.dia, r.colour): flt(r.planned_weight)
                   for r in lot.lot_fabric_step_ledger
                   if r.cloth_item == self.cloth and r.process_name == self.d_proc
                   and r.side == "Output"}
        self.assertAlmostEqual(dye_out[(self.dia, self.red)], 30.0, places=3)
        self.assertAlmostEqual(dye_out[(self.dia, blue)], 20.5, places=3)
        knit_out = [
            flt(r.planned_weight)
            for r in lot.lot_fabric_step_ledger
            if r.cloth_item == self.cloth and r.process_name == self.k_proc
            and r.side == "Output" and r.dia == self.dia
            and r.colour == self.greige
        ]
        self.assertAlmostEqual(sum(knit_out), 50.5, places=3)

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

    def test_build_uses_item_master_yarn_ratio_without_popup_recipe(self):
        yarn_b = _ensure_item("_Test Item Master Yarn B CPD")
        item = frappe.get_doc("Item", self.cloth)
        item.set("yarn_ratio_details", [])
        item.append("yarn_ratio_details", {
            "yarn_item": self.yarn,
            "ratio": 60,
        })
        item.append("yarn_ratio_details", {
            "yarn_item": yarn_b,
            "ratio": 40,
        })
        item.save(ignore_permissions=True)

        selection = {
            key: value
            for key, value in self.selection.items()
            if key not in {"yarn_item", "yarns", "colour_yarn_recipes"}
        }
        lot = frappe.get_doc({
            "doctype": "Lot",
            "lot_name": "_Test CPD Lot Item Recipe",
        }).insert(ignore_permissions=True)
        demand = {(self.cloth, self.dia, self.red): 50.9}
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(lot.name, [selection])

        cpd_name = frappe.db.get_value(
            "Item Production Detail",
            {"item": self.cloth, "is_cloth_item": 1},
            "name",
        )
        cpd = frappe.get_doc("Item Production Detail", cpd_name)
        self.assertEqual(
            [(row.yarn_item, flt(row.ratio)) for row in cpd.yarn_ratio_details],
            [(self.yarn, 60.0), (yarn_b, 40.0)],
        )
        self.assertEqual(
            [
                (row.colour, row.yarn_item, flt(row.ratio))
                for row in cpd.colour_yarn_recipes
            ],
            [
                (self.red, self.yarn, 60.0),
                (self.red, yarn_b, 40.0),
            ],
        )

    def test_build_cloth_programs_applies_manual_excess_once(self):
        lot = frappe.get_doc({
            "doctype": "Lot", "lot_name": "_Test CPD Lot Excess",
        }).insert(ignore_permissions=True)
        demand = {(self.cloth, self.dia, self.red): 50.9}
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(lot.name, [self.selection])
            res = build_cloth_programs(
                lot.name, [self.selection], excess_percentage=5
            )
        self.assertEqual(res["excess_percentage"], 5)
        lot.reload()
        requirement = next(
            r for r in lot.lot_fabric_requirements if r.cloth_item == self.cloth
        )
        program = next(
            r for r in lot.lot_fabric_programs if r.cloth_item == self.cloth
        )
        planned = sum(
            flt(r.planned_weight) for r in lot.lot_fabric_step_ledger
            if r.cloth_item == self.cloth and r.process_name == self.k_proc
            and r.side == "Output"
        )
        self.assertAlmostEqual(requirement.weight, 50.9, places=3)
        self.assertAlmostEqual(planned, 50.9, places=3)
        self.assertAlmostEqual(program.weight, 53.445, places=3)

    def test_build_cloth_programs_rejects_negative_excess(self):
        lot = frappe.get_doc({
            "doctype": "Lot", "lot_name": "_Test CPD Lot Negative Excess",
        }).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be negative"):
            build_cloth_programs(
                lot.name, [self.selection], excess_percentage=-1
            )

    def test_build_cloth_programs_requires_dyeing_for_coloured_demand(self):
        # A route whose knitting output differs from the finished colour must
        # fail fast without dyeing (not with an opaque planner error).
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

    def test_deleting_ipd_deletes_generated_process_matrices(self):
        # Use a cloth Item that no Lot test ever references. IntegrationTestCase
        # shares one class transaction, and a deleted/recreated deterministic CPD
        # name can otherwise be picked up by an earlier Lot's dangling Link.
        delete_cloth = _ensure_item("_Test Delete Cloth CPD")
        frappe.db.set_value("Item", delete_cloth, "is_cloth_item", 1)
        _reset_cpd(delete_cloth)
        selection = dict(self.selection, cloth_item=delete_cloth)
        cpd_name = _find_or_create_cpd(delete_cloth, selection, self.tuples)
        self.assertTrue(
            frappe.get_all("IPD Process Matrix", filters={"ipd": cpd_name})
        )

        frappe.delete_doc(
            "Item Production Detail",
            cpd_name,
            ignore_permissions=True,
        )

        self.assertFalse(frappe.db.exists("Item Production Detail", cpd_name))
        self.assertFalse(
            frappe.get_all("IPD Process Matrix", filters={"ipd": cpd_name})
        )

    def test_default_yarn_for_cloth_absent_then_present(self):
        from essdee_yrp.api.cloth_program import _default_yarn_for_cloth
        self.assertEqual(_default_yarn_for_cloth(self.cloth), "")  # no CPD yet
        _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        self.assertEqual(_default_yarn_for_cloth(self.cloth), self.yarn)

    def test_yarn_profile_absent_then_present(self):
        from essdee_yrp.api.cloth_program import _yarn_profile
        self.assertEqual(_yarn_profile(self.yarn), {})  # yarn never used on a CPD yet
        _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        profile = _yarn_profile(self.yarn)
        self.assertEqual(profile["knitting_process"], self.k_proc)
        self.assertEqual(profile["dyeing_process"], self.d_proc)
        self.assertEqual(profile["cloth_per_kg_yarn"], 3.0)
        self.assertEqual(profile["greige_colour"], self.greige)

    def test_cloth_program_defaults_come_from_ipd_settings(self):
        settings = frappe._dict({
            "default_knitting_process": self.k_proc,
            "default_dyeing_process": self.d_proc,
            "default_knitting_output_colour": self.greige,
            "default_compacting_process": "_Test Compact CPD",
            "default_cloth_per_kg_yarn": 1,
        })
        with (
            patch.object(cloth_program.frappe.db, "exists", return_value=True),
            patch.object(cloth_program.frappe, "get_single", return_value=settings),
        ):
            defaults = cloth_program._cloth_program_defaults()

        self.assertEqual(defaults, {
            "knitting_process": self.k_proc,
            "dyeing_process": self.d_proc,
            "knitting_output_colour": self.greige,
            "compacting_process": "_Test Compact CPD",
            "cloth_per_kg_yarn": 1.0,
        })

    def test_new_cloth_ipd_uses_cloth_program_settings_defaults(self):
        from essdee_yrp.ipd_validations import apply_ipd_settings_defaults

        doc = frappe.new_doc("Item Production Detail")
        doc.item = self.cloth
        doc.is_cloth_item = 1
        settings = frappe._dict({
            "default_knitting_process": self.k_proc,
            "default_dyeing_process": self.d_proc,
            "default_compacting_process": "_Test Compact CPD",
            "default_cloth_per_kg_yarn": 1,
        })
        with (
            patch.object(frappe.db, "exists", return_value=True),
            patch.object(frappe, "get_single", return_value=settings),
        ):
            apply_ipd_settings_defaults(doc)

        self.assertEqual(doc.knitting_process, self.k_proc)
        self.assertEqual(doc.dyeing_process, self.d_proc)
        self.assertEqual(doc.compacting_process, "_Test Compact CPD")
        self.assertEqual(doc.cloth_per_kg_yarn, 1)

    def test_cloth_rows_from_ipd(self):
        from essdee_yrp.api.cloth_program import _cloth_rows_from_ipd
        cloth2 = _ensure_item("_Test Cloth CPD NonBom")
        ipd = frappe._dict(cloth_detail=[
            frappe._dict(name1="Main Fabric", cloth=self.cloth, required_gsm=150, is_bom_item=1),
            frappe._dict(name1="Rib", cloth=None, required_gsm=0, is_bom_item=0),  # dropped: no cloth Item link
            # same cloth Item under a second label -> MERGED into one card
            # (live: CS-34606 Half Sleeve Polo-1, Lots F0724-96/97)
            frappe._dict(name1="Foam Fabric", cloth=self.cloth, required_gsm=180, is_bom_item=1),
            # is_bom_item=0 with a real cloth Item -> INCLUDED (pins the validated
            # include-all decision: 35 live is_bom_item=0 rows carry real demand)
            frappe._dict(name1="Collar", cloth=cloth2, required_gsm=0, is_bom_item=0),
        ])
        rows = _cloth_rows_from_ipd(ipd)
        self.assertEqual(rows, [
            {"cloth_item": self.cloth, "label": "Main Fabric / Foam Fabric", "required_gsm": 150.0},
            {"cloth_item": cloth2, "label": "Collar", "required_gsm": 0.0},
        ])

    def test_context_filters_to_demanded_cloths(self):
        from essdee_yrp.api import cloth_program as cp
        cloth2 = _ensure_item("_Test Cloth CPD Undemanded")
        garment_name = "_Test Garment Filter IPD"
        lot = frappe.get_doc({"doctype": "Lot", "lot_name": "_Test Filter Lot"}).insert(
            ignore_permissions=True)
        frappe.db.set_value("Lot", lot.name, "production_detail", garment_name)
        garment = frappe._dict(name=garment_name, cloth_detail=[
            frappe._dict(name1="Main Fabric", cloth=self.cloth, required_gsm=150, is_bom_item=1),
            frappe._dict(name1="Piping Fabric", cloth=cloth2, required_gsm=0, is_bom_item=1)])
        orig = frappe.get_cached_doc

        def fake_cached(dt, name=None, *a, **k):
            if dt == "Item Production Detail" and name == garment_name:
                return garment
            return orig(dt, name, *a, **k)

        demand = {(self.cloth, self.dia, self.red): 1.0}  # cloth2 has NO demand
        with patch.object(frappe, "get_cached_doc", side_effect=fake_cached), \
                patch.object(cp, "compute_cloth_demand", return_value=demand):
            ctx = cp.get_cloth_program_context(lot.name)
        self.assertEqual([c["cloth_item"] for c in ctx["cloths"]], [self.cloth])

    def test_get_cloth_program_context_composes(self):
        from essdee_yrp.api import cloth_program as cp
        # Seed the cloth's own CPD so default_yarn resolves.
        _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        # The Lot's garment IPD MUST have a name DISTINCT from the cloth's CPD, so
        # the reverse-query's get_cached_doc(cpd_name) reaches the REAL CPD (and is
        # not intercepted by the fake garment). Set it at DB level to skip link
        # validation for a stub-named garment IPD.
        garment_name = "_Test Garment Ctx IPD"
        lot = frappe.get_doc({"doctype": "Lot", "lot_name": "_Test Ctx Lot"}).insert(
            ignore_permissions=True)
        frappe.db.set_value("Lot", lot.name, "production_detail", garment_name)
        garment = frappe._dict(name=garment_name, cloth_detail=[
            frappe._dict(name1="Main Fabric", cloth=self.cloth, required_gsm=150, is_bom_item=1)])
        orig = frappe.get_cached_doc

        def fake_cached(dt, name=None, *a, **k):
            # Only the garment IPD is faked; the cloth's real CPD is left untouched.
            if dt == "Item Production Detail" and name == garment_name:
                return garment
            return orig(dt, name, *a, **k)

        # The context now filters to DEMANDED cloths — patch the demand so the
        # fake garment's single cloth survives the filter.
        demand = {(self.cloth, self.dia, self.red): 1.0}
        with patch.object(frappe, "get_cached_doc", side_effect=fake_cached), \
                patch.object(cp, "compute_cloth_demand", return_value=demand):
            ctx = cp.get_cloth_program_context(lot.name)
        self.assertEqual(len(ctx["cloths"]), 1)
        self.assertEqual(ctx["cloths"][0]["cloth_item"], self.cloth)
        self.assertEqual(ctx["cloths"][0]["default_yarn"], self.yarn)
        self.assertEqual(
            ctx["cloths"][0]["default_yarns"],
            [{"yarn_item": self.yarn, "ratio": 100.0}],
        )
        self.assertEqual(
            ctx["cloths"][0]["required_routes"],
            [{"dia": self.dia, "colour": self.red, "weight": 1.0}],
        )
        self.assertEqual(ctx["cloths"][0]["profile"]["knitting_process"], self.k_proc)

    def test_context_returns_complete_multi_yarn_recipe(self):
        from essdee_yrp.api import cloth_program as cp

        yarn_b = _ensure_item("_Test Context Yarn B CPD")
        selection = dict(
            self.selection,
            yarns=[
                {"yarn_item": self.yarn, "ratio": 55},
                {"yarn_item": yarn_b, "ratio": 45},
            ],
        )
        _find_or_create_cpd(self.cloth, selection, self.tuples)
        garment_name = "_Test Garment Multi Yarn Ctx IPD"
        lot = frappe.get_doc({
            "doctype": "Lot",
            "lot_name": "_Test Multi Yarn Ctx Lot",
        }).insert(ignore_permissions=True)
        frappe.db.set_value("Lot", lot.name, "production_detail", garment_name)
        garment = frappe._dict(name=garment_name, cloth_detail=[
            frappe._dict(
                name1="Main Fabric",
                cloth=self.cloth,
                required_gsm=150,
                is_bom_item=1,
            )
        ])
        original = frappe.get_cached_doc

        def fake_cached(doctype, name=None, *args, **kwargs):
            if doctype == "Item Production Detail" and name == garment_name:
                return garment
            return original(doctype, name, *args, **kwargs)

        demand = {(self.cloth, self.dia, self.red): 1.0}
        with patch.object(frappe, "get_cached_doc", side_effect=fake_cached), \
                patch.object(cp, "compute_cloth_demand", return_value=demand):
            context = cp.get_cloth_program_context(lot.name)

        self.assertEqual(
            context["cloths"][0]["default_yarns"],
            [
                {"yarn_item": self.yarn, "ratio": 55.0},
                {"yarn_item": yarn_b, "ratio": 45.0},
            ],
        )

    def test_duplicate_cloth_ipd_preserves_complete_route_and_process_configuration(self):
        from essdee_yrp.ipd_ui import duplicate_ipd

        source_name = _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        source = frappe.get_doc("Item Production Detail", source_name)

        duplicate_name = duplicate_ipd(source_name, self.cloth)
        duplicate = frappe.get_doc("Item Production Detail", duplicate_name)

        self.assertEqual(duplicate.approval_status, "Not Approved")
        for fieldname in (
            "is_cloth_item",
            "yarn_item",
            "knitting_process",
            "cloth_per_kg_yarn",
            "dyeing_process",
            "dia_wise_colour_change",
            "compacting_process",
            "colour_wise_dia_change",
        ):
            self.assertEqual(duplicate.get(fieldname), source.get(fieldname))

        for table_field in (
            "yarn_ratio_details",
            "knitting_dia_details",
            "dyeing_colour_details",
            "compacting_dia_details",
            "fabric_processes",
            "fabric_value_mappings",
            "colour_yarn_recipes",
            "fabric_routes",
            "compacting_reference_details",
        ):
            source_rows = [
                {
                    key: value
                    for key, value in row.as_dict().items()
                    if key not in {
                        "name",
                        "owner",
                        "creation",
                        "modified",
                        "modified_by",
                        "docstatus",
                        "idx",
                        "parent",
                        "parentfield",
                        "parenttype",
                    }
                }
                for row in source.get(table_field) or []
            ]
            duplicate_rows = [
                {
                    key: value
                    for key, value in row.as_dict().items()
                    if key not in {
                        "name",
                        "owner",
                        "creation",
                        "modified",
                        "modified_by",
                        "docstatus",
                        "idx",
                        "parent",
                        "parentfield",
                        "parenttype",
                    }
                }
                for row in duplicate.get(table_field) or []
            ]
            self.assertEqual(
                duplicate_rows,
                source_rows,
                f"{table_field} changed while duplicating the cloth IPD",
            )
