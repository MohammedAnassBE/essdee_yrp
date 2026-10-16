const garment = (doc) => !Number(doc.is_cloth_item)
const savedGarment = (doc, { isNew }) => garment(doc) && !isNew
const cloth = (doc) => Boolean(Number(doc.is_cloth_item))
const part = (component, sectionKey = component, variant = '') => ({ component, sectionKey, variant })
const section = (heading, parts, visible = () => true) => ({ heading, parts, visible })

export const IPD_TABS = [
	{ fieldname: 'item_details_tab', label: 'Item Details', visible: () => true, sections: [
		section('', [part('item')]),
		section('Item Attributes', [part('attributes')]),
		section('Bill of Materials', [part('accessories', 'accessories', 'bom'), part('processes', 'processes', 'general')], garment),
		section('Processes', [part('processes', 'processes', 'general')], cloth),
	] },
	{ fieldname: 'packing_tab', label: 'Packing', visible: savedGarment, sections: [
		section('Packing Details', [part('packing', 'packing', 'details')]),
		section('', [part('packing', 'packing', 'values')]),
	] },
	{ fieldname: 'set_item_tab', label: 'Set Item', preload: garment, visible: (doc, context) => savedGarment(doc, context) && Boolean(doc.packing_attribute), sections: [section('Set Item Details', [part('set_item')])] },
	{ fieldname: 'stiching_tab', label: 'Stiching', visible: savedGarment, sections: [
		section('Stiching Details', [part('stitching', 'stitching', 'details')], (doc) => Boolean(doc.stiching_attribute)),
		section('', [part('stitching', 'stitching', 'items')]),
		section('', [part('stitching', 'stitching', 'combination')]),
		section('Bundle Details', [part('stitching', 'stitching', 'bundles')], (doc) => Boolean(doc.stiching_item_details?.length)),
	] },
	{ fieldname: 'emblishment_tab', label: 'Emblishment', visible: garment, sections: [section('', [part('processes', 'processes', 'embellishment')])] },
	{ fieldname: 'cutting_tab', label: 'Cutting', visible: savedGarment, sections: [
		section('Cloth Details', [part('cutting', 'cutting', 'cloths')]),
		section('Cutting Details', [part('cutting', 'cutting', 'consumption')]),
		section('Cloth Mapping Details', [part('cutting', 'cutting', 'mapping')]),
	] },
	{ fieldname: 'cloth_accessory_tab', label: 'Cloth Accessory', visible: savedGarment, sections: [
		section('', [part('accessories', 'accessories', 'accessories')]),
		section('', [part('accessories', 'accessories', 'stitching')]),
	] },
	{ fieldname: 'advance_settings_tab', label: 'Advance Settings', visible: garment, sections: [
		section('Packing Details Section', [part('settings', 'packing', 'packing')]),
		section('Stitching Details Section', [part('settings', 'stitching', 'stitching')]),
		section('Cutting Details Section', [part('settings', 'cutting', 'cutting')]),
	] },
	{ fieldname: 'fabric_processes_tab', label: 'Fabric Processes', visible: cloth, sections: [
		section('', [part('fabric_processes')]),
		section('Yarn Ratio', [part('yarn_ratio')]),
		section('Fabric Routes', [part('fabric_routes')]),
	] },
	{ fieldname: 'compacting_reference_tab', label: 'Compacting Details', visible: cloth, sections: [section('', [part('compacting')])] },
]

export const TAB_FIELDS = {
	item_details_tab: ['item', 'description', 'tech_pack_version', 'pattern_version', 'primary_item_attribute', 'dependent_attribute', 'item_attributes', 'additional_cloth', 'stiching_attribute_quantity', 'item_bom', 'ipd_processes'],
	packing_tab: ['packing_combo', 'packing_attribute_no', 'auto_calculate', 'based_on_other_attribute_mapping', 'packing_mode', 'packing_attribute_details', 'packing_size_details', 'packing_assortment_json'],
	set_item_tab: ['is_set_item', 'set_item_attribute', 'major_attribute_value', 'set_item_detail'],
	stiching_tab: ['stiching_major_attribute_value', 'is_same_packing_attribute', 'stiching_item_details', 'stiching_item_detail', 'marker_groups'],
	emblishment_tab: ['emblishment_details_json'],
	cutting_tab: ['enable_panel_wise_consumption_matrix', 'cloth_detail', 'cutting_attributes', 'cloth_attributes', 'cutting_items_json', 'cutting_cloths_json', 'panel_wise_consumption_matrix_json', 'panel_wise_cloth_mapping_json'],
	cloth_accessory_tab: ['accessory_attributes', 'accessory_clothtype_json', 'cloth_accessory_json', 'stiching_accessory_json'],
	advance_settings_tab: ['packing_attribute', 'packing_process', 'pack_in_stage', 'pack_out_stage', 'stiching_attribute', 'stiching_process', 'stiching_in_stage', 'stiching_out_stage', 'cutting_process'],
	fabric_processes_tab: ['yarn_ratio_details', 'fabric_routes', 'fabric_processes', 'fabric_value_mappings'],
	compacting_reference_tab: ['compacting_reference_details'],
}
export const FIELD_TAB = Object.freeze(Object.fromEntries(Object.entries(TAB_FIELDS).flatMap(([tab, fields]) => fields.map((field) => [field, tab]))))
const SECTION_TAB = {
	item: 'item_details_tab', attributes: 'item_details_tab', processes: 'item_details_tab', review: 'item_details_tab',
	packing: 'packing_tab', set_item: 'set_item_tab', stitching: 'stiching_tab', cutting: 'cutting_tab', accessories: 'cloth_accessory_tab',
	yarn_ratio: 'fabric_processes_tab', fabric_routes: 'fabric_processes_tab', fabric_processes: 'fabric_processes_tab', compacting: 'compacting_reference_tab',
}
export function problemTab(problem) {
	return FIELD_TAB[problem.field] || (problem.field === 'colour_yarn_recipes' ? 'fabric_processes_tab' : SECTION_TAB[problem.section]) || 'item_details_tab'
}
export function tabLabel(change) {
	return IPD_TABS.find((tab) => tab.fieldname === problemTab(change))?.label || 'Item Details'
}
export function visibleTabs(tabs, doc, context = {}) {
	return tabs.filter((tab) => !tab.visible || tab.visible(doc, context))
}
export function preloadSectionKeys(tabs, doc) {
	// Include saved-document tabs and tabs that can appear after changing a field.
	return [...new Set(tabs.filter((tab) => !(tab.preload || tab.visible) || (tab.preload || tab.visible)(doc, { isNew: false }))
		.flatMap((tab) => tab.sections.filter((section) => !section.visible || section.visible(doc, { isNew: false }))
			.flatMap((section) => section.parts.map((part) => part.component))))]
}
export function resolveTab(tabs, requested) {
	return tabs.some((tab) => tab.fieldname === requested) ? requested : tabs[0]?.fieldname || ''
}
