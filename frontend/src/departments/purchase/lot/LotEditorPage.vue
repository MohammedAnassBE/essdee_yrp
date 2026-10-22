<template>
	<DepartmentPage title="Lot" back-to="/purchase/lots" back-label="Lots" :show-title="false" flat full-width inline-navigation>
		<LotEditor :key="lotId || `new:${$route.query.duplicate_from || ''}`" :lot-id="lotId" />
	</DepartmentPage>
</template>
<script setup>
import DepartmentPage from "../../../components/DepartmentPage.vue"
import LotEditor from "./LotEditor.vue"
defineProps({ lotId: { type: String, default: "" } })
</script>
