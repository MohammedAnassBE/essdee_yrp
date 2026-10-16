<template>
	<div class="ipd-section" :data-ipd-section="sectionKey">
		<div v-if="$slots.actions" class="ipd-section__actions"><slot name="actions" /></div>
		<p v-if="collapsed && reason" class="erp-help-text">{{ reason }}</p>
		<div v-if="!collapsed" class="ipd-section__body"><slot /></div>
	</div>
</template>

<script setup>
defineProps({
	sectionKey: { type: String, required: true },
	collapsed: Boolean,
	reason: { type: String, default: '' },
})
</script>
