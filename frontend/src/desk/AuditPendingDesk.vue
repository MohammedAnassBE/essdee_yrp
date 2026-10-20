<template>
	<div class="audit-pending-desk"><AuditPendingFinishingPlans desk /></div>
</template>

<script setup>
import AuditPendingFinishingPlans from "../departments/accounts/reports/AuditPendingFinishingPlans.vue"
</script>

<style scoped>
/* Keep Desk's theme local to this page; the same dashboard uses Espresso on /web. */
.audit-pending-desk {
	--erp-font-family: var(--font-stack, Inter, sans-serif);
	--erp-font-size-min: 11px;
	--erp-font-size-caption: 12px;
	--erp-font-size-label: 12px;
	--erp-font-size-table: 13px;
	--erp-font-size-md: 15px;
	--erp-font-size-section: 16px;
	--erp-font-weight-semibold: 600;
	--erp-font-weight-bold: 700;
	--erp-surface: var(--fg-color, #fff);
	--erp-surface-raised: var(--fg-color, #fff);
	--erp-surface-soft: var(--subtle-fg, #fcfbf8);
	--erp-surface-muted: var(--subtle-fg, #f4f2ec);
	--erp-border: var(--border-color, #e8e5dc);
	--erp-border-subtle: var(--border-color, #efede6);
	--erp-border-strong: var(--dark-border-color, #d6d2c6);
	--erp-text: var(--text-color, #1f1e1b);
	--erp-text-secondary: var(--text-color, #3b3a36);
	--erp-text-muted: var(--text-muted, #6e6a5f);
	--erp-text-subtle: var(--text-light, #8a867b);
	--erp-accent: var(--surface-gray-10, #171717);
	--erp-accent-hover: var(--surface-gray-9, #262626);
	--erp-accent-soft: var(--control-bg, #f1ebe9);
	--erp-accent-border: var(--border-color, #ebc0ae);
	--erp-on-accent: var(--ink-base, #fff);
	--erp-warning: var(--ink-yellow-8, #92400e);
	--erp-warning-soft: var(--surface-yellow-2, #fbf0da);
	--erp-attention-border: var(--outline-yellow-2, #f3d9a6);
	--erp-danger: var(--ink-red-8, #be123c);
	--erp-danger-soft: var(--surface-red-2, #fbe7e7);
	--erp-success-text: var(--ink-green-8, #147a48);
	--erp-success-soft: var(--surface-green-2, #e4f4eb);
	--erp-space-1: 4px;
	--erp-space-2: 8px;
	--erp-space-3: 12px;
	--erp-space-4: 16px;
	--erp-space-5: 20px;
	--erp-control-height: 38px;
	--erp-control-radius: 7px;
	--erp-panel-radius: 10px;
	--erp-focus-ring: 0 0 0 2px var(--erp-accent-border);
	--erp-shadow-card: none;
	padding: 16px 0 24px;
}
.audit-pending-desk :deep(.erp-card) { border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.audit-pending-desk :deep(.erp-command-bar) { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.audit-pending-desk :deep(.erp-action-button) { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 36px; padding: 7px 12px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); color: var(--erp-text); background: var(--erp-surface); font: inherit; font-size: 13px; cursor: pointer; }
.audit-pending-desk :deep(.erp-action-button--primary) { color: var(--erp-on-accent); border-color: var(--erp-accent); background: var(--erp-accent); }
.audit-pending-desk :deep(.erp-action-button--primary:not(:disabled):hover) { border-color: var(--erp-accent-hover); background: var(--erp-accent-hover); }
.audit-pending-desk :deep(.erp-action-button:disabled) { opacity: .6; cursor: wait; }
.audit-pending-desk :deep(.report-shell__message) { padding: 12px; color: var(--erp-danger); background: var(--erp-danger-soft); }
.audit-pending-desk :deep(.p-skeleton) { background: var(--erp-surface-muted); }
</style>
