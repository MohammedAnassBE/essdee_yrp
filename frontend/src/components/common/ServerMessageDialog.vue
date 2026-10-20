<template>
	<Dialog :visible="batches.length > 0" modal :header="current.title" class="erp-dialog--sm server-message-dialog" @update:visible="(open) => { if (!open) close() }">
		<div class="server-message-dialog__body" role="status">
			<p v-for="(entry, index) in current.messages" :key="index" :class="`server-message-dialog__message is-${entry.indicator || 'blue'}`">{{ entry.message }}</p>
		</div>
		<template #footer>
			<Button label="OK" autofocus @click="close" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, ref } from "vue"
import { setServerMessageHandler } from "../../api/serverMessages.js"

const toastSeverity = { green: "success", red: "error", orange: "warn", yellow: "warn" }
const toast = useToast()
const batches = ref([])

const current = computed(() => {
	const messages = batches.value[0] || []
	const titles = new Set(messages.map((entry) => entry.title))
	return { messages, title: titles.size === 1 ? [...titles][0] : "Message" }
})

function show(messages) {
	for (const entry of messages.filter((item) => item.alert)) {
		toast.add({ severity: toastSeverity[entry.indicator] || "info", summary: entry.message, life: 5000 })
	}
	const dialogMessages = messages.filter((item) => !item.alert)
	if (dialogMessages.length) batches.value = [...batches.value, dialogMessages]
}

function close() {
	batches.value = batches.value.slice(1)
}

setServerMessageHandler(show)
onBeforeUnmount(() => setServerMessageHandler(null))
</script>

<style scoped>
.server-message-dialog__body { display: grid; gap: var(--erp-space-3, 12px); }
.server-message-dialog__message { margin: 0; white-space: pre-line; overflow-wrap: anywhere; }
.server-message-dialog__message + .server-message-dialog__message { border-top: 1px solid var(--erp-border, var(--p-content-border-color)); padding-top: var(--erp-space-3, 12px); }
.server-message-dialog__message.is-red { color: var(--erp-danger, var(--p-red-600)); }
</style>
