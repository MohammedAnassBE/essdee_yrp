<template>
	<TemporalFieldBase v-bind="$attrs" mode="date" />
</template>

<script setup>
import TemporalFieldBase from "./TemporalFieldBase.vue"

defineOptions({ inheritAttrs: false })
</script>
