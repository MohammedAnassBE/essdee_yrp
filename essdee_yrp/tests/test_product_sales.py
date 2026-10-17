import secrets
import unittest

import frappe

from essdee_yrp.product_sales import IPD_SETTINGS, PIECE_UOM, sales_definition

SETTINGS = frappe._dict(primary='Size', packing='Finish', stage='Pack')


class TestSalesDefinition(unittest.TestCase):
    def definition(self, **changes):
        template = frappe._dict(primary_attribute='Size', dependent_attribute='Finish', name='Synthetic', custom_size_range='Range')
        template.update(changes)
        sizes = frappe._dict(size_type='Type', sizes=[frappe._dict(attribute_value='IAV-small'), frappe._dict(attribute_value='IAV-large')])
        slots = frappe._dict(fg_item_size_type_details=[frappe._dict(size='size 2', size_type_value='IAV-large'),
            frappe._dict(size='size 1', size_type_value='IAV-small')])
        return sales_definition(template, sizes, slots, {'IAV-small': 'S', 'IAV-large': 'L'}, SETTINGS)

    def test_dynamic_slots_follow_type_order(self):
        cells = self.definition()['cells']
        self.assertEqual([(c['key'], c['value'], c['link']) for c in cells], [('size 2', 'L', 'IAV-large'), ('size 1', 'S', 'IAV-small')])

    def test_no_size_range_is_unchanged(self):
        self.assertIsNone(self.definition(custom_size_range=None))

    def test_primary_and_packing_attributes_follow_ipd_settings(self):
        with self.assertRaises(ValueError):
            self.definition(primary_attribute='Colour')
        with self.assertRaises(ValueError):
            self.definition(dependent_attribute=None)


