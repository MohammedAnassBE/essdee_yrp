# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
"""Regression tests for the fabric WO Calculate backend.

Owner ruling: yarn Items are attribute-less. Colour and Dia begin on the cloth
received from knitting, so the yarn deliverable must never be colour-stamped.

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
    _normalize_generated_uom_rows,
    _selected_lot_fabrics,
    calculate_fabric_deliverables,
    get_fabric_deliverable_context,
    get_work_order_selection_context,
)
from essdee_yrp.fabric_reference import (
    get_reference_allocations,
    scale_reference_allocations,
)
from essdee_yrp.work_order_actions import get_delivery_challan_defaults
from essdee_yrp.hooks import override_whitelisted_methods
from essdee_yrp.overrides.delivery_challan import EssdeeDeliveryChallan


class TestWorkOrderDeliveryChallanDefaults(TestCase):
    def test_source_location_and_warehouse_are_left_for_operator(self):
        work_order = frappe._dict(
            name="WO-MANUAL-SOURCE-1",
            lot="LOT-MANUAL-SOURCE-1",
            includes_packing=0,
            delivery_address="SOURCE-BILLING",
            delivery_address_details="Source address",
            supplier_address="TARGET-BILLING",
            supplier_address_details="Target address",
        )
        base_defaults = {
            "from_location": "WORK-ORDER-DELIVERY-LOCATION",
            "from_warehouse": "WORK-ORDER-DELIVERY-WAREHOUSE",
            "supplier": "JOB-WORKER",
            "to_warehouse": "JOB-WORKER-WAREHOUSE",
            "items": [],
            "item_details": [],
        }

        with (
            patch(
                "essdee_yrp.work_order_actions._open_submitted_work_order",
                return_value=work_order,
            ),
            patch("frappe.has_permission", return_value=True),
            patch(
                "yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan.get_work_order_defaults",
                return_value=base_defaults,
            ),
        ):
            defaults = get_delivery_challan_defaults(work_order.name)

        self.assertEqual(defaults["from_location"], "")
        self.assertEqual(defaults["from_warehouse"], "")
        self.assertEqual(defaults["supplier"], "JOB-WORKER")
        self.assertEqual(defaults["to_warehouse"], "JOB-WORKER-WAREHOUSE")

    def test_required_addresses_are_copied_from_work_order(self):
        work_order = frappe._dict(
            name="WO-ADDRESS-1",
            lot="LOT-ADDRESS-1",
            includes_packing=0,
            delivery_address="SOURCE-BILLING",
            delivery_address_details="Source address",
            supplier_address="TARGET-BILLING",
            supplier_address_details="Target address",
        )

        with (
            patch(
                "essdee_yrp.work_order_actions._open_submitted_work_order",
                return_value=work_order,
            ),
            patch("frappe.has_permission", return_value=True),
            patch(
                "yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan.get_work_order_defaults",
                return_value={"items": [], "item_details": []},
            ),
        ):
            defaults = get_delivery_challan_defaults(work_order.name)

        self.assertEqual(defaults["from_address"], "SOURCE-BILLING")
        self.assertEqual(defaults["from_address_details"], "Source address")
        self.assertEqual(defaults["supplier_address"], "TARGET-BILLING")
        self.assertEqual(defaults["supplier_address_details"], "Target address")

    def test_zero_pending_rows_allow_excess_only_in_grouped_editor(self):
        work_order = frappe._dict(
            name="WO-EXCESS-1",
            lot="LOT-EXCESS-1",
            includes_packing=0,
            delivery_address="SOURCE-BILLING",
            delivery_address_details="Source address",
            supplier_address="TARGET-BILLING",
            supplier_address_details="Target address",
        )
        base_defaults = {
            "items": [
                {"item_variant": "FABRIC-WHITE", "pending_quantity": 0},
                {"item_variant": "FABRIC-GREEN", "pending_quantity": 2},
            ],
            "item_details": [
                {
                    "items": [
                        {
                            "values": {
                                "White": {"qty": 0, "pending_quantity": 0},
                                "Green": {"qty": 2, "pending_quantity": 2},
                                "Rib": {"qty": 0, "pending_quantity": -1},
                            }
                        }
                    ]
                }
            ],
        }

        with (
            patch(
                "essdee_yrp.work_order_actions._open_submitted_work_order",
                return_value=work_order,
            ),
            patch("frappe.has_permission", return_value=True),
            patch(
                "yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan.get_work_order_defaults",
                return_value=base_defaults,
            ) as base_get_defaults,
        ):
            defaults = get_delivery_challan_defaults(
                work_order.name,
                posting_date="2026-08-27",
                posting_time="18:30:00",
            )

        base_get_defaults.assert_called_once_with(
            work_order.name,
            posting_date="2026-08-27",
            posting_time="18:30:00",
        )
        self.assertEqual(defaults["items"][0]["pending_quantity"], 0)
        values = defaults["item_details"][0]["items"][0]["values"]
        self.assertIsNone(values["White"]["pending_quantity"])
        self.assertEqual(values["Green"]["pending_quantity"], 2)
        self.assertIsNone(values["Rib"]["pending_quantity"])

    def test_manual_delivery_challan_selection_uses_same_adapter(self):
        self.assertEqual(
            override_whitelisted_methods[
                "yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan.get_work_order_defaults"
            ],
            "essdee_yrp.work_order_actions.get_delivery_challan_defaults",
        )

    def test_saved_draft_onload_keeps_zero_pending_excess_editable(self):
        doc = EssdeeDeliveryChallan(
            {"doctype": 'YRP Delivery Challan', "docstatus": 0}
        )
        grouped = [
            {
                "items": [
                    {
                        "values": {
                            "default": {"qty": 1.824, "pending_quantity": 0}
                        }
                    }
                ]
            }
        ]

        with patch(
            "yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan.DeliveryChallan.onload",
            side_effect=lambda: doc.set_onload("item_details", grouped),
        ):
            doc.onload()

        value = doc.get_onload("item_details")[0]["items"][0]["values"]["default"]
        self.assertEqual(value["qty"], 1.824)
        self.assertIsNone(value["pending_quantity"])


class TestGeneratedFabricUOM(TestCase):
    def test_physical_pieces_are_converted_before_box_uom_is_applied(self):
        rows = [
            {
                "item_variant": "TEST-PACKED-VARIANT",
                "qty": 20,
                "pending_quantity": 10,
                "stock_update": 5,
                "uom": "Pieces",
            }
        ]
        authoritative = frappe._dict(
            uom="Boxes",
            stock_uom="Pieces",
            conversion_factor=10,
        )

        with (
            patch("yrp.stock.uom.resolve_item_uom", return_value=authoritative),
            patch(
                "yrp.stock.utils.get_conversion_factor",
                return_value={"conversion_factor": 1, "stock_uom": "Pieces"},
            ),
        ):
            _normalize_generated_uom_rows(rows)

        self.assertEqual(rows[0]["uom"], "Boxes")
        self.assertEqual(rows[0]["qty"], 2)
        self.assertEqual(rows[0]["pending_quantity"], 1)
        self.assertEqual(rows[0]["stock_update"], 0.5)


def _ensure_attributed_item(name1, attributes):
    """An Item that DECLARES the given attributes (like live TT-YARN-GREY,
    which declares Colour while the knitting matrix consumes it attr-less)."""
    name = _ensure_item(name1)
    doc = frappe.get_doc('YRP Item', name)
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
    if frappe.db.get_single_value('YRP YRP Stock Settings', "default_received_type"):
        return
    if not frappe.db.exists('YRP Received Type', "Accepted"):
        rt = frappe.new_doc('YRP Received Type')
        for f in frappe.get_meta('YRP Received Type').fields:
            if f.reqd and f.fieldtype == "Data":
                rt.set(f.fieldname, "Accepted")
        rt.insert(ignore_permissions=True)
    frappe.db.set_single_value('YRP YRP Stock Settings', "default_received_type", "Accepted")


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
            rows, 'YRP Work Order Deliverables', supports_allocations=True
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
        self.assertEqual(frappe.get_doc('YRP Item', self.yarn).get("attributes"), [])
        # Kept outside the cloth recipe to exercise the generic partial-variant
        # resolver without violating the rule that yarn Items are attr-less.
        self.declared_item = _ensure_attributed_item(
            "_Test Declared Item WOCalc", ["Colour"])
        # Cloth mirrors live Thermal Rib: declares Dia + Colour.
        self.cloth = _ensure_attributed_item("_Test Cloth WOCalc", ["Dia", "Colour"])
        frappe.db.set_value('YRP Item', self.cloth, "is_cloth_item", 1)
        _reset_cpd(self.cloth)
        self.k_proc = _ensure_process("_Test Knit CPD", is_item_conversion=1)
        self.d_proc = _ensure_process("_Test Dye CPD")
        frappe.db.set_value('YRP Process', self.k_proc, "is_cloth_process", 1)
        frappe.db.set_value('YRP Process', self.d_proc, "is_cloth_process", 1)
        _ensure_default_received_type()

        selection = {
            "cloth_item": self.cloth, "yarn_item": self.yarn,
            "knitting_process": self.k_proc, "dyeing_process": self.d_proc,
            "compacting_process": None, "cloth_per_kg_yarn": 3.0,
            "greige_colour": self.greige,
        }
        # The class shares ONE uncommitted transaction (see _reset_cpd's note) —
        # a Lot inserted by an earlier test's setUp is still visible here.
        if frappe.db.exists('SD YRP Lot', "_Test WOCalc Lot"):
            self.lot = frappe.get_doc('SD YRP Lot', "_Test WOCalc Lot")
        else:
            self.lot = frappe.get_doc({
                "doctype": 'SD YRP Lot', "lot_name": "_Test WOCalc Lot",
            }).insert(ignore_permissions=True)
        demand = {(self.cloth, self.dia, self.red): 48.05}
        with patch.object(cloth_program, "compute_cloth_demand", return_value=demand):
            build_cloth_programs(self.lot.name, [selection])

        addr = _ensure_address()
        self.wo = frappe.get_doc({
            "doctype": 'YRP Work Order',
            "wo_date": nowdate(), "process_name": self.k_proc,
            "item": self.cloth, "lot": self.lot.name,
            "planned_start_date": nowdate(), "planned_end_date": nowdate(),
            "supplier_address": addr, "delivery_address": addr,
        }).insert(ignore_permissions=True)

    def test_selection_context_requires_explicit_cloth_item_selection(self):
        cloth_ipd = frappe.db.get_value(
            'SD YRP Lot Fabric Detail',
            {"parent": self.lot.name, "cloth_item": self.cloth},
            "production_detail",
        )
        context = get_work_order_selection_context(
            self.lot.name, self.k_proc
        )
        self.assertTrue(context["is_cloth_process"])
        self.assertTrue(context["process_is_cloth_process"])
        self.assertEqual(context["item_options"], [self.cloth])
        self.assertIsNone(context["auto_item"])
        self.assertIsNone(context["auto_production_detail"])
        # Once Item is selected, the server hook derives and stores the IPD.
        self.wo.reload()
        self.assertEqual(self.wo.production_detail, cloth_ipd)

    def test_non_cloth_selection_uses_lot_garment_item_and_ipd(self):
        sewing = _ensure_process("_Test Sewing WO Selection")
        frappe.db.set_value('YRP Process', sewing, "is_cloth_process", 0)
        garment_ipd = frappe.db.get_value(
            'SD YRP Lot Fabric Detail',
            {"parent": self.lot.name, "cloth_item": self.cloth},
            "production_detail",
        )
        frappe.db.set_value(
            'SD YRP Lot',
            self.lot.name,
            {"item": self.cloth, "production_detail": garment_ipd},
        )

        context = get_work_order_selection_context(self.lot.name, sewing)
        self.assertFalse(context["is_cloth_process"])
        self.assertFalse(context["process_is_cloth_process"])
        self.assertEqual(context["item_options"], [self.cloth])
        self.assertIsNone(context["auto_item"])
        self.assertIsNone(context["auto_production_detail"])

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

        wo = frappe.get_doc('YRP Work Order', self.wo.name)
        delivs = [d for d in wo.get("deliverables") if d.is_calculated]
        self.assertEqual(len(delivs), 1)
        variant = frappe.get_doc('YRP Item Variant', delivs[0].item_variant)
        self.assertEqual(variant.item, self.yarn)
        # Owner ruling: NOT Colour-stamped — no attribute rows at all.
        self.assertEqual([r.attribute for r in variant.get("attributes") or []], [])
        # The rounded 48 kg cloth program / 3.0 cloth-per-kg-yarn = 16 kg yarn.
        self.assertAlmostEqual(delivs[0].qty, 48 / 3.0, places=2)

        # The receivable keeps its FULL attribute set (cloth declares Dia+Colour;
        # knitting stamps the greige colour) — declared attrs are never dropped.
        recvs = wo.get("receivables")
        self.assertEqual(len(recvs), 1)
        recv_variant = frappe.get_doc('YRP Item Variant', recvs[0].item_variant)
        self.assertEqual(recv_variant.item, self.cloth)
        self.assertEqual(
            {r.attribute: r.attribute_value for r in recv_variant.attributes},
            {"Dia": self.dia, "Colour": self.greige},
        )

    def test_knitting_ignores_process_default_excess(self):
        """The Lot program already contains its manually chosen excess."""
        frappe.db.set_value('YRP Process', self.k_proc, "default_excess", 5)
        frappe.clear_cache(doctype='YRP Process')
        try:
            self._calculate()
            self.wo.reload()
            self.assertAlmostEqual(self.wo.receivables[0].qty, 48, places=3)
        finally:
            frappe.db.set_value('YRP Process', self.k_proc, "default_excess", 0)
            frappe.clear_cache(doctype='YRP Process')

    def test_calculate_is_idempotent_for_partial_variant(self):
        """Second Calculate must REUSE the minted attr-less yarn variant (no
        DuplicateEntryError, no second variant on the yarn Item)."""
        self._calculate()
        self._calculate()
        # Assert the exact name set — a bare len() count would be fragile
        # against sibling tests minting OTHER variants on the same yarn in the
        # shared class transaction (review follow-up).
        variants = frappe.get_all('YRP Item Variant', filters={"item": self.yarn}, pluck="name")
        self.assertEqual(variants, [self.yarn])

    def test_calculated_receivables_keep_process_cost_enforcement(self):
        """Fabric Calculate must leave ordinary Work Order costing intact.

        A missing approved cost still blocks submit, and the standard YRP
        costing method prices every route-generated receivable.
        """
        self._calculate()
        wo = frappe.get_doc('YRP Work Order', self.wo.name)

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
                "yrp.yrp.doctype.yrp_work_order.yrp_work_order.frappe.get_doc",
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
        doc = frappe.get_doc('YRP Item Variant', v)
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
        doc = frappe.get_doc('YRP Item Variant', v)
        self.assertEqual(doc.item, self.cloth)
        self.assertEqual(
            {r.attribute: r.attribute_value for r in doc.attributes},
            {"Colour": self.red},
        )
        self.assertEqual(
            doc.item_tuple_attribute, str(tuple(sorted({"Colour": self.red}.items()))))
        self.assertEqual(_resolve_variant(self.cloth, {"Colour": self.red}), v)

    def test_route_specific_knitting_outputs_drive_context_and_receivables(self):
        """Each final-colour matrix pre-fills its own physical knitting output.

        Calculation consumes the matched matrix yarn and mints receivables in
        those route-specific colours; no global Greige fallback is involved.
        """
        suffix = frappe.generate_hash(length=6)
        grey_melange = _ensure_iav("Colour", f"_Test Routed G Mel {suffix}")
        knitting_dia = _ensure_iav("Dia", f"_Test Routed 18 Dia {suffix}")
        final_dia = _ensure_iav("Dia", f"_Test Routed 22 Dia {suffix}")
        yarn_b = _ensure_item(f"_Test Routed Yarn B {suffix}")
        cloth = _ensure_attributed_item(
            f"_Test Routed Cloth {suffix}", ["Dia", "Colour"])
        frappe.db.set_value('YRP Item', cloth, "is_cloth_item", 1)
        _reset_cpd(cloth)
        compacting = _ensure_process(f"_Test Routed Compact {suffix}")

        lot = frappe.get_doc({
            "doctype": 'SD YRP Lot',
            "lot_name": f"_Test Routed Lot {suffix}",
        }).insert(ignore_permissions=True)
        selection = {
            "cloth_item": cloth,
            "knitting_process": self.k_proc,
            "dyeing_process": self.d_proc,
            "compacting_process": compacting,
            "cloth_per_kg_yarn": 3,
            "colour_yarn_recipes": [
                {"colour": self.red, "yarn_item": self.yarn, "ratio": 100},
                {"colour": grey_melange, "yarn_item": yarn_b, "ratio": 100},
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
            "doctype": 'YRP Work Order',
            "wo_date": nowdate(),
            "process_name": self.k_proc,
            "item": cloth,
            "lot": lot.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)

        context = get_fabric_deliverable_context(work_order.name)
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
                    'YRP Item Variant', child.item_variant
                ).attributes if attr.attribute == "Colour"
            )
            for child in work_order.receivables
        }
        self.assertEqual(received_colours, {self.greige, grey_melange})
        delivered_templates = {
            frappe.db.get_value('YRP Item Variant', child.item_variant, "item")
            for child in work_order.deliverables
            if child.is_calculated
        }
        self.assertEqual(delivered_templates, {self.yarn, yarn_b})

        # The direct GMEL route is absent from the Dyeing popup entirely. Only
        # the Greige -> Red route needs a dyeing Work Order.
        dye_work_order = frappe.get_doc({
            "doctype": 'YRP Work Order',
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
            "doctype": 'YRP Work Order',
            "wo_date": nowdate(),
            "process_name": compacting,
            "item": cloth,
            "lot": lot.name,
            "planned_start_date": nowdate(),
            "planned_end_date": nowdate(),
            "supplier_address": addr,
            "delivery_address": addr,
        }).insert(ignore_permissions=True)
        with patch(
            "essdee_yrp.fabric_tracking.get_step_received",
            return_value={(knitting_dia, grey_melange): 20.0},
        ) as received:
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
        self.assertEqual(compact_row["available"], 20.0)
        self.assertTrue(any(
            call.args[:3] == (lot.name, cloth, self.k_proc)
            for call in received.call_args_list
        ))

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
                'YRP Item Variant',
                compact_work_order.deliverables[0].item_variant,
            ).attributes
        }
        received_attrs = {
            row.attribute: row.attribute_value
            for row in frappe.get_doc(
                'YRP Item Variant',
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
        self.assertEqual(frappe.get_doc('YRP Item', yarn_a).get("attributes"), [])
        self.assertEqual(frappe.get_doc('YRP Item', yarn_b).get("attributes"), [])

        cloth = _ensure_attributed_item(
            f"_Test MY Cloth {suffix}", ["Dia", "Colour"])
        frappe.db.set_value('YRP Item', cloth, "is_cloth_item", 1)
        _reset_cpd(cloth)

        knitting = _ensure_process(f"_Test MY Knitting {suffix}", is_item_conversion=1)
        dyeing = _ensure_process(f"_Test MY Dyeing {suffix}")
        washing = _ensure_process(f"_Test MY Washing {suffix}")

        ipd = frappe.new_doc('YRP Item Production Detail')
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
        return frappe.get_doc('YRP Item Production Detail', ipd.name), {
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
        if frappe.db.exists('SD YRP Lot', lot_name):
            lot = frappe.get_doc('SD YRP Lot', lot_name)
        else:
            lot = frappe.get_doc({
                "doctype": 'SD YRP Lot',
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
            "doctype": 'YRP Work Order',
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
            'YRP IPD Process Matrix',
            filters={"ipd": ipd.name},
            fields=["name", "process_name"],
        )
        self.assertEqual({m.process_name for m in matrices}, {v["knitting"], v["dyeing"]})
        self.assertNotIn(v["washing"], {m.process_name for m in matrices})

        knit_name = next(m.name for m in matrices if m.process_name == v["knitting"])
        knit = frappe.get_doc('YRP IPD Process Matrix', knit_name)
        knit_groups = knit.get_combinations_grouped()
        self.assertEqual(len(knit_groups), 1)
        knit_group = next(iter(knit_groups.values()))
        self.assertEqual(
            [(row["item"], flt(row["qty"], 3)) for row in knit_group["input"]],
            [(v["yarn_a"], 0.6), (v["yarn_b"], 0.4)],
        )
        self.assertEqual(knit_group["output"][0]["item"], v["cloth"])
        self.assertAlmostEqual(flt(knit_group["output"][0]["qty"]), 3.0, places=3)
        self.assertEqual(knit_group["output"][0]["attrs"], {"Dia": v["dia"]})

        dye_name = next(m.name for m in matrices if m.process_name == v["dyeing"])
        dye = frappe.get_doc('YRP IPD Process Matrix', dye_name)
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
            template = frappe.db.get_value('YRP Item Variant', row.item_variant, "item")
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
            frappe.db.get_value('YRP Item Variant', row.item_variant, "item"): flt(row.qty)
            for row in work_order.deliverables
            if row.is_calculated
        }
        self.assertAlmostEqual(planned[v["yarn_a"]], 6.0, places=3)
        self.assertAlmostEqual(planned[v["yarn_b"]], 4.0, places=3)
        self.assertAlmostEqual(planned[accessory], 6.0, places=3)

        # A production GRN can consume only inputs that were actually delivered
        # against the Work Order. This test isolates the matrix/BOM calculation,
        # so move its calculated inputs to that delivered state first.
        for row in work_order.deliverables:
            if row.is_calculated:
                row.db_set("pending_quantity", 0, update_modified=False)
        work_order.reload()

        receivable = work_order.receivables[0]
        grn = frappe.new_doc('YRP Goods Received Note')
        grn.against = 'YRP Work Order'
        grn.against_id = work_order.name
        grn.append("items", {
            "item_variant": receivable.item_variant,
            "quantity": 12,
            "uom": receivable.uom,
            "ref_docname": receivable.name,
        })
        calculate_grn_consumption(grn)

        consumed = {
            frappe.db.get_value('YRP Item Variant', row.item_variant, "item"): flt(row.quantity)
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
            frappe.db.get_value('YRP Item Variant', row.item_variant, "item"): flt(row.qty)
            for row in work_order.deliverables
            if row.is_calculated
        }
        self.assertAlmostEqual(planned[v["cloth"]], 20.0, places=3)
        self.assertAlmostEqual(planned[chemical], 1.0, places=3)
