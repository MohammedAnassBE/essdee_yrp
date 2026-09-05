# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
"""Regression tests for the fabric WO Calculate backend.

Legacy attribute-less yarn Items remain supported. Variant-aware yarn recipes
carry the physical input Colour in their knitting matrix combinations.

Fixtures follow test_cloth_program's pattern — everything created inside the
rolled-back test transaction, no frappe.db.commit()."""

from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from essdee_yrp.api import cloth_program
from essdee_yrp.api.cloth_program import build_cloth_programs
from essdee_yrp.api.test_cloth_program import (
    _ensure_iav,
    _ensure_item,
    _ensure_process,
    _reset_cpd,
)
from essdee_yrp.api.work_order import (
    _consolidate_fabric_rows,
    _selected_lot_fabrics,
    calculate_fabric_deliverables,
    get_fabric_deliverable_context,
    get_work_order_selection_context,
)
from essdee_yrp.fabric_reference import (
    get_reference_allocations,
    scale_reference_allocations,
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


class TestSelectedLotFabrics(TestCase):
    def test_exact_production_detail_excludes_sibling_cloths(self):
        selected = frappe._dict(
            name="selected",
            cloth_item="36's GL Dyed Cloth",
            production_detail="36's GL Dyed Cloth-3",
        )
        sibling = frappe._dict(
            name="sibling",
            cloth_item="30's GL",
            production_detail="30's GL-2",
        )
        wo = frappe._dict(
            item="36's GL Dyed Cloth",
            production_detail="36's GL Dyed Cloth-3",
        )
        lot = frappe._dict(lot_fabric_details=[selected, sibling])

        self.assertEqual(_selected_lot_fabrics(wo, lot), [selected])

    def test_item_fallback_for_legacy_work_order(self):
        selected = frappe._dict(
            name="selected",
            cloth_item="36's GL Dyed Cloth",
            production_detail="36's GL Dyed Cloth-3",
        )
        sibling = frappe._dict(
            name="sibling",
            cloth_item="30's GL",
            production_detail="30's GL-2",
        )
        wo = frappe._dict(item="36's GL Dyed Cloth")
        lot = frappe._dict(lot_fabric_details=[selected, sibling])

        self.assertEqual(_selected_lot_fabrics(wo, lot), [selected])


class TestFabricRowConsolidation(TestCase):
    def test_same_physical_variant_is_stored_once_with_route_allocations(self):
        rows = [
            {
                "item_variant": "Yarn 30's GL",
                "qty": 10,
                "pending_quantity": 10,
                "uom": "Kg",
                "received_type": "Accepted",
                "is_calculated": 1,
                "fabric_reference_variant": "Cloth-36-Grey",
            },
            {
                "item_variant": "Yarn 30's GL",
                "qty": 15,
                "pending_quantity": 15,
                "uom": "Kg",
                "received_type": "Accepted",
                "is_calculated": 1,
                "fabric_reference_variant": "Cloth-36-Red",
            },
        ]

        result = _consolidate_fabric_rows(
            rows, "Work Order Deliverables", supports_allocations=True
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["qty"], 25)
        self.assertEqual(result[0]["pending_quantity"], 25)
        self.assertIsNone(result[0]["fabric_reference_variant"])
        self.assertEqual(
            get_reference_allocations(result[0]),
            {"Cloth-36-Grey": 10, "Cloth-36-Red": 15},
        )

    def test_partial_receipt_is_split_by_stored_route_weights(self):
        self.assertEqual(
            scale_reference_allocations(
                {"Cloth-36-Grey": 40, "Cloth-36-Red": 60},
                25,
            ),
            {"Cloth-36-Grey": 10, "Cloth-36-Red": 15},
        )


class TestCalculateFabricDeliverables(IntegrationTestCase):
    def setUp(self):
        self.dia = _ensure_iav("Dia", "_Test 60 Dia CPD")
        self.greige = _ensure_iav("Colour", "_Test Greige CPD")
        self.red = _ensure_iav("Colour", "_Test Red CPD")
        self.yarn = _ensure_item("_Test Plain Yarn WOCalc")
        self.assertEqual(frappe.get_doc("Item", self.yarn).get("attributes"), [])
        # Kept outside this legacy cloth recipe to exercise the generic
        # partial-variant compatibility resolver.
        self.declared_item = _ensure_attributed_item(
            "_Test Declared Item WOCalc", ["Colour"])
        # Cloth mirrors live Thermal Rib: declares Dia + Colour.
        self.cloth = _ensure_attributed_item("_Test Cloth WOCalc", ["Dia", "Colour"])
        frappe.db.set_value("Item", self.cloth, "is_cloth_item", 1)
        _reset_cpd(self.cloth)
        self.k_proc = _ensure_process("_Test Knit CPD", is_item_conversion=1)
        self.d_proc = _ensure_process("_Test Dye CPD")
        frappe.db.set_value("Process", self.k_proc, "is_cloth_process", 1)
        frappe.db.set_value("Process", self.d_proc, "is_cloth_process", 1)
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
            "doctype": "Work Order",
            "wo_date": nowdate(), "process_name": self.k_proc,
            "item": self.cloth, "lot": self.lot.name,
            "planned_start_date": nowdate(), "planned_end_date": nowdate(),
            "supplier_address": addr, "delivery_address": addr,
        }).insert(ignore_permissions=True)

    def test_selection_context_autofills_single_cloth_item_and_ipd(self):
        cloth_ipd = frappe.db.get_value(
            "Lot Fabric Detail",
            {"parent": self.lot.name, "cloth_item": self.cloth},
            "production_detail",
        )
        context = get_work_order_selection_context(
            self.lot.name, self.k_proc
        )
        self.assertTrue(context["is_cloth_process"])
        self.assertEqual(context["item_options"], [self.cloth])
        self.assertEqual(context["auto_item"], self.cloth)
        self.assertEqual(context["auto_production_detail"], cloth_ipd)
        # The server hook applies the same derived pair to API/import-created WOs.
        self.wo.reload()
        self.assertEqual(self.wo.production_detail, cloth_ipd)

    def test_generic_identity_washing_is_a_reference_aware_gated_stage(self):
        """An ordered no-change Washing step receives Greige from Knitting,
        preserves the final route reference, and becomes Dyeing's availability
        source instead of being skipped as a popup-only special case."""
        washing = _ensure_process("_Test Ordered Identity Washing WOCalc")
        frappe.db.set_value("Process", washing, "is_cloth_process", 1)
        fabric = next(
            row for row in self.lot.lot_fabric_details
            if row.cloth_item == self.cloth
        )
        ipd = frappe.get_doc("Item Production Detail", fabric.production_detail)
        dye_sequence = next(
            row.sequence for row in ipd.fabric_processes
            if row.fabric_process == self.d_proc
        )
        for row in ipd.fabric_processes:
            if row.fabric_process == self.d_proc:
                row.sequence = 30
        for row in ipd.fabric_value_mappings:
            if flt(row.sequence) == flt(dye_sequence):
                row.sequence = 30
        ipd.append("fabric_processes", {
            "sequence": 20,
            "fabric_process": washing,
            "input_item": self.cloth,
            "output_item": self.cloth,
            "quantity_ratio": 1,
        })
        ipd.save(ignore_permissions=True)

        addr = _ensure_address("_Test Ordered Washing WO Supplier")
        wash_wo = frappe.get_doc({
            "doctype": "Work Order",
            "wo_date": nowdate(),
            "process_name": washing,
            "item": self.cloth,
            "lot": self.lot.name,
            "production_detail": ipd.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)
        wash_context = get_fabric_deliverable_context(wash_wo.name)
        self.assertEqual(wash_context["kind"], "identity")
        wash_row = wash_context["rows"][0]
        qty_row = next(
            row for row in wash_row["qty_rows"]
            if row["out_attrs"] == {"Dia": self.dia, "Colour": self.greige}
        )
        self.assertTrue(qty_row["reference_item_variant"])
        self.assertEqual(
            qty_row["target_attrs"],
            {"Dia": self.dia, "Colour": self.red},
        )

        result = calculate_fabric_deliverables(wash_wo.name, [{
            "fabric_row": wash_row["fabric_row"],
            "entries": [{
                "key": qty_row["key"],
                "out_attrs": qty_row["out_attrs"],
                "qty": 12,
            }],
        }])
        self.assertEqual(result, {"deliverables": 1, "receivables": 1})
        wash_wo.reload()
        deliverable = next(row for row in wash_wo.deliverables if row.is_calculated)
        receivable = wash_wo.receivables[0]
        self.assertEqual(deliverable.item_variant, receivable.item_variant)
        self.assertEqual(
            deliverable.fabric_reference_variant,
            qty_row["reference_item_variant"],
        )
        self.assertEqual(
            receivable.fabric_reference_variant,
            qty_row["reference_item_variant"],
        )

        # A generic identity row now appears in get_fabric_step(), so GRN must
        # still take the 1:1 identity consumption path instead of asking for a
        # non-existent process matrix.
        from essdee_yrp.fabric_grn import calculate_consumption_plan

        grn = frappe.new_doc("Goods Received Note")
        grn.against = "Work Order"
        grn.against_id = wash_wo.name
        grn.append("items", {
            "item_variant": receivable.item_variant,
            "quantity": 6,
            "uom": receivable.uom,
            "ref_docname": receivable.name,
        })
        with patch(
            "essdee_yrp.fabric_grn._allocate_to_work_order_deliverables",
            side_effect=lambda rows, _wo, _grn: rows,
        ):
            consumption = calculate_consumption_plan(grn)
        self.assertEqual(len(consumption), 1)
        self.assertEqual(consumption[0]["item_variant"], receivable.item_variant)
        self.assertEqual(flt(consumption[0]["qty"]), 6)
        self.assertEqual(
            consumption[0]["reference_item_variant"],
            qty_row["reference_item_variant"],
        )

        dye_wo = frappe.get_doc({
            "doctype": "Work Order",
            "wo_date": nowdate(),
            "process_name": self.d_proc,
            "item": self.cloth,
            "lot": self.lot.name,
            "production_detail": ipd.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)
        dye_context = get_fabric_deliverable_context(dye_wo.name)
        self.assertEqual(dye_context["kind"], "dyeing")
        self.assertEqual(
            dye_context["source_process_options"][0]["process_name"],
            washing,
        )
    def test_non_cloth_selection_uses_lot_garment_item_and_ipd(self):
        sewing = _ensure_process("_Test Sewing WO Selection")
        frappe.db.set_value("Process", sewing, "is_cloth_process", 0)
        garment_ipd = frappe.db.get_value(
            "Lot Fabric Detail",
            {"parent": self.lot.name, "cloth_item": self.cloth},
            "production_detail",
        )
        frappe.db.set_value(
            "Lot",
            self.lot.name,
            {"item": self.cloth, "production_detail": garment_ipd},
        )

        context = get_work_order_selection_context(self.lot.name, sewing)
        self.assertFalse(context["is_cloth_process"])
        self.assertEqual(context["item_options"], [self.cloth])
        self.assertEqual(context["auto_item"], self.cloth)
        self.assertEqual(context["auto_production_detail"], garment_ipd)

    def _calculate(self):
        ctx = get_fabric_deliverable_context(self.wo.name)
        self.assertEqual(ctx["kind"], "knitting")
        self.assertEqual(len(ctx["rows"]), 1)
        row = ctx["rows"][0]
        self.assertEqual(row["yarn_item"], self.yarn)
        self.assertTrue(all(qr["program"] == 48 for qr in row["qty_rows"]))
        payload = [{
            "fabric_row": row["fabric_row"],
            "colour": row["greige_colour"],
            "entries": [
                {"key": qr["key"], "qty": qr["balance"] or qr["program"]}
                for qr in row["qty_rows"]
            ],
        }]
        return calculate_fabric_deliverables(self.wo.name, payload)

    def test_attribute_less_yarn_calculates_without_colour_demand(self):
        """The yarn deliverable remains attribute-less while the knitting
        receivable starts the cloth's physical Colour + Dia route."""
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
        # The rounded 48 kg cloth program / 3.0 cloth-per-kg-yarn = 16 kg yarn.
        self.assertAlmostEqual(delivs[0].qty, 48 / 3.0, places=2)

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

    def test_knitting_ignores_process_default_excess(self):
        """The Lot program already contains its manually chosen excess."""
        frappe.db.set_value("Process", self.k_proc, "default_excess", 5)
        frappe.clear_cache(doctype="Process")
        try:
            self._calculate()
            self.wo.reload()
            self.assertAlmostEqual(self.wo.receivables[0].qty, 48, places=3)
        finally:
            frappe.db.set_value("Process", self.k_proc, "default_excess", 0)
            frappe.clear_cache(doctype="Process")

    def test_calculate_is_idempotent_for_partial_variant(self):
        """Second Calculate must REUSE the minted attr-less yarn variant (no
        DuplicateEntryError, no second variant on the yarn Item)."""
        self._calculate()
        self._calculate()
        # Assert the exact name set — a bare len() count would be fragile
        # against sibling tests minting OTHER variants on the same yarn in the
        # shared class transaction (review follow-up).
        variants = frappe.get_all("Item Variant", filters={"item": self.yarn}, pluck="name")
        self.assertEqual(variants, [self.yarn])

    def test_calculated_receivables_keep_process_cost_enforcement(self):
        """Fabric Calculate must leave ordinary Work Order costing intact.

        A missing approved cost still blocks submit, and the standard YRP
        costing method prices every route-generated receivable.
        """
        self._calculate()
        wo = frappe.get_doc("Work Order", self.wo.name)

        with patch.object(
            type(wo), "get_receivable_process_cost", return_value=None
        ):
            with self.assertRaisesRegex(
                frappe.ValidationError, "No approved Process Cost"
            ):
                wo.submit()

        process_cost = frappe._dict({
            "name": "_Test Fabric Process Cost",
            "depends_on_attribute": 0,
            "process_cost_values": [
                frappe._dict({"min_order_qty": 0, "price": 7.5}),
            ],
        })
        with (
            patch.object(
                type(wo),
                "get_receivable_process_cost",
                return_value=process_cost.name,
            ),
            patch(
                "yrp.yrp.doctype.work_order.work_order.frappe.get_doc",
                return_value=process_cost,
            ),
        ):
            wo.set_receivable_process_costs(require_approved=True)

        self.assertEqual(wo.process_cost, process_cost.name)
        self.assertTrue(wo.receivables)
        for row in wo.receivables:
            self.assertEqual(row.process_cost, process_cost.name)
            self.assertEqual(flt(row.cost), 7.5)
            self.assertEqual(
                flt(row.total_cost), round(7.5 * flt(row.qty), 2)
            )

    def test_resolve_variant_keeps_declared_drops_undeclared(self):
        """_resolve_variant: attrs the Item DECLARES are always kept (full-set
        path); attrs it does NOT declare are dropped instead of poisoning the
        tuple lookup into a duplicate-name insert."""
        from essdee_yrp.api.work_order import _resolve_variant

        v = _resolve_variant(
            self.declared_item, {"Colour": self.red, "Dia": self.dia})
        doc = frappe.get_doc("Item Variant", v)
        self.assertEqual(
            {r.attribute: r.attribute_value for r in doc.attributes},
            {"Colour": self.red},
        )

    def test_resolve_variant_nonempty_partial_subset(self):
        """Partial path with a NON-empty subset (cloth declares Dia+Colour,
        only Colour provided): the variant carries just Colour, stamps the
        base-shaped tuple hash, and a second resolve reuses it."""
        from essdee_yrp.api.work_order import _resolve_variant

        v = _resolve_variant(self.cloth, {"Colour": self.red})
        doc = frappe.get_doc("Item Variant", v)
        self.assertEqual(doc.item, self.cloth)
        self.assertEqual(
            {r.attribute: r.attribute_value for r in doc.attributes},
            {"Colour": self.red},
        )
        self.assertEqual(
            doc.item_tuple_attribute, str(tuple(sorted({"Colour": self.red}.items()))))
        self.assertEqual(_resolve_variant(self.cloth, {"Colour": self.red}), v)

    def test_identity_washing_keeps_routes_that_bypass_dyeing(self):
        """Mixed yarn routes at two dias survive before/after Dyeing without
        offering stale intermediate colours or an IPD-wide cross product."""
        suffix = frappe.generate_hash(length=6)
        black = _ensure_iav("Colour", f"_Test Bypass Black {suffix}")
        green = _ensure_iav("Colour", f"_Test Bypass Green {suffix}")
        dia2 = _ensure_iav("Dia", f"_Test Bypass 22 Dia {suffix}")
        yarn = _ensure_attributed_item(f"_Test Bypass Yarn {suffix}", ["Colour"])
        dyed_yarn = _ensure_attributed_item(f"_Test Bypass Dyed Yarn {suffix}", ["Colour"])
        cloth = _ensure_attributed_item(f"_Test Bypass Cloth {suffix}", ["Dia", "Colour"])
        frappe.db.set_value("Item", cloth, "is_cloth_item", 1)
        _reset_cpd(cloth)
        washing = _ensure_process(f"_Test Bypass Washing {suffix}")
        frappe.db.set_value("Process", washing, "is_cloth_process", 1)
        lot = frappe.get_doc({"doctype": "Lot", "lot_name": f"_Test Bypass Lot {suffix}"}).insert()
        knitting_colours = {self.red: self.greige, black: black, green: green}
        selection = {
            "cloth_item": cloth, "yarn_item": yarn,
            "knitting_process": self.k_proc, "dyeing_process": self.d_proc,
            "compacting_process": None, "cloth_per_kg_yarn": 1,
            "colour_yarn_recipes": [
                {"colour": colour, "yarn_item": dyed_yarn if colour == black else yarn,
                 "yarn_colour": black if colour == black else self.greige, "ratio": 100}
                for colour in knitting_colours
            ],
            "fabric_routes": [
                {"finished_colour": colour, "finished_dia": dia,
                 "knitting_output_colour": output_colour, "knitting_output_dia": dia}
                for colour, output_colour in knitting_colours.items()
                for dia in (self.dia, dia2)
            ],
        }
        demand = {(cloth, dia, colour): 12 for colour in knitting_colours for dia in (self.dia, dia2)}
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(lot.name, [selection])
        lot.reload()
        ipd = frappe.get_doc("Item Production Detail", lot.lot_fabric_details[0].production_detail)
        wash_step = ipd.append("fabric_processes", {
            "sequence": 30, "fabric_process": washing,
            "input_item": cloth, "output_item": cloth, "quantity_ratio": 1,
        })
        ipd.save()
        addr = _ensure_address()
        wo = frappe.get_doc({
            "doctype": "Work Order", "wo_date": nowdate(), "process_name": washing,
            "item": cloth, "lot": lot.name, "production_detail": ipd.name,
            "planned_start_date": nowdate(), "planned_end_date": nowdate(),
            "supplier_address": addr, "delivery_address": addr,
        }).insert()
        # Same identity process moved after and then before Dyeing. Both the
        # popup and Calculate must consume each route's actual incoming state.
        for sequence in (30, 15):
            with self.subTest(sequence=sequence):
                wash_step.sequence = sequence
                ipd.save()
                context = get_fabric_deliverable_context(wo.name)
                row = context["rows"][0]
                self.assertEqual(len(row["qty_rows"]), 6)
                for qty_row in row["qty_rows"]:
                    target = qty_row["target_attrs"]
                    expected_colour = (knitting_colours[target["Colour"]]
                                       if sequence == 15 else target["Colour"])
                    self.assertEqual(qty_row["in_attrs"], {
                        "Dia": target["Dia"], "Colour": expected_colour,
                    })
                    self.assertEqual(qty_row["out_attrs"], qty_row["in_attrs"])
                    self.assertTrue(qty_row["reference_item_variant"])
                result = calculate_fabric_deliverables(wo.name, [{
                    "fabric_row": row["fabric_row"], "entries": [
                        {"key": q["key"], "out_attrs": q["out_attrs"], "qty": 3}
                        for q in row["qty_rows"]
                    ],
                }])
                self.assertEqual(result, {"deliverables": 6, "receivables": 6})
                wo.reload()
                self.assertEqual(sum(r.qty for r in wo.receivables), 18)

    def test_route_specific_knitting_outputs_drive_context_and_receivables(self):
        """Each final-colour matrix pre-fills its own physical knitting output.

        Calculation consumes the matched matrix yarn and mints receivables in
        those route-specific colours; no global Greige fallback is involved.
        A cloth recipe remains a Lot-program Knitting stage when its configured
        input contract adds Consume Colour mappings to those yarn inputs.
        """
        suffix = frappe.generate_hash(length=6)
        grey_melange = _ensure_iav("Colour", f"_Test Routed G Mel {suffix}")
        knitting_dia = _ensure_iav("Dia", f"_Test Routed 18 Dia {suffix}")
        final_dia = _ensure_iav("Dia", f"_Test Routed 22 Dia {suffix}")
        yarn_a = _ensure_attributed_item(
            f"_Test Routed Yarn A {suffix}", ["Colour"])
        yarn_b = _ensure_attributed_item(
            f"_Test Routed Yarn B {suffix}", ["Colour"])
        cloth = _ensure_attributed_item(
            f"_Test Routed Cloth {suffix}", ["Dia", "Colour"])
        frappe.db.set_value("Item", cloth, "is_cloth_item", 1)
        _reset_cpd(cloth)
        knitting = _ensure_process(
            f"_Test Routed Knit {suffix}", is_item_conversion=1)
        knitting_doc = frappe.get_doc("Process", knitting)
        knitting_doc.set(
            "conversion_input_attributes", [{"attribute": "Colour"}])
        knitting_doc.set("conversion_output_attributes", [
            {"attribute": "Dia"},
            {"attribute": "Colour"},
        ])
        knitting_doc.save(ignore_permissions=True)
        compacting = _ensure_process(f"_Test Routed Compact {suffix}")

        lot = frappe.get_doc({
            "doctype": "Lot",
            "lot_name": f"_Test Routed Lot {suffix}",
        }).insert(ignore_permissions=True)
        selection = {
            "cloth_item": cloth,
            "yarn_item": yarn_a,
            "knitting_process": knitting,
            "dyeing_process": self.d_proc,
            "compacting_process": compacting,
            "cloth_per_kg_yarn": 3,
            "colour_yarn_recipes": [
                {
                    "colour": self.red,
                    "yarn_item": yarn_a,
                    "yarn_colour": self.greige,
                    "ratio": 100,
                },
                {
                    "colour": grey_melange,
                    "yarn_item": yarn_b,
                    "yarn_colour": grey_melange,
                    "ratio": 100,
                },
            ],
            "fabric_routes": [
                {
                    "finished_colour": self.red,
                    "finished_dia": self.dia,
                    "knitting_output_colour": self.greige,
                    "knitting_output_dia": self.dia,
                },
                {
                    "finished_colour": grey_melange,
                    "finished_dia": final_dia,
                    "knitting_output_colour": grey_melange,
                    "knitting_output_dia": knitting_dia,
                },
            ],
        }
        demand = {
            (cloth, self.dia, self.red): 30.0,
            (cloth, final_dia, grey_melange): 20.0,
        }
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(lot.name, [selection])

        addr = _ensure_address(f"_Test Routed WO Supplier {suffix}")
        work_order = frappe.get_doc({
            "doctype": "Work Order",
            "wo_date": nowdate(),
            "process_name": knitting,
            "item": cloth,
            "lot": lot.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)

        context = get_fabric_deliverable_context(work_order.name)
        self.assertEqual(context["kind"], "knitting")
        row = context["rows"][0]
        self.assertTrue(row["reference_routed"])
        routes = {
            qty_row["target_attrs"]["Colour"]: qty_row
            for qty_row in row["qty_rows"]
        }
        self.assertEqual(routes[self.red]["knit_colour"], self.greige)
        self.assertEqual(
            routes[grey_melange]["knit_colour"], grey_melange)
        self.assertEqual(routes[self.red]["knit_dia"], self.dia)
        self.assertEqual(routes[grey_melange]["knit_dia"], knitting_dia)
        self.assertEqual(routes[self.red]["section"], self.red)
        self.assertEqual(routes[self.red]["row_label"], self.dia)
        self.assertEqual(routes[self.red]["program"], 30)
        self.assertEqual(routes[grey_melange]["program"], 20)
        self.assertEqual(routes[self.red]["prefill"], 30)
        self.assertEqual(routes[grey_melange]["prefill"], 20)

        # A crafted payload cannot override the physical route colour. The
        # server derives it from the stable finished Dia/Colour reference.
        with self.assertRaisesRegex(
            frappe.ValidationError, "must receive colour"
        ):
            calculate_fabric_deliverables(work_order.name, [{
                "fabric_row": row["fabric_row"],
                "entries": [{
                    "key": routes[self.red]["key"],
                    "colour": self.red,
                    "qty": 30,
                }],
            }])

        result = calculate_fabric_deliverables(work_order.name, [{
            "fabric_row": row["fabric_row"],
            "entries": [
                {
                    "key": routes[self.red]["key"],
                    "colour": routes[self.red]["knit_colour"],
                    "qty": 30,
                },
                {
                    "key": routes[grey_melange]["key"],
                    "colour": routes[grey_melange]["knit_colour"],
                    "qty": 20,
                },
            ],
        }])
        self.assertEqual(result, {"deliverables": 2, "receivables": 2})

        work_order.reload()
        received_colours = {
            next(
                attr.attribute_value for attr in frappe.get_doc(
                    "Item Variant", child.item_variant
                ).attributes if attr.attribute == "Colour"
            )
            for child in work_order.receivables
        }
        self.assertEqual(received_colours, {self.greige, grey_melange})
        delivered_templates = {
            frappe.db.get_value("Item Variant", child.item_variant, "item")
            for child in work_order.deliverables
            if child.is_calculated
        }
        self.assertEqual(delivered_templates, {yarn_a, yarn_b})

        # The Lot's saved Cloth Program—not its remaining balance—is the popup
        # input source. A later draft therefore still pre-fills 30/20 while the
        # already-calculated first WO makes both advisory balances zero.
        next_work_order = frappe.get_doc({
            "doctype": "Work Order",
            "wo_date": nowdate(),
            "process_name": knitting,
            "item": cloth,
            "lot": lot.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)
        next_context = get_fabric_deliverable_context(next_work_order.name)
        next_routes = {
            qty_row["target_attrs"]["Colour"]: qty_row
            for qty_row in next_context["rows"][0]["qty_rows"]
        }
        self.assertEqual(next_routes[self.red]["balance"], 0)
        self.assertEqual(next_routes[self.red]["prefill"], 30)
        self.assertEqual(next_routes[grey_melange]["balance"], 0)
        self.assertEqual(next_routes[grey_melange]["prefill"], 20)

        # The direct GMEL route is absent from the Dyeing popup entirely. Only
        # the Greige -> Red route needs a dyeing Work Order.
        dye_work_order = frappe.get_doc({
            "doctype": "Work Order",
            "wo_date": nowdate(),
            "process_name": self.d_proc,
            "item": cloth,
            "lot": lot.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)
        dye_context = get_fabric_deliverable_context(dye_work_order.name)
        self.assertEqual(dye_context["kind"], "dyeing")
        dye_rows = dye_context["rows"][0]["qty_rows"]
        self.assertEqual(len(dye_rows), 1)
        self.assertEqual(
            dye_rows[0]["out_attrs"],
            {"Colour": self.red, "Dia": self.dia},
        )

        # The direct GMEL route skips Dyeing but still changes Dia. Availability
        # for Compacting must therefore come from this route's Knitting ledger,
        # not from a Dyeing stage the route never visits.
        compact_work_order = frappe.get_doc({
            "doctype": "Work Order",
            "wo_date": nowdate(),
            "process_name": compacting,
            "item": cloth,
            "lot": lot.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)
        compact_context = get_fabric_deliverable_context(
            compact_work_order.name
        )
        compact_rows = compact_context["rows"][0]["qty_rows"]
        self.assertEqual(len(compact_rows), 1)
        compact_row = compact_rows[0]
        self.assertEqual(
            compact_row["in_attrs"],
            {"Colour": grey_melange, "Dia": knitting_dia},
        )
        self.assertEqual(
            compact_row["out_attrs"],
            {"Colour": grey_melange, "Dia": final_dia},
        )
        self.assertIsNone(compact_row["available"])
        self.assertIn(
            knitting,
            [
                option["process_name"]
                for option in compact_context["source_process_options"]
            ],
        )

        compact_result = calculate_fabric_deliverables(
            compact_work_order.name,
            [{
                "fabric_row": compact_context["rows"][0]["fabric_row"],
                "entries": [{"key": compact_row["key"], "qty": 20}],
            }],
        )
        self.assertEqual(
            compact_result, {"deliverables": 1, "receivables": 1}
        )
        compact_work_order.reload()
        delivered_attrs = {
            row.attribute: row.attribute_value
            for row in frappe.get_doc(
                "Item Variant",
                compact_work_order.deliverables[0].item_variant,
            ).attributes
        }
        received_attrs = {
            row.attribute: row.attribute_value
            for row in frappe.get_doc(
                "Item Variant",
                compact_work_order.receivables[0].item_variant,
            ).attributes
        }
        self.assertEqual(
            delivered_attrs,
            {"Colour": grey_melange, "Dia": knitting_dia},
        )
        self.assertEqual(
            received_attrs,
            {"Colour": grey_melange, "Dia": final_dia},
        )


class TestMultiYarnClothIPD(IntegrationTestCase):
    """Direct cloth-IPD coverage: no Lot demand/auto-builder is involved.

    A minimal Lot child link is created only because the existing Work Order
    fabric API discovers cloth IPDs through Work Order.lot.
    """

    def _make_ipd(self):
        # Keep generated matrix/group names comfortably below Frappe's
        # 140-character Data/name limit.
        suffix = frappe.generate_hash(length=6)
        dia = _ensure_iav("Dia", f"_Test MY 60 Dia {suffix}")
        greige = _ensure_iav("Colour", f"_Test MY Greige {suffix}")
        red = _ensure_iav("Colour", f"_Test MY Red {suffix}")
        yarn_a = _ensure_item(f"_Test MY Yarn A {suffix}")
        yarn_b = _ensure_item(f"_Test MY Yarn B {suffix}")
        # The requested test shape: yarn templates are plain named Items with
        # no Colour (or any other) attribute.
        self.assertEqual(frappe.get_doc("Item", yarn_a).get("attributes"), [])
        self.assertEqual(frappe.get_doc("Item", yarn_b).get("attributes"), [])

        cloth = _ensure_attributed_item(
            f"_Test MY Cloth {suffix}", ["Dia", "Colour"])
        frappe.db.set_value("Item", cloth, "is_cloth_item", 1)
        _reset_cpd(cloth)

        knitting = _ensure_process(f"_Test MY Knitting {suffix}", is_item_conversion=1)
        dyeing = _ensure_process(f"_Test MY Dyeing {suffix}")
        washing = _ensure_process(f"_Test MY Washing {suffix}")

        ipd = frappe.new_doc("Item Production Detail")
        ipd.item = cloth
        ipd.is_cloth_item = 1
        ipd.yarn_item = yarn_a  # hidden compatibility field; table is authoritative
        ipd.cloth_per_kg_yarn = 3.0
        ipd.knitting_process = knitting
        ipd.dyeing_process = dyeing
        ipd.compacting_process = None
        ipd.append("yarn_ratio_details", {"yarn_item": yarn_a, "ratio": 60})
        ipd.append("yarn_ratio_details", {"yarn_item": yarn_b, "ratio": 40})
        ipd.append("knitting_dia_details", {"dia": dia})
        ipd.append("dyeing_colour_details", {
            "dia": dia, "from_colour": greige, "to_colour": red,
        })
        # Washing is identity: same cloth in/out, no value-change matrix.
        ipd.append("ipd_processes", {
            "process_name": washing,
            "process_item": cloth,
        })
        ipd.insert(ignore_permissions=True)
        return frappe.get_doc("Item Production Detail", ipd.name), {
            "dia": dia,
            "greige": greige,
            "red": red,
            "yarn_a": yarn_a,
            "yarn_b": yarn_b,
            "cloth": cloth,
            "knitting": knitting,
            "dyeing": dyeing,
            "washing": washing,
        }

    def _make_work_order(self, ipd, values, process):
        _ensure_default_received_type()
        lot_name = f"_Test MY Lot {self._testMethodName}"
        if frappe.db.exists("Lot", lot_name):
            lot = frappe.get_doc("Lot", lot_name)
        else:
            lot = frappe.get_doc({
                "doctype": "Lot",
                "lot_name": lot_name,
            }).insert(ignore_permissions=True)
        if not any(row.production_detail == ipd.name for row in lot.lot_fabric_details):
            lot.append("lot_fabric_details", {
                "cloth_item": values["cloth"],
                "production_detail": ipd.name,
            })
            lot.save(ignore_permissions=True)

        addr = _ensure_address("_Test Multi Yarn WO Supplier")
        return frappe.get_doc({
            "doctype": "Work Order",
            "wo_date": nowdate(),
            "process_name": process,
            "item": values["cloth"],
            "lot": lot.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)

    def test_multi_yarn_matrices_and_three_work_order_processes(self):
        ipd, v = self._make_ipd()

        matrices = frappe.get_all(
            "IPD Process Matrix",
            filters={"ipd": ipd.name},
            fields=["name", "process_name"],
        )
        self.assertEqual({m.process_name for m in matrices}, {v["knitting"], v["dyeing"]})
        self.assertNotIn(v["washing"], {m.process_name for m in matrices})

        knit_name = next(m.name for m in matrices if m.process_name == v["knitting"])
        knit = frappe.get_doc("IPD Process Matrix", knit_name)
        knit_groups = knit.get_combinations_grouped()
        self.assertEqual(len(knit_groups), 1)
        knit_group = next(iter(knit_groups.values()))
        self.assertEqual(
            [(row["item"], flt(row["qty"], 3)) for row in knit_group["input"]],
            [(v["yarn_a"], 0.6), (v["yarn_b"], 0.4)],
        )
        self.assertEqual(knit_group["output"][0]["item"], v["cloth"])
        self.assertAlmostEqual(flt(knit_group["output"][0]["qty"]), 3.0, places=3)
        # This fixture exercises the legacy global yarn-ratio path, which keeps
        # its historical Dia-only knitting output. Colour-wise recipes use the
        # complete Yarn Colour -> Knitting Colour/Dia contract.
        self.assertEqual(knit_group["output"][0]["attrs"], {"Dia": v["dia"]})

        dye_name = next(m.name for m in matrices if m.process_name == v["dyeing"])
        dye = frappe.get_doc("IPD Process Matrix", dye_name)
        dye_group = next(iter(dye.get_combinations_grouped().values()))
        self.assertEqual(dye_group["input"][0]["item"], v["cloth"])
        self.assertEqual(dye_group["output"][0]["item"], v["cloth"])
        self.assertEqual(
            dye_group["input"][0]["attrs"],
            {"Colour": v["greige"], "Dia": v["dia"]},
        )
        self.assertEqual(
            dye_group["output"][0]["attrs"],
            {"Colour": v["red"], "Dia": v["dia"]},
        )

        knit_wo = self._make_work_order(ipd, v, v["knitting"])
        knit_ctx = get_fabric_deliverable_context(knit_wo.name)
        knit_row = knit_ctx["rows"][0]
        self.assertEqual(knit_ctx["kind"], "knitting")
        self.assertEqual(
            [(row["yarn_item"], flt(row["ratio"])) for row in knit_row["yarns"]],
            [(v["yarn_a"], 60.0), (v["yarn_b"], 40.0)],
        )
        knit_result = calculate_fabric_deliverables(knit_wo.name, [{
            "fabric_row": knit_row["fabric_row"],
            "colour": v["greige"],
            "entries": [{
                "key": knit_row["qty_rows"][0]["key"],
                "qty": 30,
            }],
        }])
        self.assertEqual(knit_result, {"deliverables": 2, "receivables": 1})
        knit_wo.reload()
        delivered = {}
        for row in knit_wo.deliverables:
            if not row.is_calculated:
                continue
            template = frappe.db.get_value("Item Variant", row.item_variant, "item")
            delivered[template] = flt(row.qty)
        self.assertEqual(set(delivered), {v["yarn_a"], v["yarn_b"]})
        self.assertAlmostEqual(delivered[v["yarn_a"]], 6.0, places=3)
        self.assertAlmostEqual(delivered[v["yarn_b"]], 4.0, places=3)

        dye_wo = self._make_work_order(ipd, v, v["dyeing"])
        dye_ctx = get_fabric_deliverable_context(dye_wo.name)
        dye_row = dye_ctx["rows"][0]
        self.assertEqual(dye_ctx["kind"], "dyeing")
        target = next(
            row for row in dye_row["qty_rows"]
            if row["out_attrs"].get("Colour") == v["red"]
        )
        dye_result = calculate_fabric_deliverables(dye_wo.name, [{
            "fabric_row": dye_row["fabric_row"],
            "entries": [{"key": target["key"], "qty": 25}],
        }])
        self.assertEqual(dye_result, {"deliverables": 1, "receivables": 1})

        wash_wo = self._make_work_order(ipd, v, v["washing"])
        wash_ctx = get_fabric_deliverable_context(wash_wo.name)
        wash_row = wash_ctx["rows"][0]
        self.assertEqual(wash_ctx["kind"], "identity")
        red_row = next(
            row for row in wash_row["qty_rows"]
            if row["out_attrs"] == {"Dia": v["dia"], "Colour": v["red"]}
        )
        wash_result = calculate_fabric_deliverables(wash_wo.name, [{
            "fabric_row": wash_row["fabric_row"],
            "entries": [{
                "key": red_row["key"],
                "out_attrs": red_row["out_attrs"],
                "qty": 12,
            }],
        }])
        self.assertEqual(wash_result, {"deliverables": 1, "receivables": 1})
        wash_wo.reload()
        wash_deliverable = next(row for row in wash_wo.deliverables if row.is_calculated)
        wash_receivable = wash_wo.receivables[0]
        self.assertEqual(wash_deliverable.item_variant, wash_receivable.item_variant)
        self.assertAlmostEqual(flt(wash_deliverable.qty), 12.0, places=3)
        self.assertAlmostEqual(flt(wash_receivable.qty), 12.0, places=3)

    def test_yarn_ratio_total_must_equal_100(self):
        ipd, _values = self._make_ipd()
        ipd.yarn_ratio_details[1].ratio = 39
        with self.assertRaisesRegex(frappe.ValidationError, "total must be exactly 100"):
            ipd.save(ignore_permissions=True)

    def test_multi_input_recipe_cannot_consume_its_output_cloth(self):
        ipd, _values = self._make_ipd()
        ipd.set("yarn_ratio_details", [{
            "yarn_item": ipd.item,
            "ratio": 100,
        }])
        with self.assertRaisesRegex(frappe.ValidationError, "cannot use itself as yarn"):
            ipd.save(ignore_permissions=True)

    def test_item_bom_matches_planned_and_partial_grn_consumption(self):
        """The WO plan and GRN consumption use the same matrix + Item BOM math."""
        from essdee_yrp.fabric_grn import before_validate as calculate_grn_consumption

        ipd, v = self._make_ipd()
        accessory = _ensure_item(f"_Test MY Knit Chemical {frappe.generate_hash(length=6)}")
        ipd.append("item_bom", {
            "item": accessory,
            "qty_of_product": 10,
            "qty_of_bom_item": 2,
            "uom": "Kg",
            "process_name": v["knitting"],
        })
        ipd.save(ignore_permissions=True)

        work_order = self._make_work_order(ipd, v, v["knitting"])
        context = get_fabric_deliverable_context(work_order.name)
        fabric = context["rows"][0]
        result = calculate_fabric_deliverables(work_order.name, [{
            "fabric_row": fabric["fabric_row"],
            "colour": v["greige"],
            "entries": [{
                "key": fabric["qty_rows"][0]["key"],
                "qty": 30,
            }],
        }])
        self.assertEqual(result, {"deliverables": 3, "receivables": 1})

        work_order.reload()
        planned = {
            frappe.db.get_value("Item Variant", row.item_variant, "item"): flt(row.qty)
            for row in work_order.deliverables
            if row.is_calculated
        }
        self.assertAlmostEqual(planned[v["yarn_a"]], 6.0, places=3)
        self.assertAlmostEqual(planned[v["yarn_b"]], 4.0, places=3)
        self.assertAlmostEqual(planned[accessory], 6.0, places=3)

        # GRN consumption is restricted to inputs already delivered against
        # the Work Order. Record the calculated inputs as fully delivered so
        # this test exercises the partial-output consumption ratio itself.
        for row in work_order.deliverables:
            if row.is_calculated:
                row.db_set("pending_quantity", 0, update_modified=False)
        work_order.reload()

        receivable = work_order.receivables[0]
        grn = frappe.new_doc("Goods Received Note")
        grn.against = "Work Order"
        grn.against_id = work_order.name
        grn.append("items", {
            "item_variant": receivable.item_variant,
            "quantity": 12,
            "uom": receivable.uom,
            "ref_docname": receivable.name,
        })
        calculate_grn_consumption(grn)

        consumed = {
            frappe.db.get_value("Item Variant", row.item_variant, "item"): flt(row.quantity)
            for row in grn.grn_deliverables
        }
        self.assertAlmostEqual(consumed[v["yarn_a"]], 2.4, places=3)
        self.assertAlmostEqual(consumed[v["yarn_b"]], 1.6, places=3)
        self.assertAlmostEqual(consumed[accessory], 2.4, places=3)

    def test_identity_process_plan_includes_item_bom(self):
        """Matrix-less identity fabric processes still plan their BOM materials."""
        ipd, v = self._make_ipd()
        chemical = _ensure_item(f"_Test MY Wash Chemical {frappe.generate_hash(length=6)}")
        ipd.append("item_bom", {
            "item": chemical,
            "qty_of_product": 10,
            "qty_of_bom_item": 0.5,
            "uom": "Kg",
            "process_name": v["washing"],
        })
        ipd.save(ignore_permissions=True)

        work_order = self._make_work_order(ipd, v, v["washing"])
        context = get_fabric_deliverable_context(work_order.name)
        fabric = context["rows"][0]
        red = next(
            row for row in fabric["qty_rows"]
            if row["out_attrs"] == {"Dia": v["dia"], "Colour": v["red"]}
        )
        result = calculate_fabric_deliverables(work_order.name, [{
            "fabric_row": fabric["fabric_row"],
            "entries": [{
                "key": red["key"],
                "out_attrs": red["out_attrs"],
                "qty": 20,
            }],
        }])
        self.assertEqual(result, {"deliverables": 2, "receivables": 1})
        work_order.reload()
        planned = {
            frappe.db.get_value("Item Variant", row.item_variant, "item"): flt(row.qty)
            for row in work_order.deliverables
            if row.is_calculated
        }
        self.assertAlmostEqual(planned[v["cloth"]], 20.0, places=3)
        self.assertAlmostEqual(planned[chemical], 1.0, places=3)
