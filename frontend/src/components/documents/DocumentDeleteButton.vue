<template>
	<template v-if="canDelete">
		<Button type="button" class="document-delete-button" label="Delete" icon="pi pi-trash" severity="danger" text :disabled="disabled || busy" @click="confirmVisible = true" />
		<DocumentConfirmationDialog v-model:visible="confirmVisible" title="Delete document?" :message="`Permanently delete ${documentLabel || doctype} ${name}?`" confirm-label="Delete" confirm-icon="pi pi-trash" :busy="busy" @confirm="remove" />
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</template>
</template>

<script setup>
import Button from "primevue/button"
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { deleteDoc } from "../../api/frappe.js"
import { useDocumentPermissions } from "../../composables/useDocumentPermissions.js"
import { canDeleteDocument, documentDeletedToast, getDeleteRedirectTarget } from "../../utils/documentDelete.js"
import { usePageNavigation } from "../navigation/pageNavigationContext.js"
import DocumentConfirmationDialog from "./DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "./DocumentErrorDialog.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	documentLabel: { type: String, default: "" },
	name: { type: String, default: "" },
	docstatus: { type: [Number, String], default: 0 },
	disabled: { type: Boolean, default: false },
	redirectTo: { type: String, default: "" },
	redirect: { type: Boolean, default: true },
})
const emit = defineEmits(["deleted"])
const router = useRouter()
const toast = useToast()
const navigation = usePageNavigation()
const permissions = useDocumentPermissions(() => [props.doctype, props.name, props.docstatus])
const confirmVisible = ref(false)
const busy = ref(false)
const error = ref("")
const canDelete = computed(() => canDeleteDocument({ name: props.name, docstatus: props.docstatus, permissions: permissions.value }))
let active = true

onBeforeUnmount(() => { active = false })

watch(() => [props.doctype, props.name, props.docstatus], () => {
	confirmVisible.value = false
	error.value = ""
})

async function remove() {
	if (props.disabled || busy.value || !canDelete.value) return
	const { doctype, name, documentLabel } = props
	busy.value = true
	error.value = ""
	try {
		await deleteDoc(doctype, name)
	} catch (reason) {
		if (!active) return
		if (doctype === props.doctype && name === props.name) error.value = reason?.message || "Unable to delete this document."
		return
	} finally {
		if (active) {
			busy.value = false
			confirmVisible.value = false
		}
	}
	if (!active || doctype !== props.doctype || name !== props.name) return
	emit("deleted")
	if (props.redirect) await router.replace(getDeleteRedirectTarget(props.redirectTo, navigation?.backTo?.value))
	toast.add(documentDeletedToast(doctype, name, documentLabel))
}
</script>

<style scoped>
.document-delete-button.p-button { min-height: var(--erp-control-height); border-radius: var(--erp-control-radius); }
</style>
