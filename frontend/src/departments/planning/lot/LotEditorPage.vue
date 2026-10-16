<template>
	<DepartmentPage title="Lot" back-to="/planning/lots" back-label="Lots" :show-title="false" flat full-width inline-navigation>
		<LotEditor :key="lotId || 'new'" :lot-id="lotId" />
	</DepartmentPage>
</template>
<script setup>
import DepartmentPage from "../../../components/DepartmentPage.vue"
import LotEditor from "./LotEditor.vue"
defineProps({ lotId: { type: String, default: "" } })
</script>
