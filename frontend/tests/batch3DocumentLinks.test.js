import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import test from 'node:test'
import { Vue, findNodes, loadComponent, mountComponent } from '../../scripts/helpers/vue_renderer.mjs'
import * as targets from '../src/utils/linkTarget.js'
import * as productionOrderDisplay from '../src/departments/sales/productionOrderDisplay.js'
import { formatDisplayDatetime } from '../src/utils/dateFormat.js'

const require = createRequire(new URL('../package.json', import.meta.url))
const { parse } = require('@vue/compiler-sfc')
const { parse: parseScript } = require('@babel/parser')
const source = path => readFileSync(resolve(`frontend/src/departments/${path}.vue`), 'utf8')
const debitDuplicateModules = { '../../composables/useDocumentPermissions.js': { useDocumentPermissions: () => Vue.ref(null) }, '../../composables/useDuplicateAction.js': { loadDuplicateValues: async () => null }, '../../components/common/FormView.vue': () => null }
const modules = { 'vue-router': { useRouter: () => ({ push() {} }) }, '../../utils/linkTarget.js': targets }
const DocumentLink = loadComponent(resolve('frontend/src/components/common/DocumentLink.vue'), modules)
const text = node => node.type === 'comment' ? '' : node.text + node.children.map(text).join('')
const links = root => findNodes(root, node => node.type === 'a').map(node => [text(node), node.props.href])
function walk(node) { return [node, ...(node.children || []).flatMap(walk)] }
function element(path, tag, needle) {
 const ast = parse(source(path)).descriptor.template.ast
 const node = walk(ast).filter(node => node.tag === tag && node.loc.source.includes(needle)).sort((a, b) => a.loc.source.length - b.loc.source.length)[0]
 assert.ok(node, `${path}: ${tag} containing ${needle}`)
 return node.loc.source
}
// Render the real page fragment with its existing display context and the shared link component.
function fragment(path, tag, needle, context) {
 return mountComponent({ components: { DocumentLink, Button: () => null }, setup: () => ({headingId:'heading',product:'',item:'',...context}), render: Vue.compile(element(path, tag, needle)) })
}
function computedValue(path, name, context) {
 const script = parse(source(path)).descriptor.scriptSetup.content
 const ast = parseScript(script, { sourceType: 'module' })
 const declaration = ast.program.body.flatMap(node => node.declarations || []).find(node => node.id.name === name)
 assert.ok(declaration, `${path}: ${name}`)
 return new Function('computed', ...Object.keys(context), `return (${script.slice(declaration.init.start, declaration.init.end)}).value`)(Vue.computed, ...Object.values(context))
}
function readable(fn, allowed) {
 const previous = globalThis.window
 const previousLocation = globalThis.location
 globalThis.window = { location: { pathname: '/web/planning/finishing-plans/FP' }, frappe: { boot: { user: { can_read: allowed || ['Item','Supplier','UOM','User','Department','SD YRP Lot','YRP Work Order','YRP Process','SD YRP Cutting Plan','SD YRP Cutting Order Detail','SD YRP Cutting LaySheet','SD YRP Lot Transfer','YRP Delivery Challan','YRP Goods Received Note','YRP Production Order','YRP Item Production Detail','YRP Production Term','SD YRP Product Colour Code','YRP Tax Slab','YRP Debit','YRP Bill Tracking','SD YRP Finishing Plan','SD YRP Cutting Spreader','SD YRP Cutter'] } } } }
 globalThis.location = globalThis.window.location
 return Promise.resolve().then(fn).finally(() => { globalThis.window = previous; globalThis.location = previousLocation })
}
const pair = (label, slug, name = label) => [label, `/desk/${slug}/${encodeURIComponent(name)}`]
function check(root, expected) { assert.deepEqual(links(root), expected) }

