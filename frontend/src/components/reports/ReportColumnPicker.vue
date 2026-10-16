<template>
	<Dialog
		:visible="visible"
		modal
		header="Pick report columns"
		class="erp-dialog--lg report-column-dialog"
		@update:visible="$emit('update:visible', $event)"
	>
		<Message v-if="errorMessage" severity="error" :closable="false">{{ errorMessage }}</Message>
		<div class="report-column-editor">
			<section class="report-column-picker" aria-labelledby="report-column-picker-title">
				<header><div><strong id="report-column-picker-title">Available columns</strong><small>Report fields and linked document details</small></div><span>{{ selectedColumns.length }} selected</span></header>
				<label class="report-column-search"><i class="pi pi-search" /><InputText v-model="baseSearch" placeholder="Find a report column…" fluid /></label>
				<div class="report-column-picker__list">
					<section class="report-column-group">
						<h3>Report columns</h3>
						<label v-for="column in filteredBaseColumns" :key="column.key" class="report-column-option">
							<Checkbox :model-value="column.visible" binary @update:model-value="setVisible(column.key, $event)" />
							<span><strong>{{ column.label }}</strong><small>{{ column.fieldname }}</small></span>
						</label>
					</section>
					<details v-for="(source, sourceName) in linkSources" :key="sourceName" class="report-column-group" @toggle="openSource(sourceName, $event)">
						<summary><span>{{ linkSourceLabel(source) }}</span><i class="pi pi-chevron-down" /></summary>
						<label class="report-column-search"><i class="pi pi-search" /><InputText v-model="sourceSearch[sourceName]" placeholder="Find a linked field…" fluid /></label>
						<div v-if="loadingSources.has(sourceName)" class="report-column-loading"><i class="pi pi-spin pi-spinner" />Loading fields…</div>
						<label v-for="field in filteredSourceFields(sourceName)" :key="field.fieldname" class="report-column-option">
							<Checkbox :model-value="isLinkedVisible(sourceName, field.fieldname)" binary @update:model-value="toggleLinked(sourceName, field, $event)" />
							<span><strong>{{ field.label }}</strong><small>{{ field.fieldname }}</small></span>
						</label>
					</details>
				</div>
			</section>

			<section class="report-column-order" aria-labelledby="report-column-order-title">
				<header><div><strong id="report-column-order-title">Selected order</strong><small>Drag, or press Alt + ↑ / ↓ to move</small></div><i class="pi pi-arrows-v" /></header>
				<div class="report-column-order__list" @dragover.prevent @drop.prevent="dropColumn">
					<div
						v-for="(column, index) in selectedColumns"
						:key="column.key"
						class="report-column-order__row"
						:class="{ 'is-dragging': dragIndex === index, 'is-drop-before': dropIndex === index }"
						draggable="true"
						@dragstart="beginDrag($event, index)"
						@dragover.prevent.stop="setDropPosition($event, index)"
						@drop.prevent.stop="dropColumn"
						@dragend="endDrag"
					>
						<span class="report-column-position">{{ String(index + 1).padStart(2, "0") }}</span>
						<button type="button" class="report-column-handle" :aria-label="`Reorder ${column.label}`" @keydown.alt.up.prevent="moveColumn(index, -1)" @keydown.alt.down.prevent="moveColumn(index, 1)"><i class="pi pi-bars" /></button>
						<div class="report-column-order__identity"><strong>{{ column.label }}</strong><small>{{ column.kind === "linked" ? "Linked field" : column.fieldtype }}</small></div>
						<Button icon="pi pi-times" severity="secondary" text rounded :aria-label="`Hide ${column.label}`" @click="setVisible(column.key, false)" />
						<div class="report-column-order__controls">
							<SelectButton v-model="column.align" :options="alignments" option-label="label" option-value="value" :allow-empty="false" :aria-label="`Alignment for ${column.label}`" />
							<InputNumber v-model="column.width" :min="60" :max="600" :step="10" suffix=" px" show-buttons button-layout="horizontal" :aria-label="`Width for ${column.label}`" />
						</div>
					</div>
					<div v-if="!selectedColumns.length" class="report-column-empty">Choose at least one column from the left.</div>
				</div>
			</section>
		</div>

		<template #footer>
			<Button label="Reset" severity="secondary" outlined :disabled="saving" @click="reset" />
			<Button label="Cancel" severity="secondary" text :disabled="saving" @click="$emit('update:visible', false)" />
			<Button label="Apply" severity="secondary" :disabled="saving || !selectedColumns.length" @click="apply" />
			<Button label="Save" icon="pi pi-check" :loading="saving" :disabled="!selectedColumns.length" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import SelectButton from "primevue/selectbutton"
