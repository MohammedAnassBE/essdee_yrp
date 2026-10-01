<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		maximizable
		:style="{ width: 'min(96vw, 1500px)' }"
		:header="record?.name ? `Cut Panel Movement · ${record.name}` : 'Create Cut Panel Movement'"
		class="erp-cpm-dialog erp-entity-dialog"
		@update:visible="emit('update:visible', $event)"
	>
		<div v-if="loading" class="erp-dialog-loading">
			<Skeleton v-for="index in 7" :key="index" height="3.25rem" />
		</div>
		<div v-else class="erp-dialog-stack">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Message v-if="success" severity="success" :closable="false">{{ success }}</Message>

			<section class="erp-context-strip">
				<div><span>Lot</span><strong>{{ editor.context?.lot || "—" }}</strong></div>
				<div><span>Item</span><strong>{{ editor.context?.item || "—" }}</strong></div>
				<div><span>From Location</span><strong>{{ editor.context?.source_supplier || "—" }}</strong></div>
				<div><span>Warehouse</span><strong>{{ editor.context?.source_warehouse || "—" }}</strong></div>
				<div><span>Status</span><strong><em class="erp-status" :class="statusClass">{{ status }}</em></strong></div>
			</section>

			<section class="erp-editor-section erp-bundle-section">
				<header class="erp-section-header">
					<div>
						<h3>Bundle and panel selection</h3>
						<p>Select a colour, panel column, complete bundle, or individual panel.</p>
					</div>
					<div class="erp-section-actions">
						<span class="erp-count">{{ exactRowCount }} bundles</span>
						<Button
							v-if="canEdit && !record"
							label="Generate Bundles"
							icon="pi pi-refresh"
							size="small"
							:loading="generating"
							@click="generateBundles"
						/>
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
							<label v-if="canEdit" class="erp-master-check">
								<input
									type="checkbox"
									:checked="groupSelected(group)"
									@change="toggleGroup(group, $event.target.checked)"
								/>
								<span>Select colour</span>
							</label>
							<div class="erp-matrix-identity">
								<span>Colour</span><strong>{{ group.colour }}</strong>
								<em v-if="group.part">{{ group.part }}</em>
							</div>
							<div class="erp-matrix-meta">
								<span>{{ group.rows.length }} bundles</span>
								<strong>{{ groupSelectedPanelCount(group) }} panels selected</strong>
							</div>
						</header>

						<div class="erp-matrix-scroll">
							<table class="erp-bundle-table">
								<thead>
									<tr>
										<th class="erp-select-column">Bundle</th>
										<th class="erp-index-column">S.No.</th>
										<th>Size</th>
										<th>Shade</th>
										<th>Lay No.</th>
										<th>Bundle No.</th>
										<th v-for="panel in panelsForGroup(group)" :key="panel" class="erp-panel-column">
											<label class="erp-column-check">
												<span>{{ panel }}</span>
												<input
													v-if="canEdit"
													type="checkbox"
													:checked="panelColumnSelected(group, panel)"
													@change="togglePanelColumn(group, panel, $event.target.checked)"
												/>
											</label>
										</th>
										<th class="erp-total-column">Selected</th>
									</tr>
								</thead>
								<tbody>
									<tr
										v-for="(row, rowIndex) in group.rows"
										:key="`${row.lay_no}-${row.bundle_no}-${row.size}-${rowIndex}`"
										:class="{ 'erp-row-selected': rowHasSelection(group, row) }"
									>
										<td class="erp-select-column">
											<label class="erp-row-check" :title="bundleSelected(group, row) ? 'Clear complete bundle' : 'Select complete bundle'">
												<input
													type="checkbox"
													:checked="bundleSelected(group, row)"
													:disabled="!canEdit || !availablePanels(group, row).length"
													@change="toggleBundle(group, row, $event.target.checked)"
												/>
												<span>{{ bundleSelected(group, row) ? "All" : "Select" }}</span>
											</label>
										</td>
										<td class="erp-index-column">{{ rowIndex + 1 }}</td>
										<td><strong class="erp-cell-value">{{ row.size || "—" }}</strong></td>
										<td>{{ row.shade || "—" }}</td>
										<td>{{ row.lay_no || "—" }}</td>
										<td><strong class="erp-bundle-number">{{ row.bundle_no || "—" }}</strong></td>
										<td v-for="panel in panelsForGroup(group)" :key="panel" class="erp-panel-cell">
											<label v-if="Number(row[panel] || 0) > 0" :class="['erp-panel-choice', { 'erp-panel-choice--selected': row[`${panel}_moved`] }]">
												<input
													v-model="row[`${panel}_moved`]"
													type="checkbox"
													:disabled="!canEdit"
													@change="syncBundle(group, row)"
												/>
												<strong>{{ number(row[panel]) }}</strong>
											</label>
											<span v-else class="erp-not-available">—</span>
										</td>
										<td class="erp-total-column">
											<strong>{{ rowSelectedPanelCount(group, row) }}</strong>
											<span>/ {{ availablePanels(group, row).length }}</span>
										</td>
									</tr>
								</tbody>
								<tfoot>
									<tr>
										<td colspan="6"><strong>Selected quantity</strong></td>
										<td v-for="panel in panelsForGroup(group)" :key="panel" class="erp-panel-total">{{ number(panelSelectedQuantity(group, panel)) }}</td>
										<td class="erp-total-column"><strong>{{ groupSelectedPanelCount(group) }}</strong></td>
									</tr>
								</tfoot>
							</table>
						</div>
					</article>
				</div>
				<div v-else class="erp-empty">
					<i class="pi pi-box"></i>
					<div>
						<strong>{{ generated ? "No bundles available" : "Bundles are not generated yet" }}</strong>
						<span>{{ generated ? "No exact bundles are available at this location." : "Click Generate Bundles to load the current cutting bundles." }}</span>
					</div>
				</div>
			</section>

			<section v-if="movementData.collapsed_details?.length" class="erp-editor-section">
				<header class="erp-section-header">
					<div><h3>Collapsed bundles</h3><p>Select a row to move its full balance, then adjust the quantity if required.</p></div>
					<span class="erp-count">{{ movementData.collapsed_details.length }} rows</span>
				</header>
				<div class="erp-table-scroll">
					<table class="erp-table">
						<thead><tr><th class="erp-select-column">Move</th><th>S.No.</th><th>Size</th><th>Colour</th><th>Panel</th><th>Lay No.</th><th>Bundle No.</th><th>Available</th><th>Move Qty</th></tr></thead>
						<tbody>
							<tr v-for="(row, index) in movementData.collapsed_details" :key="index" :class="{ 'erp-row-selected': row.moved }">
								<td class="erp-select-column"><input v-model="row.moved" type="checkbox" :disabled="!canEdit" @change="toggleCollapsed(row)" /></td>
								<td>{{ index + 1 }}</td><td>{{ row.size || "—" }}</td><td>{{ row.colour || "—" }}</td><td>{{ row.panel || "—" }}</td><td>{{ row.lay_no || "—" }}</td><td>{{ row.bundle_no || "—" }}</td>
								<td class="erp-number">{{ number(row.quantity, 3) }}</td>
								<td><InputNumber v-model="row.move_qty" :min="0" :max="Number(row.quantity || 0)" :disabled="!canEdit || !row.moved" :max-fraction-digits="3" fluid /></td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>

			<section v-if="movementData.accessory_data?.length" class="erp-editor-section">
				<header class="erp-section-header">
					<div><h3>Accessory fabric</h3><p>Enter only the weight moving with these cut panels.</p></div>
					<span class="erp-count">{{ movementData.accessory_data.length }} rows</span>
				</header>
				<div class="erp-table-scroll">
					<table class="erp-table">
						<thead><tr><th>S.No.</th><th>Cloth</th><th>Cloth Type</th><th>Colour</th><th>Shade</th><th>Dia</th><th>Available Weight</th><th>Move Weight</th></tr></thead>
						<tbody>
							<tr v-for="(row, index) in movementData.accessory_data" :key="index" :class="{ 'erp-row-selected': Number(row.moved_weight || 0) > 0 }">
								<td>{{ index + 1 }}</td><td>{{ row.cloth_name || "—" }}</td><td>{{ row.cloth_type || "—" }}</td><td>{{ row.colour || "—" }}</td><td>{{ row.shade || "—" }}</td><td>{{ row.dia || "—" }}</td>
								<td class="erp-number">{{ number(row.weight, 3) }} kg</td>
								<td><InputNumber v-model="row.moved_weight" :min="0" :max="Number(row.weight || 0)" :disabled="!canEdit" :max-fraction-digits="3" suffix=" kg" fluid /></td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
		</div>

		<template #footer>
			<div class="erp-dialog-footer">
				<div class="erp-footer-summary" :class="{ 'erp-footer-summary--active': hasSelection }">
					<i :class="hasSelection ? 'pi pi-check-circle' : 'pi pi-info-circle'"></i>
					<span>{{ hasSelection ? selectionSummaryText : "Select at least one bundle, panel, collapsed quantity, or accessory weight." }}</span>
				</div>
				<div class="erp-footer-actions">
					<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
					<DocumentPrintButton v-if="record?.permissions?.can_print" doctype="SD YRP Cut Panel Movement" :name="record.name" :formats="record.print_formats || []" :disabled="saving" />
					<Button v-if="record?.permissions?.can_cancel" label="Cancel Movement" icon="pi pi-ban" severity="danger" outlined :loading="saving && saveMode === 'cancel'" @click="cancelMovement" />
					<Button v-if="canEdit" label="Save Draft" icon="pi pi-save" severity="secondary" outlined :disabled="!generated" :loading="saving && saveMode === 'draft'" @click="save(false)" />
					<Button v-if="canSubmit" label="Save & Submit" icon="pi pi-check" :disabled="!hasSelection" :loading="saving && saveMode === 'submit'" @click="save(true)" />
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { changeMovementStatus, generateMovementBundles, getMovementEditor, saveMovement } from "./cpmApi.js"
import DocumentPrintButton from "./DocumentPrintButton.vue"

