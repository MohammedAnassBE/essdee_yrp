<template>
	<div class="erp-empty-state lot-empty">
		<div>
			<i class="pi pi-inbox" />
			<strong>{{ title }}</strong>
			<span>{{ reason }}</span>
		</div>
	</div>
</template>

<script setup>
defineProps({ title: { type: String, required: true }, reason: { type: String, required: true } })
</script>
