import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as ipdLinks from '../src/departments/merch/ipd/ipdLinks.js'
import test from 'node:test'
import { resolve } from 'node:path'
import { Vue, findNodes, loadComponent, mountComponent } from '../../scripts/helpers/vue_renderer.mjs'
import * as targets from '../src/utils/linkTarget.js'
import * as values from '../src/utils/documentValues.js'
import * as overview from '../src/utils/documentOverview.js'
import * as grid from '../src/components/common/entryGrid.js'
import * as childFields from '../src/components/common/childTableFields.js'
import * as groups from '../src/engine/stock/groupItemsForDisplay.js'
import * as stockItemComposer from '../src/utils/stockItemComposer.js'
import * as lotViews from '../src/departments/purchase/lot/lotViews.js'
import * as lotEditor from '../src/departments/purchase/lot/lotEditor.js'
import * as program from '../src/engine/lotClothProgram.js'
import * as costViews from '../src/departments/merch/process-cost/processCostViews.js'
import * as priceViews from '../src/departments/purchase/purchaseViews.js'
import * as lotOcrView from '../src/departments/sales/lotOcrView.js'

const nodes = (root, type) => findNodes(root, node => node.type === type)
const text = node => node.type === 'comment' ? '' : node.text + node.children.map(text).join('')
const links = root => nodes(root, 'a').map(node => [text(node), node.props.href])
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const control = (props, { slots }) => Vue.h('control', props, slots.default?.())
const formControl = (props) => Vue.h('form-control', props)
const column = { setup: () => () => null }
const table = { setup(props, { attrs, slots }) { return () => Vue.h('table', {}, (slots.default?.() || []).flatMap(col => col.type === Vue.Fragment ? col.children : [col]).flatMap(col => (attrs.value || []).map((data, index) => Vue.h('td', {}, col.children?.body?.({ data, index }))))) } }
const defaults = {
 'vue-router': { useRouter: () => ({ push() {} }), RouterLink: control },
 '../../utils/linkTarget.js': targets, '../../../utils/linkTarget.js': targets, '../../../../utils/linkTarget.js': targets,
 '../../utils/documentValues.js': values, '../../utils/documentOverview.js': overview,
 './entryGrid.js': grid, './childTableFields.js': childFields,
 '../../engine/stock/groupItemsForDisplay.js': groups,
 '../../utils/stockItemComposer.js': stockItemComposer,
 './lotViews.js': lotViews, './lotEditor.js': lotEditor, '../../purchase/lot/lotEditor.js': lotEditor,
 '../../purchase/lot/lotViews.js': lotViews, '../../../engine/lotClothProgram.js': program,
 './processCostViews.js': costViews, './purchaseViews.js': priceViews, './lotOcrView.js': lotOcrView,
 '../ipdLinks.js': ipdLinks,
 './LinkField.vue': control, './FormField.vue': formControl,
 '../../../../components/common/FormField.vue': formControl,
 '../../../components/common/FormField.vue': formControl,
 './ClothProgramDialog.vue': control,
 '../../../components/documents/DocumentStatusBadge.vue': control,
 'primevue/column': column, 'primevue/datatable': table,
 ...Object.fromEntries(['button','select','checkbox','inputtext','message','tag','skeleton','dialog'].map(name => [`primevue/${name}`, control])),
}
function component(path, modules = {}) { return loadComponent(resolve(`frontend/src/${path}.vue`), { ...defaults, ...modules }) }
function readable(fn, allowed = ['Item', 'Supplier', 'UOM', 'User', 'YRP Process', 'SD YRP Lot', 'YRP Process Cost', 'YRP Item Production Detail', 'Item Attribute', 'YRP Item Attribute Value']) {
 const previous = globalThis.window
 globalThis.window = { frappe: { boot: { user: { can_read: allowed } } }, addEventListener() {}, removeEventListener() {}, matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) }
 return Promise.resolve().then(fn).finally(() => { globalThis.window = previous })
}

