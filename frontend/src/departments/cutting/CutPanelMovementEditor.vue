<template>
	<div class="cut-panel-movement-editor">
		<section class="erp-editor-section erp-bundle-section">
			<header class="erp-section-header">
				<div>
					<h3>Bundle and panel selection</h3>
					<p>Select a colour, panel column, complete bundle, or individual panel.</p>
				</div>
				<div class="erp-section-actions">
					<span class="erp-count">{{ exactRowCount }} bundles</span>
					<Button v-if="editable && showGenerate" label="Generate Bundles" icon="pi pi-refresh" size="small" :loading="generating" @click="emit('generate')" />
				</div>
			</header>

			<div v-if="generated" class="erp-selection-summary">
				<div><span>Selected bundles</span><strong>{{ selectedExactCount }} / {{ exactRowCount }}</strong></div>
				<div><span>Selected panels</span><strong>{{ selectedPanelCount }}</strong></div>
				<div><span>Collapsed quantity</span><strong>{{ number(selectedCollapsedQuantity, 3) }}</strong></div>
				<div><span>Accessory weight</span><strong>{{ number(selectedAccessoryWeight, 3) }} kg</strong></div>
			</div>

			<div v-if="exactGroups.length" class="erp-bundle-matrices">
				<article v-for="group in exactGroups" :key="group.colour" class="erp-bundle-matrix">
					<header class="erp-matrix-heading">
						<label v-if="editable" class="erp-master-check erp-check-target">
							<input type="checkbox" :checked="groupSelected(group)" :aria-label="`Select all ${group.colour || 'colour'} bundles`" @change="toggleGroup(group, $event.target.checked)" />
							<span>Select colour</span>
						</label>
						<div class="erp-matrix-identity"><span>Colour</span><strong>{{ group.colour }}</strong><em v-if="group.part">{{ group.part }}</em></div>
						<div class="erp-matrix-meta"><span>{{ group.rows.length }} bundles</span><strong>{{ groupSelectedPanelCount(group) }} panels selected</strong></div>
					</header>

					<div class="erp-matrix-scroll" role="region" tabindex="0" :aria-label="`Cut bundle selection for ${group.colour || 'this colour'}`">
						<table class="erp-bundle-table">
							<thead><tr>
								<th class="erp-select-column">Bundle</th><th class="erp-index-column">S.No.</th><th>Size</th><th>Shade</th><th>Lay No.</th><th>Bundle No.</th>
								<th v-for="panel in panelsForGroup(group)" :key="panel" class="erp-panel-column">
									<label class="erp-column-check erp-check-target"><span>{{ panel }}</span><input v-if="editable" type="checkbox" :checked="panelColumnSelected(group, panel)" :aria-label="`Select ${panel} panels for ${group.colour || 'this colour'}`" @change="togglePanelColumn(group, panel, $event.target.checked)" /></label>
								</th>
								<th class="erp-total-column">Selected</th>
							</tr></thead>
							<tbody>
								<tr v-for="(row, rowIndex) in group.rows" :key="`${row.lay_no}-${row.bundle_no}-${row.size}-${rowIndex}`" :class="{ 'erp-row-selected': rowHasSelection(group, row) }">
									<td class="erp-select-column"><label class="erp-row-check erp-check-target"><input type="checkbox" :checked="bundleSelected(group, row)" :disabled="!editable || !availablePanels(group, row).length" :aria-label="`Select bundle ${row.bundle_no || rowIndex + 1}`" @change="toggleBundle(group, row, $event.target.checked)" /><span>{{ bundleSelected(group, row) ? "All" : "Select" }}</span></label></td>
									<td class="erp-index-column">{{ rowIndex + 1 }}</td><td><strong class="erp-cell-value">{{ row.size || "—" }}</strong></td><td>{{ row.shade || "—" }}</td><td>{{ row.lay_no || "—" }}</td><td><strong class="erp-bundle-number">{{ row.bundle_no || "—" }}</strong></td>
									<td v-for="panel in panelsForGroup(group)" :key="panel" class="erp-panel-cell">
										<label v-if="Number(row[panel] || 0) > 0" :class="['erp-panel-choice', 'erp-check-target', { 'erp-panel-choice--selected': row[`${panel}_moved`] }]">
											<input v-model="row[`${panel}_moved`]" type="checkbox" :disabled="!editable" :aria-label="`Move ${panel} from bundle ${row.bundle_no || rowIndex + 1}`" @change="syncBundle(group, row)" /><strong>{{ number(row[panel]) }}</strong>
										</label><span v-else class="erp-not-available">—</span>
									</td>
									<td class="erp-total-column"><strong>{{ rowSelectedPanelCount(group, row) }}</strong><span>/ {{ availablePanels(group, row).length }}</span></td>
								</tr>
							</tbody>
							<tfoot><tr><td colspan="6"><strong>Selected quantity</strong></td><td v-for="panel in panelsForGroup(group)" :key="panel" class="erp-panel-total">{{ number(panelSelectedQuantity(group, panel)) }}</td><td class="erp-total-column"><strong>{{ groupSelectedPanelCount(group) }}</strong></td></tr></tfoot>
						</table>
					</div>
				</article>
			</div>
			<div v-else class="erp-empty"><i class="pi pi-box" /><div><strong>{{ generated ? "No bundles available" : "Bundles are not generated yet" }}</strong><span>{{ generated ? "No exact bundles are available at this location." : "Click Generate Bundles to load the current cut-panel stock." }}</span></div></div>
		</section>

		<section v-if="movementData.collapsed_details?.length" class="erp-editor-section">
			<header class="erp-section-header"><div><h3>Collapsed bundles</h3><p>Select a row, then enter the quantity to move.</p></div><span class="erp-count">{{ movementData.collapsed_details.length }} rows</span></header>
			<div class="erp-table-scroll" role="region" tabindex="0" aria-label="Collapsed bundle quantities">
				<table class="erp-table"><thead><tr><th class="erp-select-column">Move</th><th>S.No.</th><th>Size</th><th>Colour</th><th>Panel</th><th>Lay No.</th><th>Bundle No.</th><th>Available</th><th>Move Qty</th></tr></thead><tbody>
					<tr v-for="(row, index) in movementData.collapsed_details" :key="index" :class="{ 'erp-row-selected': row.moved }">
						<td class="erp-select-column"><label class="erp-check-target"><input v-model="row.moved" type="checkbox" :disabled="!editable" :aria-label="`Move collapsed bundle ${row.bundle_no || index + 1}`" @change="toggleCollapsed(row)" /></label></td>
						<td>{{ index + 1 }}</td><td>{{ row.size || "—" }}</td><td>{{ row.colour || "—" }}</td><td>{{ row.panel || "—" }}</td><td>{{ row.lay_no || "—" }}</td><td>{{ row.bundle_no || "—" }}</td><td class="erp-number">{{ number(row.quantity, 3) }}</td>
						<td><InputNumber v-model="row.move_qty" :aria-label="`Move quantity for collapsed bundle ${row.bundle_no || index + 1}`" :min="0" :max="Number(row.quantity || 0)" :disabled="!editable || !row.moved" :max-fraction-digits="3" fluid @update:model-value="commit" /></td>
					</tr>
				</tbody></table>
			</div>
		</section>

		<section v-if="movementData.accessory_data?.length" class="erp-editor-section">
			<header class="erp-section-header"><div><h3>Accessory fabric</h3><p>Enter only the weight moving with these cut panels.</p></div><span class="erp-count">{{ movementData.accessory_data.length }} rows</span></header>
			<div class="erp-table-scroll" role="region" tabindex="0" aria-label="Accessory fabric quantities">
				<table class="erp-table"><thead><tr><th>S.No.</th><th>Cloth</th><th>Cloth Type</th><th>Colour</th><th>Shade</th><th>Dia</th><th>Available Weight</th><th>Move Weight</th></tr></thead><tbody>
					<tr v-for="(row, index) in movementData.accessory_data" :key="index" :class="{ 'erp-row-selected': Number(row.moved_weight || 0) > 0 }">
						<td>{{ index + 1 }}</td><td>{{ row.cloth_name || "—" }}</td><td>{{ row.cloth_type || "—" }}</td><td>{{ row.colour || "—" }}</td><td>{{ row.shade || "—" }}</td><td>{{ row.dia || "—" }}</td><td class="erp-number">{{ number(row.weight, 3) }} kg</td>
						<td><InputNumber v-model="row.moved_weight" :aria-label="`Move weight for ${row.cloth_name || `accessory row ${index + 1}`}`" :min="0" :max="Number(row.weight || 0)" :disabled="!editable" :max-fraction-digits="3" suffix=" kg" fluid @update:model-value="commit" /></td>
					</tr>
				</tbody></table>
			</div>
		</section>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import { computed } from "vue"