import { computed, reactive, ref, watch } from "vue"

import { linkSourceLabel, MAX_LINKED_COLUMNS } from "../../composables/reportColumns.js"
import { moveDraftItem, reorderDraftItem, syncOrderedDraft } from "../common/orderedDraft.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	columns: { type: Array, default: () => [] },
	linkSources: { type: Object, default: () => ({}) },
	fieldsBySource: { type: Object, default: () => ({}) },
	loadFieldOptions: { type: Function, required: true },
	applyLayout: { type: Function, required: true },
	saveLayout: { type: Function, required: true },
	resetLayout: { type: Function, required: true },
	error: { type: String, default: "" },
})

const emit = defineEmits(["update:visible"])
const localColumns = ref([])
const baseSearch = ref("")
const sourceSearch = reactive({})
const loadingSources = reactive(new Set())
const saving = ref(false)
const localError = ref("")
const dragIndex = ref(null)
const dropIndex = ref(null)
const alignments = [
	{ label: "Auto", value: "auto" },
	{ label: "Left", value: "left" },
	{ label: "Center", value: "center" },
	{ label: "Right", value: "right" },
]

const errorMessage = computed(() => localError.value || props.error)
const selectedColumns = computed(() => localColumns.value.filter((column) => column.visible))
const filteredBaseColumns = computed(() => localColumns.value.filter((column) => (
	column.kind === "base" && matchesSearch(column, baseSearch.value)
)))

watch(() => props.visible, (visible) => {
	if (!visible) return
	localError.value = ""
	baseSearch.value = ""
	localColumns.value = syncOrderedDraft(localColumns.value, props.columns, {
		clone: (column) => ({ ...column }),
	})
})

function filteredSourceFields(source) {
	return (props.fieldsBySource[source] || []).filter((field) => matchesSearch(field, sourceSearch[source]))
}

async function openSource(source, event) {
	if (!event.currentTarget.open || props.fieldsBySource[source] || loadingSources.has(source)) return
	loadingSources.add(source)
	localError.value = ""
	try {
		await props.loadFieldOptions(source)
	} catch (reason) {
		localError.value = reason?.message || "Unable to load linked fields."
	} finally {
		loadingSources.delete(source)
	}
}

function isLinkedVisible(source, fieldname) {
	return localColumns.value.some((column) => (
		column.kind === "linked" && column.source_column === source
		&& column.target_field === fieldname && column.visible
	))
}

function toggleLinked(source, field, visible) {
	const key = `linked:${source}:${field.fieldname}`
	const existing = localColumns.value.find((column) => column.key === key)
	if (existing) {
		setVisible(key, visible)
		return
	}
	if (!visible) return
	if (!hasLinkedColumnCapacity()) return showLinkedColumnLimit()
	const sourceLabel = props.linkSources[source]?.label || source
	localColumns.value.push({
		...field,
		key,
		column_key: key,
		kind: "linked",
		source_column: source,
		target_field: field.fieldname,
		label: `${sourceLabel} · ${field.label || field.fieldname}`,
		visible: true,
		align: "auto",
		width: 120,
	})
}

