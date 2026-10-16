<template>
	<SewingWorkspaceShell title="Sewing Plan" section="plans" :back-to="backTo" :back-label="backLabel" v-slot="{ supplier, capabilities }">
		<SewingPlanWorkspace :key="supplier" :capabilities="capabilities" />
	</SewingWorkspaceShell>
</template>

<script setup>
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
import SewingPlanWorkspace from "./SewingPlanWorkspace.vue"
defineProps({
	backTo: { type: String, default: "" },
	backLabel: { type: String, default: "" },
})
</script>