test('B1 EntryGrid links only typed nonempty cells, resolves Dynamic Link and preserves label', () => readable(async () => {
 const columns = [
  { key: 'item', label: 'Item', type: 'link', fieldtype: 'Link', options: 'Item', doctype: 'Item' },
  { key: 'dynamic', label: 'Dynamic', type: 'text', fieldtype: 'Dynamic Link', options: 'target' },
  { key: 'plain', label: 'Plain', type: 'select', options: ['A'] },
  { key: 'empty', label: 'Empty', fieldtype: 'Link', options: 'Item' },
  { key: 'private', label: 'Private', fieldtype: 'Link', options: 'Season' },
 ]
 const props = Vue.reactive({ rows: [{ key: 'r', label: 'Row' }], columns, modelValue: { r: { item: 'A/B', dynamic: 'user@example.test', target: 'User', plain: 'A', private: 'Summer' } }, readonly: true })
 const root = mountComponent(component('components/common/EntryGrid'), props)
 assert.deepEqual(links(root), [['A/B', '/web/purchase/items/A%2FB'], ['user@example.test', '/desk/user/user%40example.test']])
 assert.equal(nodes(root, 'td').length, 5)
 const anchor = nodes(root, 'a')[0]
 const event = { button: 0, target: { closest: () => anchor }, preventDefault() { throw Error('link mousedown prevented') } }
 nodes(root, 'td')[0].props.onMousedown(event)
 nodes(root, 'td')[0].props.onClick(event)
 await tick()
 assert.equal(nodes(root, 'input').length, 0)
}))

test('B1 ChildTableField read-only Link and Dynamic Link values use raw row targets', () => readable(() => {
 const root = mountComponent(component('components/common/ChildTableField'), {
  field: { fieldname: 'children', options: 'Child' }, disabled: true,
  childMeta: { fields: [{ fieldname: 'item', fieldtype: 'Link', options: 'Item' }, { fieldname: 'ref', fieldtype: 'Dynamic Link', options: 'target' }, { fieldname: 'data', fieldtype: 'Data' }] },
  modelValue: [{ item: 'A/B', ref: 'U', target: 'User', data: 'Plain' }],
 })
 assert.deepEqual(links(root), [['A/B', '/web/purchase/items/A%2FB'], ['U', '/desk/user/U']])
 assert.equal(nodes(root, 'form-control').length, 1)
}))

test('B1 ChildTableField Table MultiSelect links each child Link value', () => readable(() => {
 const root = mountComponent(component('components/common/ChildTableField'), {
  field: { fieldname: 'categories', fieldtype: 'Table MultiSelect', options: 'Category Row' }, disabled: true,
  childMeta: { fields: [{ fieldname: 'item', fieldtype: 'Link', options: 'Item' }] },
  modelValue: [{ item: 'A' }, { item: 'B' }],
 })
 assert.deepEqual(links(root), [['A', '/web/purchase/items/A'], ['B', '/web/purchase/items/B']])
}))

test('B2 WorkOrderOverview links metadata targets and preserves substituted labels', () => readable(() => {
 const root = mountComponent(component('departments/fabric-store/WorkOrderOverview'), { details: [
  { fieldname: 'supplier', fieldtype: 'Link', options: 'Supplier', value: 'Supplier Display', link_name: 'SUP/1' },
  { fieldname: 'ref', fieldtype: 'Dynamic Link', options: 'against', link_doctype: 'Item', value: 'A/B' },
  { fieldname: 'comments', fieldtype: 'Data', value: 'Plain' },
  { fieldname: 'empty', fieldtype: 'Link', options: 'Item', value: '' },
 ] })
 assert.deepEqual(links(root), [['Supplier Display', '/desk/supplier/SUP%2F1'], ['A/B', '/web/purchase/items/A%2FB']])
 assert.ok(nodes(root, 'dd').some(node => text(node) === 'Plain'))
}))

