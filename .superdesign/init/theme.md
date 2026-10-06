# Theme

Bright Ledger uses a bright neutral canvas, white data surfaces, a single emerald action/focus ramp, and saffron only for pending or action-required attention. Dense desktop controls remain 32–38px, mobile targets expand, and all motion respects `prefers-reduced-motion`. The raw global CSS below is the source of truth.

## frontend/src/styles/enterprise.css

```css
:root {
	color-scheme: light;
	--erp-font-family: Inter, "SF Pro Text", "Segoe UI Variable", "Segoe UI", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
	--erp-font-size-min: 11px;
	--erp-font-size-caption: 12px;
	--erp-font-size-body: 14px;
	--erp-font-size-section: 16px;
	--erp-font-size-title: 24px;
	--erp-font-weight-regular: 400;
	--erp-font-weight-medium: 500;
	--erp-font-weight-semibold: 600;
	--erp-font-weight-bold: 700;
	--erp-line-height-tight: 1.2;
	--erp-line-height-body: 1.4;
	--erp-line-height-relaxed: 1.55;

	/* Bright Ledger neutrals keep dense ERP screens crisp without feeling clinical. */
	--erp-bg: #f7f8fa;
	--erp-canvas: #f7f8fa;
	--erp-surface: #ffffff;
	--erp-surface-raised: #ffffff;
	--erp-surface-soft: #fbfcfd;
	--erp-surface-muted: #f1f3f5;
	--erp-surface-hover: #f4f6f8;
	--erp-mint: #ecfdf5;
	--erp-border-subtle: #eaecf0;
	--erp-border: #dfe3e8;
	--erp-border-strong: #cbd2d9;
	--erp-text: #101828;
	--erp-text-secondary: #344054;
	--erp-text-muted: #667085;
	--erp-text-subtle: #8a94a6;

	/* A single emerald ramp carries brand, selection, and primary action states. */
	--erp-emerald-50: #ecfdf5;
	--erp-emerald-100: #d1fae5;
	--erp-emerald-200: #a7f3d0;
	--erp-emerald-300: #6ee7b7;
	--erp-emerald-400: #34d399;
	--erp-emerald-500: #10b981;
	--erp-emerald-600: #059669;
	--erp-emerald-700: #047857;
	--erp-emerald-800: #065f46;
	--erp-emerald-900: #064e3b;
	--erp-accent: var(--erp-emerald-600);
	--erp-accent-hover: var(--erp-emerald-700);
	--erp-accent-dark: var(--erp-emerald-800);
	--erp-accent-strong: var(--erp-emerald-700);
	--erp-accent-soft: var(--erp-emerald-50);
	--erp-accent-border: var(--erp-emerald-200);

	/* Saffron is deliberately reserved for attention, never primary actions. */
	--erp-attention: #fc8019;
	--erp-attention-hover: #e86f0c;
	--erp-attention-soft: #fff4e8;
	--erp-attention-border: #fed7aa;
	--erp-attention-text: #9a4800;
	--erp-success: #039855;
	--erp-success-soft: #ecfdf3;
	--erp-danger: #d92d20;
	--erp-danger-soft: #fef3f2;
	--erp-warning: var(--erp-attention-text);
	--erp-warning-soft: var(--erp-attention-soft);
	--erp-info: #175cd3;
	--erp-info-soft: #eff8ff;

	--erp-space-1: 4px;
	--erp-space-2: 8px;
	--erp-space-3: 12px;
	--erp-space-4: 16px;
	--erp-space-5: 20px;
	--erp-space-6: 24px;
	--erp-space-7: 32px;
	--erp-space-8: 40px;
	--erp-control-radius: 9px;
	--erp-panel-radius: 14px;
	--erp-pill-radius: 999px;
	--erp-radius-sm: var(--erp-control-radius);
	--erp-radius-md: var(--erp-panel-radius);
	--erp-radius-lg: 18px;
	--erp-control-height-compact: 32px;
	--erp-control-height: 38px;
	--erp-shadow-xs: 0 1px 2px rgb(16 24 40 / 5%);
	--erp-shadow-sm: 0 1px 3px rgb(16 24 40 / 7%), 0 1px 2px rgb(16 24 40 / 4%);
	--erp-shadow-md: 0 10px 28px rgb(16 24 40 / 9%), 0 2px 7px rgb(16 24 40 / 5%);
	--erp-shadow-lg: 0 24px 64px rgb(16 24 40 / 16%), 0 8px 20px rgb(16 24 40 / 7%);
	--erp-shadow-card: var(--erp-shadow-sm);
	--erp-shadow-dialog: var(--erp-shadow-lg);
	--erp-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
	--erp-ease-standard: cubic-bezier(0.2, 0, 0, 1);
	--erp-transition-fast: 140ms var(--erp-ease-standard);
	--erp-transition-base: 200ms var(--erp-ease-out);
	--erp-transition-slow: 320ms var(--erp-ease-out);
	--erp-layer-content: 1;
	--erp-layer-sticky: 20;
	--erp-layer-overlay: 100;
	--erp-layer-dialog: 200;
	--erp-layer-toast: 300;
}

.erp-workspace {
	min-width: 0;
	color: var(--erp-text);
	font-family: var(--erp-font-family);
	font-size: var(--erp-font-size-body);
	line-height: var(--erp-line-height-body);
}

.erp-page-header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: var(--erp-space-4);
	margin-bottom: var(--erp-space-5);
}

.erp-page-header__eyebrow {
	margin: 0 0 var(--erp-space-1);
	color: var(--erp-accent);
	font-size: 0.7rem;
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: 0.12em;
	text-transform: uppercase;
}

.erp-page-header h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: clamp(1.55rem, 2vw, 2rem);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: -0.035em;
	line-height: 1.1;
}

.erp-page-header__description {
	max-width: 680px;
	margin: var(--erp-space-2) 0 0;
	color: var(--erp-text-muted);
	font-size: 0.86rem;
	line-height: 1.5;
}

.erp-command-bar {
	display: flex;
	align-items: center;
	gap: var(--erp-space-2);
	flex-wrap: wrap;
}

.erp-card {
	background: var(--erp-surface-raised);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-radius-lg);
	box-shadow: var(--erp-shadow-sm);
}

.erp-section-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
	min-height: 34px;
}

.erp-section-header h2,
.erp-section-header h3 {
	margin: 0;
	font-size: var(--erp-font-size-section);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: -0.01em;
}

.erp-count-badge {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	min-width: 23px;
	height: 20px;
	padding: 0 7px;
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	background: var(--erp-mint);
	border: 1px solid var(--erp-accent-border);
	border-radius: var(--erp-pill-radius);
}

.erp-tabs {
	min-width: 0;
	min-height: 0;
}

.erp-tabs .p-tablist-tab-list {
	background: transparent;
	border-color: var(--erp-border);
}

.erp-tabs .p-tab {
	padding: 0.82rem 1rem;
	color: var(--erp-text-muted);
	font-size: 0.82rem;
	font-weight: var(--erp-font-weight-semibold);
}

.erp-tabs .p-tab-active {
	color: var(--erp-accent);
}

.erp-tabs .p-tablist-active-bar {
	height: 2px;
	background: var(--erp-accent);
}

.erp-scroll-region {
	min-width: 0;
	min-height: 0;
	overflow: auto;
	scrollbar-gutter: stable;
}

.erp-table-wrap {
	width: 100%;
	overflow: auto;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-radius-md);
	scrollbar-gutter: stable;
}

.erp-data-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 13px;
}

.erp-data-table th {
	position: sticky;
	z-index: var(--erp-layer-content);
	top: 0;
	padding: 9px 10px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: 0.025em;
	text-align: left;
	text-transform: uppercase;
	white-space: nowrap;
	background: var(--erp-surface-muted);
	border-bottom: 1px solid var(--erp-border-strong);
}

.erp-data-table td {
	padding: 9px 10px;
	color: var(--erp-text-secondary);
	border-bottom: 1px solid var(--erp-border-subtle);
	vertical-align: middle;
}

.erp-data-table tbody tr:last-child td {
	border-bottom: 0;
}

.erp-data-table tbody tr:hover td {
	background: var(--erp-surface-hover);
}

.erp-number {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.erp-status {
	display: inline-flex;
	align-items: center;
	min-height: 22px;
	padding: 2px 8px;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-bold);
	background: var(--erp-surface-muted);
	border-radius: var(--erp-pill-radius);
}

.erp-status--success {
	color: var(--erp-accent-dark);
	background: var(--erp-success-soft);
}

.erp-status--warning {
	color: var(--erp-attention-text);
	background: var(--erp-attention-soft);
}

.erp-status--danger {
	color: var(--erp-danger);
	background: var(--erp-danger-soft);
}

.erp-empty-state {
	display: grid;
	min-height: 180px;
	padding: var(--erp-space-6);
	color: var(--erp-text-muted);
	font-size: 0.84rem;
	text-align: center;
	place-items: center;
}

.erp-dialog-body {
	min-width: 0;
	max-height: min(68dvh, 720px);
	overflow: auto;
	scrollbar-gutter: stable;
}

.erp-dialog-footer {
	display: flex;
	align-items: center;
	justify-content: flex-end;
	gap: var(--erp-space-2);
	padding-top: var(--erp-space-3);
}

.erp-field-label {
	display: block;
	margin-bottom: 5px;
	color: var(--erp-text-secondary);
	font-size: 0.7rem;
	font-weight: var(--erp-font-weight-semibold);
}

.erp-field-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--erp-space-3) var(--erp-space-4);
}

.erp-help-text {
	display: block;
	margin-top: 5px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	line-height: 1.35;
}

.erp-action-button.p-button {
	min-height: 34px;
	padding: 0.45rem 0.75rem;
	border-radius: var(--erp-radius-sm);
	font-size: 0.76rem;
	font-weight: var(--erp-font-weight-semibold);
}

.erp-action-button--primary.p-button {
	color: white;
	background: var(--erp-accent);
	border-color: var(--erp-accent);
}

.erp-action-button--primary.p-button:hover {
	background: var(--erp-accent-hover);
	border-color: var(--erp-accent-hover);
}

:where(button, a, input, select, textarea, [tabindex]):focus-visible {
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 28%, transparent);
	outline-offset: 2px;
}

.app-shell .p-button {
	min-height: var(--erp-control-height);
	border-radius: var(--erp-control-radius);
	font-family: var(--erp-font-family);
	font-size: 13px;
	font-weight: var(--erp-font-weight-semibold);
	transition:
		background var(--erp-transition-fast),
		border-color var(--erp-transition-fast),
		box-shadow var(--erp-transition-fast),
		color var(--erp-transition-fast),
		transform var(--erp-transition-fast);
}

.app-shell .p-button:not(.p-button-secondary):not(.p-button-success):not(.p-button-info):not(.p-button-warn):not(.p-button-danger):not(.p-button-contrast):not(.p-button-outlined):not(.p-button-text):not(.p-button-link) {
	color: #fff;
	background: var(--erp-accent);
	border-color: var(--erp-accent);
}

.app-shell .p-button:not(.p-button-secondary):not(.p-button-success):not(.p-button-info):not(.p-button-warn):not(.p-button-danger):not(.p-button-contrast):not(.p-button-outlined):not(.p-button-text):not(.p-button-link):not(:disabled):hover {
	color: #fff;
	background: var(--erp-accent-hover);
	border-color: var(--erp-accent-hover);
}

.app-shell .p-button:not(:disabled):active {
	transform: translateY(1px);
	transition-duration: 70ms;
}

.app-shell .p-button.p-button-sm {
	min-height: var(--erp-control-height-compact);
	font-size: var(--erp-font-size-caption);
}

.app-shell :where(
	.p-inputtext,
	.p-inputnumber-input,
	.p-select,
	.p-multiselect,
	.p-autocomplete-input,
	.erp-date-time-picker .p-datepicker-input
) {
	min-height: var(--erp-control-height);
	color: var(--erp-text);
	font-family: var(--erp-font-family);
	font-size: 13px;
	background: var(--erp-surface-raised);
	border-color: var(--erp-border-strong);
	border-radius: var(--erp-control-radius);
	box-shadow: none;
}

.app-shell :where(.p-inputtext, .p-inputnumber-input, .p-autocomplete-input, .erp-date-time-picker .p-datepicker-input)::placeholder {
	color: var(--erp-text-subtle);
	opacity: 1;
}

.app-shell :where(
	.p-inputtext:focus,
	.p-inputnumber:focus-within .p-inputnumber-input,
	.p-select.p-focus,
	.p-multiselect.p-focus,
	.p-autocomplete:focus-within .p-autocomplete-input,
	.erp-date-time-picker:focus-within .p-datepicker-input
) {
	border-color: var(--erp-accent);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--erp-accent) 14%, transparent);
}

.app-shell :where(.p-select-label, .p-multiselect-label) {
	display: flex;
	align-items: center;
	min-height: calc(var(--erp-control-height) - 2px);
	padding-block: 6px;
}

.app-shell .p-message {
	border-radius: var(--erp-control-radius);
	font-size: 13px;
}

.app-shell .p-tag,
.p-dialog .p-tag {
	min-height: 22px;
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
}

.p-dialog {
	overflow: hidden;
	color: var(--erp-text);
	font-family: var(--erp-font-family);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-dialog);
}

.p-dialog .p-dialog-header {
	padding: 16px 18px 12px;
	border-bottom: 1px solid var(--erp-border);
}

.p-dialog .p-dialog-title {
	font-size: 17px;
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: -0.015em;
}

.p-dialog .p-dialog-content {
	padding: 16px 18px;
}

.p-dialog .p-dialog-footer {
	padding: 12px 18px 16px;
	border-top: 1px solid var(--erp-border);
}

.erp-entity-dialog.p-dialog {
	display: flex;
	max-height: calc(100dvh - 32px);
	flex-direction: column;
}

.erp-entity-dialog.p-dialog .p-dialog-header,
.erp-entity-dialog.p-dialog .p-dialog-footer {
	position: relative;
	z-index: var(--erp-layer-content);
	flex: 0 0 auto;
	background: var(--erp-surface);
}

.erp-entity-dialog.p-dialog .p-dialog-content {
	min-height: 0;
	overflow-y: auto;
	flex: 1 1 auto;
	scrollbar-gutter: stable;
}

:where(.p-select-overlay, .p-autocomplete-overlay, .p-multiselect-overlay) {
	font-family: var(--erp-font-family);
	font-size: 13px;
	border-color: var(--erp-border);
	border-radius: var(--erp-control-radius);
	box-shadow: var(--erp-shadow-md);
}

/* App-owned date/time overlay. Keep every rule under this panel class so
   Frappe Desk date controls and unrelated PrimeVue calendars stay untouched. */
.erp-date-time-panel.p-datepicker-panel {
	width: min(22rem, calc(100vw - 24px));
	padding: 10px;
	color: var(--erp-text);
	font-family: var(--erp-font-family);
	font-size: 13px;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border-strong);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-dialog);
}

.erp-date-time-panel .p-datepicker-header {
	padding: 3px 2px 9px;
	background: transparent;
	border-bottom: 1px solid var(--erp-border);
}

.erp-date-time-panel .p-datepicker-title {
	gap: 3px;
}

.erp-date-time-panel .p-datepicker-select-month,
.erp-date-time-panel .p-datepicker-select-year {
	min-height: 30px;
	padding: 4px 6px;
	color: var(--erp-text);
	font-size: 13px;
	font-weight: var(--erp-font-weight-semibold);
	border-radius: 6px;
}

.erp-date-time-panel .p-datepicker-prev-button,
.erp-date-time-panel .p-datepicker-next-button {
	width: 30px;
	height: 30px;
	color: var(--erp-text-muted);
	border-radius: 7px;
}

.erp-date-time-panel .p-datepicker-prev-button:hover,
.erp-date-time-panel .p-datepicker-next-button:hover,
.erp-date-time-panel .p-datepicker-select-month:hover,
.erp-date-time-panel .p-datepicker-select-year:hover {
	color: var(--erp-accent);
	background: var(--erp-accent-soft);
}

.erp-date-time-panel .p-datepicker-day-view {
	margin-top: 6px;
}

.erp-date-time-panel .p-datepicker-weekday-cell {
	padding: 3px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
}

.erp-date-time-panel .p-datepicker-day-cell {
	padding: 2px;
}

.erp-date-time-panel .p-datepicker-day {
	width: 32px;
	height: 32px;
	font-size: 12px;
	font-variant-numeric: tabular-nums;
	border-radius: 7px;
}

.erp-date-time-panel.p-datepicker-panel .p-datepicker-day:not(.p-disabled):hover {
	color: var(--erp-accent-hover);
	background: var(--erp-accent-soft);
}

.erp-date-time-panel.p-datepicker-panel .p-datepicker-day.p-datepicker-day-selected {
	color: #fff;
	font-weight: var(--erp-font-weight-semibold);
	background: var(--erp-accent);
}

.erp-date-time-panel.p-datepicker-panel .p-datepicker-day-cell.p-datepicker-today > .p-datepicker-day:not(.p-datepicker-day-selected) {
	color: var(--erp-accent);
	font-weight: var(--erp-font-weight-semibold);
	box-shadow: inset 0 0 0 1px var(--erp-accent-border);
}

.erp-date-time-panel .p-datepicker-time-picker {
	gap: 8px;
	padding: 10px 4px 2px;
	border-top: 1px solid var(--erp-border);
}

.erp-date-time-panel.p-datepicker-panel .p-datepicker-hour-picker > span,
.erp-date-time-panel.p-datepicker-panel .p-datepicker-minute-picker > span,
.erp-date-time-panel.p-datepicker-panel .p-datepicker-second-picker > span {
	font-size: 14px;
	font-weight: var(--erp-font-weight-semibold);
	font-variant-numeric: tabular-nums;
}

.erp-date-time-panel .p-datepicker-buttonbar {
	gap: 6px;
	padding: 9px 2px 1px;
	border-top: 1px solid var(--erp-border);
}

.erp-date-time-panel .p-datepicker-buttonbar .p-button {
	min-height: 30px;
	padding: 5px 9px;
	color: var(--erp-accent);
	font-size: 12px;
	font-weight: var(--erp-font-weight-semibold);
	border-radius: 7px;
}

.erp-date-time-panel :where(button, [tabindex]):focus-visible {
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 28%, transparent);
	outline-offset: 2px;
}

::selection {
	color: var(--erp-accent-dark);
	background: var(--erp-emerald-100);
}

.app-shell :where(button, a, [role="button"]):not(:disabled) {
	-webkit-tap-highlight-color: transparent;
}

.app-shell :where(button, a, [role="button"]):not(:disabled):active {
	transition-duration: 70ms;
}

.p-toast,
.p-confirmdialog {
	font-family: var(--erp-font-family);
}

.p-toast .p-toast-message {
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-md);
}

@media (max-width: 760px) {
	.erp-page-header,
	.erp-section-header {
		align-items: stretch;
		flex-direction: column;
	}

	.erp-field-grid {
		grid-template-columns: 1fr;
	}
}

@media (max-width: 620px) {
	.p-dialog.work-order-action-panel,
	.p-dialog.related-document-workspace-dialog,
	.p-dialog.fabric-action-dialog,
	.p-dialog.fabric-stock-operation-dialog {
		width: 100vw !important;
		height: 100dvh !important;
		max-height: 100dvh !important;
		margin: 0 !important;
		border-radius: 0 !important;
	}

	.p-dialog.work-order-action-panel .p-dialog-content,
	.p-dialog.related-document-workspace-dialog .p-dialog-content,
	.p-dialog.fabric-action-dialog .p-dialog-content,
	.p-dialog.fabric-stock-operation-dialog .p-dialog-content {
		min-height: 0;
		flex: 1;
		overflow-y: auto;
	}

	.related-document-workspace-dialog .fabric-document-workspace--embedded {
		height: 100%;
		min-height: 0;
	}
}
```