class TestProductSalesSite(unittest.TestCase):
    """Real ZZ-labelled Items inside a savepoint; every record rolls back per test."""

    def setUp(self):
        from yrp.attribute_values import ensure_value_master
        from yrp.yrp_retail.test_category import TestItemCategory

        if not frappe.db.exists('UOM', PIECE_UOM):
            self.skipTest(f'UOM {PIECE_UOM} is required.')
        self.addCleanup(self.clear_caches)
        self.fixture = TestItemCategory()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        label = self.label
        size = frappe.get_doc('Item Attribute', 'Size')
        self.size_values = [label('Size') for _ in range(2)]
        for value in self.size_values:
            size.append('item_attribute_values', {'attribute_value': value, 'abbr': 'T' + frappe.generate_hash(length=6)})
        size.save()
        self.size_links = [ensure_value_master('Size', value) for value in self.size_values]
        self.size_type = frappe.get_doc({'doctype': 'SD YRP FG Item Size Type', 'size_type': label('Slots'),
            'fg_item_size_type_details': [{'size': 'size 2', 'size_type_value': self.size_links[1]},
                {'size': 'size 1', 'size_type_value': self.size_links[0]}]}).insert()
        self.size_range = frappe.get_doc({'doctype': 'SD YRP FG Item Size Range', 'name1': label('Range'),
            'uid': secrets.randbelow(1_000_000_000), 'size_type': self.size_type.name,
            'sizes': [{'attribute_value': link} for link in self.size_links]}).insert()
        self.size_mapping = frappe.get_doc({'doctype': 'YRP Item Item Attribute Mapping', 'attribute_name': 'Size',
            'values': [{'attribute_value': link} for link in self.size_links]}).insert()
        self.stage = frappe.get_doc({'doctype': 'Item Attribute', 'attribute_name': label('Stage'),
            'item_attribute_values': [{'attribute_value': 'Pack', 'abbr': 'PK'}, {'attribute_value': 'Cut', 'abbr': 'CT'}]}).insert()
        pack, cut = (ensure_value_master(self.stage.name, value) for value in ('Pack', 'Cut'))
        self.stage_mapping = frappe.get_doc({'doctype': 'YRP Item Item Attribute Mapping', 'attribute_name': self.stage.name,
            'values': [{'attribute_value': pack}, {'attribute_value': cut}]}).insert()
        self.dependent_mapping = frappe.get_doc({'doctype': 'YRP Item Dependent Attribute Mapping',
            'dependent_attribute': self.stage.name,
            'details': [{'attribute_value': pack, 'uom': PIECE_UOM}, {'attribute_value': cut, 'uom': PIECE_UOM}],
            'mapping': [{'dependent_attribute_value': pack, 'depending_attribute': 'Size'},
                {'dependent_attribute_value': cut, 'depending_attribute': 'Size'}]}).insert()
        self.set_ipd_settings('Size', self.stage.name, pack)

    def label(self, text):
        return 'ZZ ' + self.fixture.label(text)

    def clear_caches(self):
        if hasattr(frappe.db, 'value_cache'):
            frappe.db.value_cache.clear()
        frappe.clear_document_cache(IPD_SETTINGS, IPD_SETTINGS)
        frappe.clear_document_cache('Item Attribute', 'Size')

    def set_ipd_settings(self, primary, packing, stage):
        for fieldname, value in (('default_primary_attribute', primary), ('default_packing_attribute', packing),
                ('default_pack_out_stage', stage)):
            frappe.db.set_single_value(IPD_SETTINGS, fieldname, value)
        self.clear_caches()

    def template(self, **changes):
        values = {'stock_uom': PIECE_UOM, 'has_variants': 1, 'variant_based_on': 'Item Attribute',
            'primary_attribute': 'Size', 'dependent_attribute': self.stage.name,
            'dependent_attribute_mapping': self.dependent_mapping.name,
            'attributes': [{'attribute': 'Size', 'mapping': self.size_mapping.name},
                {'attribute': self.stage.name, 'mapping': self.stage_mapping.name}],
            'custom_size_range': self.size_range.name, 'custom_pieces_per_box': 12, 'custom_box_per_carton': 10}
        values.update(changes)
        return self.fixture.item(**values)

    def variants(self, template):
        return frappe.get_all('Item', filters={'variant_of': template}, pluck='name', order_by='name')

    def test_template_save_creates_size_pack_variants_once(self):
        template = self.template().insert()
        names = self.variants(template.name)
        self.assertEqual(len(names), 2)
        self.assertEqual(set(names), {f'{template.name}-{value}' for value in self.size_values})
        for name in names:
            item = frappe.get_doc('Item', name)
            self.assertEqual({r.attribute: r.attribute_value for r in item.attributes}[self.stage.name], 'Pack')
            self.assertEqual({r.uom: r.conversion_factor for r in item.uoms}.get('Box'), 12)
        template.reload()
        template.save()
        self.assertEqual(self.variants(template.name), names)
        self.assertEqual(template.custom_pieces_per_carton, 120)
        self.assertEqual({r.uom: r.conversion_factor for r in template.uoms}.get('Carton'), 120)

    def test_variants_copy_the_saved_template_not_a_cached_copy(self):
        template = self.template(custom_size_range=None).insert()
        frappe.get_cached_doc('Item', template.name)
        group = frappe.get_doc({'doctype': 'Item Group', 'item_group_name': self.label('Leaf'),
            'parent_item_group': frappe.db.get_value('Item Group', {'lft': 1}, 'name')}).insert()
        template.custom_size_range = self.size_range.name
        template.item_group = group.name
        template.save()
        for name in self.variants(template.name):
            item = frappe.get_doc('Item', name)
            self.assertEqual(item.item_group, group.name)
            self.assertEqual({r.uom: r.conversion_factor for r in item.uoms}.get('Box'), 12)

    def test_sellable_variants_follow_size_range_order(self):
        from essdee_yrp.product_sales import get_sellable_variants

        template = self.template().insert()
        rows = get_sellable_variants(template.name)
        self.assertEqual([row.size for row in rows], self.size_values)

    def test_empty_ipd_settings_fail_loudly(self):
        self.set_ipd_settings(None, None, None)
        with self.assertRaisesRegex(frappe.ValidationError, 'SD YRP IPD Settings'):
            self.template().insert()

    def test_invalid_sales_template_is_rejected(self):
        for changes in ({'stock_uom': self.fixture.uom.name}, {'stock_uom': 'Box'}, {'custom_box_per_carton': 0},
                {'item_group': frappe.db.get_value('Item Group', {'is_group': 1}, 'name')}):
            with self.assertRaises(frappe.ValidationError):
                self.template(**changes).insert()

    def test_plain_item_keeps_no_size_rules(self):
        item = self.fixture.item(custom_pieces_per_box=6, custom_box_per_carton=4).insert()
        self.assertEqual(item.custom_pieces_per_carton, 24)
        with self.assertRaises(frappe.ValidationError):
            self.fixture.item(custom_size_range=self.size_range.name).insert()

    def test_size_range_growth_adds_only_the_new_variant(self):
        from yrp.attribute_values import ensure_value_master

        template = self.template().insert()
        old = {name: [r.attribute_value for r in frappe.get_doc('Item', name).attributes] for name in self.variants(template.name)}
        size = frappe.get_doc('Item Attribute', 'Size')
        value = self.label('Third Size')
        size.append('item_attribute_values', {'attribute_value': value, 'abbr': 'G' + frappe.generate_hash(length=6)})
        size.save()
        link = ensure_value_master('Size', value)
        self.size_type.append('fg_item_size_type_details', {'size': 'size 3', 'size_type_value': link})
        self.size_type.save()
        self.size_range.append('sizes', {'attribute_value': link})
        self.size_range.save()
        names = self.variants(template.name)
        self.assertEqual(len(names), 3)
        for name, attributes in old.items():
            self.assertEqual([r.attribute_value for r in frappe.get_doc('Item', name).attributes], attributes)

    def test_box_sticker_and_lotwise_read_the_template(self):
        from essdee_yrp.essdee_yrp.doctype.sd_yrp_box_sticker_print.sd_yrp_box_sticker_print import (
            get_fg_details,
        )
        from essdee_yrp.essdee_yrp.doctype.sd_yrp_lotwise_item_profit.sd_yrp_lotwise_item_profit import (
            get_item_size_rates,
        )

        template = self.template().insert()
        for index, name in enumerate(self.variants(template.name)):
            frappe.db.set_value('Item', name, 'custom_mrp', 100 + index)
        rows = get_fg_details(template.name)
        self.assertEqual([row['size'] for row in rows], self.size_values)
        self.assertTrue(all(row['mrp'] for row in rows))
        self.assertEqual([row['size'] for row in get_item_size_rates(template.name)], self.size_values)

    def test_native_size_master_rejects_duplicate_and_uncovered_values(self):
        link = self.size_type.fg_item_size_type_details[0].size_type_value
        self.size_type.append('fg_item_size_type_details', {'size': 'size 3', 'size_type_value': link})
        with self.assertRaises(frappe.ValidationError):
            self.size_type.save()
        self.size_range.append('sizes', {'attribute_value': self.size_range.sizes[0].attribute_value})
        with self.assertRaises(frappe.ValidationError):
            self.size_range.save()


