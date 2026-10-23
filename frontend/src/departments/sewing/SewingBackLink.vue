<template>
	<BackLink :to="to" :label="label" />
</template>

<script setup>
import BackLink from "../../components/navigation/BackLink.vue"

defineProps({
	to: { type: [String, Object], required: true },
	label: { type: String, required: true },
})
</script>
