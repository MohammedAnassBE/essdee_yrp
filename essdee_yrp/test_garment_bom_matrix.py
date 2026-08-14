from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.garment_bom_matrix import _build_matrix


class TestGarmentBomMatrix(FrappeTestCase):
    def test_matrix_keeps_cloth_inputs_and_finished_variant_output(self):
        ipd = frappe._dict(
            name="_Test Garment IPD",
            item="_Test Finished Item",
            cutting_process="_Test Cutting",
            dependent_attribute="Stage",
            item_attributes=[
                frappe._dict(attribute="Colour"),
                frappe._dict(attribute="Size"),
                frappe._dict(attribute="Stage"),
            ],
        )
        cloth_item = frappe._dict(
            attributes=[
                frappe._dict(attribute="Colour"),
                frappe._dict(attribute="Dia"),
            ]
        )
        rows = [
            {
                "item": "_Test Cloth",
                "attrs": {"Colour": "Red", "Dia": "20"},
                "quantity": 0.25,
                "uom": "Kg",
            }
        ]

        real_get_value = frappe.db.get_value

        def get_value(doctype, *args, **kwargs):
            if doctype == "Item":
                return "Pieces"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(frappe, "get_cached_doc", return_value=cloth_item),
            patch.object(frappe.db, "get_value", side_effect=get_value),
        ):
            matrix = _build_matrix(
                ipd,
                "_Test Finished Variant",
                {"Colour": "Red", "Size": "M", "Stage": "Packed"},
                "_Test Cloth",
                rows,
            )

        self.assertEqual(matrix.reference_item_variant, "_Test Finished Variant")
        self.assertEqual(matrix.input_item, "_Test Cloth")
        self.assertEqual(matrix.output_item, "_Test Finished Item")
        self.assertEqual(matrix.combinations[0].side, "Input")
        self.assertEqual(matrix.combinations[0].quantity, 0.25)
        self.assertEqual(matrix.combinations[1].side, "Output")
        self.assertEqual(matrix.combinations[1].quantity, 1)
        self.assertEqual(
            {row.attribute for row in matrix.output_attributes},
            {"Colour", "Size"},
        )

    def test_output_only_matrix_supports_an_ipd_without_bom_cloth(self):
        ipd = frappe._dict(
            name="_Test Accessory Only IPD",
            item="_Test Finished Item",
            cutting_process="_Test Cutting",
            dependent_attribute="Stage",
            item_attributes=[frappe._dict(attribute="Colour")],
        )

        real_get_value = frappe.db.get_value

        def get_value(doctype, *args, **kwargs):
            if doctype == "Item":
                return "Pieces"
            return real_get_value(doctype, *args, **kwargs)

        with patch.object(frappe.db, "get_value", side_effect=get_value):
            matrix = _build_matrix(
                ipd,
                "_Test Finished Variant",
                {"Colour": "Red", "Stage": "Packed"},
                None,
                [],
            )

        self.assertFalse(matrix.input_item)
        self.assertEqual(len(matrix.combinations), 1)
        self.assertEqual(matrix.combinations[0].side, "Output")