test('B3 StockItemMatrix links item, lot, UOM and typed contextual dimensions only', () => readable(() => {
 const props = { doctype: 'Purchase Order', dimensions: [{ fieldname: 'project', fieldtype: 'Link', options: 'Item' }, { fieldname: 'received_type', fieldtype: 'Select', options: 'Item' }], groups: [{ items: [{ name: 'A/B', default_uom: 'Nos', delivery_location: 'SUP/1', schedule_date: '2026-10-20', dimensions: { lot: 'LOT/1', project: 'PROJECT', received_type: 'Fresh' }, values: { default: { qty: 1 } } }] }] }
 const root = mountComponent(component('components/stock/StockItemMatrix'), props)
 assert.deepEqual(links(root), [['A/B', '/web/purchase/items/A%2FB'], ['LOT/1', '/web/purchase/lots/LOT%2F1'], ['PROJECT', '/web/purchase/items/PROJECT'], ['SUP/1', '/desk/supplier/SUP%2F1'], ['Nos', '/desk/uom/Nos']])
 const grouped = mountComponent(component('components/stock/StockItemMatrix'), { ...props, groupByItem: true })
 assert.ok(links(grouped).some(([label, href]) => label === 'A/B' && href.endsWith('A%2FB')))
 assert.ok(links(grouped).some(([label, href]) => label === 'LOT/1' && href.endsWith('LOT%2F1')))
}))

test('B4 WorkOrderItemMatrix links Item, Lot and Process Cost outside Merch', () => readable(() => {
 const root = mountComponent(component('departments/fabric-store/WorkOrderItemMatrix'), { groups: [{ items: [{ name: 'A/B', lot: 'LOT/1', process_cost: 'PC/1', values: { default: { qty: 1 } } }] }] })
 assert.deepEqual(links(root), [['A/B', '/web/purchase/items/A%2FB'], ['LOT/1', '/web/purchase/lots/LOT%2F1'], ['PC/1', '/web/merch/process-costs/PC%2F1']])
}))

const ipdKey = Symbol('ipd')
function ipdFields(readonly) {
 const fields = [
  { fieldname: 'copied_from', label: 'Copied From' }, { fieldname: 'approved_by', label: 'Approved By' },
  { fieldname: 'stitching_process', label: 'Process' }, { fieldname: 'primary_item_attribute', label: 'Attribute' },
  { fieldname: 'pack_in_stage', label: 'Stage' }, { fieldname: 'data', label: 'Data', fieldtype: 'Data' },
 ]
 const editor = { readonly, context: { link_names: { fields: { pack_in_stage: { value: 'IAV/1', name: 'IAV/1' } } } }, draft: { copied_from: 'IPD/1', approved_by: 'U', stitching_process: 'Stitching', primary_item_attribute: 'Size', pack_in_stage: 'IAV/1', data: 'Plain' }, fields: Object.fromEntries(fields.slice(0, 5).map((field, index) => [field.fieldname, { fieldtype: 'Link', options: ['YRP Item Production Detail','User','YRP Process','Item Attribute','YRP Item Attribute Value'][index] }])), registerFocus: () => () => {} }
 const child = component('departments/merch/ipd/sections/IpdFields', { '../useIpdEditor.js': { IPD_EDITOR_KEY: ipdKey }, '../ipdEditor.js': { stableStringify: JSON.stringify } })
 return mountComponent({ setup() { Vue.provide(ipdKey, editor); return () => Vue.h(child, { fields }) } })
}
test('B5 IpdFields uses stored Link metadata in read mode and enables editor open buttons', () => readable(() => {
 assert.equal(links(ipdFields(true)).length, 5)
 const controls = nodes(ipdFields(false), 'form-control')
 assert.equal(controls.length, 6)
 assert.ok(controls.every(node => node.props['show-open-button'] !== false && node.props.showOpenButton !== false))
}))

test('B5 IPD identity and copy banner link raw names while retaining display labels', () => readable(() => {
 const root = mountComponent(component('departments/merch/ipd/IpdIdentity'), { item: 'A/B', itemName: 'Display Item', headingId: 'heading' })
 assert.deepEqual(links(root), [['Display Item', '/web/purchase/items/A%2FB']])
 const banner = mountComponent(component('departments/merch/ipd/IpdCopyBanner', { './ipdTabs.js': { tabLabel: value => value } }), { source: { name: 'IPD/1' } })
 assert.deepEqual(links(banner), [['IPD/1', '/web/merch/item-production-details/IPD%2F1']])
}))