function setVisible(key, visible) {
	const index = localColumns.value.findIndex((column) => column.key === key)
	if (index < 0) return
	const next = [...localColumns.value]
	const [column] = next.splice(index, 1)
	if (visible && column.kind === "linked" && !column.visible && !hasLinkedColumnCapacity()) {
		return showLinkedColumnLimit()
	}
	column.visible = Boolean(visible)
	localError.value = ""
	if (column.visible) {
		const lastVisible = next.findLastIndex((candidate) => candidate.visible)
		next.splice(lastVisible + 1, 0, column)
	} else next.push(column)
	localColumns.value = next
}

function hasLinkedColumnCapacity() {
	return localColumns.value.filter((column) => column.kind === "linked" && column.visible).length < MAX_LINKED_COLUMNS
}

function showLinkedColumnLimit() {
	localError.value = `You can select up to ${MAX_LINKED_COLUMNS} linked fields.`
}

function beginDrag(event, index) {
	dragIndex.value = index
	dropIndex.value = index
	event.dataTransfer.effectAllowed = "move"
	event.dataTransfer.setData("text/plain", selectedColumns.value[index]?.key || "")
}

function setDropPosition(event, index) {
	if (dragIndex.value === null) return
	const bounds = event.currentTarget.getBoundingClientRect()
	dropIndex.value = event.clientY < bounds.top + bounds.height / 2 ? index : index + 1
	event.dataTransfer.dropEffect = "move"
}

function dropColumn() {
	if (dragIndex.value === null || dropIndex.value === null) return endDrag()
	applySelectedOrder(reorderDraftItem(selectedColumns.value, dragIndex.value, dropIndex.value))
	endDrag()
}

function moveColumn(index, direction) {
	const ordered = moveDraftItem(selectedColumns.value, index, direction)
	if (ordered !== selectedColumns.value) applySelectedOrder(ordered)
}

function applySelectedOrder(ordered) {
	localColumns.value = [...ordered, ...localColumns.value.filter((column) => !column.visible)]
}

function endDrag() {
	dragIndex.value = null
	dropIndex.value = null
}

function apply() {
	props.applyLayout(localColumns.value)
	emit("update:visible", false)
}

async function save() {
	saving.value = true
	localError.value = ""
	try {
		await props.saveLayout(localColumns.value)
		emit("update:visible", false)
	} catch (reason) {
		localError.value = reason?.message || "Unable to save report columns."
	} finally {
		saving.value = false
	}
}

async function reset() {
	saving.value = true
	localError.value = ""
	try {
		await props.resetLayout()
		emit("update:visible", false)
	} catch (reason) {
		localError.value = reason?.message || "Unable to reset report columns."
	} finally {
		saving.value = false
	}
}

function matchesSearch(field, search) {
	const query = String(search || "").trim().toLowerCase()
	return !query || [field.label, field.fieldname].some((value) => String(value || "").toLowerCase().includes(query))
}
</script>

<style scoped>
.report-column-editor {
	display: grid;
	grid-template-columns: minmax(280px, .85fr) minmax(520px, 1.35fr);
	gap: var(--erp-space-3);
	min-height: 34rem;
}

.report-column-picker,
.report-column-order {
	display: flex;
	min-width: 0;
	padding: var(--erp-space-3);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	flex-direction: column;
}

.report-column-picker > header,
.report-column-order > header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-2);
	margin-bottom: var(--erp-space-2);
}

.report-column-picker header div,
.report-column-order header div {
	display: grid;
	gap: 2px;
}

.report-column-picker header small,
.report-column-order header small,
.report-column-option small,
.report-column-order__identity small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.report-column-picker header strong,
.report-column-order header strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-semibold);
}

.report-column-option strong,
.report-column-order__identity strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-medium);
}

.report-column-order__identity small {
	justify-self: start;
	padding: 1px 6px;
	border-radius: 6px;
	background: var(--erp-surface-muted);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: .03em;
	text-transform: uppercase;
}

