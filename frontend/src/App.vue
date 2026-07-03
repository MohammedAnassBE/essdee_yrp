<template>
	<Toast position="top-right" />
	<ConfirmDialog />
	<router-view />
</template>

<script setup>
import Toast from "primevue/toast"
import ConfirmDialog from "primevue/confirmdialog"
</script>

<!-- Global (unscoped): Q19 placed the toast top-right; offset it below the 56px
     topbar so a visible toast never overlaps the role chip + logout button. -->
<style>
.p-toast.p-toast-top-right {
	top: 68px;
}
</style>
