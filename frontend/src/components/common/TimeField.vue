<template>
	<TemporalFieldBase v-bind="$attrs" mode="time" />
</template>

<script setup>
import TemporalFieldBase from "./TemporalFieldBase.vue"

defineOptions({ inheritAttrs: false })
</script>