## frontend/src/styles/main.css

```css
:root {
	font-family: var(--erp-font-family, Inter, "Segoe UI Variable", "Segoe UI", ui-sans-serif, system-ui, sans-serif);
	color: var(--erp-text, #101828);
	background: var(--erp-canvas, #f7f8fa);
	font-synthesis: none;
	text-rendering: optimizeLegibility;
	-webkit-font-smoothing: antialiased;
	--erp-shell-header-height: 64px;
}

* {
	box-sizing: border-box;
}

html {
	min-height: 100%;
	scroll-behavior: smooth;
}

body,
#app {
	min-height: 100%;
	margin: 0;
}

body {
	min-width: 320px;
	color: var(--erp-text, #101828);
	background: var(--erp-canvas, #f7f8fa);
}

button,
input,
select,
textarea {
	font: inherit;
}

a {
	color: inherit;
	text-decoration: none;
}

.app-shell {
	min-height: 100vh;
	min-height: 100dvh;
	color: var(--erp-text);
	font-family: var(--erp-font-family);
	font-size: var(--erp-font-size-body);
	line-height: var(--erp-line-height-body);
	background: var(--erp-canvas);
}

.app-skip-link {
	position: fixed;
	z-index: calc(var(--erp-layer-toast) + 1);
	top: var(--erp-space-3);
	left: var(--erp-space-3);
	padding: 9px 13px;
	color: #fff;
	font-weight: var(--erp-font-weight-semibold);
	background: var(--erp-accent-dark);
	border-radius: var(--erp-control-radius);
	box-shadow: var(--erp-shadow-md);
	transform: translateY(calc(-100% - var(--erp-space-6)));
	transition: transform var(--erp-transition-base);
}

.app-skip-link:focus {
	transform: translateY(0);
}

.app-topbar {
	position: sticky;
	z-index: var(--erp-layer-sticky);
	top: 0;
	display: flex;
	align-items: center;
	justify-content: space-between;
	height: var(--erp-shell-header-height);
	padding: 0 clamp(16px, 3vw, 40px);
	background: rgb(255 255 255 / 92%);
	border-bottom: 1px solid var(--erp-border-subtle);
	box-shadow: 0 1px 0 rgb(16 24 40 / 2%);
	backdrop-filter: blur(16px) saturate(160%);
}

.app-brand {
	display: inline-flex;
	align-items: center;
	gap: 11px;
	min-width: 0;
	border-radius: var(--erp-control-radius);
}

.app-brand__mark {
	display: grid;
	width: 34px;
	height: 34px;
	flex: 0 0 auto;
	color: #fff;
	font-size: 12px;
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: -0.025em;
	background: var(--erp-accent);
	border: 1px solid color-mix(in srgb, var(--erp-accent-dark) 22%, transparent);
	border-radius: 10px;
	box-shadow: 0 4px 12px color-mix(in srgb, var(--erp-accent) 20%, transparent);
	place-items: center;
	transition: background var(--erp-transition-fast), transform var(--erp-transition-fast);
}

.app-brand:hover .app-brand__mark {
	background: var(--erp-accent-hover);
	transform: translateY(-1px);
}

.app-brand:active .app-brand__mark {
	transform: translateY(0) scale(0.97);
}

.app-brand__copy {
	display: flex;
	min-width: 0;
	flex-direction: column;
}

.app-brand__name {
	color: var(--erp-text);
	font-size: 14px;
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: -0.015em;
	line-height: 1.15;
}

.app-brand__suite {
	color: var(--erp-text-subtle);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: 0.085em;
	line-height: 1.25;
	text-transform: uppercase;
}

.app-topbar__nav,
.app-topbar__context,
.app-topbar__home {
	display: flex;
	align-items: center;
}

.app-topbar__nav {
	gap: var(--erp-space-2);
}

.app-topbar__context {
	gap: 7px;
	min-height: 32px;
	padding: 0 11px;
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-caption);
	font-weight: var(--erp-font-weight-semibold);
	background: var(--erp-accent-soft);
	border: 1px solid var(--erp-accent-border);
	border-radius: var(--erp-pill-radius);
}

.app-topbar__context::before {
	width: 6px;
	height: 6px;
	background: var(--erp-accent);
	border-radius: 50%;
	content: "";
}

.app-topbar__home {
	gap: 7px;
	min-height: 36px;
	padding: 0 11px;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-caption);
	font-weight: var(--erp-font-weight-semibold);
	border-radius: var(--erp-control-radius);
	transition: color var(--erp-transition-fast), background var(--erp-transition-fast), transform var(--erp-transition-fast);
}

.app-topbar__home:hover {
	color: var(--erp-accent-dark);
	background: var(--erp-accent-soft);
}

.app-topbar__home:active {
	transform: scale(0.98);
}

.app-main {
	min-height: calc(100vh - var(--erp-shell-header-height));
	min-height: calc(100dvh - var(--erp-shell-header-height));
}

.app-route-enter-active,
.app-route-leave-active {
	transition: opacity var(--erp-transition-base), transform var(--erp-transition-base);
}

.app-route-enter-from {
	opacity: 0;
	transform: translateY(5px);
}

.app-route-leave-to {
	opacity: 0;
}

.administrator-page {
	width: min(1240px, calc(100% - 64px));
	margin: 0 auto;
	padding: clamp(40px, 6vw, 72px) 0 64px;
}

.administrator-page__header {
	display: grid;
	grid-template-columns: minmax(0, 700px) auto;
	align-items: end;
	justify-content: space-between;
	gap: var(--erp-space-6);
	margin-bottom: var(--erp-space-7);
}

.administrator-page__eyebrow {
	margin: 0 0 var(--erp-space-2);
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: 0.12em;
	text-transform: uppercase;
}

.administrator-page__header h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: clamp(2rem, 4vw, 3.25rem);
	font-weight: var(--erp-font-weight-bold);
	line-height: 1.05;
	letter-spacing: -0.048em;
}

.administrator-page__description {
	max-width: 640px;
	margin: var(--erp-space-3) 0 0;
	color: var(--erp-text-muted);
	font-size: 15px;
	line-height: var(--erp-line-height-relaxed);
}

.administrator-page__summary {
	display: inline-flex;
	align-items: center;
	gap: var(--erp-space-2);
	min-height: 36px;
	padding: 0 13px;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-caption);
	font-weight: var(--erp-font-weight-semibold);
	white-space: nowrap;
	background: var(--erp-surface-raised);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-pill-radius);
	box-shadow: var(--erp-shadow-xs);
}

.administrator-page__summary strong {
	color: var(--erp-accent-dark);
	font-variant-numeric: tabular-nums;
}

.administrator-page__section-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-4);
	margin-bottom: var(--erp-space-4);
}

.administrator-page__section-header h2 {
	margin: 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: -0.01em;
}

.department-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--erp-space-4);
}

.department-card-link {
	display: block;
	min-width: 0;
	border-radius: var(--erp-radius-lg);
	transition: transform var(--erp-transition-base), box-shadow var(--erp-transition-base);
}

.department-card {
	--accent: var(--erp-accent);
	position: relative;
	min-height: 126px;
	overflow: hidden;
	background: var(--erp-surface-raised);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-radius-lg);
	box-shadow: var(--erp-shadow-xs);
	transition: border-color var(--erp-transition-base), box-shadow var(--erp-transition-base);
}

.department-card::before {
	position: absolute;
	top: 18px;
	bottom: 18px;
	left: 0;
	width: 3px;
	background: var(--accent);
	border-radius: 0 var(--erp-pill-radius) var(--erp-pill-radius) 0;
	content: "";
	opacity: 0.72;
	transition: opacity var(--erp-transition-fast);
}

.department-card .p-card-body,
.department-card .p-card-content {
	height: 100%;
}

.department-card .p-card-body {
	padding: 0;
}

.department-card .p-card-content {
	display: flex;
	align-items: center;
	padding: 22px 24px;
}

.department-card__layout {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr) auto;
	align-items: center;
	width: 100%;
}

.department-card-link:hover,
.department-card-link:focus-visible {
	box-shadow: var(--erp-shadow-md);
	outline: none;
	transform: translateY(-3px);
}

.department-card-link:hover .department-card,
.department-card-link:focus-visible .department-card {
	border-color: color-mix(in srgb, var(--accent) 38%, var(--erp-border));
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 7%, transparent);
}

.department-card-link:hover .department-card::before,
.department-card-link:focus-visible .department-card::before {
	opacity: 1;
}

.department-card-link:focus-visible {
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--erp-accent) 24%, transparent), var(--erp-shadow-md);
}

.department-card-link:active {
	box-shadow: var(--erp-shadow-sm);
	transform: translateY(-1px) scale(0.995);
}

.department-card__mark {
	display: grid;
	width: 48px;
	height: 48px;
	margin-right: var(--erp-space-4);
	color: white;
	font-size: var(--erp-font-size-caption);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: 0.07em;
	background: var(--accent);
	border-radius: 13px;
	box-shadow: 0 5px 14px color-mix(in srgb, var(--accent) 20%, transparent);
	place-items: center;
}

.department-card__content {
	display: flex;
	min-width: 0;
	flex-direction: column;
	gap: 5px;
}

.department-card__content strong {
	overflow: hidden;
	color: var(--erp-text);
	font-size: 16px;
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: -0.018em;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.department-card__arrow {
	display: grid;
	width: 34px;
	height: 34px;
	margin-left: var(--erp-space-3);
	color: var(--accent);
	font-size: 0.9rem;
	background: color-mix(in srgb, var(--accent) 8%, white);
	border: 1px solid color-mix(in srgb, var(--accent) 13%, var(--erp-border));
	border-radius: 50%;
	place-items: center;
	transition: background var(--erp-transition-fast), transform var(--erp-transition-base);
}

.department-card-link:hover .department-card__arrow,
.department-card-link:focus-visible .department-card__arrow {
	background: color-mix(in srgb, var(--accent) 13%, white);
	transform: translateX(3px);
}

.department-page {
	width: calc(100% - 32px);
	margin: 0 auto;
	padding: var(--erp-space-2) 0 var(--erp-space-4);
}

.department-page--flat {
	width: min(1500px, calc(100% - 48px));
	padding-top: var(--erp-space-3);
}

.department-page--full-width {
	width: calc(100% - 24px);
}

.department-page--full-width .department-page__content {
	min-height: 0;
}

.back-link {
	margin: 0;
}

.erp-page-nav {
	display: flex;
	align-items: center;
	min-height: 44px;
	margin-bottom: var(--erp-space-1);
}

.department-page__panel {
	min-height: calc(100vh - var(--erp-shell-header-height) - 76px);
	min-height: calc(100dvh - var(--erp-shell-header-height) - 76px);
	background: var(--erp-surface-raised);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-radius-lg);
	box-shadow: var(--erp-shadow-sm);
}

.department-page__panel .p-card-body {
	padding: clamp(20px, 3vw, 30px);
}

.department-page__panel h1 {
	margin: 0 0 var(--erp-space-5);
	color: var(--erp-text);
	font-size: clamp(1.35rem, 2vw, 1.75rem);
	font-weight: var(--erp-font-weight-bold);
	line-height: var(--erp-line-height-tight);
	letter-spacing: -0.03em;
}

.department-page__panel--flat {
	min-height: auto;
	background: transparent;
	border: 0;
	border-radius: 0;
	box-shadow: none;
}

.department-page__panel--flat .p-card-body {
	padding: var(--erp-space-1) var(--erp-space-2) var(--erp-space-6);
}

.department-page__panel--flat .p-card-content {
	padding: 0;
}

.department-page__content {
	min-height: calc(100vh - var(--erp-shell-header-height) - 154px);
	min-height: calc(100dvh - var(--erp-shell-header-height) - 154px);
}

@media (max-width: 820px) {
	:root {
		--erp-shell-header-height: 58px;
	}

	.app-topbar {
		padding-inline: 14px;
	}

	.administrator-page {
		width: min(100% - 28px, 1240px);
		padding: 36px 0 44px;
	}

	.administrator-page__header {
		grid-template-columns: 1fr;
		gap: var(--erp-space-4);
		margin-bottom: var(--erp-space-6);
	}

	.administrator-page__summary {
		justify-self: start;
	}

	.department-page,
	.department-page--full-width {
		width: calc(100% - 16px);
		padding: var(--erp-space-1) 0 var(--erp-space-2);
	}

	.department-page--flat {
		width: calc(100% - 20px);
	}

	.department-page__panel {
		min-height: calc(100vh - var(--erp-shell-header-height) - 62px);
		min-height: calc(100dvh - var(--erp-shell-header-height) - 62px);
		border-radius: var(--erp-panel-radius);
	}

	.department-page__panel .p-card-body {
		padding: 18px;
	}

	.department-grid {
		grid-template-columns: 1fr;
		gap: var(--erp-space-3);
	}

	.department-card {
		min-height: 112px;
		border-radius: var(--erp-panel-radius);
	}

	.department-card .p-card-content {
		padding: 18px 20px;
	}
}

@media (max-width: 540px) {
	.app-brand__suite,
	.app-topbar__context,
	.app-topbar__home span {
		display: none;
	}

	.app-topbar__home {
		width: 38px;
		justify-content: center;
		padding: 0;
	}

	.administrator-page {
		width: calc(100% - 24px);
		padding-top: 30px;
	}

	.administrator-page__header h1 {
		font-size: clamp(2rem, 12vw, 2.65rem);
	}

	.department-card__mark {
		width: 44px;
		height: 44px;
		margin-right: var(--erp-space-3);
	}
}

@media (prefers-reduced-motion: reduce) {
	html {
		scroll-behavior: auto;
	}

	.app-shell *,
	.app-shell *::before,
	.app-shell *::after {
		animation-duration: 0.01ms !important;
		animation-iteration-count: 1 !important;
		transition-duration: 0.01ms !important;
	}

	.app-route-enter-from,
	.app-route-leave-to {
		transform: none;
	}
}
```
