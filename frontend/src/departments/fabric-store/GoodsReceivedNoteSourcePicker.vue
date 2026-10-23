<template>
	<section class="grn-source-picker" aria-labelledby="grn-source-picker-title">
		<header>
			<h1 id="grn-source-picker-title">New Goods Received Note</h1>
			<p>Choose what is being received. The receivable items, supplier and locations are filled from it.</p>
		</header>
		<div class="grn-source-picker__fields">
			<label class="common-field">
				<span class="common-field__label erp-field-label">Against</span>
				<Select :model-value="against" :options="AGAINST_OPTIONS" option-label="label" option-value="value" aria-label="Against" fluid @update:model-value="changeAgainst" />
			</label>
			<LinkField
				:key="against"
				:model-value="againstId"
				:label="`${againstLabel} *`"
				:doctype="against"
				:filters="sourceFilters"
				:show-open-button="false"
				show-clear
				@update:model-value="changeSource"
			/>
			<LinkField
				v-if="isWorkOrder && againstId"
				v-model="deliveryChallan"
				:label="requiresDeliveryChallan ? 'Delivery Challan *' : 'Delivery Challan'"
				doctype="YRP Delivery Challan"
				:filters="{ work_order: againstId, docstatus: 1 }"
				:show-open-button="false"
				show-clear
			/>
		</div>
		<Message v-if="isWorkOrder && againstId" severity="secondary" :closable="false">{{ requiresDeliveryChallan ? "This rework Work Order requires a submitted Delivery Challan." : "Choose the Delivery Challan being received, or continue without one when this receipt is not tied to a dispatch." }}</Message>
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<footer><Button label="Continue to GRN" icon="pi pi-arrow-right" :disabled="!canContinue" :loading="checking" @click="emit('select', source)" /></footer>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Select from "primevue/select"
import { computed, ref } from "vue"

import { getList } from "../../api/frappe.js"
import LinkField from "../../components/common/LinkField.vue"
import { goodsReceivedNoteSource } from "./grnSource.js"

const props = defineProps({ initialSource: { type: Object, default: () => ({}) } })
const emit = defineEmits(["select"])
const AGAINST_OPTIONS = [{ label: "Work Order", value: "YRP Work Order" }, { label: "Purchase Order", value: "Purchase Order" }]
const against = ref("YRP Work Order")
const againstId = ref("")
const deliveryChallan = ref("")
const requiresDeliveryChallan = ref(false)
const checking = ref(false)
const error = ref("")
let checkSequence = 0

const isWorkOrder = computed(() => against.value === "YRP Work Order")
const againstLabel = computed(() => AGAINST_OPTIONS.find((option) => option.value === against.value)?.label || "Source")
const sourceFilters = computed(() => isWorkOrder.value ? { docstatus: 1, open_status: "Open" } : { docstatus: 1 })
const source = computed(() => goodsReceivedNoteSource(against.value, againstId.value, deliveryChallan.value))
const canContinue = computed(() => Boolean(againstId.value) && !checking.value && !(requiresDeliveryChallan.value && !deliveryChallan.value))

function changeAgainst(value) {
	against.value = value
	changeSource("")
}

/** Rework Work Orders receive only against a Delivery Challan, as on the Work Order's Make GRN dialog. */
async function changeSource(name) {
	const sequence = ++checkSequence
	againstId.value = name || ""
	deliveryChallan.value = ""
	requiresDeliveryChallan.value = false
	error.value = ""
	if (!name || !isWorkOrder.value) return
	checking.value = true
	try {
		const [workOrder] = await getList("YRP Work Order", { fields: ["name", "is_rework"], filters: [["name", "=", name]], pageLength: 1 })
		if (sequence === checkSequence) requiresDeliveryChallan.value = Boolean(Number(workOrder?.is_rework || 0))
	} catch (reason) {
		if (sequence === checkSequence) error.value = reason?.message || "Unable to load the Work Order."
	} finally {
		if (sequence === checkSequence) checking.value = false
	}
}

async function preselectSource({ against: initialAgainst, against_id: initialId, delivery_challan: initialChallan } = {}) {
	if (AGAINST_OPTIONS.some((option) => option.value === initialAgainst)) against.value = initialAgainst
	if (!initialId) return
	await changeSource(initialId)
	if (initialChallan && isWorkOrder.value) deliveryChallan.value = initialChallan
}

preselectSource(props.initialSource)
</script>

<style scoped>
.grn-source-picker { display: grid; max-width: 720px; gap: var(--erp-space-3); margin: var(--erp-space-3) 0; padding: var(--erp-space-4); border: 1px solid var(--erp-border); border-radius: var(--erp-radius, 8px); background: var(--erp-surface); }
.grn-source-picker h1 { margin: 0; font-size: 20px; }
.grn-source-picker p { margin: 4px 0 0; color: var(--erp-text-muted); }
.grn-source-picker__fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--erp-space-3); }
.grn-source-picker footer { display: flex; justify-content: flex-end; }
</style>
