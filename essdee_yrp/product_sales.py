"""Essdee size range, packaging and sellable variants on Item templates."""
import frappe
from frappe import _
from frappe.utils import cint
from yrp import attribute_links as attribute_db

IPD_SETTINGS = 'SD YRP IPD Settings'
PIECE_UOM = 'Pieces'
PACKAGING_UOMS = (('Box', 'custom_pieces_per_box'), ('Carton', 'custom_pieces_per_carton'))
SIZE_SLOTS = tuple(f'size {index}' for index in range(1, 11))


def get_pack_out_settings():
    """Primary attribute, packing attribute and plain pack-out stage from IPD Settings."""
    settings = frappe._dict(
        primary=attribute_db.get_single_value(IPD_SETTINGS, 'default_primary_attribute'),
        packing=attribute_db.get_single_value(IPD_SETTINGS, 'default_packing_attribute'),
        stage=attribute_db.get_single_value(IPD_SETTINGS, 'default_pack_out_stage'),
    )
    if not (settings.primary and settings.packing and settings.stage):
        frappe.throw(_('Set Default Primary Attribute, Default Packing Attribute and Default Pack Out Stage in SD YRP IPD Settings.'))
    return settings


def sales_definition(template, size_range, size_type, values, settings):
    """Build size cells in Size Type slot order, without IO."""
    if not template.get('custom_size_range'):
        return None
    if template.get('primary_attribute') != settings.primary:
        raise ValueError(f'Size Range requires {settings.primary} as the Item template primary attribute.')
    if template.get('dependent_attribute') != settings.packing:
        raise ValueError(f'Size Range requires {settings.packing} as the Item template dependent attribute.')
    if not size_range.get('size_type'):
        raise ValueError('Sales Size Range requires a Size Type.')
    selected = [r.get('attribute_value') for r in size_range.get('sizes') or []]
    if not selected or len(selected) != len(set(selected)) or None in selected:
        raise ValueError('Size Range must contain distinct, nonempty values.')
    cells, keys, used = [], set(), set()
    for row in size_type.get('fg_item_size_type_details') or []:
        key, link = row.get('size'), row.get('size_type_value')
        if not key and not link:
            continue
        if key not in SIZE_SLOTS or key in keys or (link and link in used):
            raise ValueError('Size Type must have distinct size 1 to size 10 slots and distinct values.')
        keys.add(key)
        if not link:
            continue
        used.add(link)
        if link in selected:
            cells.append({'key': key, 'link': link, 'value': values.get(link, link)})
    if set(selected) - used:
        raise ValueError('Every Size Range value must be mapped in its Size Type.')
    return {'size_type': size_range.size_type, 'cells': cells}


def load_sales_definition(template):
    if not template.get('custom_size_range'):
        return None
    settings = get_pack_out_settings()
    size_range = frappe.get_doc('SD YRP FG Item Size Range', template.custom_size_range)
    size_type = frappe.get_doc('SD YRP FG Item Size Type', size_range.size_type) if size_range.get('size_type') else frappe._dict()
    links = {r.attribute_value for r in size_range.sizes}
    links.update(r.size_type_value for r in size_type.get('fg_item_size_type_details') or [])
    values = {r.name: r.attribute_value for r in frappe.get_all('YRP Item Attribute Value',
        filters={'name': ['in', list(links)]}, fields=['name', 'attribute_value'])} if links else {}
    try:
        return sales_definition(template, size_range, size_type, values, settings)
    except ValueError as exc:
        frappe.throw(str(exc))


def set_pieces_per_carton(item):
    item.custom_pieces_per_carton = cint(item.get('custom_pieces_per_box')) * cint(item.get('custom_box_per_carton'))


def validate_sales_template(item, method=None):
    """Derive packaging, then check an Item template that carries a Size Range."""
    set_pieces_per_carton(item)
    if not item.get('custom_size_range'):
        return
    if not item.has_variants or item.variant_of:
        frappe.throw(_('Size Range can be set only on an Item template.'))
    if frappe.db.get_value('Item Group', item.item_group, 'is_group') != 0:
        frappe.throw(_('Select a leaf Item Group for a sales Item template.'))
    if item.stock_uom != PIECE_UOM:
        frappe.throw(_('Sales Size Range requires {0} as the Item template stock UOM.').format(PIECE_UOM))
    if cint(item.get('custom_pieces_per_box')) <= 0 or cint(item.get('custom_box_per_carton')) <= 0:
        frappe.throw(_('Pieces Per Box and Box Per Carton must be greater than zero.'))
    for uom, field in PACKAGING_UOMS:
        row = next((r for r in item.uoms if r.uom == uom), None) or item.append('uoms', {'uom': uom})
        row.conversion_factor = cint(item.get(field))
    load_sales_definition(item)


