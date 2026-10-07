<template>
	<Dialog
		:visible="visible"
		modal
		header="Customize Columns"
		:style="{ width: 'min(58rem, calc(100vw - 24px))' }"
		@update:visible="$emit('update:visible', $event)"
	>
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

		<div class="column-editor">
			<section class="column-picker" aria-labelledby="column-picker-title">
				<div class="column-section-head">
					<div>
						<strong id="column-picker-title">Choose fields</strong>
						<small>Select the fields to display</small>
					</div>
					<span>{{ visibleColumns.length }} selected</span>
				</div>

				<label class="column-search">
					<i class="pi pi-search" aria-hidden="true"></i>
					<InputText v-model="fieldSearch" placeholder="Find a field…" fluid />
				</label>

				<div class="column-picker-list">
					<label
						v-for="column in filteredColumns"
						:key="column.fieldname"
						:for="`column-${column.fieldname}`"
						class="column-picker-row"
						:class="{ 'column-picker-row--enabled': column.enabled }"
					>
						<Checkbox
							:input-id="`column-${column.fieldname}`"
							:model-value="column.enabled"
							binary
							@update:model-value="setColumnEnabled(column, $event)"
						/>
						<span>
							<strong>{{ column.label }}</strong>
						</span>
					</label>
					<div v-if="!filteredColumns.length" class="column-empty compact">
						No fields match “{{ fieldSearch }}”
					</div>
				</div>
			</section>

			<section class="column-order" aria-labelledby="column-order-title">
				<div class="column-section-head">
					<div>
						<strong id="column-order-title">Column order</strong>
						<small>Drag, or press Alt + ↑ / ↓ to move</small>
					</div>
					<i class="pi pi-arrows-v" aria-hidden="true"></i>
				</div>

				<div
					class="column-order-list"
					:class="{ 'column-order-list--dragging': dragIndex !== null }"
					@dragover.prevent
					@drop.prevent="dropColumn"
				>
					<div
						v-for="(column, index) in visibleColumns"
						:key="column.fieldname"
						class="column-order-row"
						:class="{
							'column-order-row--dragging': dragIndex === index,
							'column-order-row--drop-before': dropIndex === index,
							'column-order-row--drop-after':
								dropIndex === index + 1 && index === visibleColumns.length - 1,
						}"
						draggable="true"
						@dragstart="beginDrag($event, index)"
						@dragover.prevent.stop="setDropPosition($event, index)"
						@drop.prevent.stop="dropColumn"
						@dragend="endDrag"
					>
						<span class="column-position">{{ String(index + 1).padStart(2, "0") }}</span>
						<span
							class="column-drag-handle"
							role="button"
							tabindex="0"
							aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown"
							:aria-label="`Reorder ${column.label}, position ${index + 1} of ${visibleColumns.length}`"
							:title="`Drag ${column.label}, or press Alt + Up or Alt + Down, to reorder`"
							@keydown.alt.up.prevent="moveColumn(index, -1)"
							@keydown.alt.down.prevent="moveColumn(index, 1)"
						>
							<i class="pi pi-bars" aria-hidden="true"></i>
						</span>
						<span class="column-order-label">
							<strong>{{ column.label }}</strong>
						</span>
						<Button
							icon="pi pi-times"
							severity="secondary"
							text
							rounded
							size="small"
							:aria-label="`Hide ${column.label}`"
							@click="setColumnEnabled(column, false)"
						/>
					</div>

					<div v-if="!visibleColumns.length" class="column-empty">
						<i class="pi pi-table" aria-hidden="true"></i>
						<strong>No optional columns selected</strong>
						<span>Choose fields from the left to build the list.</span>
					</div>
				</div>
				<span class="sr-only" aria-live="polite">{{ reorderAnnouncement }}</span>
			</section>
		</div>

		<template #footer>
			<Button
				label="Reset to Default"
				severity="secondary"
				outlined
				:loading="saving"
				@click="reset"
			/>
			<Button
				label="Cancel"
				severity="secondary"
				text
				:disabled="saving"
				@click="$emit('update:visible', false)"
			/>
			<Button label="Save Columns" icon="pi pi-check" :loading="saving" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import { computed, ref, watch } from "vue"

import { resetUserListview, saveUserListview } from "../../api/frappe.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, required: true },
	columns: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:visible", "saved"])
const localColumns = ref([])
const saving = ref(false)
const error = ref("")
const fieldSearch = ref("")
const dragIndex = ref(null)
const dropIndex = ref(null)
const reorderAnnouncement = ref("")

const visibleColumns = computed(() => localColumns.value.filter((column) => column.enabled))
const filteredColumns = computed(() => {
	const query = fieldSearch.value.trim().toLowerCase()
	if (!query) return localColumns.value
	return localColumns.value.filter((column) =>
		[column.label, column.fieldname, column.fieldtype].some((value) =>
			String(value || "").toLowerCase().includes(query),
		),
	)
})

