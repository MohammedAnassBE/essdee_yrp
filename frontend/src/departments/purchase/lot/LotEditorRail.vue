<template>
	<div v-if="!lotId" class="lot-documents-rail"><section class="lot-documents-section"><div class="lot-documents-empty"><i class="pi pi-inbox" /><span>Linked purchase documents appear after the Lot is saved.</span></div></section></div>
	<LotDocumentsRail v-else ref="rail" :documents="documents" :loading="loading" :error="error" @retry="load" @open="openDocument" />
	<LotDocumentDialog v-if="lotId" v-model:visible="visible" :lot="lotId" :doctype="selected.doctype" :name="selected.name" @hide="rail?.restoreFocus()" />
</template>
<script setup>
import { onBeforeUnmount, ref } from "vue"
import { getLotDocuments } from "../../../api/purchase.js"
import LotDocumentDialog from "./LotDocumentDialog.vue"
import LotDocumentsRail from "./LotDocumentsRail.vue"
const props = defineProps({ lotId: { type: String, default: "" } })
const rail = ref(null)
const documents = ref({})
const loading = ref(false)
const error = ref("")
const visible = ref(false)
const selected = ref({ doctype: "", name: "" })
let sequence = 0
async function load() {
	if (!props.lotId) return
	const request = ++sequence
	loading.value = true
	error.value = ""
	try {
		const result = await getLotDocuments(props.lotId)
		if (request === sequence) documents.value = result
	} catch (reason) { if (request === sequence) error.value = reason.message }
	finally { if (request === sequence) loading.value = false }
}
function openDocument(document) { selected.value = document; visible.value = true }
onBeforeUnmount(() => { ++sequence })
load()
</script>
