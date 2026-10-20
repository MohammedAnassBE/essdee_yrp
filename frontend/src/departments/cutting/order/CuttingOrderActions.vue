<template>
	<div v-if="hasActions" class="order-actions" role="group" aria-label="Cutting Order actions">
		<Button
			class="order-actions-trigger"
			label="More Actions"
			icon="pi pi-chevron-down"
			icon-pos="right"
			severity="secondary"
			outlined
			:loading="Boolean(busy)"
			aria-haspopup="menu"
			aria-controls="cutting-order-more-actions"
			:aria-expanded="moreActionsOpen"
			@click="toggleMoreActions"
		/>
		<Menu
			id="cutting-order-more-actions"
			ref="moreActionsMenu"
			:model="moreActionItems"
			popup
			:base-z-index="5000"
			class="order-actions-menu"
			@show="moreActionsOpen = true"
			@hide="moreActionsOpen = false"
		/>
	</div>

	<Teleport to="body">
		<Message v-if="feedback" class="order-action-feedback" severity="success" closable @close="feedback = ''">{{ feedback }}</Message>
	</Teleport>
	<DocumentErrorDialog :message="actionError" title="Cutting Order action failed" @dismiss="actionError = ''" />

	<Dialog v-model:visible="reportOpen" modal dismissable-mask maximizable header="Completed Cut Quantity" class="action-dialog action-dialog--wide completed-report-dialog">
		<div ref="capture" class="completed-report-capture">
			<CuttingCompletedReport :doc="reportDoc" :groups="data.completed_items" :generated-at="generatedAt" reference-label="Cutting Order" :reference-value="doc.name" />
		</div>
		<Message v-if="copyFeedback" :severity="copyError ? 'error' : 'success'" :closable="false">{{ copyFeedback }}</Message>
		<template #footer><Button label="Close" severity="secondary" text @click="reportOpen = false" /><Button label="Copy" icon="pi pi-copy" :loading="copying" @click="copyReport" /></template>
	</Dialog>

	<Dialog v-model:visible="editorOpen" modal dismissable-mask maximizable header="Update Completed Cut Quantity" class="action-dialog action-dialog--wide">
		<div class="completed-editor">
			<div v-for="(group, groupIndex) in completedDraft" :key="groupIndex" class="completed-table-wrap" role="region" tabindex="0" :aria-label="`Completed cut quantities group ${groupIndex + 1}`">
				<table><thead><tr><th>S.No.</th><th v-for="attribute in group.attributes || inferredAttributes(group)" :key="attribute">{{ attribute }}</th><th v-for="size in group.primary_attribute_values || []" :key="size">{{ size }}</th><th>Completed</th></tr></thead><tbody><tr v-for="(row, rowIndex) in group.items || []" :key="rowIndex"><td>{{ rowIndex + 1 }}</td><td v-for="attribute in group.attributes || inferredAttributes(group)" :key="attribute">{{ row.attributes?.[attribute] || '—' }}</td><td v-for="size in group.primary_attribute_values || []" :key="size">{{ quantity(row.values?.[size]) }}</td><td><Checkbox v-model="row.completed" binary :aria-label="`Mark completed cut quantity row ${rowIndex + 1} in group ${groupIndex + 1}`" /></td></tr></tbody></table>
			</div>
		</div>
		<template #footer><Button label="Close" severity="secondary" text @click="editorOpen = false" /><Button label="Save Completed" icon="pi pi-check" :loading="busy === 'completed'" @click="saveCompleted" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import Menu from "primevue/menu"
import Message from "primevue/message"
import { computed, ref } from "vue"

import { callMethod } from "../../../api/frappe.js"
import { updateCuttingOrderCompleted } from "../../../api/cuttingOrder.js"
import { copyElementAsImage } from "../../../components/reports/copyElementAsImage.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import CuttingCompletedReport from "../CuttingCompletedReport.vue"

const props = defineProps({ doc: { type: Object, required: true }, data: { type: Object, default: () => ({}) } })
const emit = defineEmits(["refresh"])
const busy = ref("")
const feedback = ref("")
const actionError = ref("")
const reportOpen = ref(false)
const generatedAt = ref("")
const capture = ref(null)
const copying = ref(false)
const copyFeedback = ref("")
const copyError = ref(false)
const editorOpen = ref(false)
const completedDraft = ref([])
const actions = computed(() => props.data.actions || {})
const reportDoc = computed(() => ({ ...props.doc, lot: props.doc.name }))
const moreActionsMenu = ref(null)
const moreActionsOpen = ref(false)
const moreActionItems = computed(() => {
	const disabled = Boolean(busy.value)
	return [
		actions.value.can_calculate_laysheets ? { label: "Calculate LaySheets", icon: "pi pi-calculator", disabled, command: calculate } : null,
		actions.value.can_get_completed ? { label: "Get Completed", icon: "pi pi-chart-bar", disabled, command: openCompletedReport } : null,
		actions.value.can_update_completed ? { label: "Update Completed", icon: "pi pi-check-square", disabled, command: openCompletedEditor } : null,
	].filter(Boolean)
})
const hasActions = computed(() => moreActionItems.value.length > 0)

