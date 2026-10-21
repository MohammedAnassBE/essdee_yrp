<template>
	<Dialog :visible="visible" modal dismissable-mask maximizable :header="currentName ? `Edit Delivery Challan · ${currentName}` : 'Create Delivery Challan from Work Order'" class="erp-work-order-dc-dialog erp-entity-dialog erp-dialog--xl" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="erp-work-order-dc__loading"><Skeleton v-for="index in 5" :key="index" height="3rem" /></div>
		<div v-else class="erp-work-order-dc">
			<div class="erp-work-order-dc__context">
				<div><span>Work Order</span><strong>{{ editor.work_order || "—" }}</strong></div>
				<div><span>From / To Location</span><strong>{{ editor.context?.source_supplier || "—" }}</strong></div>
				<div><span>Warehouse</span><strong>{{ editor.context?.source_warehouse || "—" }}</strong></div>
			</div>
			<WorkOrderDeliveryMatrix title="Deliverables" :groups="editor.item_details || []" :quantities="quantities" @update="setQuantity" />
			<WorkOrderDeliveryMatrix v-for="block in editor.correction_item_details || []" :key="block.work_order_correction" :title="block.title || block.work_order_correction" :groups="block.item_details || []" :quantities="correctionQuantities" @update="setCorrectionQuantity" />
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
			<DocumentSaveButton :saved="Boolean(currentName)" :dirty="dirty" :docstatus="Number(savedEditor.record?.docstatus || 0)" :document-label="`Delivery Challan ${currentName}`.trim()" :show-save="canWrite" :show-submit="canWrite && Boolean(activePermissions.can_submit)" :disabled="!canSave" :loading="saving" @save="save(false)" @submit="save(true)" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" title="Delivery Challan could not be created" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { getDeliveryChallanWorkspace, saveDeliveryChallan } from "../../api/fabricStore.js"
import { createWorkOrderDeliveryChallan, getWorkOrderDeliveryEditor } from "./cpmApi.js"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import WorkOrderDeliveryMatrix from "./WorkOrderDeliveryMatrix.vue"

const props = defineProps({
	visible: Boolean,
	cuttingPlan: { type: String, required: true },
	permissions: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed", "created"])
const editor = reactive({ context: {}, item_details: [], correction_item_details: [] })
const quantities = reactive({})
const correctionQuantities = reactive({})
const loading = ref(false)
const saving = ref(false)
const saveMode = ref("")
const error = ref("")
const currentName = ref("")
const savedEditor = ref({})
const cleanSignature = ref("")
const signature = computed(() => JSON.stringify({ quantities, correctionQuantities }))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)
const activePermissions = computed(() => currentName.value ? savedEditor.value.permissions || {} : props.permissions)
const canWrite = computed(() => Boolean(currentName.value ? activePermissions.value.can_write : activePermissions.value.can_create))
const canSave = computed(() => Boolean(canWrite.value && [...Object.values(quantities), ...Object.values(correctionQuantities)].some((value) => Number(value) > 0)))

watch(() => [props.visible, props.cuttingPlan], ([visible]) => { if (visible) { currentName.value = ""; savedEditor.value = {}; load() } })

async function load() {
	loading.value = true
	error.value = ""
	clear(quantities)
	clear(correctionQuantities)
	try {
		Object.assign(editor, await getWorkOrderDeliveryEditor(props.cuttingPlan))
		if (currentName.value) {
			savedEditor.value = await getDeliveryChallanWorkspace(currentName.value)
			editor.item_details = savedEditor.value.matrices?.items || []
			editor.correction_item_details = savedEditor.value.matrices?.correction_items || []
			readQuantities(editor.item_details, quantities)
			for (const block of editor.correction_item_details) readQuantities(block.item_details, correctionQuantities)
		}
		cleanSignature.value = signature.value
	} catch (reason) {
		error.value = reason.message || "Unable to load Work Order deliverables."
	} finally {
		loading.value = false
	}
}

function setQuantity(reference, quantity) { if (reference) quantities[reference] = quantity }
function setCorrectionQuantity(reference, quantity) { if (reference) correctionQuantities[reference] = quantity }

async function save(submit) {
	if (!canSave.value) return
	saving.value = true
	saveMode.value = submit ? "submit" : "draft"
	error.value = ""
	try {
		const saved = currentName.value
			? await saveDeliveryChallan({
				...savedEditor.value.values,
				item_details: applyQuantities(editor.item_details, quantities),
				correction_item_details: editor.correction_item_details.map(block => ({ ...block, item_details: applyQuantities(block.item_details, correctionQuantities) })),
			}, { name: currentName.value, submit, expectedModified: savedEditor.value.record?.modified })
			: await createWorkOrderDeliveryChallan(props.cuttingPlan, {
			quantities: positiveQuantities(quantities),
			correction_quantities: positiveQuantities(correctionQuantities),
		}, submit)
		currentName.value = saved.record?.name || saved.name
		if (!submit) await load()
		emit("changed", saved)
		if (submit) emit("created", { doctype: "YRP Delivery Challan", name: currentName.value })
		if (submit) emit("update:visible", false)
	} catch (reason) {
		error.value = reason.message || "Unable to create the Delivery Challan."
	} finally {
		saving.value = false
		saveMode.value = ""
	}
}

function positiveQuantities(values) {
	return Object.fromEntries(Object.entries(values).filter(([, quantity]) => Number(quantity) > 0))
}
function readQuantities(groups, target) {
	for (const group of groups || []) for (const row of group.items || []) for (const cell of Object.values(row.values || {})) {
		if (cell?.ref_docname) target[cell.ref_docname] = Number(cell.qty || 0)
	}
}
function applyQuantities(groups, quantities) {
	const result = JSON.parse(JSON.stringify(groups || []))
	for (const group of result) for (const row of group.items || []) for (const cell of Object.values(row.values || {})) {
		if (cell?.ref_docname) cell.qty = cell.delivered_quantity = Number(quantities[cell.ref_docname] || 0)
	}
	return result
}
function clear(value) { for (const key of Object.keys(value)) delete value[key] }
</script>

<style scoped>
.erp-work-order-dc,
.erp-work-order-dc__loading {
	display: grid;
	gap: var(--erp-space-3);
}

.erp-work-order-dc__context {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface-soft);
}

.erp-work-order-dc__context > div {
	display: grid;
	gap: var(--erp-space-1);
	padding: 10px var(--erp-space-3);
	border-right: 1px solid var(--erp-border);
}

.erp-work-order-dc__context > div:last-child {
	border-right: 0;
}

.erp-work-order-dc__context span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	letter-spacing: 0.035em;
	text-transform: uppercase;
}

.erp-work-order-dc__context strong {
	overflow: hidden;
	color: var(--erp-text);
	font-size: 13px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

@media (max-width: 680px) {
	.erp-work-order-dc__context {
		grid-template-columns: 1fr;
	}

	.erp-work-order-dc__context > div {
		border-right: 0;
		border-bottom: 1px solid var(--erp-border);
	}

	.erp-work-order-dc__context > div:last-child {
		border-bottom: 0;
	}
}
</style>