watch(
	() => props.visible,
	(visible) => {
		if (!visible) return
		error.value = ""
		fieldSearch.value = ""
		endDrag()
		localColumns.value = props.columns.map((column) => ({
			fieldname: column.fieldname,
			fieldtype: column.fieldtype,
			label: column.label,
			enabled: Boolean(column.enabled),
		}))
	},
)

function setColumnEnabled(column, enabled) {
	const index = localColumns.value.findIndex((candidate) => candidate.fieldname === column.fieldname)
	if (index < 0 || localColumns.value[index].enabled === Boolean(enabled)) return
	const next = [...localColumns.value]
	const [updated] = next.splice(index, 1)
	updated.enabled = Boolean(enabled)
	if (updated.enabled) {
		const lastEnabled = next.findLastIndex((candidate) => candidate.enabled)
		next.splice(lastEnabled + 1, 0, updated)
	} else {
		next.push(updated)
	}
	localColumns.value = next
	reorderAnnouncement.value = updated.enabled
		? `${updated.label} added at position ${visibleColumns.value.length}.`
		: `${updated.label} hidden.`
}

function beginDrag(event, index) {
	dragIndex.value = index
	dropIndex.value = index
	event.dataTransfer.effectAllowed = "move"
	event.dataTransfer.setData("text/plain", visibleColumns.value[index]?.fieldname || "")
}

function setDropPosition(event, index) {
	if (dragIndex.value === null) return
	const bounds = event.currentTarget.getBoundingClientRect()
	dropIndex.value = event.clientY < bounds.top + bounds.height / 2 ? index : index + 1
	event.dataTransfer.dropEffect = "move"
}

function dropColumn() {
	if (dragIndex.value === null || dropIndex.value === null) {
		endDrag()
		return
	}
	const ordered = [...visibleColumns.value]
	const [moved] = ordered.splice(dragIndex.value, 1)
	let destination = dropIndex.value
	if (destination > dragIndex.value) destination -= 1
	destination = Math.max(0, Math.min(destination, ordered.length))
	ordered.splice(destination, 0, moved)
	applyVisibleOrder(ordered)
	reorderAnnouncement.value = `${moved.label} moved to position ${destination + 1}.`
	endDrag(false)
}

function moveColumn(index, direction) {
	const ordered = [...visibleColumns.value]
	const destination = Math.max(0, Math.min(index + direction, ordered.length - 1))
	if (destination === index) return
	const [moved] = ordered.splice(index, 1)
	ordered.splice(destination, 0, moved)
	applyVisibleOrder(ordered)
	reorderAnnouncement.value = `${moved.label} moved to position ${destination + 1}.`
}

function applyVisibleOrder(ordered) {
	const hidden = localColumns.value.filter((column) => !column.enabled)
	localColumns.value = [...ordered, ...hidden]
}

function endDrag(clearAnnouncement = true) {
	dragIndex.value = null
	dropIndex.value = null
	if (clearAnnouncement) reorderAnnouncement.value = ""
}

async function save() {
	saving.value = true
	error.value = ""
	try {
		await saveUserListview(
			props.doctype,
			localColumns.value.map(({ fieldname, enabled }) => ({ fieldname, enabled: enabled ? 1 : 0 })),
		)
		emit("update:visible", false)
		emit("saved")
	} catch (reason) {
		error.value = reason.message || "Unable to save columns."
	} finally {
		saving.value = false
	}
}

async function reset() {
	saving.value = true
	error.value = ""
	try {
		await resetUserListview(props.doctype)
		emit("update:visible", false)
		emit("saved")
	} catch (reason) {
		error.value = reason.message || "Unable to reset columns."
	} finally {
		saving.value = false
	}
}
</script>

<style scoped>
.column-editor {
	--column-accent: var(--erp-accent);
	--column-accent-dark: var(--erp-accent-hover);
	--column-accent-soft: var(--erp-accent-soft);
	--column-line: var(--erp-border);

	display: grid;
	grid-template-columns: minmax(240px, 0.8fr) minmax(320px, 1.2fr);
	gap: 16px;
	min-height: 30rem;
}

.column-picker,
.column-order {
	display: flex;
	min-width: 0;
	padding: 14px;
	background: var(--erp-surface);
	border: 1px solid var(--column-line);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-xs);
	flex-direction: column;
}

.column-section-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	min-height: 40px;
	margin-bottom: 10px;
}

.column-section-head > div {
	display: grid;
	gap: 2px;
}

.column-section-head strong {
	color: var(--erp-text);
	font-size: 0.88rem;
}

.column-section-head small {
	color: var(--erp-text-muted);
	font-size: 0.7rem;
}

