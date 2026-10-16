<template>
	<DepartmentPage title="Bulk LaySheets" back-to="/cutting/bulk-lay-sheets" back-label="Bulk LaySheets" :show-title="false" flat full-width>
		<div class="bulk-editor-page erp-workspace"><BulkSetupEditor @saved="saved" @cancel="router.push('/cutting/bulk-lay-sheets')" /></div>
	</DepartmentPage>
</template>

<script setup>
import { useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import BulkSetupEditor from "./cutting/bulk/BulkSetupEditor.vue"

const router = useRouter()
function saved(payload) {
	const name = payload?.record?.name
	if (name) router.replace({ name: "cutting-bulk-lay-sheet", params: { bulkLaySheetsId: name }, state: preserveListNavigationState(name) })
}
</script>

<style scoped>
.bulk-editor-page { width: 100%; min-width: 0; }
</style>
