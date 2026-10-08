<template>
	<SewingWorkspaceShell title="Sewing Plan" section="plans" v-slot="{ supplier }">
		<section data-sewing-destination="plans" aria-label="Sewing Plan workspace">
			<p class="erp-empty-state">Sewing Unit: {{ supplier }}</p>
		</section>
	</SewingWorkspaceShell>
</template>

<script setup>
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
</script>