const props = defineProps({
	modelValue: { type: Object, default: () => ({}) },
	context: { type: Object, default: () => ({}) },
	record: { type: Object, default: null },
	editable: { type: Boolean, default: false },
	generated: { type: Boolean, default: false },
	showGenerate: { type: Boolean, default: false },
	generating: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "generate"])
const movementData = computed(() => props.modelValue || {})
const exactGroups = computed(() => Object.entries(movementData.value.data || {}).map(([colour, detail]) => ({ colour, part: detail.part, rows: detail.data || [] })).filter((group) => group.rows.length))
const exactRowCount = computed(() => exactGroups.value.reduce((total, group) => total + group.rows.length, 0))
const selectedExactCount = computed(() => exactGroups.value.reduce((total, group) => total + group.rows.filter((row) => rowHasSelection(group, row)).length, 0))
const selectedPanelCount = computed(() => exactGroups.value.reduce((total, group) => total + groupSelectedPanelCount(group), 0))
const selectedCollapsedQuantity = computed(() => (movementData.value.collapsed_details || []).reduce((total, row) => total + (row.moved ? Number(row.move_qty || 0) : 0), 0))
const selectedAccessoryWeight = computed(() => (movementData.value.accessory_data || []).reduce((total, row) => total + Number(row.moved_weight || 0), 0))
const hasSelection = computed(() => selectedPanelCount.value > 0 || selectedCollapsedQuantity.value > 0 || selectedAccessoryWeight.value > 0)
const selectionSummaryText = computed(() => [
	selectedExactCount.value ? `${selectedExactCount.value} bundles / ${selectedPanelCount.value} panels` : "",
	selectedCollapsedQuantity.value ? `${number(selectedCollapsedQuantity.value, 3)} collapsed qty` : "",
	selectedAccessoryWeight.value ? `${number(selectedAccessoryWeight.value, 3)} kg accessory` : "",
].filter(Boolean).join(" · "))

