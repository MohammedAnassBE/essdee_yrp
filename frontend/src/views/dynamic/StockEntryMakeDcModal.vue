<template>
	<Dialog
		:visible="visible"
		@update:visible="emit('update:visible', $event)"
		header="Make Delivery Challan"
		modal
		:closable="!creating"
		:closeOnEscape="!creating"
		:style="{ width: 'min(520px, calc(100vw - 32px))' }"
	>
		<div class="make-dc-form">
			<Message v-if="errorMessage" severity="error" closable @close="errorMessage = ''">
				{{ errorMessage }}
			</Message>

			<div class="make-dc-field">
				<label>Work Order <span>*</span></label>
				<LinkField
					v-model="form.workOrder"
					target-doctype="Work Order"
					:filters="{ docstatus: 1, open_status: 'Open', is_delivered: 0 }"
					placeholder="Search open Work Order…"
					force-selection
					:disabled="creating"
				/>
			</div>

			<div class="make-dc-locations">
				<div class="make-dc-field">
					<label>From Location <span>*</span></label>
					<LinkField
						v-model="form.fromLocation"
						target-doctype="Supplier"
						:filters="{ disabled: 0 }"
						placeholder="Search From Location…"
						force-selection
						:disabled="creating"
					/>
				</div>

				<div class="make-dc-field">
					<label>To Location <span>*</span></label>
					<LinkField
						v-model="form.toLocation"
						target-doctype="Supplier"
						:filters="{ disabled: 0 }"
						placeholder="Search To Location…"
						force-selection
						:disabled="creating"
					/>
				</div>
			</div>

			<p class="make-dc-hint">
				The draft DC will use the Stock Entry quantities and link every item to the selected Work Order.
			</p>
		</div>

		<template #footer>
			<Button
				label="Cancel"
				severity="secondary"
				text
				:disabled="creating"
				@click="emit('update:visible', false)"
			/>
			<Button
				label="Make DC"
				icon="pi pi-send"
				:loading="creating"
				:disabled="!canCreate"
				@click="makeDeliveryChallan"
			/>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import LinkField from "@/components/LinkField.vue"
import { callMethod } from "@/api/client"

const props = defineProps({
	visible: { type: Boolean, default: false },
	stockEntry: { type: String, required: true },
	fromLocation: { type: String, default: "" },
	toLocation: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "created"])

const form = reactive({
	workOrder: "",
	fromLocation: "",
	toLocation: "",
})
const creating = ref(false)
const errorMessage = ref("")

const canCreate = computed(
	() => !!form.workOrder && !!form.fromLocation && !!form.toLocation && !creating.value,
)

watch(
	() => props.visible,
	(open) => {
		if (!open) return
		form.workOrder = ""
		form.fromLocation = props.fromLocation || ""
		form.toLocation = props.toLocation || ""
		errorMessage.value = ""
	},
)

async function makeDeliveryChallan() {
	if (!canCreate.value) return
	creating.value = true
	errorMessage.value = ""
	try {
		const result = await callMethod("essdee_yrp.api.stock_entry.make_delivery_challan", {
			stock_entry: props.stockEntry,
			work_order: form.workOrder,
			from_location: form.fromLocation,
			to_location: form.toLocation,
		})
		if (!result?.name) throw new Error("The Delivery Challan was not created.")
		emit("update:visible", false)
		emit("created", result.name)
	} catch (error) {
		errorMessage.value = error?.message || "Could not create the Delivery Challan."
	} finally {
		creating.value = false
	}
}
</script>

<style scoped>
.make-dc-form {
	display: grid;
	gap: 18px;
}
.make-dc-locations {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 16px;
}
.make-dc-field {
	display: grid;
	gap: 7px;
}
.make-dc-field label {
	font-size: 12px;
	font-weight: 700;
	letter-spacing: 0.02em;
	color: var(--esd-text-700);
}
.make-dc-field label span {
	color: var(--p-red-500);
}
.make-dc-hint {
	margin: 0;
	font-size: 12.5px;
	line-height: 1.5;
	color: var(--esd-muted);
}
@media (max-width: 600px) {
	.make-dc-locations {
		grid-template-columns: 1fr;
	}
}
</style>