for (const department of ['purchase', 'planning']) {
 test(`B6 ${department} Lot BOM links process, item and UOM`, () => readable(() => {
  const root = mountComponent(component(`departments/${department}/lot/LotBomTab`), { bom: { summary: [{ process_name: 'Stitching', item: 'A/B', uom: 'Nos', required_qty: 1 }] } })
  assert.deepEqual(links(root), [['Stitching', '/desk/yrp-process/Stitching'], ['A/B', '/web/purchase/items/A%2FB'], ['Nos', '/desk/uom/Nos']])
 }))
 test(`B6 ${department} derived Lot facts link UOM and raw stage names`, () => readable(() => {
  const root = mountComponent(component(`departments/${department}/lot/LotEditorDetails`), { form: { lot_fabric_details: [] }, derived: { uom: 'Nos', packing_uom: 'Box', pack_in_stage: 'Cut', pack_in_stage_name: 'IAV/1', pack_out_stage: 'Packed' }, fields: lotEditor.LOT_EDIT_GROUPS.flatMap(group => group.fields.map(fieldname => ({ fieldname }))), fabricMeta: {} })
  assert.deepEqual(links(root), [['Nos', '/desk/uom/Nos'], ['Cut', '/desk/yrp-item-attribute-value/IAV%2F1'], ['Box', '/desk/uom/Box']])
 }))
}

test('B7 ProcessCostGrid links attribute row labels with their raw names', () => readable(() => {
 const root = mountComponent(component('departments/merch/process-cost/ProcessCostGrid'), { readonly: true, tiers: [{ attribute_value: 'IAV/1', attribute_value_label: 'Small', min_order_qty: 1, price: 2 }] })
 assert.deepEqual(links(root), [['Small', '/desk/yrp-item-attribute-value/IAV%2F1']])
}))

test('B7 Item Price overview retains raw approver when its label is substituted', () => {
 const fields = priceViews.itemPriceOverviewFields({ record: { docstatus: 1, approved_by: 'Approver Display' }, fields: [{ fieldname: 'approved_by', fieldtype: 'Link', options: 'User', value: 'user@example.test' }] })
 assert.equal(fields[0].value, 'Approver Display')
 assert.equal(fields[0].link_name, 'user@example.test')
})

test('B6 Lot fabric links cloth, IPD, ledger processes and conversion raw items', () => readable(() => {
 const root = mountComponent(component('departments/purchase/lot/LotFabricTab'), { fabrics: [{ cloth_item: 'Cloth/1', production_detail: 'IPD/1', steps: [{ process_name: 'Knitting', rows: [{ side: 'Input', planned_weight: 1 }] }], conversions: [{ process_name: 'Knitting', planned_item: 'Plan/1', actual_item: 'Actual/1', actual_quantity: 1, production_detail: 'IPD/2' }] }] })
 const actual = links(root)
 for (const pair of [['Cloth/1', '/web/purchase/items/Cloth%2F1'], ['IPD/1', '/web/merch/item-production-details/IPD%2F1'], ['Knitting', '/desk/yrp-process/Knitting'], ['Plan/1', '/web/purchase/items/Plan%2F1'], ['Actual/1', '/web/purchase/items/Actual%2F1'], ['IPD/2', '/web/merch/item-production-details/IPD%2F2']]) assert.ok(actual.some(value => JSON.stringify(value) === JSON.stringify(pair)), JSON.stringify(pair))
 assert.ok(actual.every(([, href]) => !href.startsWith('/app/')))
}))

