<template>
	<span class="pd-status" :class="`pd-status--${tone}`" :data-lot-status="status">{{ status }}</span>
</template>

<script setup>
import { computed } from "vue"
import { LADDER_TONE } from "./dashboardRows.js"

/** Lot ladder status pill; "No Work Order yet" is neutral. */
const props = defineProps({ status: { type: String, required: true } })
const tone = computed(() => LADDER_TONE[props.status] || "neutral")
</script>