const props = defineProps({
	visible: Boolean,
	cuttingPlan: { type: String, required: true },
	movement: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "changed"])

const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const hasGenerated = ref(false)
const saveMode = ref("")
const error = ref("")
const success = ref("")
const editor = reactive({ context: {}, defaults: {}, permissions: {}, record: null })
const movementData = reactive(emptyMovement())

const record = computed(() => editor.record)
const canEdit = computed(() => record.value ? Boolean(record.value.permissions?.can_write) : Boolean(editor.permissions?.can_create))
const canSubmit = computed(() => canEdit.value && Boolean(record.value ? record.value.permissions?.can_submit : editor.permissions?.can_submit))
const status = computed(() => record.value?.status || "Draft")
const statusClass = computed(() => `erp-status--${status.value.toLowerCase()}`)
const exactGroups = computed(() => Object.entries(movementData.data || {}).map(([colour, detail]) => ({ colour, part: detail.part, rows: detail.data || [] })).filter((group) => group.rows.length))
const exactRowCount = computed(() => exactGroups.value.reduce((total, group) => total + group.rows.length, 0))
const generated = computed(() => hasGenerated.value)
const selectedExactCount = computed(() => exactGroups.value.reduce((total, group) => total + group.rows.filter((row) => rowHasSelection(group, row)).length, 0))
const selectedPanelCount = computed(() => exactGroups.value.reduce((total, group) => total + groupSelectedPanelCount(group), 0))
const selectedCollapsedQuantity = computed(() => (movementData.collapsed_details || []).reduce((total, row) => total + (row.moved ? Number(row.move_qty || 0) : 0), 0))
const selectedAccessoryWeight = computed(() => (movementData.accessory_data || []).reduce((total, row) => total + Number(row.moved_weight || 0), 0))
const hasSelection = computed(() => selectedPanelCount.value > 0 || selectedCollapsedQuantity.value > 0 || selectedAccessoryWeight.value > 0)
const selectionSummaryText = computed(() => {
	const parts = []
	if (selectedExactCount.value) parts.push(`${selectedExactCount.value} bundles / ${selectedPanelCount.value} panels`)
	if (selectedCollapsedQuantity.value) parts.push(`${number(selectedCollapsedQuantity.value, 3)} collapsed qty`)
	if (selectedAccessoryWeight.value) parts.push(`${number(selectedAccessoryWeight.value, 3)} kg accessory`)
	return parts.join(" · ")
})