const directCases = [
 ['D1', 'FabricPurchaseOrder', 'strong', 'record.supplier_name', { record: { supplier: 'SUP/1', supplier_name: 'Supplier Display' } }, [pair('Supplier Display', 'supplier', 'SUP/1')]],
 ['D1', 'FabricPurchaseOrder', 'span', 'purchase-order-lots__chip', { lotDraft: ['LOT/1'], removeLot() {} }, [['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D3', 'FabricWorkOrder', 'span', 'work-order-page__lot', { record: { lot: 'LOT/1' } }, [['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D3', 'FabricWorkOrder', 'span', 'record.item ||', { record: { item: 'ITEM/1' } }, [['ITEM/1','/web/purchase/items/ITEM%2F1']]],
 ['D3', 'fabric-store/WorkOrderEditor', 'strong', 'form.parent_wo', { form: { parent_wo: 'WO/1' } }, [['WO/1','/web/planning/work-orders/WO%2F1']]],
 ['D6', 'CuttingPlan', 'strong', 'doc.lot', { doc: { lot: 'LOT/1' } }, [['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D6', 'CuttingPlan', 'strong', 'doc.item', { doc: { item: 'ITEM/1' } }, [['ITEM/1','/web/purchase/items/ITEM%2F1']]],
 ['D6', 'cutting/CuttingPlanTabs', 'td', 'row.changed_by', { row: { changed_by: 'user@example.test' } }, [pair('user@example.test','user')]],
 ['D7', 'CuttingOrder', 'strong', 'record.cutting_order_detail', { record: { cutting_order_detail: 'DETAIL/1' } }, [pair('DETAIL/1','sd-yrp-cutting-order-detail')]],
 ['D8', 'CuttingBulkLaySheet', 'strong', 'record.main_lot', { record: { main_lot: 'LOT/1' } }, [['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D8', 'CuttingBulkLaySheet', 'strong', 'record.from_location', { record: { from_location: 'SUP/1' } }, [pair('SUP/1','supplier')]],
 ['D8', 'cutting/bulk/BulkActiveLaySheet', 'td', 'item.cloth_item_variant', { item: { cloth_item_variant: 'ITEM/1' } }, [['ITEM/1','/web/purchase/items/ITEM%2F1']]],
 ['D9', 'CuttingLaySheetPlanner', 'strong', 'record.lot', { record: { lot: 'LOT/1' } }, [['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D9', 'CuttingLaySheetPlanner', 'strong', 'record.item', { record: { item: 'ITEM/1' } }, [['ITEM/1','/web/purchase/items/ITEM%2F1']]],
 ['D10', 'sales/ProductionOrder', 'h1', 'record.item', { record: { item: 'ITEM/1' } }, [['ITEM/1','/web/purchase/items/ITEM%2F1']]],
 ['D10', 'sales/ProductionOrder', 'strong', 'v-for="lot', { workspace: { linked_lots: ['LOT/1'] } }, [['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D10', 'sales/ProductionOrderTransferHistory', 'strong', 'row.requested_by', { row: { requested_by: 'USER/1' } }, [pair('USER/1','user')]],
 ['D10', 'sales/ProductionOrderTransferHistory', 'strong', 'row.approved_by', { row: { approved_by: 'USER/2' } }, [pair('USER/2','user')]],
 ['D11', 'pd/components/ProductColours', 'strong', 'row.product_colour', { row: { product_colour: 'COLOUR/1' } }, [pair('COLOUR/1','sd-yrp-product-colour-code')]],
 ['D12', 'accounts/components/PurchaseInvoiceHeader', 'dd', 'record.supplier', { record: { supplier: 'SUP/1' } }, [pair('SUP/1','supplier')]],
 ['D12', 'accounts/components/PurchaseInvoiceGroupedItems', 'td', 'value(row.item)', { row: { item: 'ITEM/1' }, value: value => value || '—' }, [['ITEM/1','/web/purchase/items/ITEM%2F1']]],
 ['D12', 'accounts/components/PurchaseInvoiceGroupedItems', 'td', 'value(row.lot)', { row: { lot: 'LOT/1' }, value: value => value || '—' }, [['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D12', 'accounts/components/PurchaseInvoiceGroupedItems', 'td', 'value(row.uom)', { row: { uom: 'Nos' }, value: value => value || '—' }, [pair('Nos','uom')]],
 ['D12', 'accounts/components/PurchaseInvoiceGroupedItems', 'td', 'value(row.tax)', { row: { tax: 'TAX/1' }, value: value => value || '—' }, [pair('TAX/1','yrp-tax-slab')]],
 ['D12', 'accounts/components/PurchaseInvoiceTabs', 'td', 'grn.against_id', { grn: { against: 'YRP Work Order', against_id: 'WO/1' } }, [['WO/1','/web/planning/work-orders/WO%2F1']]],
 ['D12', 'accounts/components/PurchaseInvoiceVerification', 'td', 'value(debit.name)', { debit: { name: 'DEBIT/1' }, value: value => value || '—' }, [['DEBIT/1','/web/accounts/debits/DEBIT%2F1']]],
 ['D12', 'accounts/components/PurchaseInvoiceVerification', 'td', 'value(approval.user)', { approval: { user: 'USER/1' }, value: value => value || '—' }, [pair('USER/1','user')]],
 ['D12', 'accounts/components/PurchaseInvoiceEditorHeader', 'span', 'purchase-invoice-editor__fact', { billTracking: 'BILL/1' }, [['BILL/1','/web/hr/bill-tracking/BILL%2F1']]],
 ['D14', 'hr/BillTracking', 'dd', 'record.supplier', { record: { supplier: 'SUP/1' } }, [pair('SUP/1','supplier')]],
 ['D14', 'hr/BillTracking', 'td', 'row.assigned_to', { row: { assigned_to: 'Accounts' } }, [pair('Accounts','department')]],
 ['D14', 'hr/BillTracking', 'td', 'row.assigned_by', { row: { assigned_by: 'USER/1' } }, [pair('USER/1','user')]],
 ['D15', 'finishing/plan/FinishingGrnTab', 'td', 'batch.grn', { batch: { grn: 'GRN/1' } }, [['GRN/1','/web/planning/goods-received-notes/GRN%2F1']]],
 ['D15', 'finishing/plan/FinishingOldLotTab', 'td', 'group.fp', { group: { fp: 'FP/1', lot: 'LOT/1' }, buckets: () => [1] }, [['FP/1','/web/planning/finishing-plans/FP%2F1'],['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D15', 'finishing/plan/FinishingAlternativesTab', 'h3', 'lot.name', { lot: { name: 'LOT/1', item: 'ITEM/1' } }, [['LOT/1','/web/planning/lots/LOT%2F1'],['ITEM/1','/web/purchase/items/ITEM%2F1']]],
 ['D15', 'finishing/plan/FinishingDispatchHistoryTab', 'td', 'log.source_name', { log: { source_doctype: 'YRP Work Order', source_name: 'WO/1' } }, [['YRP Work Order WO/1','/web/planning/work-orders/WO%2F1']]],
 ['D15', 'finishing/plan/FinishingProfitAndLossTab', 'small', 'document.owner', { document: { modified: '2026-10-23 14:05:09', owner: 'USER/1' }, formatDisplayDatetime }, [pair('USER/1','user')]],
 ['D16', 'finishing/FinishingDispatch', 'h2', 'row.doc_name', { row: { lot: 'LOT/1', item: 'ITEM/1', doc_name: 'FP/1' } }, [['LOT/1','/web/planning/lots/LOT%2F1'],['ITEM/1','/web/purchase/items/ITEM%2F1'],['FP/1','/web/planning/finishing-plans/FP%2F1']]],
]
for (const [id, path, tag, needle, context, expected] of directCases) {
 test(`${id} ${path} ${needle} links raw names`, () => readable(() => check(fragment(path, tag, needle, context), expected)))
 test(`${id} ${path} ${needle} stays plain without permission`, () => readable(() => check(fragment(path, tag, needle, context), []), []))
}

for (const [id, path, values, expected] of [
 ['D4','fabric-store/DeliveryChallanWorkspace',{work_order:'WO/1',process_name:'Cut',item:'ITEM/1',lot:'LOT/1'}, [['WO/1','/web/planning/work-orders/WO%2F1'],pair('Cut','yrp-process'),['ITEM/1','/web/purchase/items/ITEM%2F1'],['LOT/1','/web/planning/lots/LOT%2F1']]],
 ['D5','fabric-store/GoodsReceivedNoteWorkspace',{against:'YRP Work Order',against_id:'WO/1',process_name:'Cut',item:'ITEM/1',supplier:'SUP/1',supplier_name:'Supplier Display'}, [['WO/1','/web/planning/work-orders/WO%2F1'],pair('Cut','yrp-process'),['ITEM/1','/web/purchase/items/ITEM%2F1'],pair('Supplier Display','supplier','SUP/1')]],
 ['D15','finishing/FinishingPlan',{lot:'LOT/1',item:'ITEM/1',work_order:'WO/1',pieces_per_box:10}, [['LOT/1','/web/planning/lots/LOT%2F1'],['ITEM/1','/web/purchase/items/ITEM%2F1'],['WO/1','/web/planning/work-orders/WO%2F1']]],
]) test(`${id} headerFacts preserve labels and raw targets`, () => readable(() => {
 const headerFacts = computedValue(path,'headerFacts',{ workspace: Vue.ref({record:values}),record:Vue.ref(values),form:{} })
 check(fragment(path,id === 'D15' ? 'span' : 'div', 'v-for="fact in headerFacts', {headerFacts}), expected)
}))

for (const path of ['fabric-store/DeliveryChallanWorkspace','fabric-store/GoodsReceivedNoteWorkspace']) test(`D4/D5 ${path} matrix item and UOM links`, () => readable(() => {
 check(fragment(path,'strong','section.name ||', {section:{name:'ITEM/1'}}), [['ITEM/1','/web/purchase/items/ITEM%2F1']])
 check(fragment(path,'td','row.default_uom ||', {row:{default_uom:'Nos'}}), [pair('Nos','uom')])
}))

test('D10 ProductionOrderOverview links typed facts only and preserves substituted labels', () => readable(() => {
 const fields = [{fieldname:'production_detail',label:'IPD',fieldtype:'Link',options:'YRP Item Production Detail',value:'IPD/1'}, {fieldname:'submitted_by',fieldtype:'Link',options:'User',link_name:'USER/1',value:'User Display'}, {fieldname:'comments',fieldtype:'Data',value:'Plain'}, {fieldname:'empty',fieldtype:'Link',options:'Item',value:''}]
 const root = loadComponent(resolve('frontend/src/departments/sales/ProductionOrderOverview.vue'), { ...modules, './productionOrderDisplay.js': productionOrderDisplay })
 check(mountComponent(root,{fields}), [['IPD/1','/web/merch/item-production-details/IPD%2F1'],pair('User Display','user','USER/1')])
}))

const editors = ['fabric-store/PurchaseOrderEditor','fabric-store/WorkOrderEditor','cutting/plan/CuttingPlanEditor','cutting/order/CuttingOrderEditor','sales/ProductionOrderEditor','accounts/components/PurchaseInvoiceEditorBody','hr/BillTrackingEditorPage','pd/components/ProductFieldsPanel','cutting/bulk/BulkSetupEditor']
for (const path of editors) test(`Editors ${path} top-level LinkFields allow permission-gated open icons`, () => {
 const ast = parse(source(path)).descriptor.template.ast
 function visit(node, picker = false) {
  const excluded = picker || ['Dialog','td','StockItemComposer'].includes(node.tag)
  if (!excluded && ['LinkField','FormField'].includes(node.tag)) assert.ok(!node.loc.source.includes(':show-open-button="false"'), node.loc.source)
  for (const child of node.children || []) visit(child, excluded)
 }
 visit(ast)
})

test('D7 CuttingOrderTabs keeps Data item plain and supplies the order detail target', () => {
 const fields = computedValue('cutting/order/CuttingOrderTabs','overviewFields',{props:{data:{record:{cutting_order_detail:'DETAIL/1',item:'Data Item'},details:[]}}})
 assert.equal(fields.find(field => field.fieldname === 'item').fieldtype,'Data')
 assert.equal(fields.find(field => field.fieldname === 'cutting_order_detail').options,'SD YRP Cutting Order Detail')
})

test('D8 BulkWorkflowRail keeps row selection cards free of anchors', () => {
 assert.ok(!element('cutting/bulk/BulkWorkflowRail','article','bulk-workflow-card').includes('DocumentLink'))
})


test('D13 Debits resolves only Link metadata and leaves Data and Check values plain', () => readable(async () => {
 const route = {params:{debitId:'DEBIT/1'},query:{}}
 const fields = [{fieldname:'work_order',fieldtype:'Link',options:'YRP Work Order'}, {fieldname:'approved_by',fieldtype:'Link',options:'User'}, {fieldname:'amended_from',fieldtype:'Link',options:'YRP Debit'}, {fieldname:'debit_no',fieldtype:'Data'}, {fieldname:'inspection',fieldtype:'Check'}]
 const control = (props,{slots}) => Vue.h('control',props,slots.default?.())
 const component = loadComponent(resolve('frontend/src/departments/accounts/Debits.vue'), {
  ...modules, 'vue-router':{useRoute:()=>route,useRouter:()=>({push(){}})},
  '../../utils/linkTarget.js':targets,
  '../../config/fields/debit.js': {detailGroups:[{fields:fields.map(field=>field.fieldname)}]},
  ...debitDuplicateModules,
  '../../router/departmentLock.js':{isOutsideLayout:()=>false,getHomePath:()=>'/'},
  '../../api/frappe.js':{getDoc:async()=>({work_order:'WO/1',approved_by:'USER/1',amended_from:'DEBIT/0',debit_no:'Plain',inspection:1}),getMeta:async()=>[{name:'YRP Debit',fields}]},
  ...Object.fromEntries(['../../components/DepartmentPage.vue','../../components/common/ListView.vue','../../components/documents/DocumentStatusBadge.vue','../../components/documents/DocumentErrorDialog.vue','primevue/button','primevue/dialog'].map(path=>[path,control])),
 })
 const root = mountComponent(component,{})
 await new Promise(resolve=>setImmediate(resolve)); await Vue.nextTick()
 check(root,[['WO/1','/web/planning/work-orders/WO%2F1'],pair('USER/1','user'),['DEBIT/0','/web/accounts/debits/DEBIT%2F0']])
 assert.ok(text(root).includes('Plain'))
}))

test('D13b Debits outside the layout loads only the linked debit and closes to the layout home', () => readable(async () => {
 const route = {params:{debitId:'DEBIT/1'},query:{}}
 const pushes = []
 const dialog = {}
 const fields = [{fieldname:'debit_no',fieldtype:'Data'}]
 const named = tag => (props,{slots}) => Vue.h(tag,props,slots.default?.())
 const component = loadComponent(resolve('frontend/src/departments/accounts/Debits.vue'), {
  ...modules, 'vue-router':{useRoute:()=>route,useRouter:()=>({push:path=>pushes.push(path)})},
  '../../utils/linkTarget.js':targets,
  ...debitDuplicateModules,
  '../../router/departmentLock.js':{isOutsideLayout:path=>path==='/accounts/debits',getHomePath:()=>'/sales'},
  '../../config/fields/debit.js': {detailGroups:[{fields:['debit_no']}]},
  '../../api/frappe.js':{getDoc:async()=>({debit_no:'Plain'}),getMeta:async()=>[{name:'YRP Debit',fields}]},
  '../../components/common/ListView.vue':named('listview'),
  'primevue/dialog':(props,{slots})=>{Object.assign(dialog,props);return Vue.h('dialog',props,slots.default?.())},
  ...Object.fromEntries(['../../components/DepartmentPage.vue','../../components/documents/DocumentStatusBadge.vue','../../components/documents/DocumentErrorDialog.vue','primevue/button'].map(path=>[path,named('control')])),
 })
 const root = mountComponent(component,{})
 await new Promise(resolve=>setImmediate(resolve)); await Vue.nextTick()
 assert.equal(findNodes(root,node=>node.type==='listview').length,0)
 assert.ok(text(root).includes('Plain'))
 dialog['onUpdate:visible'](false); await Vue.nextTick()
 assert.deepEqual(pushes,['/sales'])
}))

test('D11 LotwiseWorkspaceHeader uses raw product or FG item and leaves fallback title plain', () => readable(() => {
 for (const [props, expected] of [
  [{title:'Product Display',product:'PRODUCT/1'}, [['Product Display','/web/pd/products/PRODUCT%2F1']]],
  [{title:'Item Display',item:'FG/1'}, [pair('Item Display','sd-yrp-fg-item-master','FG/1')]],
  [{title:'Fallback'}, []],
 ]) check(fragment('pd/components/LotwiseWorkspaceHeader','h1','title',props),expected)
}, ['SD YRP Product','SD YRP FG Item Master']))

test('D6 MaterialRequirementGroups links raw cloth items while accessory Data remains plain', () => readable(() => {
 const component = loadComponent(resolve('frontend/src/departments/cutting/shared/MaterialRequirementGroups.vue'), {...modules,'../../../utils/linkTarget.js':targets,'primevue/button':()=>null})
 const root = mountComponent(component,{kind:'accessory',rows:[{accessory:'Data accessory',cloth_item_variant:'ITEM/1'}]})
 check(root,[['ITEM/1','/web/purchase/items/ITEM%2F1']])
 assert.ok(text(root).includes('Data accessory'))
}))

test('D5 GRN supplier display without a raw supplier stays plain', () => readable(() => {
 const path = 'fabric-store/GoodsReceivedNoteWorkspace'
 const headerFacts = computedValue(path,'headerFacts',{workspace:Vue.ref({record:{supplier_name:'Display Only'}}),form:{}})
 const root = fragment(path,'div','v-for="fact in headerFacts',{headerFacts})
 check(root,[])
 assert.ok(text(root).includes('Display Only'))
}))

test('Editors retain hidden open icons in item composer cells, grid cells and dialog pickers', () => {
 for (const [path, tag, needle] of [
  ['fabric-store/PurchaseOrderEditor','StockItemComposer','entry-fields'],
  ['cutting/bulk/BulkSetupEditor','td','v-model="row.lot"'],
  ['FabricPurchaseOrder','LinkField','v-model="lotCandidate"'],
  ['FabricWorkOrder','LinkField','v-model="grnDeliveryChallan"'],
 ]) {
  const snippet = element(path,tag,needle)
  assert.ok(snippet.includes(':show-open-button="false"'), snippet)
 }
})

test('D12 masked supplier display with no raw target stays plain', () => readable(() => {
 const root = fragment('accounts/components/PurchaseInvoiceHeader','dd','record.supplier',{record:{supplier:'XXXXXXXX',supplier_link_name:''}})
 check(root,[])
 assert.equal(text(root),'XXXXXXXX')
}))
