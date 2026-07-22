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
    _requirement_payload,
    build_cloth_programs,
)
from essdee_yrp.fabric_chain import final_combos, get_fabric_steps
from essdee_yrp.fabric_plan import solve_chain_backward


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

    def test_find_or_create_cpd_rejects_greige_drift(self):
        """(e) A second selection with a DIFFERENT greige on the same shared cloth
        CPD must be rejected up front — union-merging (Grey, Red) beside
        (Ecru, Red) rows would create same-output matrix groups, making the
        backward solver AMBIGUOUS at plan time (task-6 final-review guard)."""
        _find_or_create_cpd(self.cloth, self.selection, self.tuples)
        other_greige = _ensure_iav("Colour", "_Test Other Greige CPD")
        drift_selection = dict(self.selection, greige_colour=other_greige)
        with self.assertRaisesRegex(frappe.ValidationError, "already dyes from"):
            _find_or_create_cpd(self.cloth, drift_selection, self.tuples)

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

        programs = {r.dia: flt(r.weight)
                    for r in lot.lot_fabric_programs if r.cloth_item == self.cloth}
        self.assertEqual(set(programs), {self.dia})
        self.assertAlmostEqual(programs[self.dia], 50.5, places=3)

        dye_out = {(r.dia, r.colour): flt(r.planned_weight)
                   for r in lot.lot_fabric_step_ledger
                   if r.cloth_item == self.cloth and r.process_name == self.d_proc
                   and r.side == "Output"}
        self.assertAlmostEqual(dye_out[(self.dia, self.red)], 30.0, places=3)
        self.assertAlmostEqual(dye_out[(self.dia, blue)], 20.5, places=3)
        knit_out = {(r.dia, r.colour): flt(r.planned_weight)
                    for r in lot.lot_fabric_step_ledger
                    if r.cloth_item == self.cloth and r.process_name == self.k_proc
                    and r.side == "Output"}
        self.assertAlmostEqual(knit_out[(self.dia, self.greige)], 50.5, places=3)

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