function panelsForGroup(group) { const panels = movementData.value.panels || []; return Array.isArray(panels) ? panels : panels[group.part] || [] }
function availablePanels(group, row) { return panelsForGroup(group).filter((panel) => Number(row[panel] || 0) > 0) }
function rowSelectedPanelCount(group, row) { return availablePanels(group, row).filter((panel) => Boolean(row[`${panel}_moved`])).length }
function rowHasSelection(group, row) { return rowSelectedPanelCount(group, row) > 0 }
function bundleSelected(group, row) { const panels = availablePanels(group, row); return Boolean(panels.length && panels.every((panel) => Boolean(row[`${panel}_moved`]))) }
function groupSelected(group) { const rows = group.rows.filter((row) => availablePanels(group, row).length); return Boolean(rows.length && rows.every((row) => bundleSelected(group, row))) }
function panelColumnSelected(group, panel) { const rows = group.rows.filter((row) => Number(row[panel] || 0) > 0); return Boolean(rows.length && rows.every((row) => Boolean(row[`${panel}_moved`]))) }
function groupSelectedPanelCount(group) { return group.rows.reduce((total, row) => total + rowSelectedPanelCount(group, row), 0) }
function panelSelectedQuantity(group, panel) { return group.rows.reduce((total, row) => total + (row[`${panel}_moved`] ? Number(row[panel] || 0) : 0), 0) }
function toggleBundle(group, row, selected) { for (const panel of availablePanels(group, row)) row[`${panel}_moved`] = selected; row.bundle_moved = selected; commit() }
function toggleGroup(group, selected) { for (const row of group.rows) { for (const panel of availablePanels(group, row)) row[`${panel}_moved`] = selected; row.bundle_moved = selected } commit() }
function togglePanelColumn(group, panel, selected) { for (const row of group.rows) { if (Number(row[panel] || 0) > 0) row[`${panel}_moved`] = selected; row.bundle_moved = bundleSelected(group, row) } commit() }
function syncBundle(group, row) { row.bundle_moved = bundleSelected(group, row); commit() }
function toggleCollapsed(row) { row.move_qty = row.moved ? Number(row.quantity || 0) : 0; commit() }
function commit() { emit("update:modelValue", JSON.parse(JSON.stringify(movementData.value || {}))) }
function number(value, precision = 0) { return Number(value || 0).toFixed(precision) }

defineExpose({ hasSelection, selectionSummaryText })
</script>