.report-column-picker > header > span {
	padding: 1px 7px;
	border-radius: var(--erp-pill-radius);
	background: var(--erp-surface-muted);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	border: 0;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	min-width: 23px;
}

.report-column-search {
	position: relative;
	display: flex;
	align-items: center;
	margin-bottom: var(--erp-space-2);
}

.report-column-search > i {
	position: absolute;
	z-index: 1;
	left: 11px;
	color: var(--erp-text-muted);
}

.report-column-search :deep(input) {
	padding-left: 32px;
}

.report-column-picker__list,
.report-column-order__list {
	overflow: auto;
	height: 29rem;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
}

.report-column-group {
	padding: var(--erp-space-2);
	border-bottom: 1px solid var(--erp-border-subtle);
}

.report-column-group:last-child {
	border-bottom: 0;
}

.report-column-group h3,
.report-column-group summary {
	margin: 0;
	padding: 6px 5px;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-semibold);
}

.report-column-group summary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	cursor: pointer;
	list-style: none;
}

.report-column-group summary small {
	color: var(--erp-text-muted);
	font-weight: var(--erp-font-weight-semibold);
}

.report-column-group[open] summary i {
	transform: rotate(180deg);
}

.report-column-option {
	display: flex;
	align-items: center;
	gap: 9px;
	min-height: 40px;
	padding: 6px 8px;
	border-radius: var(--erp-control-radius);
	border: 1px solid transparent;
}

.report-column-option:hover {
	background: var(--erp-surface-hover);
}

.report-column-option > span,
.report-column-order__controls {
	display: flex;
	flex-wrap: wrap;
	grid-column: 3 / -1;
	align-items: center;
	gap: 8px;
}

.report-column-order__identity {
	display: grid;
	min-width: 0;
	gap: 1px;
}

.report-column-loading,
.report-column-empty {
	padding: var(--erp-space-4);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	text-align: center;
}

.report-column-order__list {
	display: flex;
	flex-direction: column;
	gap: 7px;
	padding: 8px;
}

.report-column-order__row {
	position: relative;
	display: grid;
	flex: none;
	grid-template-columns: 28px 32px minmax(0, 1fr) 34px;
	align-items: center;
	gap: 6px 7px;
	min-height: 58px;
	padding: 6px 7px;
	border: 1px solid var(--erp-border-subtle);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.report-column-order__row:hover {
	background: var(--erp-surface-hover);
}

.report-column-order__row.is-dragging {
	opacity: .42;
}

.report-column-order__row.is-drop-before::before {
	position: absolute;
	top: -5px;
	right: 4px;
	left: 4px;
	height: 3px;
	border-radius: var(--erp-pill-radius);
	background: var(--erp-accent);
	content: "";
}

.report-column-position {
	color: var(--erp-text-muted);
	font-family: var(--erp-font-family-mono);
	font-size: var(--erp-font-size-min);
	text-align: center;
	font-variant-numeric: tabular-nums;
}

.report-column-handle {
	display: grid;
	width: 30px;
	height: 34px;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface-muted);
	color: var(--erp-text-subtle);
	cursor: grab;
	place-items: center;
}

.report-column-handle:hover {
	color: var(--erp-text);
}

.report-column-order__row :deep(.p-selectbutton .p-togglebutton) {
	min-width: 47px;
	padding: 5px 7px;
	font-size: var(--erp-font-size-min);
}

.report-column-order__row :deep(.p-inputnumber-input) {
	width: 76px;
}

@media (max-width: 1040px) {
	.report-column-editor {
		grid-template-columns: minmax(0, 1fr);
	}

	.report-column-picker__list,
	.report-column-order__list {
		height: 22rem;
	}
}
@media (pointer: coarse) {
	.report-column-option {
		min-height: 44px;
	}
}
</style>
