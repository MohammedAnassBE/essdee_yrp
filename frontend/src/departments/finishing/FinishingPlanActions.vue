<template>
	<div v-if="items.length" class="finishing-actions" role="group" aria-label="Finishing Plan actions">
		<Button
			label="More Actions"
			icon="pi pi-chevron-down"
			icon-pos="right"
			severity="secondary"
			outlined
			:loading="busy"
			aria-haspopup="menu"
			aria-controls="finishing-plan-more-actions"
			:aria-expanded="menuOpen"
			@click="menu?.toggle($event)"
		/>
		<Menu id="finishing-plan-more-actions" ref="menu" :model="items" popup :base-z-index="5000" @show="menuOpen = true" @hide="menuOpen = false" />
	</div>

	<Dialog v-model:visible="printOpen" modal header="Select Size to Print Finishing Inward" class="erp-dialog--sm">
		<form class="finishing-actions__form" @submit.prevent="printInward">
			<label class="common-field">
				<span>Size</span>
				<Select v-model="printSize" :options="workspace.primary_values || []" placeholder="Select size" aria-label="Size" fluid />
			</label>
		</form>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="printing" @click="printOpen = false" />
			<Button label="Print" icon="pi pi-print" :loading="printing" :disabled="!printSize" @click="printInward" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="printError" title="Finishing Inward print failed" @dismiss="printError = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Menu from "primevue/menu"
import Select from "primevue/select"
import { computed, ref } from "vue"

import { prepareFinishingInwardPrint } from "../../api/finishing.js"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"

const props = defineProps({
	workspace: { type: Object, required: true },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["command", "entry"])
const confirmAction = useActionConfirmation()
const menu = ref(null)
const menuOpen = ref(false)
const printOpen = ref(false)
const printSize = ref("")
const printing = ref(false)
const printError = ref("")
const confirmations = {
	request_audit: { label: "Audit Request", icon: "pi pi-send", message: "Send this Finishing Plan to Accounts for audit?" },
	complete_audit: { label: "Audit Completed", icon: "pi pi-verified", message: "Confirm that Accounts has completed the audit for this Finishing Plan?" },
	complete_ocr: { label: "Complete OCR", icon: "pi pi-check-circle", message: "Complete OCR for this audited Finishing Plan? It will be locked for new entries." },
}
const items = computed(() => {
	const actions = props.workspace.actions || {}
	const options = props.workspace.entry_options || {}
	const disabled = props.busy
	return [
		...Object.entries(confirmations).filter(([key]) => actions[key]).map(([key, action]) => ({ label: action.label, icon: action.icon, disabled, command: () => confirm(key) })),
		actions.fetch_rejected_quantity ? { label: "Fetch Rejected Quantity", icon: "pi pi-refresh", disabled, command: () => emit("command", "fetch_rejected_quantity") } : null,
		actions.print_inward ? { label: "Print Finishing Inward", icon: "pi pi-print", disabled, command: openPrint } : null,
		actions.create_entries && options.alternative_items?.length ? { label: "Create Alternative Plan", icon: "pi pi-clone", disabled, command: () => emit("entry", "create_alternative_plan") } : null,
		actions.create_entries && options.alternate_lots?.length ? { label: "Update Quantity", icon: "pi pi-sync", disabled, command: () => emit("entry", "update_alternative_quantity") } : null,
	].filter(Boolean)
})

function confirm(command) {
	const action = confirmations[command]
	confirmAction({
		header: `${action.label}?`,
		message: action.message,
		acceptLabel: action.label,
		acceptIcon: action.icon,
		acceptSeverity: "primary",
		rejectLabel: "Not now",
		accept: () => emit("command", command),
	})
}

function openPrint() {
	printSize.value = ""
	printOpen.value = true
}

async function printInward() {
	if (!printSize.value || printing.value) return
	printing.value = true
	try {
		const { url } = await prepareFinishingInwardPrint(props.workspace.record.name, printSize.value)
		window.open(url, "_blank", "noopener")
		printOpen.value = false
	} catch (reason) {
		printError.value = reason?.message || "Unable to print Finishing Inward."
	} finally {
		printing.value = false
	}
}
</script>

<style scoped>
.finishing-actions { display: inline-flex; }
.finishing-actions__form { display: grid; gap: 12px; }
</style>