<style scoped>
.cut-panel-movement-editor{display:grid;gap:14px}.erp-editor-section{overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.erp-section-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.erp-section-header h3{margin:0;color:var(--erp-text);font-size:.92rem}.erp-section-header p{margin:2px 0 0;color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-section-actions{display:flex;align-items:center;gap:8px}.erp-count{padding:4px 8px;border-radius:var(--erp-pill-radius);background:var(--erp-accent-soft);color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:700}.erp-selection-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.erp-selection-summary>div{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 13px;border-right:1px solid var(--erp-border)}.erp-selection-summary>div:last-child{border-right:0}.erp-selection-summary span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-selection-summary strong{color:var(--erp-accent-hover);font-size:var(--erp-font-size-caption);font-variant-numeric:tabular-nums}.erp-bundle-matrices{display:grid;gap:12px;padding:12px;background:var(--erp-surface-soft)}.erp-bundle-matrix{overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface)}.erp-matrix-heading{display:flex;align-items:center;gap:16px;min-height:48px;padding:8px 12px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-muted)}.erp-master-check,.erp-row-check,.erp-column-check,.erp-panel-choice{cursor:pointer}.erp-check-target{display:inline-grid;min-width:44px;min-height:44px;place-items:center}.erp-master-check{display:flex;align-items:center;gap:7px;padding-right:14px;border-right:1px solid var(--erp-border);color:#3e5348;font-size:var(--erp-font-size-min);font-weight:700}.erp-matrix-identity{display:flex;align-items:baseline;gap:7px;min-width:0}.erp-matrix-identity>span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-transform:uppercase}.erp-matrix-identity strong{color:var(--erp-text);font-size:.88rem}.erp-matrix-identity em{padding:2px 6px;border-radius:var(--erp-pill-radius);background:var(--erp-accent-soft);color:#2e6347;font-size:var(--erp-font-size-min);font-style:normal}.erp-matrix-meta{display:flex;align-items:center;gap:12px;margin-left:auto;font-size:var(--erp-font-size-min)}.erp-matrix-meta span{color:var(--erp-text-muted)}.erp-matrix-meta strong{color:var(--erp-accent-hover)}.erp-matrix-scroll,.erp-table-scroll{overflow-x:auto;overflow-y:visible}.erp-matrix-scroll:focus-visible,.erp-table-scroll:focus-visible{outline:2px solid var(--erp-accent-dark);outline-offset:-2px}.erp-bundle-table,.erp-table{width:100%;min-width:760px;border-collapse:collapse;color:#34483e;font-size:var(--erp-font-size-caption)}.erp-bundle-table th,.erp-table th{position:sticky;top:0;z-index:2;padding:8px 9px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft);color:#526159;font-size:var(--erp-font-size-min);text-align:left;text-transform:uppercase;white-space:nowrap}.erp-bundle-table td,.erp-table td{height:44px;padding:4px 9px;border-bottom:1px solid #edf1ef;background:var(--erp-surface);white-space:nowrap}.erp-row-selected td{background:#f5fbf8}.erp-bundle-table tfoot td{position:sticky;bottom:0;background:var(--erp-surface-muted)}.erp-select-column{width:82px}.erp-index-column{width:54px;color:#748179}.erp-row-check{display:inline-flex;align-items:center;gap:6px}.erp-cell-value,.erp-bundle-number{color:#253d31}.erp-panel-column,.erp-panel-cell,.erp-total-column,.erp-panel-total{text-align:center!important}.erp-panel-choice{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-width:62px;padding:4px 7px;border:1px solid var(--erp-border);border-radius:6px;background:var(--erp-surface-soft)}.erp-panel-choice--selected{border-color:#a8d8bf;background:#eaf7f0;color:var(--erp-accent)}.erp-not-available{color:#b1bbb5}.erp-number{text-align:right;font-variant-numeric:tabular-nums}.erp-empty{display:flex;align-items:center;justify-content:center;gap:10px;min-height:150px;padding:28px;color:var(--erp-text-muted)}.erp-empty>i{display:grid;width:38px;height:38px;border-radius:var(--erp-control-radius);background:var(--erp-accent-soft);color:var(--erp-accent);place-items:center}.erp-empty>div{display:grid;gap:3px}.erp-empty strong{color:var(--erp-text);font-size:13px}.erp-empty span{font-size:var(--erp-font-size-caption)}input[type="checkbox"]{width:18px;height:18px;margin:0;accent-color:var(--erp-accent)}
@media(max-width:950px){.erp-selection-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.erp-matrix-heading{align-items:flex-start;flex-wrap:wrap}.erp-matrix-meta{width:100%;margin-left:0}}
</style>