.column-section-head > span {
	padding: 4px 8px;
	color: var(--column-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	background: var(--column-accent-soft);
	border-radius: 999px;
}

.column-section-head > i {
	color: var(--column-accent-dark);
}

.column-search {
	position: relative;
	display: flex;
	align-items: center;
	margin-bottom: 10px;
}

.column-search > i {
	position: absolute;
	left: 11px;
	z-index: 1;
	color: var(--erp-text-muted);
}

.column-search :deep(input) {
	height: 38px;
	padding-left: 32px;
	border-color: var(--column-line);
	border-radius: var(--erp-control-radius);
}

.column-search:focus-within > i {
	color: var(--column-accent-dark);
}

.column-search :deep(input:focus) {
	border-color: var(--column-accent);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--column-accent) 11%, transparent);
}

.column-picker-list,
.column-order-list {
	overflow-y: auto;
	height: 23.5rem;
	padding: 4px;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: 12px;
	scrollbar-color: var(--erp-border-strong) transparent;
	scrollbar-width: thin;
}

.column-picker-row {
	display: flex;
	align-items: center;
	gap: 10px;
	min-height: 44px;
	padding: 8px 10px;
	border: 1px solid transparent;
	border-radius: 9px;
	cursor: pointer;
	transition: 140ms ease;
}

.column-picker-row:hover {
	background: var(--erp-surface-soft);
	border-color: var(--erp-border);
}

.column-picker-row--enabled {
	background: var(--column-accent-soft);
	border-color: var(--erp-accent-border);
}

.column-picker-row:focus-within {
	border-color: var(--column-accent);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--column-accent) 10%, transparent);
}

.column-picker-row > span,
.column-order-label {
	display: grid;
	gap: 2px;
	min-width: 0;
}

.column-picker-row strong,
.column-order-label strong {
	overflow: hidden;
	color: var(--erp-text-secondary);
	font-size: 0.79rem;
	font-weight: 680;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.column-order-list {
	position: relative;
	display: grid;
	align-content: start;
	gap: 7px;
	height: 26.35rem;
	padding: 8px;
}

.column-order-list--dragging {
	background: linear-gradient(180deg, var(--erp-surface), var(--column-accent-soft));
}

.column-order-row {
	position: relative;
	display: grid;
	grid-template-columns: 30px 30px minmax(0, 1fr) 30px;
	align-items: center;
	gap: 8px;
	min-height: 50px;
	padding: 7px 8px;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: 11px;
	box-shadow: var(--erp-shadow-xs);
	cursor: grab;
	transition:
		opacity 120ms ease,
		border-color 120ms ease,
		box-shadow 120ms ease,
		transform 120ms ease;
}

.column-order-row:hover {
	border-color: var(--erp-accent-border);
	box-shadow: var(--erp-shadow-sm);
	transform: translateY(-1px);
}

.column-order-row:active {
	cursor: grabbing;
}

.column-order-row--dragging {
	opacity: 0.36;
	box-shadow: none;
}

.column-order-row--drop-before::before,
.column-order-row--drop-after::after {
	position: absolute;
	right: 5px;
	left: 5px;
	height: 3px;
	background: var(--column-accent);
	border-radius: 999px;
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--column-accent) 12%, transparent);
	content: "";
}

.column-order-row--drop-before::before {
	top: -6px;
}

.column-order-row--drop-after::after {
	bottom: -6px;
}

.column-position {
	color: var(--erp-text-muted);
	font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	text-align: center;
}

.column-drag-handle {
	display: grid;
	width: 28px;
	height: 32px;
	color: var(--erp-text-muted);
	background: var(--erp-surface-muted);
	border: 1px solid var(--erp-border);
	border-radius: 8px;
	cursor: grab;
	place-items: center;
}

.column-drag-handle:focus-visible {
	color: var(--column-accent-dark);
	outline: 3px solid color-mix(in srgb, var(--column-accent) 18%, transparent);
}

.column-empty {
	display: flex;
	align-items: center;
	justify-content: center;
	flex-direction: column;
	gap: 6px;
	min-height: 100%;
	padding: 24px;
	color: var(--erp-text-muted);
	text-align: center;
}

.column-empty > i {
	margin-bottom: 4px;
	color: var(--column-accent-dark);
	font-size: 1.35rem;
}

.column-empty strong {
	color: var(--erp-text-secondary);
	font-size: 0.82rem;
}

.column-empty span,
.column-empty.compact {
	font-size: var(--erp-font-size-caption);
}

.column-empty.compact {
	min-height: 100px;
}

.sr-only {
	position: absolute;
	width: 1px;
	height: 1px;
	overflow: hidden;
	clip: rect(0, 0, 0, 0);
	white-space: nowrap;
	clip-path: inset(50%);
}

@media (max-width: 760px) {
	.column-editor {
		grid-template-columns: 1fr;
	}

	.column-picker-list,
	.column-order-list {
		height: 18rem;
	}
}
</style>
