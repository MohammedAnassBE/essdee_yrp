<template>
	<SewingWorkspaceShell title="Reports" section="reports" :embedded="embedded" v-slot="{ supplier, capabilities }">
		<SewingReportsWorkspace :key="supplier" :capabilities="capabilities" />
	</SewingWorkspaceShell>
</template>

<script setup>
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
import SewingReportsWorkspace from "./SewingReportsWorkspace.vue"

defineProps({ embedded: { type: Boolean, default: false } })
</script>
