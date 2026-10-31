<template>
	<span
		v-tooltip.bottom="{ value: user.tooltip, class: 'app-user-avatar-tooltip' }"
		class="app-user-avatar"
		:class="showImage ? '' : `app-user-avatar--tone-${user.tone}`"
		role="img"
		:aria-label="user.tooltip.replaceAll('\n', ', ')"
		tabindex="0"
	>
		<img v-if="showImage" :src="user.image" alt="" @error="imageFailed = true" />
		<span v-else aria-hidden="true">{{ user.initials }}</span>
	</span>
</template>

<script setup>
import Tooltip from "primevue/tooltip"
import { computed, ref } from "vue"

import { getSessionUser } from "./sessionUser.js"

const vTooltip = Tooltip
const user = getSessionUser()
const imageFailed = ref(false)
const showImage = computed(() => Boolean(user.image) && !imageFailed.value)
</script>
