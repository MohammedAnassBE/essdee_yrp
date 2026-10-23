<template>
	<FabricStockOperationDialog v-if="editing" :visible="visible" :operation="operation" :name="editorName" :expected-modified="editorModified" :new-defaults="newDefaults" @update:visible="emit('update:visible', $event)" @changed="emit('changed', $event)" />
	<DocumentTransactionDialog v-else :visible="visible" :doctype="doctype" :name="name" @update:visible="viewVisibility" @changed="emit('changed', $event)" @edit="edit" @amended="edit" />
</template>

<script setup>
import { ref, watch } from "vue"
import DocumentTransactionDialog from "../../components/documents/DocumentTransactionDialog.vue"
import FabricStockOperationDialog from "./FabricStockOperationDialog.vue"

/** Opens an existing stock document: drafts in the editor, submitted or cancelled ones read-only. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	operation: { type: String, default: "stock_entry" },
	doctype: { type: String, default: "YRP Stock Entry" },
	name: { type: String, default: "" },
	docstatus: { type: Number, default: 0 },
	expectedModified: { type: String, default: "" },
	newDefaults: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])
const editing = ref(false)
const editorName = ref("")
const editorModified = ref("")

watch(() => [props.visible, props.name, props.docstatus], ([visible]) => {
	if (!visible) return
	editing.value = !props.name || Number(props.docstatus) === 0
	editorName.value = props.name
	editorModified.value = props.expectedModified
}, { immediate: true })

function edit(payload) {
	const record = payload?.record || payload || {}
	editorName.value = record.name || props.name
	editorModified.value = record.modified || ""
	editing.value = true
}
function viewVisibility(value) {
	if (!value && editing.value) return
	emit("update:visible", value)
}
</script>
