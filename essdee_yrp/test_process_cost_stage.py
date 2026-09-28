"""Process-cost attribute choices follow the current IPD process input stage."""
import unittest
from inspect import unwrap
from unittest.mock import Mock, patch

import frappe
from essdee_yrp.process_cost import get_item_attributes


class ProcessCostStageTest(unittest.TestCase):
    def test_printing_input_stage_offers_panel_and_colour(self):
        ipd = frappe._dict(
            cutting_process='Cutting', stiching_process='Stitching', packing_process='Packing',
            stiching_attribute='Panel', packing_attribute='Colour', primary_item_attribute='Size',
            stiching_in_stage='Cut', stiching_out_stage='Piece',
            ipd_processes=[frappe._dict(process_name='Printing', in_stage='Cut', out_stage='Cut')],
        )
        with (
            patch('essdee_yrp.process_cost._check_process_cost_permissions'),
            patch('essdee_yrp.process_cost.frappe.db', new=frappe._dict(get_value=Mock())) as db,
            patch('essdee_yrp.process_cost.frappe.has_permission'),
            patch('essdee_yrp.process_cost.frappe.get_cached_doc', return_value=ipd),
        ):
            db.get_value.side_effect = [0, 'IPD', 0]
            result = unwrap(get_item_attributes)(
                'Item Attribute', '', 'name', 0, 20,
                {'item': 'Garment', 'lot': 'Lot', 'process': 'Printing'},
            )
        self.assertEqual(result, [['Panel'], ['Colour']])

    def test_cloth_process_uses_selected_cloth_ipd_attributes(self):
        ipd = frappe._dict(is_cloth_item=1, item_attributes=[
            frappe._dict(attribute='Dia'), frappe._dict(attribute='Colour')])
        with (
            patch('essdee_yrp.process_cost._check_process_cost_permissions'),
            patch('essdee_yrp.process_cost._resolve_ipd_name', return_value='Cloth IPD') as resolve,
            patch('essdee_yrp.process_cost.frappe.has_permission'),
            patch('essdee_yrp.process_cost.frappe.get_cached_doc', return_value=ipd),
        ):
            result = unwrap(get_item_attributes)(
                'Item Attribute', '', 'name', 0, 20,
                {'item': 'Cloth', 'lot': 'Lot', 'process': 'Knitting'})
        resolve.assert_called_once_with('Cloth', 'Lot', 'Knitting')
        self.assertEqual(result, [['Dia'], ['Colour']])

    def test_cloth_ipd_resolution_rejects_an_unrelated_item(self):
        from essdee_yrp.process_cost import _resolve_ipd_name
        with (
            patch('essdee_yrp.process_cost.frappe.db.get_value', return_value=1),
            patch('essdee_yrp.api.work_order._get_work_order_selection_context',
                  return_value={'options': [{'item': 'Cloth', 'production_detail': 'Cloth IPD'}]}),
            patch('essdee_yrp.process_cost.frappe.throw', side_effect=frappe.ValidationError),
        ):
            self.assertEqual(_resolve_ipd_name('Cloth', 'Lot', 'Knitting'), 'Cloth IPD')
            with self.assertRaises(frappe.ValidationError):
                _resolve_ipd_name('Other Cloth', 'Lot', 'Knitting')

    def test_garment_cost_keeps_lot_item_fetch_behavior(self):
        from essdee_yrp.process_cost import before_validate
        doc = frappe._dict(lot='Lot', process_name='Printing', item='Wrong Item')
        with patch('essdee_yrp.process_cost.frappe.db.get_value', side_effect=[0, 'Garment', 'Nos']):
            before_validate(doc)
        self.assertEqual(doc.item, 'Garment')
        self.assertEqual(doc.uom, 'Nos')

    def test_cloth_cost_save_checks_selected_lot_process(self):
        from essdee_yrp.process_cost import before_validate
        doc = frappe._dict(lot='Lot', process_name='Knitting', item='Cloth')
        with (
            patch('essdee_yrp.process_cost.frappe.db.get_value', return_value=1),
            patch('essdee_yrp.process_cost._resolve_ipd_name') as resolve,
        ):
            before_validate(doc)
        resolve.assert_called_once_with('Cloth', 'Lot', 'Knitting')
        self.assertEqual(doc.item, 'Cloth')
