"""Fractional yarn recipes consume the same planned inputs across split GRNs."""
import unittest
from unittest.mock import patch

import frappe
from essdee_yrp.fabric_grn import _align_cloth_input_rounding


class ClothInputRoundingTest(unittest.TestCase):
    def align(self, actual, planned=3.333):
        row = frappe._dict(item_variant='Dyed Yarn', uom='Kg',
                          reference_item_variant='Finished Cloth', qty=actual)
        wo = frappe._dict(process_name='Knitting', receivables=[], deliverables=[
            frappe._dict(item_variant='Dyed Yarn', uom='Kg', qty=planned,
                         is_calculated=1, fabric_reference_variant='Finished Cloth')])
        with (
            patch('essdee_yrp.fabric_grn._get_output_demands', return_value=[]),
            patch('essdee_yrp.fabric_grn._calculate_consumed_rows',
                  return_value=[{**row, 'qty': 3.333333}]),
        ):
            return _align_cloth_input_rounding([row], wo, frappe._dict(is_cloth_item=1))[0]['qty']

    def test_full_receipt_uses_rounded_wo_input(self):
        self.assertEqual(self.align(3.333333), 3.333)

    def test_split_receipts_sum_to_full_input(self):
        self.assertAlmostEqual(self.align(1.6666665) * 2, 3.333, places=6)

    def test_real_shortfall_is_not_scaled_away(self):
        self.assertEqual(self.align(3.333333, planned=3), 3.333333)

    def test_rounded_up_blend_input_is_preserved(self):
        self.assertEqual(self.align(3.333333, planned=3.3335), 3.3335)

    def test_plan_rounds_each_yarn_before_combining_blend(self):
        from essdee_yrp.fabric_plan import solve_chain_backward
        combo = frozenset({('Colour', 'Greige')})
        group = {'output': [{'qty': 3}], 'input': [
            {'item': 'Yarn A', 'qty': 0.5, 'attrs': {'Colour': 'Greige'}},
            {'item': 'Yarn B', 'qty': 0.5, 'attrs': {'Colour': 'Greige'}},
        ]}
        with (
            patch('essdee_yrp.fabric_plan.get_fabric_steps', return_value=[
                {'process_name': 'Knitting', 'position': 0, 'shape': 'conversion'}]),
            patch('essdee_yrp.fabric_plan._load_output_indexed_groups',
                  return_value=({('', combo): [group]}, {'Colour'})),
        ):
            plans, missing = solve_chain_backward(frappe._dict(name='IPD'), {combo: 10})
        self.assertFalse(missing)
        self.assertAlmostEqual(sum(plans[0]['inputs'].values()), 3.334)