watch(() => [props.visible, props.movement, props.cuttingPlan], ([visible]) => { if (visible) load() })

async function load() {
	loading.value = true
	error.value = ""
	success.value = ""
	hasGenerated.value = false
	try {
		const data = await getMovementEditor(props.cuttingPlan, props.movement)
		Object.assign(editor, data || {})
		replaceMovement(data?.movement_data || data?.record?.movement_data || {})
		hasGenerated.value = Boolean(data?.record)
	} catch (reason) {
		error.value = reason.message || "Unable to load the Cut Panel Movement."
	} finally {
		loading.value = false
	}
}

function panelsForGroup(group) {
	const panels = movementData.panels || []
	return Array.isArray(panels) ? panels : panels[group.part] || []
}

function availablePanels(group, row) {
	return panelsForGroup(group).filter((panel) => Number(row[panel] || 0) > 0)
}

function rowSelectedPanelCount(group, row) {
	return availablePanels(group, row).filter((panel) => Boolean(row[`${panel}_moved`])).length
}

function rowHasSelection(group, row) {
	return rowSelectedPanelCount(group, row) > 0
}

function bundleSelected(group, row) {
	const panels = availablePanels(group, row)
	return Boolean(panels.length && panels.every((panel) => Boolean(row[`${panel}_moved`])))
}

