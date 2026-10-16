import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { addActualDia, canRemoveActualDia, changeActualDia, diaSiblings, prepareActualDiaGroups, receivableBalance, setActualDiaRowError, unusedDias } from '../frontend/src/departments/fabric-store/grnActualDia.js'

const context = { enabled: true, attribute: 'Dia', dia_options: ['14', '14.5', '19'] }
const source = { name: 'Greige', item_variant: 'Greige-14', attributes: { Colour: 'Greige', Dia: '14' }, row_index: 1, table_index: 0, dimensions: { received_type: 'Accepted', lot: 'LOT-1' }, values: { default: { name: 'GRNI-1', item_variant: 'Greige-14', qty: 30, rate: 10, amount: 300, secondary_qty: 1, freight_amount: 2, pending_quantity: 50, ref_doctype: 'YRP Work Order Receivables', ref_docname: 'REC-1' } } }
const group = { items: [source] }
assert.deepEqual(unusedDias(group, source, context), ['14.5', '19'])
assert.equal(receivableBalance(group, source), 20)
const added = addActualDia(group, source, context, '14.5')
assert.equal(added.name, 'Greige')
assert.equal(added.item_variant, undefined)
assert.equal(added.row_index, undefined)
assert.equal(added.table_index, undefined)
assert.deepEqual(added.attributes, { Colour: 'Greige', Dia: '14.5' })
assert.equal(added.values.default.ref_docname, 'REC-1')
assert.equal(added.values.default.rate, 10)
for (const field of ['qty', 'secondary_qty', 'freight_amount']) assert.equal(added.values.default[field], 0)
assert.equal(Object.hasOwn(added.values.default, 'amount'), false)
const workspaceSource = readFileSync(new URL('../frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue', import.meta.url), 'utf8')
const rowValueCode = workspaceSource.match(/^function rowValue\(row\).*$/m)[0]
const rowValue = new Function(`${rowValueCode}; return rowValue`)()
added.values.default.qty = 20
assert.equal(rowValue(added), 200, 'new Dia row computes value from its quantity and inherited rate')
added.values.default.qty = 0
assert.equal(added.values.default.name, undefined)
assert.equal(canRemoveActualDia(source), false)
assert.equal(canRemoveActualDia(added), true)
assert.equal(addActualDia(group, source, context, '14.5'), null)
assert.deepEqual(unusedDias(group, added, context, true), ['14.5', '19'])
changeActualDia(added, context.attribute, '19')
assert.equal(added.attributes.Dia, '19')
added.values.default.qty = 30
assert.equal(canRemoveActualDia(added), false)
assert.equal(receivableBalance(group, added), -10)
assert.equal(receivableBalance(group, source), -10)
group.items.push({ ...source, values: { default: { ref_docname: 'REC-2', qty: 100, pending_qty: 500 } } })
assert.equal(diaSiblings(group, source).length, 2)
assert.equal(receivableBalance(group, source), -10)
assert.equal(setActualDiaRowError([group], 'Row 2: only Dia may differ'), true)
assert.equal(added.actual_dia_error, 'Row 2: only Dia may differ')
assert.equal(setActualDiaRowError([group], 'No matching receivable'), false)
assert.equal(setActualDiaRowError([group], 'Row 99: invalid'), false)
const matrixGroup = { primary_attribute: 'Dia', primary_attribute_values: ['14', '14.5'], attributes: ['Colour'], items: [{ name: 'Greige', attributes: { Colour: 'Greige' }, primary_attribute: 'Dia', values: { '14': source.values.default, '14.5': { qty: 0 } } }] }
const prepared = prepareActualDiaGroups([matrixGroup], context)[0]
assert.equal(prepared.items.length, 1)
assert.equal(prepared.primary_attribute, null)
assert.equal(prepared.items[0].attributes.Dia, '14')
assert.equal(prepared.items[0].values.default.ref_docname, 'REC-1')
assert.deepEqual(prepareActualDiaGroups([matrixGroup], { enabled: false }), [matrixGroup])
const reopened = prepareActualDiaGroups([{
	...matrixGroup,
	primary_attribute_values: ['14', '14.5', '19'],
	items: [
		{ ...matrixGroup.items[0], values: { '19': { ref_docname: 'A', qty: 40 } } },
		{ ...matrixGroup.items[0], values: { '14': { ref_docname: 'B', qty: 30 } } },
		{ ...matrixGroup.items[0], values: { '14.5': { ref_docname: 'B', qty: 20 } } },
	],
}], context)[0]
assert.deepEqual(reopened.items.map((row) => row.attributes.Dia), ['19', '14', '14.5'])
assert.equal(diaSiblings(reopened, reopened.items[2])[0], reopened.items[1], 'Add Dia belongs to the planned 14 Dia row')
console.log('GRN Actual Dia helpers OK')
