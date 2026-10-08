<template>
	<SewingWorkspaceShell title="Sewing Plan" section="plans" v-slot="{ supplier, capabilities }">
		<SewingPlanWorkspace :key="supplier" :capabilities="capabilities" />
	</SewingWorkspaceShell>
</template>

<script setup>
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
import SewingPlanWorkspace from "./SewingPlanWorkspace.vue"
</script>