function groupSelected(group) {
	const selectable = group.rows.filter((row) => availablePanels(group, row).length)
	return Boolean(selectable.length && selectable.every((row) => bundleSelected(group, row)))
}

function panelColumnSelected(group, panel) {
	const rows = group.rows.filter((row) => Number(row[panel] || 0) > 0)
	return Boolean(rows.length && rows.every((row) => Boolean(row[`${panel}_moved`])))
}

function groupSelectedPanelCount(group) {
	return group.rows.reduce((total, row) => total + rowSelectedPanelCount(group, row), 0)
}

function panelSelectedQuantity(group, panel) {
	return group.rows.reduce((total, row) => total + (row[`${panel}_moved`] ? Number(row[panel] || 0) : 0), 0)
}

function toggleBundle(group, row, selected) {
	for (const panel of availablePanels(group, row)) row[`${panel}_moved`] = selected
	row.bundle_moved = selected
}

function toggleGroup(group, selected) {
	for (const row of group.rows) toggleBundle(group, row, selected)
}

function togglePanelColumn(group, panel, selected) {
	for (const row of group.rows) {
		if (Number(row[panel] || 0) > 0) row[`${panel}_moved`] = selected
		syncBundle(group, row)
	}
}

function syncBundle(group, row) {
	row.bundle_moved = bundleSelected(group, row)
}

function toggleCollapsed(row) {
	row.move_qty = row.moved ? Number(row.quantity || 0) : 0
}

async function generateBundles() {
	generating.value = true
	error.value = ""
	try {
		const data = await generateMovementBundles(props.cuttingPlan, editor.defaults?.posting_date, editor.defaults?.posting_time)
		replaceMovement(data || {})
		hasGenerated.value = true
	} catch (reason) {
		error.value = reason.message || "Unable to generate the available bundles."
	} finally {
		generating.value = false
	}
}

async function save(submit) {
	error.value = ""
	success.value = ""
	if (submit && !hasSelection.value) {
		error.value = "Select at least one bundle, panel, collapsed quantity, or accessory weight."
		return
	}
	saving.value = true
	saveMode.value = submit ? "submit" : "draft"
	try {
		const saved = await saveMovement(
			props.cuttingPlan,
			{ ...editor.defaults, movement_data: clone(movementData) },
			record.value?.name,
			submit,
			record.value?.modified,
		)
		editor.record = saved
		replaceMovement(saved.movement_data || {})
		success.value = submit ? "Cut Panel Movement submitted." : "Draft movement saved."
		emit("changed", saved)
		if (submit) emit("update:visible", false)
	} catch (reason) {
		error.value = reason.message || "Unable to save the Cut Panel Movement."
	} finally {
		saving.value = false
		saveMode.value = ""
	}
}

