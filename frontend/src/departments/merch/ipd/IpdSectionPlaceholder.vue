<template>
	<IpdSection :section-key="sectionKey">
		<div class="erp-empty-state erp-empty-state--compact">
			<i class="pi pi-hammer" aria-hidden="true" />
			<strong>This section is not available on the web yet.</strong>
			<span>Open the IPD in Desk to change it.</span>
		</div>
	</IpdSection>
</template>

<script setup>
import IpdSection from "./IpdSection.vue"

defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
</script>