for (const department of ['purchase', 'planning']) {
 test(`B6 ${department} rail supplier links require raw IDs and keep dialog clicks separate`, () => readable(() => {
  const root = mountComponent(component(`departments/${department}/lot/LotDocumentsRail`, { '../../../components/common/WorkspaceLoadError.vue': control }), { documents: { purchase_orders: { count: 2, rows: [ { name: 'PO1', supplier: 'SUP/1', supplier_name: 'Supplier Display' }, { name: 'PO2', supplier_name: 'Only Display' } ] } } })
  assert.deepEqual(links(root), [['Supplier Display', '/desk/supplier/SUP%2F1']])
  assert.ok(text(root).includes('Only Display'))
  const anchor = nodes(root, 'a')[0]
  const event = { button: 0, ctrlKey: true, target: { closest: selector => selector === 'a' ? anchor : null }, stopPropagation() { this.stopped = true } }
  for (const handler of [anchor.props.onClick].flat()) handler(event)
  assert.equal(event.stopped, true)
  assert.equal(nodes(root, 'button').length, 0)
 }))
 test(`B6 ${department} dialog supplier and typed facts use raw targets`, () => readable(async () => {
  const root = mountComponent(component(`departments/${department}/lot/LotDocumentDialog`, {
   [`../../../api/${department}.js`]: { getLotDocument: async () => ({ record: { supplier: 'SUP/1', supplier_name: 'Supplier Display' }, details: [{ fieldname: 'item', fieldtype: 'Link', options: 'Item', value: 'A/B' }, { fieldname: 'data', fieldtype: 'Data', value: 'Plain' }] }) },
   '../../../components/stock/StockItemMatrix.vue': control, '../../fabric-store/WorkOrderItemMatrix.vue': control,
   '../../../router/webDocumentRoutes.js': { webDocumentPath: () => '' }, '../../../utils/documentOverview.js': overview,
  }), { lot: 'LOT', name: 'PO', doctype: 'Purchase Order', visible: true })
  await tick()
  assert.deepEqual(links(root), [['Supplier Display', '/desk/supplier/SUP%2F1'], ['A/B', '/web/purchase/items/A%2FB']])
 }))
}

test('B6 Merch PPO item and sales OCR process use DocumentLink', () => readable(() => {
 const ppo = mountComponent(component('departments/merch/lot/MerchLotPpoPanel', { '../../../components/common/LinkField.vue': control, '../../../components/documents/DocumentActionStrip.vue': control, '../merchViews.js': { MERCH_ROUTES: {} } }), { showPanel: true, ppo: { name: 'PPO', item: 'A/B' } })
 assert.ok(links(ppo).some(([label, href]) => label === 'A/B' && href === '/web/purchase/items/A%2FB'))
 const ocr = mountComponent(component('departments/sales/LotOcrTable', { '../../router/webDocumentRoutes.js': { webDocumentRoute: () => '' } }), { payload: { processes: { Stitching: {} } } })
 assert.deepEqual(links(ocr), [['Stitching', '/desk/yrp-process/Stitching']])
}))

test('B7 Process Cost header links the process name', () => readable(async () => {
 const workspaceControl = { setup(props, { attrs, slots }) { return () => Vue.h('workspace', {}, slots.header?.({ record: attrs.workspace.record || {}, headingId: 'heading' })) } }
 const root = mountComponent(component('departments/merch/process-cost/ProcessCostPage', {
  'vue-router': { useRoute: () => ({ query: {} }), useRouter: () => ({ push() {}, replace() {} }) },
  '../../../router/listDocumentNavigation.js': { preserveListNavigationState: () => ({}) },
  '../merchViews.js': { MERCH_ROUTES: {} },
  '../../../api/merch.js': { getProcessCostWorkspace: async () => ({ record: { name: 'PC', process_name: 'Stitching' } }) },
  '../../../components/DepartmentPage.vue': control,
  ...Object.fromEntries(['DocumentOverview','DocumentStatusBadge','DocumentActionStrip','DocumentConfirmationDialog','DocumentErrorDialog'].map(name => [`../../../components/documents/${name}.vue`, control])),
  '../../fabric-store/FabricDocumentWorkspace.vue': workspaceControl,
  '../../purchase/lot/LotDocumentsRail.vue': control, './ProcessCostGrid.vue': control,
  ...Object.fromEntries(['tab','tablist','tabpanel','tabpanels','tabs'].map(name => [`primevue/${name}`, control])),
 }), { processCostId: 'PC' })
 await tick()
 assert.deepEqual(links(root), [['Stitching', '/desk/yrp-process/Stitching']])
}))

