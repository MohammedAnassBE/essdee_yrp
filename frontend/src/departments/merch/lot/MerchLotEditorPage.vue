<template>
	<DepartmentPage
		title="Lot"
		back-to="/merch/lots"
		back-label="Lots"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<MerchLotEditor
			:key="lotId || `new:${$route.query.duplicate_from || ''}`"
			:lot-id="lotId"
		/>
	</DepartmentPage>
</template>
<script setup>
import DepartmentPage from "../../../components/DepartmentPage.vue"
import MerchLotEditor from "./MerchLotEditor.vue"
defineProps({ lotId: { type: String, default: "" } })
</script>