async function calculate() {
	busy.value = "calculate"; feedback.value = ""; actionError.value = ""
	try {
		await callMethod("essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order.sd_yrp_cutting_order.calculate_laysheets", { cutting_order: props.doc.name })
		feedback.value = "LaySheet calculation queued."
		emit("refresh")
	} catch (reason) { actionError.value = reason?.message || "Unable to calculate LaySheets." }
	finally { busy.value = "" }
}

function openCompletedReport() {
	generatedAt.value = formatTimestamp(new Date())
	copyFeedback.value = ""; copyError.value = false; reportOpen.value = true
}

function openCompletedEditor() { completedDraft.value = clone(normaliseGroups(props.data.completed_items)); editorOpen.value = true }

async function saveCompleted() {
	busy.value = "completed"; feedback.value = ""; actionError.value = ""
	try {
		await updateCuttingOrderCompleted(props.doc.name, completedDraft.value, props.doc.modified)
		editorOpen.value = false; feedback.value = "Completed quantities updated."; emit("refresh")
	} catch (reason) { actionError.value = reason?.message || "Unable to update completed quantities." }
	finally { busy.value = "" }
}

async function copyReport() {
	copying.value = true; copyFeedback.value = ""; copyError.value = false
	try { await copyElementAsImage(capture.value); copyFeedback.value = "Completed quantities copied to clipboard." }
	catch (reason) { copyError.value = true; copyFeedback.value = reason?.message || "Unable to copy completed quantities." }
	finally { copying.value = false }
}

function normaliseGroups(value) {
	if (Array.isArray(value)) return value
	if (value?.items) return [value]
	if (value && typeof value === "object") return Object.values(value).filter((group) => group?.items)
	return []
}
function inferredAttributes(group) { return Object.keys(group.items?.[0]?.attributes || {}) }
function quantity(value) { if (value && typeof value === "object") return Object.values(value).reduce((total, entry) => total + Number(entry || 0), 0) || "—"; return Number(value || 0) || "—" }
function clone(value) { return JSON.parse(JSON.stringify(value || [])) }
function formatTimestamp(value) { const pad = (part) => String(part).padStart(2, "0"); return `${pad(value.getDate())}-${pad(value.getMonth() + 1)}-${value.getFullYear()} · ${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}` }
function toggleMoreActions(event) { moreActionsMenu.value?.toggle(event) }
</script>

<style scoped>
.order-actions { display: flex; align-items: center; min-width: 0; }
.order-actions :deep(.order-actions-trigger.p-button:focus-visible) { outline: 2px solid color-mix(in srgb, var(--erp-accent) 45%, var(--erp-surface)); outline-offset: 2px; }
.order-actions :deep(.order-actions-trigger .p-button-label) { white-space: nowrap; }
.order-action-feedback { position: fixed; z-index: 6100; top: 72px; left: 50%; width: min(92vw, 560px); margin: 0; transform: translateX(-50%); box-shadow: var(--erp-shadow-dialog); }
:global(.order-actions-menu.p-menu) { width: 242px; padding: 6px; font-family: var(--erp-font-family); font-size: var(--erp-font-size-caption); background: var(--erp-surface); border: 1px solid var(--erp-border-strong); border-radius: var(--erp-panel-radius); box-shadow: var(--erp-shadow-dialog); }
:global(.order-actions-menu .p-menu-item-content) { border-radius: 7px; }
:global(.order-actions-menu .p-menu-item-link) { gap: 9px; padding: 9px 10px; color: var(--erp-text); }
:global(.order-actions-menu .p-menu-item-icon) { color: var(--erp-text-muted); font-size: .82rem; }
:global(.order-actions-menu .p-menu-item-content:hover) { background: var(--erp-accent-soft); }
.completed-editor { display: grid; gap: 12px; }
.completed-table-wrap { overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.completed-table-wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: 2px; }
.completed-table-wrap table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.completed-table-wrap th, .completed-table-wrap td { padding: 8px 10px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.completed-table-wrap th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface-muted); }
.completed-table-wrap th:last-child, .completed-table-wrap td:last-child { border-right: 0; }
.completed-table-wrap tr:last-child td { border-bottom: 0; }
</style>
