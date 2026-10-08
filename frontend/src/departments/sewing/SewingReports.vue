<template>
	<SewingWorkspaceShell title="Reports" section="reports" v-slot="{ supplier }">
		<section data-sewing-destination="reports" aria-label="Sewing Reports workspace">
			<p class="erp-empty-state">Sewing Unit: {{ supplier }}</p>
		</section>
	</SewingWorkspaceShell>
</template>

<script setup>
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
</script>
