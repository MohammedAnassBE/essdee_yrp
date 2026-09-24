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
            db.get_value.side_effect = ['IPD', 0]
            result = unwrap(get_item_attributes)(
                'Item Attribute', '', 'name', 0, 20,
                {'item': 'Garment', 'lot': 'Lot', 'process': 'Printing'},
            )
        self.assertEqual(result, [['Panel'], ['Colour']])