def ensure_size_variants(item, method=None):
    """Create the missing Size x pack-out stage variants of a sales Item template."""
    if item.variant_of or not item.has_variants or not item.get('custom_size_range') or item.get('disabled'):
        return []
    from yrp.yrp.doctype.yrp_item.yrp_item import build_variant_attributes, get_or_create_variant

    definition = load_sales_definition(item)
    settings = get_pack_out_settings()
    frappe.has_permission('Item', 'create', throw=True)
    # create_variant copies from get_cached_doc; on_update runs before Frappe clears this template's cache.
    item.clear_cache()
    add_missing_size_values(item, settings.primary, definition['cells'])
    return [
        get_or_create_variant(item.name, build_variant_attributes({settings.primary: cell['value']}, settings.stage, item))
        for cell in definition['cells']
    ]


def add_missing_size_values(item, attribute, cells):
    """Grow the template's own size mapping with new Size Range values; never remove."""
    from yrp.yrp.doctype.yrp_item_item_attribute_mapping.ownership import has_other_references

    row = next((r for r in item.attributes if r.attribute == attribute), None)
    if not row or not row.get('mapping'):
        return
    mapping = frappe.get_doc('YRP Item Item Attribute Mapping', row.mapping)
    current = {attribute_db.value(r.attribute_value) for r in mapping.get('values') or []}
    missing = [cell['link'] for cell in cells if cell['value'] not in current]
    if not current or not missing:
        return
    if has_other_references(mapping.name, item):
        frappe.throw(_('Item template {0} shares its {1} mapping; repair ownership first.').format(item.name, attribute))
    for link in missing:
        mapping.append('values', {'attribute_value': link})
    mapping.save()
    frappe.clear_document_cache('YRP Item Item Attribute Mapping', mapping.name)


def refresh_range_templates(size_range, method=None):
    for name in frappe.get_all('Item', filters={'custom_size_range': size_range.name, 'has_variants': 1,
            'variant_of': ['is', 'not set'], 'disabled': 0}, pluck='name'):
        ensure_size_variants(frappe.get_doc('Item', name))


def is_sellable_stage(template, attributes, settings):
    """A variant of a template staged by the packing attribute sells only at the pack-out stage."""
    return template.get('dependent_attribute') != settings.packing or attributes.get(settings.packing) == settings.stage


def get_sellable_variants(template):
    """Enabled variants with the primary attribute and the pack-out stage, in Size Range order."""
    settings = get_pack_out_settings()
    rows = frappe.db.sql("""
        select v.name as item, p.attribute_value as size, v.custom_mrp as mrp
        from `tabItem` v
        join `tabItem Variant Attribute` p on p.parent = v.name and p.parenttype = 'Item'
            and p.parentfield = 'attributes' and p.attribute = %(primary)s
        join `tabItem Variant Attribute` k on k.parent = v.name and k.parenttype = 'Item'
            and k.parentfield = 'attributes' and k.attribute = %(packing)s and k.attribute_value = %(stage)s
        where v.variant_of = %(template)s and v.disabled = 0
        order by p.idx, v.name
    """, {'template': template, **settings}, as_dict=True)
    size_range = frappe.db.get_value('Item', template, 'custom_size_range')
    order = {}
    if size_range:
        links = frappe.get_all('SD YRP FG Item Size', filters={'parent': size_range, 'parenttype': 'SD YRP FG Item Size Range'},
            pluck='attribute_value', order_by='idx')
        order = {attribute_db.value(link): index for index, link in enumerate(links)}
    return sorted(rows, key=lambda row: order.get(row.size, len(order)))


def validate_slot_rows(rows, domains):
    """Empty slot values are allowed; set keys and values must be valid and distinct."""
    if not rows:
        raise ValueError('Size Type requires at least one size slot.')
    keys = set()
    values = set()
    for row in rows:
        key, value = row.get('size'), row.get('size_type_value')
        if not key and not value:
            continue
        if key not in SIZE_SLOTS:
            raise ValueError(f'Size Type slot {key!r} is not valid. Use one of size 1 to size 10.')
        if key in keys or (value and value in values):
            raise ValueError('Size Type requires distinct slots and distinct values.')
        if value and domains.get(value) != 'Size':
            raise ValueError('Size Type values must belong to the Size attribute.')
        keys.add(key)
        if value:
            values.add(value)


def validate_range_rows(rows, domains, coverage=None):
    selected=[row.get('attribute_value') for row in rows]
    if not selected or len(selected) != len(set(selected)) or any(not value for value in selected):
        raise ValueError('Size Range requires distinct, nonempty size values.')
    if any(domains.get(value) != 'Size' for value in selected):
        raise ValueError('Size Range values must belong to the Size attribute.')
    if coverage is not None and set(selected)-coverage:
        raise ValueError('Every Size Range value must have a slot in its Size Type.')


def size_value_domains(links):
    return {r.name:r.attribute_name for r in frappe.get_all('YRP Item Attribute Value',
        filters={'name':['in',list(links)]},fields=['name','attribute_name'])} if links else {}
