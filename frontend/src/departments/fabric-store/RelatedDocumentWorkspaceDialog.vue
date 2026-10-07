<template>
	<Dialog
		:visible="visible"
		modal
		maximizable
		:closable="!domainComponent"
		:close-on-escape="!domainComponent"
		:header="dialogTitle"
		class="related-document-workspace-dialog erp-entity-dialog"
		:style="{ width: 'min(96vw, 1540px)' }"
		:content-style="{ padding: 0, overflow: 'hidden', scrollbarGutter: 'auto' }"
		@update:visible="requestVisibility"
	>
		<component
			:is="domainComponent"
			v-if="domainComponent"
			presentation="embedded"
			:name="name"
			:source-context="sourceContext"
			@changed="handleChanged"
			@closed="close"
		/>
		<div v-else class="related-document-workspace-dialog__unsupported">
			<Message severity="error" :closable="false">{{ doctype || "This document type" }} is not supported in the Fabric Store workspace.</Message>
			<Button label="Close" severity="secondary" @click="close" />
		</div>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { computed, ref, watch } from "vue"

import FabricDeliveryChallan from "../FabricDeliveryChallan.vue"
import FabricGoodsReceivedNote from "../FabricGoodsReceivedNote.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, required: true },
	name: { type: String, default: "" },
	sourceContext: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed", "closed"])
const components = {
	"YRP Delivery Challan": FabricDeliveryChallan,
	"YRP Goods Received Note": FabricGoodsReceivedNote,
}
const documentLabels = {
	"YRP Delivery Challan": "Delivery Challan",
	"YRP Goods Received Note": "Goods Received Note",
}
const domainComponent = computed(() => components[props.doctype] || null)
const displayName = ref(props.name)
const dialogTitle = computed(() => `${documentLabels[props.doctype] || props.doctype || "Related document"}${displayName.value ? ` · ${displayName.value}` : " · New"}`)

function requestVisibility(value) { if (!value) close() }
function close() { emit("update:visible", false); emit("closed") }
function handleChanged(payload) {
	if (payload?.record?.name) displayName.value = payload.record.name
	emit("changed", payload)
}
watch(() => [props.visible, props.name], ([visible, name], previous) => {
	if (visible && (!previous?.[0] || name !== previous?.[1])) displayName.value = name
})
</script>

<style scoped>
:global(.related-document-workspace-dialog .p-dialog-content) { display: flex; min-height: 0; flex-direction: column; }
.related-document-workspace-dialog__unsupported { display: grid; min-height: 180px; place-content: center; justify-items: center; gap: var(--erp-space-3); padding: var(--erp-space-4); text-align: center; background: color-mix(in srgb, var(--erp-surface-soft) 70%, white); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }
@media (max-width: 620px) {
	:global(.related-document-workspace-dialog .p-dialog-content) { position: relative; display: block; }
	:global(.related-document-workspace-dialog .delivery-challan-workspace--embedded),
	:global(.related-document-workspace-dialog .goods-received-note-workspace--embedded) { position: absolute; inset: 0; display: flex; width: auto; min-height: 0; flex-direction: column; }
	:global(.related-document-workspace-dialog .p-dialog-maximize-button) { display: none; }
}
</style>
