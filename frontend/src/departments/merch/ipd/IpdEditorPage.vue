<template>
	<DepartmentPage title="Item Production Detail" back-to="/merch/item-production-details" back-label="Item Production Details" :show-title="false" flat full-width inline-navigation>
		<IpdEditor :ipd-id="ipdId" />
	</DepartmentPage>
</template>

<script setup>
import DepartmentPage from "../../../components/DepartmentPage.vue"
import IpdEditor from "./IpdEditor.vue"

defineProps({ ipdId: { type: String, default: "" } })
</script>
