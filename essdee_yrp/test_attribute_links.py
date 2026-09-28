"""Link storage, domain values, scoped validation, and historical preservation."""
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp import attribute_links
from yrp.attribute_value_identity import attribute_value_name
from yrp.attribute_values import ensure_value_master


class TestAttributeLinks(IntegrationTestCase):
    def setUp(self):
        frappe.set_user('Administrator')
        self.colour = '_Test Attribute Link Red'
        self.dia = '_Test Attribute Link 24 Dia'
        self.ensure_native_value('Colour', self.colour)
        self.ensure_native_value('Dia', self.dia)
        self.colour_link = ensure_value_master('Colour', self.colour)

    def ensure_native_value(self, attribute, value):
        if not frappe.db.exists('Item Attribute', attribute):
            frappe.get_doc({
                'doctype': 'Item Attribute',
                'attribute_name': attribute,
                'item_attribute_values': [{'attribute_value': value, 'abbr': value}],
            }).insert(ignore_permissions=True)
        elif not frappe.db.exists('Item Attribute Value', {'parent': attribute, 'attribute_value': value}):
            doc = frappe.get_doc('Item Attribute', attribute)
            doc.append('item_attribute_values', {'attribute_value': value, 'abbr': value})
            doc.save(ignore_permissions=True)

    def test_plain_values_and_links_resolve_without_mutating_native_values(self):
        self.assertEqual(attribute_links.value(self.colour_link), self.colour)
        self.assertEqual(attribute_links.value(self.colour), self.colour)
        self.assertEqual(attribute_links.value(1.25), 1.25)
        self.assertEqual(attribute_links.link(self.colour, 'Colour'), self.colour_link)
        with self.assertRaises(frappe.ValidationError):
            attribute_links.link(self.colour_link, 'Dia')

    def test_internal_child_insert_stores_link_and_business_query_returns_text(self):
        row = self.make_row()
        stored = frappe.db.get_value(row.doctype, row.name, ['colour', 'dia', 'weight'], as_dict=True)
        self.assertEqual(stored.colour, self.colour_link)
        self.assertEqual(stored.dia, attribute_value_name('Dia', self.dia))
        self.assertEqual(stored.weight, 12.5)
        read = attribute_links.get_value(row.doctype, {'name': row.name, 'colour': self.colour}, ['colour', 'dia'], as_dict=True)
        self.assertEqual(read, {'colour': self.colour, 'dia': self.dia})
        attribute_links.set_value(row.doctype, row.name, 'colour', self.colour)
        self.assertEqual(frappe.db.get_value(row.doctype, row.name, 'colour'), self.colour_link)

    def test_backfill_preserves_text_quantities_and_audit_timestamp(self):
        row = self.make_row()
        frappe.db.set_value(row.doctype, row.name, 'colour', self.colour, update_modified=False)
        before = frappe.db.get_value(row.doctype, row.name, ['modified', 'weight'], as_dict=True)
        with patch.object(attribute_links, 'fields', return_value={row.doctype: ['colour']}):
            attribute_links.backfill()
            self.assertEqual(attribute_links.backfill()['field_values'], 0)
        self.assertEqual(frappe.db.get_value(row.doctype, row.name, 'colour'), self.colour_link)
        self.assertEqual(before, frappe.db.get_value(row.doctype, row.name, ['modified', 'weight'], as_dict=True))

    def make_row(self):
        row = frappe.get_doc({'doctype': 'SD YRP Lot Fabric Requirement',
            'parenttype': 'SD YRP Lot', 'parentfield': 'lot_fabric_requirements',
            'parent': '_Test Attribute Links', 'cloth_item': 'test',
            'colour': self.colour, 'dia': self.dia, 'weight': 12.5})
        row.name = frappe.generate_hash(length=10)
        row.db_insert()
        return row
