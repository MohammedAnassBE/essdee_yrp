<template>
	<DepartmentPage title="Bulk LaySheets" accent="#079669" back-to="/cutting/bulk-lay-sheets" back-label="Bulk LaySheets" :show-title="false" flat full-width>
		<div class="bulk-editor-page erp-workspace"><BulkSetupEditor @saved="saved" @cancel="router.push('/cutting/bulk-lay-sheets')" /></div>
	</DepartmentPage>
</template>

<script setup>
import { useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import BulkSetupEditor from "./cutting/bulk/BulkSetupEditor.vue"

const router = useRouter()
function saved(payload) {
	const name = payload?.record?.name
	if (name) router.replace({ name: "cutting-bulk-lay-sheet", params: { bulkLaySheetsId: name } })
}
</script>

<style scoped>
.bulk-editor-page { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; }
</style>
