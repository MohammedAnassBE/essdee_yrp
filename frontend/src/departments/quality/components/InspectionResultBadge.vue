<template>
	<strong v-if="result" class="quality-result-badge" :class="`quality-result-badge--${result.toLowerCase()}`">
		<i :class="icons[result] || 'pi pi-info-circle'" aria-hidden="true" />{{ result }}
	</strong>
</template>

<script setup>
defineProps({ result: { type: String, default: "" } })
const icons = { Pass: "pi pi-check-circle", Fail: "pi pi-times-circle", Hold: "pi pi-pause-circle" }
</script>