async function cancelMovement() {
	if (!window.confirm(`Cancel Cut Panel Movement ${record.value?.name}?`)) return
	saving.value = true
	saveMode.value = "cancel"
	error.value = ""
	try {
		const changed = await changeMovementStatus(props.cuttingPlan, record.value.name, "cancel")
		editor.record = changed
		emit("changed", changed)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason.message || "Unable to cancel the Cut Panel Movement."
	} finally {
		saving.value = false
		saveMode.value = ""
	}
}

function replaceMovement(value) {
	Object.assign(movementData, emptyMovement(), clone(value))
}

function emptyMovement() {
	return { panels: [], data: {}, accessory_data: [], collapsed_details: [], is_set_item: 0 }
}

function clone(value) { return JSON.parse(JSON.stringify(value || {})) }
function number(value, precision = 0) { return Number(value || 0).toFixed(precision) }
</script>

<style scoped>
.erp-dialog-stack,.erp-dialog-loading{display:grid;gap:14px}.erp-context-strip{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface-soft)}.erp-context-strip>div{display:grid;gap:4px;padding:11px 13px;border-right:1px solid var(--erp-border)}.erp-context-strip>div:last-child{border-right:0}.erp-context-strip span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-context-strip strong{overflow:hidden;color:var(--erp-text);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.erp-status{display:inline-flex;width:max-content;padding:3px 8px;border-radius:var(--erp-pill-radius);background:#eef2f0;color:#526159;font-size:var(--erp-font-size-min);font-style:normal;text-transform:uppercase}.erp-status--submitted{background:#e1f6eb;color:#087744}.erp-status--cancelled{background:#fde8e8;color:#b42318}.erp-editor-section{overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.erp-section-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.erp-section-header h3{margin:0;color:var(--erp-text);font-size:.92rem}.erp-section-header p{margin:2px 0 0;color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-section-actions{display:flex;align-items:center;gap:8px}.erp-count{padding:4px 8px;border-radius:var(--erp-pill-radius);background:var(--erp-accent-soft);color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:700}.erp-selection-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.erp-selection-summary>div{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 13px;border-right:1px solid var(--erp-border)}.erp-selection-summary>div:last-child{border-right:0}.erp-selection-summary span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-selection-summary strong{color:var(--erp-accent-hover);font-size:var(--erp-font-size-caption);font-variant-numeric:tabular-nums}.erp-bundle-matrices{display:grid;gap:12px;padding:12px;background:var(--erp-surface-soft)}.erp-bundle-matrix{overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface);box-shadow:none}.erp-matrix-heading{display:flex;align-items:center;gap:16px;min-height:48px;padding:8px 12px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-muted)}.erp-master-check,.erp-row-check,.erp-column-check,.erp-panel-choice{cursor:pointer}.erp-master-check{display:flex;align-items:center;gap:7px;padding-right:14px;border-right:1px solid var(--erp-border);color:#3e5348;font-size:var(--erp-font-size-min);font-weight:700}.erp-matrix-identity{display:flex;align-items:baseline;gap:7px;min-width:0}.erp-matrix-identity>span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-transform:uppercase}.erp-matrix-identity strong{color:var(--erp-text);font-size:.88rem}.erp-matrix-identity em{padding:2px 6px;border-radius:var(--erp-pill-radius);background:var(--erp-accent-soft);color:#2e6347;font-size:var(--erp-font-size-min);font-style:normal}.erp-matrix-meta{display:flex;align-items:center;gap:12px;margin-left:auto;font-size:var(--erp-font-size-min)}.erp-matrix-meta span{color:var(--erp-text-muted)}.erp-matrix-meta strong{color:var(--erp-accent-hover)}.erp-matrix-scroll{overflow:auto;max-height:360px}.erp-bundle-table{width:100%;min-width:760px;border-collapse:separate;border-spacing:0;color:#34483e;font-size:var(--erp-font-size-caption)}.erp-bundle-table th{position:sticky;top:0;z-index:2;padding:8px 9px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft);color:#526159;font-size:var(--erp-font-size-min);letter-spacing:.025em;text-align:left;text-transform:uppercase;white-space:nowrap}.erp-bundle-table td{height:42px;padding:6px 9px;border-bottom:1px solid #edf1ef;background:var(--erp-surface);white-space:nowrap}.erp-bundle-table tbody tr:last-child td{border-bottom:0}.erp-bundle-table tbody tr:hover td{background:#fbfdfc}.erp-bundle-table tbody tr.erp-row-selected td{background:#f5fbf8}.erp-bundle-table tfoot td{position:sticky;bottom:0;z-index:1;height:36px;border-top:1px solid var(--erp-border);border-bottom:0;background:var(--erp-surface-muted);color:#315342;font-size:var(--erp-font-size-min)}.erp-select-column{width:82px}.erp-index-column{width:54px;color:#748179}.erp-row-check{display:inline-flex;align-items:center;gap:6px;color:#6f7d75;font-size:var(--erp-font-size-min)}.erp-row-check:has(input:checked){color:var(--erp-accent);font-weight:700}.erp-cell-value,.erp-bundle-number{color:#253d31}.erp-bundle-number{font-variant-numeric:tabular-nums}.erp-panel-column{min-width:98px;text-align:center!important}.erp-column-check{display:flex;align-items:center;justify-content:center;gap:6px}.erp-panel-cell{text-align:center}.erp-panel-choice{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-width:62px;padding:5px 7px;border:1px solid var(--erp-border);border-radius:6px;background:var(--erp-surface-soft);color:#596860}.erp-panel-choice--selected{border-color:#a8d8bf;background:#eaf7f0;color:var(--erp-accent)}.erp-panel-choice strong{font-size:var(--erp-font-size-caption);font-variant-numeric:tabular-nums}.erp-not-available{color:#b1bbb5}.erp-total-column{width:78px;text-align:center!important}.erp-total-column strong{color:var(--erp-accent)}.erp-total-column span{color:#829087;font-size:var(--erp-font-size-min)}.erp-panel-total{text-align:center;font-weight:700;font-variant-numeric:tabular-nums}.erp-table-scroll{overflow:auto;max-height:320px}.erp-table{width:100%;min-width:760px;border-collapse:collapse;font-size:var(--erp-font-size-caption)}.erp-table th{position:sticky;top:0;z-index:1;padding:8px 10px;background:var(--erp-surface-muted);color:#506057;font-size:var(--erp-font-size-min);text-align:left;text-transform:uppercase;white-space:nowrap}.erp-table td{padding:7px 10px;border-top:1px solid #e5ece8;color:#33483d;white-space:nowrap}.erp-table tr.erp-row-selected td{background:#f5fbf8}.erp-table :deep(.p-inputnumber){min-width:105px}.erp-table :deep(.p-inputnumber-input){padding:.45rem .55rem;font-size:var(--erp-font-size-caption)}.erp-number{text-align:right;font-variant-numeric:tabular-nums}.erp-empty{display:flex;align-items:center;justify-content:center;gap:10px;min-height:150px;padding:28px;color:var(--erp-text-muted)}.erp-empty>i{display:grid;place-items:center;width:38px;height:38px;border-radius:var(--erp-control-radius);background:var(--erp-accent-soft);color:var(--erp-accent);font-size:1rem}.erp-empty>div{display:grid;gap:3px}.erp-empty strong{color:var(--erp-text);font-size:13px}.erp-empty span{font-size:var(--erp-font-size-caption)}.erp-dialog-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%}.erp-footer-summary{display:flex;align-items:center;gap:7px;color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-footer-summary--active{color:var(--erp-accent)}.erp-footer-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}input[type="checkbox"]{width:14px;height:14px;margin:0;accent-color:var(--erp-accent)}@media(max-width:950px){.erp-context-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.erp-selection-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.erp-dialog-footer{align-items:flex-end;flex-direction:column}.erp-footer-actions{flex-wrap:wrap}.erp-matrix-heading{align-items:flex-start;flex-wrap:wrap}.erp-matrix-meta{width:100%;margin-left:0}}
</style>