test('B7 Item Price header, attribute and tiers retain labels and raw targets', () => readable(async () => {
 const record = { name: 'PRICE', item_name: 'A/B', supplier: 'SUP/1', supplier_name: 'Supplier Display', depends_on_attribute: 1, attribute: 'Size' }
 const workspaceControl = { setup(props, { attrs, slots }) { return () => Vue.h('workspace', {}, [slots.header?.({ record: attrs.workspace.record || {}, headingId: 'heading' }), slots.fields?.()]) } }
 const root = mountComponent(component('departments/purchase/ItemPricePage', {
  '../../api/purchase.js': { getItemPriceWorkspace: async () => ({ record, tiers: [{ attribute_value: 'IAV/1', attribute_value_label: 'Small', moq: 1, price: 2, lead_time: 1 }] }) },
  '../../components/DepartmentPage.vue': control,
  ...Object.fromEntries(['DocumentStatusBadge','DocumentActionStrip','DocumentConfirmationDialog','DocumentErrorDialog','DocumentOverview'].map(name => [`../../components/documents/${name}.vue`, control])),
  '../fabric-store/FabricDocumentWorkspace.vue': workspaceControl, './ItemPriceActionDialog.vue': control,
 }), { priceId: 'PRICE' })
 await tick()
 assert.deepEqual(links(root), [['A/B', '/web/purchase/items/A%2FB'], ['Supplier Display', '/desk/supplier/SUP%2F1'], ['Size', '/desk/item-attribute/Size'], ['Small', '/desk/yrp-item-attribute-value/IAV%2F1']])
}))

test('B5 IpdFields uses actual meta for Select presentations and normalized stage labels', () => readable(() => {
 const editor = { readonly: true, draft: { pack_in_stage: 'Cut' }, fields: { pack_in_stage: { fieldtype: 'Link', options: 'YRP Item Attribute Value' } }, context: { link_names: { fields: { pack_in_stage: { value: 'Cut', name: 'IAV/1' } } } }, registerFocus: () => () => {} }
 const child = component('departments/merch/ipd/sections/IpdFields', { '../useIpdEditor.js': { IPD_EDITOR_KEY: ipdKey }, '../ipdEditor.js': { stableStringify: JSON.stringify } })
 const root = mountComponent({ setup() { Vue.provide(ipdKey, editor); return () => Vue.h(child, { fields: [{ fieldname: 'pack_in_stage', label: 'Stage', fieldtype: 'Select', options: ['Cut'] }] }) } })
 assert.deepEqual(links(root), [['Cut', '/desk/yrp-item-attribute-value/IAV%2F1']])
}))

test('B1 EntryGrid supports per-row raw link names without changing option labels', () => readable(() => {
 const root = mountComponent(component('components/common/EntryGrid'), { rows: [{ key: 'r', label: 'Row' }], columns: [{ key: 'stage', type: 'value', fieldtype: 'Link', link_doctype: 'YRP Item Attribute Value', options: [{ value: 'Cut', label: 'Cut' }], linkName: (value, row) => row.key === 'r' && value === 'Cut' ? 'IAV/1' : '' }], modelValue: { r: { stage: 'Cut' } }, readonly: true })
 assert.deepEqual(links(root), [['Cut', '/desk/yrp-item-attribute-value/IAV%2F1']])
}))

test('B5 IPD grid link columns resolve normalized values by table row and leave stale labels plain', async () => {
 const { ipdLinkColumns, ipdAttributeLinkName } = await import('../src/departments/merch/ipd/ipdLinks.js')
 const editor = { context: { link_names: { fields: { pack_in_stage: { value: 'Cut', name: 'IAV/1' } }, tables: { ipd_processes: { ROW: { in_stage: { value: 'Cut', name: 'IAV/1' } } } } } } }
 const columns = ipdLinkColumns([{ key: 'in_stage', fieldtype: 'Link', link_doctype: 'YRP Item Attribute Value', type: 'value', options: ['Cut'] }, { key: 'data', type: 'text' }], editor, 'ipd_processes')
 assert.equal(columns[0].linkName('Cut', { key: 'ROW' }), 'IAV/1')
 assert.equal(columns[0].linkName('Packed', { key: 'ROW' }), '')
 assert.equal(columns[1].fieldtype, undefined)
 assert.equal(ipdAttributeLinkName(editor, 'pack_in_stage', 'Cut'), 'IAV/1')
 assert.equal(ipdAttributeLinkName(editor, 'pack_in_stage', 'Packed'), '')
})