def make_sales_fixture():
    """Sales Item template with size variants. Caller must call fixture.doCleanups()."""
    fixture = TestProductSalesSite()
    try:
        fixture.setUp()
        fixture.template_item = fixture.template().insert()
        fixture.item_names = fixture.variants(fixture.template_item.name)
        return fixture
    except BaseException:
        fixture.doCleanups()
        raise


class TestSizeContracts(unittest.TestCase):
    def test_empty_duplicate_keys_and_non_size_values_rejected(self):
        from essdee_yrp.product_sales import validate_slot_rows
        valid = [{'size': 'size 1', 'size_type_value': 's'}, {'size': 'size 10', 'size_type_value': 'l'}]
        validate_slot_rows(valid, {'s': 'Size', 'l': 'Size'})
        for rows in ([], [{'size': '', 'size_type_value': 's'}], [*valid, valid[0]],
                [{'size': 'size 2', 'size_type_value': 'colour'}]):
            with self.assertRaises(ValueError):
                validate_slot_rows(rows, {'s': 'Size', 'l': 'Size', 'colour': 'Colour'})

    def test_empty_slot_values_and_blank_rows_are_allowed(self):
        from essdee_yrp.product_sales import validate_slot_rows
        validate_slot_rows([{'size': 'size 1', 'size_type_value': 's'}, {'size': 'size 2', 'size_type_value': None},
            {'size': 'size 3', 'size_type_value': ''}, {'size': '', 'size_type_value': ''}], {'s': 'Size'})
        with self.assertRaises(ValueError):
            validate_slot_rows([{'size': 'size 1', 'size_type_value': None}, {'size': 'size 1', 'size_type_value': 's'}], {'s': 'Size'})

    def test_sales_definition_skips_empty_slot_values(self):
        size_range = frappe._dict(size_type='Type', sizes=[frappe._dict(attribute_value='s')])
        size_type = frappe._dict(fg_item_size_type_details=[frappe._dict(size='size 1', size_type_value=None),
            frappe._dict(size='size 2', size_type_value='s'), frappe._dict(size=None, size_type_value=None)])
        template = frappe._dict(primary_attribute='Size', dependent_attribute='Finish', custom_size_range='Range')
        cells = sales_definition(template, size_range, size_type, {'s': 'S'}, SETTINGS)['cells']
        self.assertEqual([(c['key'], c['link']) for c in cells], [('size 2', 's')])

    def test_only_size_1_to_size_10_slot_keys_are_accepted(self):
        from essdee_yrp.product_sales import validate_slot_rows
        for key in ('size1', 'Size 1', 'size 0', 'size 11', 'adult-small', None):
            with self.assertRaisesRegex(ValueError, 'size 1 to size 10'):
                validate_slot_rows([{'size': key, 'size_type_value': 's'}], {'s': 'Size'})

    def test_only_the_pack_out_stage_sells(self):
        from essdee_yrp.product_sales import is_sellable_stage
        staged = frappe._dict(dependent_attribute='Finish')
        self.assertTrue(is_sellable_stage(staged, {'Finish': 'Pack'}, SETTINGS))
        self.assertFalse(is_sellable_stage(staged, {'Finish': 'Cut'}, SETTINGS))
        self.assertTrue(is_sellable_stage(frappe._dict(dependent_attribute=None), {}, SETTINGS))

    def test_range_coverage_and_domain(self):
        from essdee_yrp.product_sales import validate_range_rows
        validate_range_rows([{'attribute_value': 's'}], {'s': 'Size'}, {'s', 'l'})
        for rows, covered in (([], {'s'}), ([{'attribute_value': 's'}, {'attribute_value': 's'}], {'s'}),
                ([{'attribute_value': 'l'}], {'s'}), ([{'attribute_value': 'colour'}], {'colour'})):
            with self.assertRaises(ValueError):
                validate_range_rows(rows, {'s': 'Size', 'l': 'Size', 'colour': 'Colour'}, covered)
