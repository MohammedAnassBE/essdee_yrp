<template>
	<Dialog :visible="visible" modal class="erp-entity-dialog bom-mapping-dialog" :style="{ width: dialogWidth }" :header="`${detail?.bom_item || itemName} Mapping`" @update:visible="close">
		<div class="bom-mapping-body" :aria-busy="loading">
			<p v-if="loading" role="status" class="erp-help-text">Loading mapping…</p>
			<p v-if="error" class="ipd-grid-notice ipd-grid-notice--error" role="alert">{{ error }}</p>
			<template v-if="detail && !loading">
				<dl class="bom-mapping-facts">
					<div><dt>Item</dt><dd>{{ detail.item }}</dd></div>
					<div><dt>BOM Item</dt><dd>{{ detail.bom_item }}</dd></div>
					<div><dt>UOM</dt><dd>{{ detail.bom_uom || '—' }}</dd></div>
				</dl>
				<div class="bom-mapping-sides">
					<section v-for="side in sides" :key="side.field" class="bom-mapping-side" :aria-label="side.title">
						<h3 class="ipd-subhead">
							<span>{{ side.title }}</span>
							<Button v-if="!readOnly" label="Add row" icon="pi pi-plus" text :disabled="saving" :aria-label="`Add ${side.title} row`" @click="tables[side.field].push({ attribute: null, same_attribute: 0 })" />
						</h3>
						<table v-if="tables[side.field].length" class="ipd-simple-table bom-mapping-compact bom-mapping-attributes">
							<caption class="bom-mapping-sr-only">{{ side.title }}</caption>
							<thead><tr><th scope="col">Attribute</th><th scope="col" class="bom-mapping-narrow">Same Attribute</th><th v-if="!readOnly" scope="col" class="bom-mapping-narrow"><span class="bom-mapping-sr-only">Remove</span></th></tr></thead>
							<tbody>
								<tr v-for="(attributeRow, index) in tables[side.field]" :key="index">
									<td>
										<span v-if="readOnly">{{ attributeRow.attribute }}</span>
										<Select v-else v-model="attributeRow.attribute" :options="detail[side.options]" :disabled="saving" :aria-label="`${side.title} row ${index + 1} Attribute`" placeholder="Select attribute" />
									</td>
									<td class="bom-mapping-center">
										<span v-if="readOnly">{{ Number(attributeRow.same_attribute) ? 'Yes' : 'No' }}</span>
										<Checkbox v-else v-model="attributeRow.same_attribute" binary :true-value="1" :false-value="0" :disabled="saving" :aria-label="`${side.title} row ${index + 1} Same Attribute`" />
									</td>
									<td v-if="!readOnly" class="bom-mapping-center"><Button icon="pi pi-trash" text severity="secondary" :aria-label="`Remove ${side.title} row ${index + 1}`" :disabled="saving" @click="tables[side.field].splice(index, 1)" /></td>
								</tr>
							</tbody>
						</table>
						<p v-else class="bom-mapping-empty">No attributes</p>
					</section>
				</div>
				<div v-if="!readOnly" class="bom-mapping-actions">
					<Button label="Get Combination" :disabled="saving" @click="getCombination" />
					<Button label="Disable" severity="secondary" outlined :disabled="saving || tablesChanged" @click="rows = disableRows(rows, columns)" />
					<Button label="Enable" severity="secondary" outlined :disabled="saving || tablesChanged" @click="rows = enableRows(rows)" />
				</div>
				<p v-if="tablesChanged" class="ipd-grid-notice" role="status">Get Combination after changing attributes.</p>
				<p v-if="!columns.item.length && !columns.all_same" class="erp-help-text">Add an item attribute</p>
				<p v-if="columns.all_same" class="erp-help-text">All item attributes use the same values on the BOM item.</p>
				<p v-if="dropped" class="ipd-grid-notice" role="status">{{ dropped }} saved {{ dropped === 1 ? 'line no longer matches' : 'lines no longer match' }} the IPD Cutting combinations.</p>
				<div v-if="columns.item.length" ref="grid" class="bom-mapping-scroll">
					<table class="ipd-simple-table bom-mapping-compact bom-mapping-grid">
						<caption class="bom-mapping-sr-only">BOM mapping combinations</caption>
						<thead>
							<tr>
								<th scope="col" class="bom-mapping-narrow">S.No</th><th scope="col" class="bom-mapping-narrow"><span class="bom-mapping-sr-only">Include row</span></th>
								<th v-for="attribute in columns.item" :key="`item:${attribute}`" scope="col">{{ attribute }}</th>
								<th v-for="attribute in columns.bom" :key="`bom:${attribute}`" scope="col">
									<div class="bom-mapping-fill">
										<span>{{ attribute }}</span>
										<template v-if="!readOnly">
											<Select v-model="header[attribute]" :options="detail.bom_values[attribute] || []" filter :aria-label="`Fill BOM ${attribute}`" :disabled="saving || tablesChanged" placeholder="Select" />
											<Button label="Fill" outlined :aria-label="`Fill BOM ${attribute} column`" :disabled="saving || tablesChanged" @click="rows = fillColumn(rows, attribute, header[attribute])" />
										</template>
									</div>
								</th>
								<th scope="col">
									<div class="bom-mapping-fill">
										<span>Quantity</span>
										<template v-if="!readOnly">
											<InputNumber v-model="headerQuantity" :max-fraction-digits="6" :use-grouping="false" aria-label="Fill Quantity" placeholder="Qty" :disabled="saving || tablesChanged" />
											<Button label="Fill" outlined aria-label="Fill Quantity column" :disabled="saving || tablesChanged" @click="rows = fillColumn(rows, 'quantity', headerQuantity)" />
										</template>
									</div>
								</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, index) in rows" :key="row.key" :class="{ 'is-excluded': !row.included }">
								<th scope="row" class="bom-mapping-index">{{ index + 1 }}</th>
								<td class="bom-mapping-center">
									<span v-if="readOnly" role="img" :aria-label="row.included ? 'Included' : 'Excluded'" :class="['pi', row.included ? 'pi-minus-circle bom-mapping-included' : 'pi-plus-circle']" />
									<Button v-else :icon="row.included ? 'pi pi-minus-circle' : 'pi pi-plus-circle'" :severity="row.included ? 'danger' : 'secondary'" text :aria-label="row.included ? 'Exclude row' : 'Include row'" :aria-pressed="row.included" :disabled="saving || tablesChanged" @click="toggleRow(row.key)" />
								</td>
								<td v-for="attribute in columns.item" :key="`item:${attribute}`">{{ row.item[attribute] }}</td>
								<td v-for="attribute in columns.bom" :key="`bom:${attribute}`">
									<span v-if="readOnly">{{ row.included ? row.bom[attribute] : '' }}</span>
									<Select v-else :model-value="row.included ? row.bom[attribute] : null" :options="detail.bom_values[attribute] || []" filter :disabled="saving || tablesChanged || !row.included" :aria-label="`Row ${index + 1} BOM ${attribute}`" :invalid="Boolean(problem(row, `bom:${attribute}`))" :aria-invalid="Boolean(problem(row, `bom:${attribute}`))" :placeholder="row.included ? 'Select' : ''" @update:model-value="row.bom[attribute] = $event" />
									<small v-if="problem(row, `bom:${attribute}`)" class="bom-mapping-problem">{{ problem(row, `bom:${attribute}`) }}</small>
								</td>
								<td class="bom-mapping-quantity">
									<span v-if="readOnly">{{ row.included || Number(row.quantity) ? row.quantity : '' }}</span>
									<InputNumber v-else :model-value="row.included || Number(row.quantity) ? row.quantity : null" :max-fraction-digits="6" :use-grouping="false" :disabled="saving || tablesChanged || !row.included" :aria-label="`Row ${index + 1} Quantity`" :invalid="Boolean(problem(row, 'quantity'))" :aria-invalid="Boolean(problem(row, 'quantity'))" @update:model-value="row.quantity = $event" />
									<small v-if="problem(row, 'quantity')" class="bom-mapping-problem">{{ problem(row, 'quantity') }}</small>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</template>
		</div>
		<template #footer>
			<Button label="Cancel" text severity="secondary" :disabled="saving" @click="close(false)" />
			<Button v-if="!readOnly" label="Save mapping" icon="pi pi-save" :loading="saving" :disabled="loading || !detail" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Select from "primevue/select"