test('B1 EntryGrid never links Data or Select even if target hints are present', () => readable(() => {
 const root = mountComponent(component('components/common/EntryGrid'), { rows: [{ key: 'r', label: 'Row' }], columns: [{ key: 'data', type: 'text', fieldtype: 'Data', link_doctype: 'Item' }, { key: 'select', type: 'select', fieldtype: 'Select', options: ['A'], link_doctype: 'Item' }], modelValue: { r: { data: 'A', select: 'A' } }, readonly: true })
 assert.deepEqual(links(root), [])
}))

test('B5 IPD grid columns declare only their actual Link targets', () => {
 const definitions = {
  'sections/IpdAccessoriesSection.vue': { item: 'Item', process_name: 'YRP Process', dependent_attribute_value: 'YRP Item Attribute Value', uom: 'UOM' },
  'sections/IpdProcessesSection.vue': { process_name: 'YRP Process', process_item: 'Item', in_stage: 'YRP Item Attribute Value' },
  'sections/IpdCuttingSection.vue': { cloth: 'Item' },
  'cloth/IpdYarnRatioSection.vue': { yarn_item: 'Item', colour: 'YRP Item Attribute Value', yarn_colour: 'YRP Item Attribute Value' },
  'cloth/IpdFabricProcessesSection.vue': { fabric_process: 'YRP Process', input_item: 'Item', output_item: 'Item', attribute: 'Item Attribute' },
 }
 for (const [path, fields] of Object.entries(definitions)) {
  const source = readFileSync(resolve(`frontend/src/departments/merch/ipd/${path}`), 'utf8')
  for (const [key, doctype] of Object.entries(fields)) {
   const columns = [...source.matchAll(new RegExp(`\\{ key: "${key}", [^\\n]+`, 'g'))].map(match => match[0])
   assert.ok(columns.length, `${path}: ${key}`)
   assert.ok(columns.every(column => column.includes('fieldtype: "Link"') && column.includes(`link_doctype: "${doctype}"`)), `${path}: ${key}`)
  }
 }
 const source = readFileSync(resolve('frontend/src/departments/merch/ipd/sections/garmentGrids.js'), 'utf8')
 assert.match(source, /type: "link", fieldtype: "Data", doctype: "Item Attribute Value"/)
})

test('B1 EntryGrid still opens and edits typed Link cells with doctype options', () => readable(async () => {
 let opened = 0
 const editor = { setup(props, { expose }) { expose({ open() { opened++ } }); return () => Vue.h('link-editor', props) } }
 const root = mountComponent(component('components/common/EntryGrid', { './LinkField.vue': editor }), { rows: [{ key: 'r', label: 'Row' }], columns: [{ key: 'item', label: 'Item', type: 'link', fieldtype: 'Link', options: 'Item', doctype: 'Item' }], modelValue: { r: { item: 'A' } } })
 nodes(root, 'table')[0].querySelector = () => null
 nodes(root, 'td')[0].props.onClick({ button: 0 })
 await tick()
 assert.equal(links(root).length, 0)
 assert.equal(nodes(root, 'link-editor')[0].props.doctype, 'Item')
 assert.equal(nodes(root, 'link-editor')[0].props['search-handler'], null)
 assert.equal(opened, 1)
}))

test('B3 StockItemMatrix accepts stock dimension options without explicit fieldtype', () => readable(() => {
 const root = mountComponent(component('components/stock/StockItemMatrix'), { dimensions: [{ fieldname: 'project', options: 'Item' }], groups: [{ items: [{ name: '', dimensions: { project: 'A' } }] }] })
 assert.deepEqual(links(root), [['A', '/web/purchase/items/A']])
}))

test('B6 Merch derived Lot facts link UOM and raw stage names', () => readable(() => {
 const root = mountComponent(component('departments/merch/lot/MerchLotEditorDetails'), { form: { lot_fabric_details: [] }, derived: { uom: 'Nos', packing_uom: 'Box', pack_in_stage: 'Cut', pack_in_stage_name: 'IAV/1', pack_out_stage: 'Packed' }, fields: lotEditor.LOT_EDIT_GROUPS.flatMap(group => group.fields.map(fieldname => ({ fieldname }))), fabricMeta: {} })
 assert.deepEqual(links(root), [['Nos', '/desk/uom/Nos'], ['Cut', '/desk/yrp-item-attribute-value/IAV%2F1'], ['Box', '/desk/uom/Box']])
}))