import { computed, inject, nextTick, ref, watch } from "vue"

import { getIpdBomMapping } from "../../../../api/merch.js"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { disableRows, enableRows, fillColumn, freshGrid, gridFromValues, mappingOutput, setRowIncluded } from "./bomMapping.js"
import "./sections.css"

const props = defineProps({
	visible: { type: Boolean, default: false },
	bomRow: { type: String, default: "" },
	itemName: { type: String, default: "" },
	readonly: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible"])
const editor = inject(IPD_EDITOR_KEY)
const detail = ref(null), rows = ref([]), tables = ref({ item_attributes: [], bom_item_attributes: [] })
const loading = ref(false), saving = ref(false), error = ref(""), attempted = ref(false)
const dropped = ref(0), header = ref({}), headerQuantity = ref(null), grid = ref(null)
const generatedTables = ref("")
let loadSequence = 0
const sides = [
	{ field: "item_attributes", title: "Item Attributes", options: "item_attribute_options" },
	{ field: "bom_item_attributes", title: "BOM Item Attributes", options: "bom_attribute_options" },
]
const readOnly = computed(() => props.readonly || editor.readonly || Boolean(detail.value?.is_shared))
const columns = computed(() => detail.value?.columns || { item: [], bom: [], same: [], all_same: false })
const tablesChanged = computed(() => JSON.stringify(tables.value) !== generatedTables.value)
const output = computed(() => mappingOutput(rows.value, columns.value))
const dialogWidth = computed(() => columns.value.item.length + columns.value.bom.length > 3 ? "min(1200px, 96vw)" : "min(1040px, 96vw)")

watch(() => [props.visible, props.bomRow], () => {
	if (props.visible) load(false)
	else loadSequence += 1
}, { immediate: true })

function close(visible) {
	if (!saving.value) emit("update:visible", visible)
}
function problem(row, column) {
	return attempted.value ? output.value.problems[row.key]?.[column] || "" : ""
}
function toggleRow(key) {
	rows.value = rows.value.map((row) => row.key === key ? setRowIncluded(row, !row.included) : row)
}
function tableError() {
	for (const side of sides) {
		const attributes = tables.value[side.field].map((row) => row.attribute)
		if (attributes.some((attribute) => !detail.value[side.options].includes(attribute))) return `${side.title}: choose an attribute from the Item's attributes.`
		if (new Set(attributes).size !== attributes.length) return `${side.title}: duplicate attribute.`
	}
	return ""
}
async function getCombination() {
	error.value = tableError()
	if (!error.value) await load(true)
}
async function load(fresh) {
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	attempted.value = false
	if (!fresh) detail.value = null
	try {
		const result = await getIpdBomMapping(editor.record?.name || editor.draft?.name, props.bomRow, fresh ? tables.value : null)
		if (sequence !== loadSequence) return
		detail.value = result
		tables.value = Object.fromEntries(sides.map(({ field }) => [field, result[field].map((row) => ({ ...row }))]))
		generatedTables.value = JSON.stringify(tables.value)
		const loaded = fresh ? { rows: freshGrid(result.combinations, result.columns), dropped: 0 } : gridFromValues(result.combinations, result.columns, result.values)
		rows.value = loaded.rows
		dropped.value = loaded.dropped
		header.value = {}
		headerQuantity.value = null
	} catch (reason) {
		if (sequence === loadSequence) error.value = reason?.message || "Unable to load this mapping."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}
async function save() {
	if (readOnly.value || loading.value || saving.value) return
	attempted.value = true
	error.value = tableError() || (tablesChanged.value ? "Get Combination after changing attributes." : output.value.error)
	if (error.value) {
		await nextTick()
		grid.value?.querySelector('input[aria-invalid="true"], [role="combobox"][aria-invalid="true"]')?.focus()
		return
	}
	saving.value = true
	try {
		await editor.saveBomMapping(props.bomRow, output.value.values, tables.value, detail.value.mapping_modified)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason?.message || "Unable to save this mapping."
	} finally {
		saving.value = false
	}
}
</script>

<style scoped>
.bom-mapping-body { display: grid; gap: var(--erp-space-3); min-width: 0; }
.bom-mapping-body > * { min-width: 0; }
.bom-mapping-facts { display: flex; flex-wrap: wrap; gap: var(--erp-space-1) var(--erp-space-4); margin: 0; }
.bom-mapping-facts div { display: flex; gap: 6px; align-items: baseline; }
.bom-mapping-facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.bom-mapping-facts dt::after { content: ":"; }
.bom-mapping-facts dd { margin: 0; font-size: var(--erp-font-size-body); font-weight: 600; }
.bom-mapping-sides { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-4); align-items: start; }
.bom-mapping-side { display: grid; gap: var(--erp-space-2); min-width: 0; }
.bom-mapping-side .ipd-subhead { min-height: 38px; font-size: var(--erp-font-size-table); }
.bom-mapping-empty { margin: 0; padding: 10px 12px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border); border-radius: var(--erp-control-radius); }
.bom-mapping-actions { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); }
.bom-mapping-compact th, .bom-mapping-compact td { padding: 3px 10px; height: 44px; }
.bom-mapping-compact { font-size: var(--erp-font-size-body); }
.bom-mapping-compact thead th { height: 38px; }
.bom-mapping-compact :deep(.p-inputnumber) { width: auto; }
.bom-mapping-attributes :deep(.p-select) { min-width: 180px; max-width: 100%; }
.bom-mapping-narrow { width: 1px; white-space: nowrap; }
.bom-mapping-center { text-align: center !important; }
.bom-mapping-index { width: 1px; text-align: right !important; font-weight: 500; }
.bom-mapping-scroll { overflow: auto; max-height: 55vh; }
.bom-mapping-grid { width: 100%; }
.bom-mapping-grid thead { position: sticky; top: 0; z-index: 1; }
.bom-mapping-grid th { color: var(--erp-text-secondary); font-size: var(--erp-font-size-label); text-transform: none; white-space: nowrap; }
.bom-mapping-grid td { white-space: nowrap; }
.bom-mapping-fill { display: flex; align-items: center; gap: 6px; }
.bom-mapping-fill > span { margin-right: 4px; }
.bom-mapping-fill :deep(.p-select) { min-width: 150px; }
.bom-mapping-grid td :deep(.p-select) { min-width: 170px; }
.bom-mapping-grid :deep(.p-inputnumber-input) { width: 120px; text-align: right; }
.bom-mapping-grid .is-excluded { background: var(--erp-surface-muted); }
.bom-mapping-problem { display: block; margin-top: 2px; color: var(--erp-danger); white-space: normal; }
.bom-mapping-included { color: var(--erp-danger); }
.bom-mapping-sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (max-width: 700px) { .bom-mapping-sides { grid-template-columns: minmax(0, 1fr); } }
</style>

