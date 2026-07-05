<!--
  Generic detail / edit / create page for EVERY DocType (per CUSTOM_UI.md §7 +
  the /web plan "Reusable components"). ONE form component, three modes:

    view    — read-only field grid + child DataTables + tabs + side panel.
    edit    — same fields/tables become PrimeVue inputs bound to a `form` model
              (deep-copied from the doc). Save → useDoc.save(form, id).
    create  — props.id === "new"; a blank form built from meta (+ meta defaults);
              no doc/linked/activity/approval load. Save → useDoc.save(form).

  Write flows go through useDoc (create/update/submit/cancel/delete/amend) →
  standard Frappe REST → the yrp controllers run (SLEs written there, NEVER here).

  Child-table contract (the /web backend-integration contract item 1):
  send the child rows as a FLAT array in the child field (`items`,
  `deliverables`+`receivables`, `stock_update_details`) and leave the hidden
  grouped-JSON field (`item_details` / `deliverable_details` /
  `receivable_details`) EMPTY — each voucher's before_validate skips ungroup
  when that field is falsy, so the flat rows persist as-is. EXCEPTION: the grouped
  size-pivot / item->attribute->variant editor (StockItemGridEditor) IS built for
  the doctypes in STOCK_GROUPED_MAP (Stock Entry / Delivery Challan / Goods
  Received Note / Work Order deliverables+receivables) — those send grouped
  JSON + an EMPTY flat array, so before_validate runs ungroup and the server
  resolves/creates the variants. Every other doctype uses the flat path above.

  Reads: frappe.client.get (doc + child rows + _comments), getdoctype (meta),
  linked_with.get (Linked Documents), get_docinfo (Activity).
-->
<template>
	<div class="doc-detail">
		<!-- Breadcrumb -->
		<nav class="crumbs">
			<a @click="goHome">Home</a>
			<span class="sep">/</span>
			<a @click="goList">{{ registry?.label || docRoute }}</a>
			<span class="sep">/</span>
			<span class="crumb-cur esd-mono">{{ isCreate ? "New" : id }}</span>
		</nav>

		<!-- Header -->
		<div class="detail-head">
			<div class="id-block">
				<!-- Q2: the human title is the hero; the serial drops to a small mono
				     chip below it (or becomes the hero itself when there's no title). -->
				<div class="doc-hero">
					<span v-if="isCreate">New {{ registry?.label || doctype }}</span>
					<span v-else>{{ titleLine || id }}</span>
				</div>
				<div v-if="!isCreate && titleLine" class="doc-id esd-mono">{{ id }}</div>
				<div v-if="mode === 'edit'" class="doc-subtle edit-hint">Editing</div>
			</div>

			<!-- Prev/Next document navigation (Frappe v15 form-arrow parity) — view
			     mode only. Left = previous, right = next, stepping through the list
			     the user came from. Disabled at the list ends; tooltip names the
			     target document. -->
			<div v-if="showDocNav" class="doc-nav">
				<Button
					class="doc-nav__btn"
					icon="pi pi-chevron-left"
					text
					rounded
					size="small"
					:disabled="!docHasPrev"
					aria-label="Previous document"
					v-tooltip.bottom="docPrevName ? `Previous: ${docPrevName}` : 'No previous document'"
					@click="docGoPrev"
				/>
				<Button
					class="doc-nav__btn"
					icon="pi pi-chevron-right"
					text
					rounded
					size="small"
					:disabled="!docHasNext"
					aria-label="Next document"
					v-tooltip.bottom="docNextName ? `Next: ${docNextName}` : 'No next document'"
					@click="docGoNext"
				/>
			</div>

			<Tag
				v-if="!loading && doc && mode === 'view' && (isSubmittable || isWorkflow || doc.status)"
				class="head-status"
				:value="statusLabel"
				:severity="statusSeverity"
				rounded
			/>

			<!-- Delivery Challan e-Waybill number + status, once the EWB exists. -->
			<Tag
				v-if="!loading && doc && mode === 'view' && isDeliveryChallan && doc.ewaybill"
				class="head-status"
				:value="ewbStatusTag"
				severity="info"
				rounded
			/>

			<div class="head-actions">
				<!-- ── VIEW mode ── -->
				<template v-if="mode === 'view' && doc">
					<!-- Draft (docstatus 0): Edit (secondary) + Submit (primary forward). -->
					<Button
						v-if="docstatus === 0 && canWrite(doctype)"
						label="Edit"
						icon="pi pi-pencil"
						size="small"
						severity="secondary"
						outlined
						@click="enterEdit"
					/>
					<Button
						v-if="docstatus === 0 && isSubmittable && canSubmit(doctype)"
						label="Submit"
						icon="pi pi-arrow-right"
						iconPos="right"
						size="small"
						class="forward-cta"
						:loading="acting === 'submit'"
						@click="onSubmit"
					/>
					<!-- Work Order: Calculate Deliverables (fabric processes, draft only).
					     essdee flow — the popup reads the WO's Lot's fabric details via
					     essdee_yrp.api.work_order.get_fabric_deliverable_context. -->
					<Button
						v-if="isWorkOrder && docstatus === 0 && !isCreate && canWrite(doctype)"
						label="Calculate Deliverables"
						icon="pi pi-calculator"
						size="small"
						severity="secondary"
						outlined
						@click="onCalculateDeliverables"
					/>

					<!-- Submitted (docstatus 1): ONE primary forward CTA; the remaining
					     create-next actions collapse into a "More" overflow menu so the
					     submitted header stops being a wall of equal buttons. forwardActions
					     keeps the exact per-doctype gating (Create DC · Create GRN). -->
					<span
						v-if="primaryForward"
						v-tooltip.bottom="primaryForward.tooltip"
						class="cta-wrap"
					>
						<Button
							:label="primaryForward.label"
							:icon="primaryForward.icon"
							size="small"
							class="forward-cta"
							:disabled="primaryForward.disabled"
							:loading="primaryForward.loadingKey && acting === primaryForward.loadingKey"
							@click="primaryForward.handler"
						/>
					</span>

					<!-- Cancelled (docstatus 2): Amend (primary forward). -->
					<Button
						v-if="docstatus === 2 && isSubmittable && canAmend(doctype)"
						label="Amend"
						icon="pi pi-clone"
						size="small"
						class="forward-cta"
						:loading="acting === 'amend'"
						@click="onAmend"
					/>

					<!-- Overflow: secondary create-next actions + Print + Open in Desk. -->
					<Button
						v-if="moreMenuModel.length"
						type="button"
						label="More"
						icon="pi pi-ellipsis-h"
						iconPos="right"
						size="small"
						severity="secondary"
						outlined
						aria-haspopup="true"
						aria-controls="dd_more_menu"
						@click="(e) => moreMenu.toggle(e)"
					/>
					<Menu ref="moreMenu" id="dd_more_menu" :model="moreMenuModel" :popup="true" />
					<!-- Delivery Challan e-Waybill (GST e-Way Bill) lifecycle — context-gated
					     Menu: generate/fetch when none exists; print/update/cancel once it does. -->
					<Button
						v-if="isDeliveryChallan && docstatus === 1"
						type="button"
						label="e-Waybill"
						icon="pi pi-truck"
						size="small"
						severity="secondary"
						outlined
						aria-haspopup="true"
						aria-controls="dd_ewb_menu"
						@click="(e) => ewbMenu.toggle(e)"
					/>
					<Menu ref="ewbMenu" id="dd_ewb_menu" :model="ewbMenuModel" :popup="true" />
					<!-- Send SMS — only when the DC has a supplier to text. -->
					<Button
						v-if="isDeliveryChallan && docstatus === 1 && doc.supplier"
						label="Send SMS"
						icon="pi pi-comment"
						size="small"
						severity="secondary"
						outlined
						@click="sendSmsOpen = true"
					/>
					<!-- Send WhatsApp — gated on the doctype being WhatsApp-enabled
					     (server-configured) AND having a supplier to message, same
					     docstatus/supplier shape as Send SMS. -->
					<Button
						v-if="isWhatsAppEnabled && docstatus === 1 && doc[whatsAppSupplierKey]"
						label="Send WhatsApp"
						icon="pi pi-whatsapp"
						size="small"
						severity="secondary"
						outlined
						@click="sendWhatsAppOpen = true"
					/>

					<!-- Destructive, set apart from the forward CTA. -->
					<Button
						v-if="docstatus === 1 && isSubmittable && canCancel(doctype)"
						label="Cancel"
						icon="pi pi-ban"
						size="small"
						severity="danger"
						outlined
						:loading="acting === 'cancel'"
						@click="onCancel"
					/>
					<Button
						v-if="(docstatus === 0 || docstatus === 2) && canDelete(doctype)"
						label="Delete"
						icon="pi pi-trash"
						size="small"
						severity="danger"
						outlined
						:loading="acting === 'delete'"
						@click="onDelete"
					/>
				</template>

				<!-- ── EDIT mode ── -->
				<template v-else-if="mode === 'edit'">
					<Button
						label="Discard"
						icon="pi pi-times"
						size="small"
						severity="secondary"
						outlined
						:disabled="saving"
						@click="onDiscard"
					/>
					<Button
						v-if="canWrite(doctype)"
						label="Save"
						icon="pi pi-check"
						size="small"
						class="forward-cta"
						:loading="saving"
						@click="onSave"
					/>
				</template>

				<!-- ── CREATE mode ── -->
				<template v-else-if="mode === 'create'">
					<Button
						label="Discard"
						icon="pi pi-times"
						size="small"
						severity="secondary"
						outlined
						:disabled="saving"
						@click="onDiscard"
					/>
					<Button
						v-if="canCreate(doctype)"
						label="Save"
						icon="pi pi-check"
						size="small"
						class="forward-cta"
						:loading="saving"
						@click="onSave"
					/>
				</template>
			</div>
		</div>

		<!-- Q5: required-field-missing banner — complements the toast and stays put
		     until the user fixes it (long grouped forms scroll the toast'd field
		     off-screen). -->
		<Message
			v-if="missingField"
			severity="warn"
			closable
			class="form-banner"
			@close="missingField = null"
		>
			Required field missing: <b>{{ missingField.label }}</b> — fill it in to save.
		</Message>

		<!-- Q15: persistent, readable save/submit error. The toast vanishes before
		     a multi-line stock/validation message can be read; this banner holds
		     it open while the user fixes the cause. -->
		<Message
			v-if="serverError"
			severity="error"
			closable
			class="form-banner"
			@close="serverError = null"
		>
			<div class="srv-err">
				<div class="srv-err__title">{{ serverError.title }}</div>
				<div
					v-for="(line, i) in serverError.lines"
					:key="i"
					class="srv-err__line"
				>{{ line }}</div>
				<div v-if="serverError.refresh" class="srv-err__actions">
					<Button label="Refresh" icon="pi pi-refresh" size="small" @click="refreshFromConflict" />
				</div>
			</div>
		</Message>

		<!-- Realtime: another user changed this doc since we opened it. Non-blocking
		     warn banner; Refresh loads the latest (discards local edits in v1). The
		     loaded doc.value.modified is NOT advanced until Refresh, so the save
		     guard keeps working. -->
		<Message
			v-if="staleNotice"
			severity="warn"
			closable
			class="form-banner"
			@close="staleNotice = false"
		>
			<div class="srv-err">
				<div class="srv-err__title">This document was modified by another user.</div>
				<div class="srv-err__line">Refresh to load the latest version before making changes.</div>
				<div class="srv-err__actions">
					<Button label="Refresh" icon="pi pi-refresh" size="small" @click="refreshFromConflict" />
				</div>
			</div>
		</Message>

		<Dialog
			v-model:visible="printDialogOpen"
			header="Print"
			modal
			class="print-dialog"
			:style="{ width: 'min(420px, calc(100vw - 32px))' }"
		>
			<div class="print-form">
				<label class="field-label" for="print-format">Print Format</label>
				<Select
					id="print-format"
					v-model="selectedPrintFormat"
					:options="printFormatOptions"
					filter
					class="fld"
					fluid
				/>
			</div>
			<template #footer>
				<Button
					label="Cancel"
					severity="secondary"
					text
					@click="printDialogOpen = false"
				/>
				<Button
					label="Print"
					icon="pi pi-print"
					:disabled="!selectedPrintFormat"
					@click="submitPrintDialog"
				/>
			</template>
		</Dialog>

		<!-- WO Calculate Deliverables (essdee fabric processes) — draft WO only -->
		<FabricDeliverablesModal
			v-if="isWorkOrder && doc"
			v-model:visible="calcDeliverablesOpen"
			:work-order="doc.name"
			@calculated="onDeliverablesCalculated"
		/>

		<!-- Delivery Challan e-Waybill lifecycle + SMS modals (yrp_ewaybill_api).
		     Each posts its own whitelisted action and reloads the view on success. -->
		<EWaybillGenerateModal
			v-model:visible="ewbGenerateOpen"
			:doctype="doctype"
			:docname="props.id"
			:doc="doc"
			@generated="onEwbGenerated"
		/>
		<EWaybillFetchModal
			v-model:visible="ewbFetchOpen"
			:doctype="doctype"
			:docname="props.id"
			:doc="doc"
			@fetched="onEwbFetched"
		/>
		<EWaybillCancelModal
			v-model:visible="ewbCancelOpen"
			:doctype="doctype"
			:docname="props.id"
			:doc="doc"
			@cancelled="onEwbCancelled"
		/>
		<EWaybillVehicleModal
			v-model:visible="ewbVehicleOpen"
			:doctype="doctype"
			:docname="props.id"
			:doc="doc"
			@updated="onEwbUpdated"
		/>
		<SendSmsModal
			v-model:visible="sendSmsOpen"
			:doctype="doctype"
			:docname="props.id"
			:doc="doc"
			@sent="onSmsSent"
		/>
		<SendWhatsAppModal
			v-model:visible="sendWhatsAppOpen"
			:doctype="doctype"
			:docname="props.id"
			:doc="doc"
			:supplier-key="whatsAppSupplierKey"
			@sent="onWhatsAppSent"
		/>

		<!-- Loading (doc load, or create-mode meta load) — skeleton mimics the
		     grouped detail cards instead of a blank flash. -->
		<div v-if="loading || (isCreate && metaLoading)" class="esd-detail-skel" aria-busy="true" aria-label="Loading">
			<div v-for="c in 2" :key="`sk-${c}`" class="esd-detail-skel__card">
				<div class="esd-skel-band" />
				<div class="esd-skel-body">
					<div v-for="i in 4" :key="`sk-${c}-${i}`" class="esd-skel-line" />
				</div>
			</div>
		</div>

		<!-- Error (load failure) -->
		<Message v-else-if="error && !doc && !isCreate" severity="error" :closable="false">
			{{ error }}
		</Message>

		<!-- ════════════════ CREATE / EDIT FORM ════════════════ -->
		<div v-else-if="isFormMode" class="form-layout">
			<div class="detail-main form-card">
				<!-- Prompt-named create: a REQUIRED Name input at the very top of the
				     form. Prompt-named doctypes (Item Master Template, FG Item Master
				     Template, …) take the document name from the user; without this the
				     REST insert has no name and the server rejects the save. Shown ONLY
				     in create mode for prompt naming — never in edit, never for
				     series/field/hash-named doctypes. -->
				<section
					v-if="mode === 'create' && isPromptNaming"
					class="esd-card form-section"
				>
					<header class="esd-card__head">
						<span class="esd-card__title">Naming</span>
					</header>
					<div class="esd-card__body form-grid">
						<div id="field-__newname" class="form-field wide">
							<label class="field-label" for="fld-__newname">
								{{ (registry?.label || doctype) }} Name
								<span class="req">*</span>
							</label>
							<InputText
								id="fld-__newname"
								v-model="newName"
								:invalid="!newName.trim()"
								class="fld"
							/>
							<small class="field-help">Required — set a unique name for this document.</small>
						</div>
					</div>
				</section>

				<!-- Field grid (inputs), grouped into titled cards by Section Break
				     so the edit form mirrors the read-view Details cards. -->
				<section
					v-for="s in visibleFormSections"
					:key="s.key"
					class="esd-card form-section"
				>
					<header class="esd-card__head">
						<span class="esd-card__title">{{ s.label }}</span>
					</header>
					<div class="esd-card__body form-grid">
					<div
						v-for="f in s.fields"
						:key="f.fieldname"
						:id="'field-' + f.fieldname"
						class="form-field"
						:class="{ wide: f.wide }"
					>
						<label class="field-label" :for="'fld-' + f.fieldname">
							{{ f.label }}
							<span v-if="isReqd(f)" class="req">*</span>
						</label>

						<!-- Data / Small Text -->
						<InputText
							v-if="f.input === 'text'"
							:id="'fld-' + f.fieldname"
							v-model="form[f.fieldname]"
							:disabled="isReadOnly(f)"
							:invalid="isMissing(f)"
							class="fld"
						/>

						<!-- Text / Long Text / Code -->
						<Textarea
							v-else-if="f.input === 'textarea'"
							:id="'fld-' + f.fieldname"
							v-model="form[f.fieldname]"
							:disabled="isReadOnly(f)"
							:invalid="isMissing(f)"
							rows="3"
							autoResize
							class="fld"
						/>

						<!-- Int / Float / Percent / Currency -->
						<InputNumber
							v-else-if="f.input === 'number'"
							:id="'fld-' + f.fieldname"
							v-model="form[f.fieldname]"
							:disabled="isReadOnly(f)"
							:invalid="isMissing(f)"
							:minFractionDigits="f.minFraction"
							:maxFractionDigits="f.maxFraction"
							:suffix="f.suffix"
							class="fld"
							fluid
						/>

						<!-- Date -->
						<DatePicker
							v-else-if="f.input === 'date'"
							:id="'fld-' + f.fieldname"
							:modelValue="toDateObj(form[f.fieldname])"
							@update:modelValue="form[f.fieldname] = fromDateObj($event, false)"
							:disabled="isReadOnly(f)"
							:invalid="isMissing(f)"
							dateFormat="dd-mm-yy"
							showIcon
							iconDisplay="input"
							class="fld"
							fluid
						/>

						<!-- Datetime -->
						<DatePicker
							v-else-if="f.input === 'datetime'"
							:id="'fld-' + f.fieldname"
							:modelValue="toDateObj(form[f.fieldname])"
							@update:modelValue="form[f.fieldname] = fromDateObj($event, true)"
							:disabled="isReadOnly(f)"
							:invalid="isMissing(f)"
							dateFormat="dd-mm-yy"
							showTime
							hourFormat="24"
							showIcon
							iconDisplay="input"
							class="fld"
							fluid
						/>

						<!-- Time — plain HH:MM:SS text input (picker component intentionally
						     avoided) + a quick "Now" button for the common posting_time
						     case (after toggling Edit Posting Date and Time). The user
						     can still type a specific time. -->
						<div
							v-else-if="f.input === 'time'"
							class="time-fld"
						>
							<InputText
								:id="'fld-' + f.fieldname"
								v-model="form[f.fieldname]"
								:disabled="isReadOnly(f)"
								:invalid="isMissing(f)"
								placeholder="HH:MM:SS"
								class="fld time-input"
							/>
							<Button
								v-if="!isReadOnly(f)"
								label="Now"
								icon="pi pi-clock"
								size="small"
								severity="secondary"
								outlined
								class="time-now"
								@click="form[f.fieldname] = nowTimeStr()"
							/>
						</div>

						<!-- Check -->
						<div v-else-if="f.input === 'check'" class="fld-check">
							<ToggleSwitch
								:inputId="'fld-' + f.fieldname"
								:modelValue="!!form[f.fieldname]"
								@update:modelValue="form[f.fieldname] = $event ? 1 : 0"
								:disabled="isReadOnly(f)"
							/>
							<span class="check-label">{{ checkWord(f) }}</span>
						</div>

						<!-- Select -->
						<Select
							v-else-if="f.input === 'select'"
							:id="'fld-' + f.fieldname"
							v-model="form[f.fieldname]"
							:options="f.options"
							@change="onFieldChanged(f.fieldname)"
							:disabled="isReadOnly(f)"
							:invalid="isMissing(f)"
							showClear
							placeholder="Select…"
							class="fld"
							fluid
						/>

						<!-- Link / Dynamic Link → LinkField (AutoComplete + "open linked doc").
						     target-doctype is reactive: a Dynamic Link re-resolves from its
						     controlling field at runtime. search-handler is per-(doctype,
						     fieldname) — used for Addresses filtered by the selected party. -->
						<LinkField
							v-else-if="f.input === 'link'"
							:model-value="form[f.fieldname]"
							@update:model-value="form[f.fieldname] = $event"
							:target-doctype="f.isDynamic ? form[f.dynamicField] : f.linkTarget"
							:search-handler="linkSearchHandlerFor(f)"
							:disabled="isReadOnly(f)"
							:invalid="isMissing(f)"
							@item-select="onFieldChanged(f.fieldname)"
							@change="onFieldChanged(f.fieldname)"
						/>

						<!-- Fallback (unknown but editable scalar) -->
						<InputText
							v-else
							:id="'fld-' + f.fieldname"
							v-model="form[f.fieldname]"
							:disabled="isReadOnly(f)"
							class="fld"
						/>

						<!-- Q13: inline help (meta description / SPA override). -->
						<small v-if="f.help" class="field-help">{{ f.help }}</small>
					</div>
					</div>
				</section>

				<div v-if="!formFields.length" class="empty-inline">
					No editable fields for this DocType.
				</div>

				<!-- R3a: stock size-pivot editor(s) — grouped item_details path.
				     Renders INSTEAD of the flat grid for stock vouchers only;
				     the replaced flat child fields are dropped from
				     editableChildTables above. -->
				<div
					v-for="pv in stockPivots"
					:key="'pivot-' + pv.childField"
					class="child-editor"
				>
					<div class="child-editor-head">
						<h4>{{ pv.label }}</h4>
						<span class="child-cols-note pivot-note">
							{{ useGrnSplit ? "received-type split · server resolves variants on save" : "size-pivot · server resolves variants on save" }}
						</span>
					</div>
					<!-- R3b: GRN against Work Order needs the received-type SPLIT UX
					     (split one item's qty across multiple received types). All
					     other stock vouchers (and GRN-against-Purchase-Order) keep the
					     generic pivot. Both editors expose the same loadData/getItems/
					     hasItems surface and register into gridRefs identically, so
					     hydratePivotsForEdit + buildPayload are unchanged. -->
					<GRNReceivedTypeEditor
						v-if="useGrnSplit"
						:ref="(el) => setGridRef(pv.childField, el)"
						:editable="true"
						@change="onGridChange"
					/>
					<StockItemGridEditor
						v-else
						:ref="(el) => setGridRef(pv.childField, el)"
						:grouped-field="pv.groupedField"
						:value-fields="pv.valueFields"
						:entry-fields="pv.entryFields"
						:cell-fields="pv.cellFields || []"
						:show-allow-zero-rate="!!pv.showAllowZeroRate"
						:show-secondary-toggle="!!pv.showSecondaryToggle"
						:locked-items="!!pv.lockedItems"
						:editable="true"
						@change="onGridChange"
					/>
				</div>

				<!-- Child-table editors (flat grid) -->
				<div
					v-for="ct in editableChildTables"
					:key="ct.fieldname"
					class="child-editor"
				>
					<div class="child-editor-head">
						<h4>{{ ct.label }}</h4>
						<div class="child-head-actions">
							<span v-if="!ct.columnsAvailable" class="child-cols-note">
								columns unavailable — open in Desk
							</span>
							<template v-else>
								<Button
									label="Columns"
									icon="pi pi-sliders-h"
									size="small"
									severity="secondary"
									outlined
									@click="toggleColChooser(ct.fieldname, $event)"
								/>
								<Popover :ref="(el) => setColChooserRef(ct.fieldname, el)">
									<div class="col-chooser">
										<div class="col-chooser__head">
											<div class="col-chooser__title">Show columns</div>
											<div class="col-chooser__total">
												{{ childWidthUnitsTotal(ct.fieldname, ct.columns) }}/{{ MAX_TABLE_WIDTH_UNITS }}
											</div>
										</div>
										<div
											v-for="col in ct.columns"
											:key="col.fieldname"
											class="col-chooser__row"
										>
											<Checkbox
												:inputId="'colsel-edit-' + ct.fieldname + '-' + col.fieldname"
												:modelValue="isColumnVisible(ct.fieldname, ct.columns, col.fieldname)"
												binary
												@update:modelValue="toggleColumn(ct.fieldname, ct.columns, col.fieldname)"
											/>
											<label :for="'colsel-edit-' + ct.fieldname + '-' + col.fieldname">{{ col.label }}</label>
											<InputNumber
												class="col-chooser__width"
												inputClass="col-chooser__width-input"
												:modelValue="childColWidthUnits(ct.fieldname, col)"
												:min="1"
												:max="childWidthUnitMax(ct.fieldname, ct.columns, col)"
												:useGrouping="false"
												@update:modelValue="(value) => setChildColWidthUnits(ct.fieldname, ct.columns, col, value)"
											/>
										</div>
									</div>
								</Popover>
								<Button
									label="Add Row"
									icon="pi pi-plus"
									size="small"
									severity="secondary"
									outlined
									@click="addChildRow(ct)"
								/>
							</template>
						</div>
					</div>

					<DataTable
						:value="form[ct.fieldname]"
						class="esd-table child-dt edit-dt"
						:rowHover="false"
						editMode="cell"
						resizableColumns
						columnResizeMode="fixed"
						:tableStyle="{ tableLayout: 'fixed', minWidth: '100%' }"
						@cell-edit-complete="onCellEditComplete(ct, $event)"
						@column-resize-end="onChildColumnResizeEnd(ct.fieldname, ct.columns, $event, reqdFieldnames(ct.columns))"
					>
						<Column
							v-for="col in shownColumns(ct.fieldname, ct.columns, reqdFieldnames(ct.columns))"
							:key="col.fieldname"
							:field="col.fieldname"
							:header="col.label + (col.reqd ? ' *' : '')"
							:style="{ width: childColWidth(ct.fieldname, col) }"
						>
							<template #body="{ data, field }">
								<span :class="{ 'esd-mono': col.input === 'link' }">
									{{ childCellDisplay(data[field], col) }}
								</span>
							</template>
							<template #editor="{ data, field }">
								<!-- readonly columns (e.g. Item.attributes.mapping —
								     auto-created by Item._ensure_attribute_mappings_exist)
								     render a static span on cell-click instead of an
								     input, so the user can't pick a value. -->
								<span
									v-if="col.readonly"
									:class="{ 'esd-mono': col.input === 'link' }"
									class="cell-static"
								>{{ childCellDisplay(data[field], col) }}</span>
								<InputNumber
									v-else-if="col.input === 'number'"
									v-model="data[field]"
									:minFractionDigits="col.minFraction"
									:maxFractionDigits="col.maxFraction"
									class="cell-input"
									fluid
									autofocus
								/>
								<AutoComplete
									v-else-if="col.input === 'link'"
									v-model="data[field]"
									:suggestions="childLinkSuggestions"
									@complete="onChildLinkComplete(col, $event, data)"
									dropdown
									completeOnFocus
									class="cell-input"
									fluid
									autofocus
								/>
								<InputText
									v-else
									v-model="data[field]"
									class="cell-input"
									fluid
									autofocus
								/>
							</template>
						</Column>

						<Column :style="{ width: childActionColWidth }" bodyStyle="text-align:center">
							<template #body="{ index }">
								<Button
									icon="pi pi-trash"
									text
									rounded
									severity="danger"
									size="small"
									@click="removeChildRow(ct, index)"
								/>
							</template>
						</Column>

						<template #empty>
							<div v-if="ct.columnsAvailable" class="esd-empty">
								<i class="pi pi-table" />
								<p class="esd-empty__text">No rows yet.</p>
								<Button
									label="Add Row"
									icon="pi pi-plus"
									size="small"
									severity="secondary"
									outlined
									@click="addChildRow(ct)"
								/>
							</div>
							<div v-else class="esd-empty">
								<i class="pi pi-table" />
								<p class="esd-empty__text">Editing this table isn’t available here — open in Desk.</p>
							</div>
						</template>
					</DataTable>
				</div>

				<!-- Lot: the two custom order editors (Desk parity — LotOrder /
				     CutPlanItems islands). `items` and `lot_order_details` are hidden
				     child tables rebuilt server-side from the item_details /
				     order_item_details JSON these editors emit (see buildPayload). -->
				<template v-if="isLot">
					<div class="child-editor">
						<div class="child-editor-head">
							<h4>Order Items</h4>
							<span class="child-cols-note pivot-note">qty · ratio · MRP per size — server explodes the order matrix on save</span>
						</div>
						<p v-if="isLotTransferred" class="child-cols-note lot-locked-note">
							This Lot has been transferred — its order items are locked (edit in Desk if needed).
						</p>
						<LotOrderEditor
							ref="lotItemsGrid"
							:readonly="isLotTransferred"
							:production-detail="form.production_detail || ''"
							@change="onGridChange"
						/>
					</div>
					<div class="child-editor">
						<div class="child-editor-head">
							<h4>Order Details</h4>
							<span class="child-cols-note pivot-note">size × colour matrix — cut/stitch/pack progress is preserved on save</span>
						</div>
						<LotOrderDetailGrid
							ref="lotOrderGrid"
							:readonly="isLotTransferred"
							@change="onGridChange"
						/>
					</div>
				</template>

				<!-- Work Order: `comments` rendered as the VERY LAST element of the
				     form — below the deliverables/receivables
				     pivots AND any other child tables. `comments` is excluded from the
				     regular form-field grid (work-order.js hideFormFields) so it lands
				     here instead of above the tables. Mirrors the Desk's bottom-of-form
				     placement (Desk uses field_order). Editable Text field. -->
				<section
					v-if="woCommentsField"
					class="esd-card form-section wo-comments-section"
				>
					<header class="esd-card__head">
						<span class="esd-card__title">{{ woCommentsField.label }}</span>
					</header>
					<div class="esd-card__body">
						<div :id="'field-' + woCommentsField.fieldname" class="form-field wide">
							<Textarea
								:id="'fld-' + woCommentsField.fieldname"
								v-model="form[woCommentsField.fieldname]"
								:disabled="isReadOnly(woCommentsField)"
								rows="3"
								autoResize
								class="fld"
							/>
							<small v-if="woCommentsField.help" class="field-help">{{ woCommentsField.help }}</small>
						</div>
					</div>
				</section>

				<!-- ITEM: Attribute Values card grid — surfaces the actual values
				     configured per attribute (Stage = Cut/Piece/Pack, …). The
				     bare child-table tab only shows mapping IDs which the user
				     can't read. -->
				<div
					v-if="hasAttributeValuesEditor && doc && mode === 'edit'"
					class="child-editor"
				>
					<div class="child-editor-head">
						<h4>Attribute Values</h4>
					</div>
					<ItemAttributeListView :item-name="doc.name" :doctype="doctype" />
				</div>

				<!-- ITEM: Dependent Attribute matrix editor — also visible in edit
				     mode so the user can configure per-stage UOM/Display Name/
				     applicable attributes without leaving the form. The editor
				     has its own Save (separate server method); it doesn't go
				     through the parent form save. -->
				<div
					v-if="isItem && doc && doc.dependent_attribute && mode === 'edit'"
					class="child-editor"
				>
					<div class="child-editor-head">
						<h4>Dependent Attribute ({{ doc.dependent_attribute }})</h4>
					</div>
					<ItemDependentAttributeEditor
						:item-name="doc.name"
						:editable="canWrite(doctype)"
					/>
				</div>
			</div>
		</div>

		<!-- ════════════════ VIEW BODY ════════════════ -->
		<div v-else-if="doc" class="detail-layout">
			<!-- Main pane: tabs -->
			<div class="detail-main">
				<!-- Record-led header: the doc's load-bearing values surfaced ABOVE the
				     tabs (value-forward hero strip), so the first glance answers "what
				     is this record" before any tab is opened. Reuses quickInfo (same
				     resolve/format rules) — presentational only. -->
				<div v-if="heroFacts.length" class="hero-facts">
					<div v-for="f in heroFacts" :key="'hf-' + f.label" class="hero-fact">
						<div class="hero-fact__l">{{ f.label }}</div>
						<div class="hero-fact__v" :title="f.value">{{ f.value }}</div>
					</div>
				</div>
				<Tabs v-model:value="activeTab">
					<TabList>
						<Tab value="details">Details</Tab>
						<Tab v-if="hasAttributeValuesEditor" value="attribute-values">Attribute Values</Tab>
						<Tab v-if="isLot" value="lot-items">Order Items</Tab>
						<Tab v-if="isLot" value="lot-order-details">Order Details</Tab>
						<Tab v-for="ct in childTables" :key="ct.fieldname" :value="ct.fieldname">
							{{ ct.label }}
							<span v-if="tabBadge(ct)" class="tab-badge">{{ tabBadge(ct) }}</span>
						</Tab>
						<Tab v-if="isItem && doc.dependent_attribute" value="dependent-attribute">
							Dependent Attribute
						</Tab>
						<Tab value="linked">
							Linked Documents
							<span v-if="linkedTotal" class="tab-badge">{{ linkedTotal }}</span>
						</Tab>
						<Tab value="activity">Activity</Tab>
					</TabList>

					<TabPanels>
						<!-- DETAILS -->
						<TabPanel value="details">
							<div v-if="detailSections.length" class="details-stack">
								<section
									v-for="s in detailSections"
									:key="s.key"
									class="detail-card"
								>
									<header class="detail-card__head">
										<span class="detail-card__dot" />
										<span class="detail-card__title">{{ s.label }}</span>
									</header>
									<div class="detail-card__body">
										<div class="field-grid">
											<div v-for="f in s.fields" :key="f.fieldname" class="field">
												<div
													class="field-value"
													:class="{
														link: f.isLink && !isEmptyValue(doc[f.fieldname]),
														'is-empty': isEmptyValue(doc[f.fieldname]),
													}"
													@click="f.isLink && navigateLink(f, doc[f.fieldname])"
												>
													<!-- Q1: Link shows the human name + muted code; plain fields show the
													     formatted value (Q20 bool words via fieldname). -->
													<template v-if="f.isLink && !isEmptyValue(doc[f.fieldname])">
														<span class="lv-name">{{ linkPartsFor(f, doc[f.fieldname]).primary }}</span>
														<span
															v-if="linkPartsFor(f, doc[f.fieldname]).code"
															class="lv-code esd-mono"
														>{{ linkPartsFor(f, doc[f.fieldname]).code }}</span>
													</template>
													<template v-else>{{ displayValue(doc[f.fieldname], f.type, f.fieldname) }}</template>
												</div>
												<label class="field-label">{{ f.label }}</label>
											</div>
										</div>
									</div>
								</section>
							</div>
							<div v-else class="empty-inline">No displayable fields.</div>
						</TabPanel>

						<!-- CHILD TABLES (one panel each) -->
						<TabPanel v-for="ct in childTables" :key="ct.fieldname" :value="ct.fieldname">
							<!-- #B: stock-grouped child tables show the read-only grouped pivot
							     (item → attributes → sizes), same as edit mode -->
							<StockItemGridEditor
								v-if="pivotChildFields.has(ct.fieldname)"
								:editable="false"
								:grouped-field="pivotFor(ct.fieldname)?.groupedField"
								:value-fields="pivotFor(ct.fieldname)?.valueFields || []"
								:entry-fields="pivotFor(ct.fieldname)?.entryFields || []"
								:cell-fields="pivotFor(ct.fieldname)?.cellFields || []"
								:initial-data="viewGrouped[ct.fieldname] || []"
							/>
							<div v-else>
								<div class="child-view-toolbar">
									<Button
										label="Columns"
										icon="pi pi-sliders-h"
										size="small"
										severity="secondary"
										outlined
										@click="toggleColChooser(ct.fieldname, $event)"
									/>
									<Popover :ref="(el) => setColChooserRef(ct.fieldname, el)">
										<div class="col-chooser">
											<div class="col-chooser__head">
												<div class="col-chooser__title">Show columns</div>
												<div class="col-chooser__total">
													{{ childWidthUnitsTotal(ct.fieldname, ct.columns) }}/{{ MAX_TABLE_WIDTH_UNITS }}
												</div>
											</div>
											<div
												v-for="col in ct.columns"
												:key="col.fieldname"
												class="col-chooser__row"
											>
												<Checkbox
													:inputId="'colsel-view-' + ct.fieldname + '-' + col.fieldname"
													:modelValue="isColumnVisible(ct.fieldname, ct.columns, col.fieldname)"
													binary
													@update:modelValue="toggleColumn(ct.fieldname, ct.columns, col.fieldname)"
												/>
												<label :for="'colsel-view-' + ct.fieldname + '-' + col.fieldname">{{ col.label }}</label>
												<InputNumber
													class="col-chooser__width"
													inputClass="col-chooser__width-input"
													:modelValue="childColWidthUnits(ct.fieldname, col)"
													:min="1"
													:max="childWidthUnitMax(ct.fieldname, ct.columns, col)"
													:useGrouping="false"
													@update:modelValue="(value) => setChildColWidthUnits(ct.fieldname, ct.columns, col, value)"
												/>
											</div>
										</div>
									</Popover>
								</div>
								<DataTable
									:value="rowsFor(ct)"
									class="esd-table child-dt"
									:rowHover="false"
									dataKey="name"
									resizableColumns
									columnResizeMode="fixed"
									:tableStyle="{ tableLayout: 'fixed', minWidth: '100%' }"
									@column-resize-end="onChildColumnResizeEnd(ct.fieldname, ct.columns, $event)"
								>
									<Column
										v-for="col in shownColumns(ct.fieldname, ct.columns)"
										:key="col.fieldname"
										:field="col.fieldname"
										:header="col.label"
										:style="{ width: childColWidth(ct.fieldname, col) }"
									>
										<template #body="{ data }">
											<span :class="{ 'esd-mono': col.isLink }">
												{{ displayValue(data[col.fieldname], col.type) }}
											</span>
										</template>
									</Column>
									<template #empty>
										<div class="esd-empty">
											<i class="pi pi-table" />
											<p class="esd-empty__text">No rows.</p>
										</div>
									</template>
								</DataTable>
							</div>
						</TabPanel>

						<!-- LOT: Order Items + Order Details (read-only Desk-island mirrors) -->
						<TabPanel v-if="isLot" value="lot-items">
							<LotOrderEditor
								:readonly="true"
								:initial-data="lotOnload.item_details ?? []"
								:production-detail="doc?.production_detail || ''"
							/>
						</TabPanel>
						<TabPanel v-if="isLot" value="lot-order-details">
							<LotOrderDetailGrid
								:readonly="true"
								:initial-data="lotOnload.order_item_details ?? []"
							/>
						</TabPanel>

						<!-- ATTRIBUTE VALUES (Item) — Desk AttributeList.vue port -->
						<TabPanel v-if="hasAttributeValuesEditor" value="attribute-values">
							<ItemAttributeListView :item-name="doc.name" :doctype="doctype" />
						</TabPanel>

						<!-- DEPENDENT ATTRIBUTE (Item, when set) — Desk port -->
						<TabPanel v-if="isItem && doc.dependent_attribute" value="dependent-attribute">
							<ItemDependentAttributeEditor
								:item-name="doc.name"
								:editable="canWrite(doctype)"
							/>
						</TabPanel>

						<!-- LINKED DOCUMENTS -->
						<TabPanel value="linked">
							<div v-if="linkedLoading" class="state-block sm">
								<i class="pi pi-spin pi-spinner" /> <span>Finding linked documents…</span>
							</div>
							<div v-else-if="linkedGroups.length" class="linked-panel">
								<div v-for="g in linkedGroups" :key="g.doctype" class="linked-group">
									<div class="linked-group-head">
										<h5>{{ g.doctype }}</h5>
										<span class="count">{{ g.rows.length }}</span>
									</div>
									<a
										v-for="row in g.rows"
										:key="row.name"
										class="linked-row"
										@click="navigateDoc(g.doctype, row.name)"
									>
										<span class="lr-id esd-mono">{{ row.name }}</span>
										<span class="lr-meta">{{ linkedRowMeta(row) }}</span>
										<span class="lr-arrow"><i class="pi pi-arrow-right" /></span>
									</a>
								</div>
							</div>
							<div v-else class="empty-inline">
								No documents link to this {{ registry?.label || doctype }} yet.
							</div>
						</TabPanel>

						<!-- ACTIVITY -->
						<TabPanel value="activity">
							<div v-if="activityLoading" class="state-block sm">
								<i class="pi pi-spin pi-spinner" /> <span>Loading activity…</span>
							</div>
							<Timeline
								v-else-if="activityEvents.length"
								:value="activityEvents"
								class="esd-timeline"
							>
								<template #marker="{ item }">
									<span class="tl-dot" :class="item.tone">
										<i :class="item.icon" />
									</span>
								</template>
								<template #content="{ item }">
									<div class="tl-when">{{ formatDateTime(item.when) }} · {{ item.who }}</div>
									<div class="tl-msg" v-html="item.text" />
								</template>
							</Timeline>
							<div v-else class="empty-inline">No activity recorded.</div>
						</TabPanel>
					</TabPanels>
				</Tabs>
			</div>

			<!-- SIDE PANEL -->
			<aside class="detail-side">
				<!-- Quick Info -->
				<Card class="side-card">
					<template #title>
						<header class="esd-card__head">
							<span class="esd-card__title">Quick Info</span>
						</header>
					</template>
					<template #content>
						<div v-for="m in quickInfo" :key="m.label" class="meta-row">
							<span class="k">{{ m.label }}</span>
							<span class="v">{{ m.value }}</span>
						</div>
						<div v-if="!quickInfo.length" class="empty-inline sm">No summary fields.</div>
					</template>
				</Card>

				<!-- Connections (Desk `links` panel parity — DC + GRN for WO) -->
				<Card v-if="connections.length" class="side-card">
					<template #title>
						<header class="esd-card__head">
							<span class="esd-card__title">Connections</span>
						</header>
					</template>
					<template #content>
						<a
							v-for="c in connections"
							:key="c.doctype"
							class="meta-row link-row"
							@click="navigateConnection(c)"
						>
							<span class="k">{{ c.label }}</span>
							<span class="v count-pill">{{ c.count ?? "…" }}</span>
						</a>
					</template>
				</Card>

				<!-- Linked summary -->
				<Card class="side-card">
					<template #title>
						<header class="esd-card__head">
							<span class="esd-card__title">Linked Summary</span>
						</header>
					</template>
					<template #content>
						<div v-if="linkedLoading" class="empty-inline sm">Loading…</div>
						<template v-else-if="linkedGroups.length">
							<a
								v-for="g in linkedGroups"
								:key="g.doctype"
								class="meta-row link-row"
								@click="goToFirst(g)"
							>
								<span class="k">{{ g.doctype }}</span>
								<span class="v count-pill">{{ g.rows.length }}</span>
							</a>
						</template>
						<div v-else class="empty-inline sm">No linked documents.</div>
					</template>
				</Card>
			</aside>
		</div>
	</div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue"
import { useRouter, onBeforeRouteLeave } from "vue-router"
import Tabs from "primevue/tabs"
import TabList from "primevue/tablist"
import Tab from "primevue/tab"
import TabPanels from "primevue/tabpanels"
import TabPanel from "primevue/tabpanel"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Tag from "primevue/tag"
import Timeline from "primevue/timeline"
import Card from "primevue/card"
import Button from "primevue/button"
import Message from "primevue/message"
import InputText from "primevue/inputtext"
import Textarea from "primevue/textarea"
import InputNumber from "primevue/inputnumber"
import DatePicker from "primevue/datepicker"
import ToggleSwitch from "primevue/toggleswitch"
import Select from "primevue/select"
import AutoComplete from "primevue/autocomplete"
import Tooltip from "primevue/tooltip"
import Dialog from "primevue/dialog"
import Popover from "primevue/popover"
import Checkbox from "primevue/checkbox"
import Menu from "primevue/menu"
import { useDoc } from "@/composables/useDoc"
import { useDocNav } from "@/composables/useDocNav"
import { useRealtime } from "@/composables/useRealtime"
import { usePermissions } from "@/composables/usePermissions"
import { useAppConfirm } from "@/composables/useConfirm"
import { useAppToast } from "@/composables/useToast"
import { useLinkTitles } from "@/composables/useLinkTitles"
import { searchLink, getMeta, getDocWithOnload, callMethod, getCount, getList, errorLines, isConflictError } from "@/api/client"
import { getRegistryByRoute, getRegistryByDoctype, WORKFLOW_SEVERITY } from "@/config/doctypes"
import {
	getDetailFieldConfig,
	getDetailGroups,
	getFormFieldOrder,
	getHiddenFormFields,
	getLinkSearchHandler,
	getReadOnlyChildFields,
	getFieldLabel,
	getFieldHelp,
	getBoolLabels,
} from "@/config/fields"
import {
	ACTION_COL_WIDTH,
	MAX_TABLE_WIDTH_UNITS,
	useVisibleColumns,
	persistVisibleColumns,
	resolvedColumnWidth,
	persistColumnWidth,
	resolvedColumnWidthUnits,
	persistColumnWidthUnits,
} from "@/composables/useChildTableColumns"
// Q10: tooltip directive for gated (disabled-with-reason) action buttons.
const vTooltip = Tooltip
import FabricDeliverablesModal from "./FabricDeliverablesModal.vue"
import StockItemGridEditor from "./StockItemGridEditor.vue"
import LotOrderEditor from "./LotOrderEditor.vue"
import LotOrderDetailGrid from "./LotOrderDetailGrid.vue"
import ItemDependentAttributeEditor from "./ItemDependentAttributeEditor.vue"
import ItemAttributeListView from "./ItemAttributeListView.vue"
import LinkField from "@/components/LinkField.vue"
import GRNReceivedTypeEditor from "./GRNReceivedTypeEditor.vue"
import EWaybillGenerateModal from "./EWaybillGenerateModal.vue"
import EWaybillFetchModal from "./EWaybillFetchModal.vue"
import EWaybillCancelModal from "./EWaybillCancelModal.vue"
import EWaybillVehicleModal from "./EWaybillVehicleModal.vue"
import SendSmsModal from "./SendSmsModal.vue"
import SendWhatsAppModal from "./SendWhatsAppModal.vue"

const props = defineProps({
	docRoute: { type: String, required: true },
	id: { type: String, required: true },
})

const router = useRouter()
const { canWrite, canCreate, canDelete, canSubmit, canCancel, canAmend, isAdmin, hasRole } = usePermissions()
const confirm = useAppConfirm()
const toast = useAppToast()
const linkTitles = useLinkTitles()

// Q15: persistent, closable inline banner for the last save/submit/cancel error
// (the toast vanishes; multi-line stock/validation messages need to stay put
// while the user fixes them). Cleared on a successful action or manual close.
const serverError = ref(null) // { title, lines: string[], refresh?: bool } | null

// ── Realtime: live "document modified by another user" notice ──
const realtime = useRealtime()
const staleNotice = ref(false) // another user changed this doc since we loaded
let rtDispose = null // disposer for the current doc subscription
let rtSuppressUntil = 0 // ignore doc_update echoes from our OWN writes until this ts

// Call right before a local write so its own doc_update echo doesn't raise a
// false "modified" notice. We reload after every write (adopting the new
// `modified`), so a short suppression window is enough.
function markLocalWrite() {
	rtSuppressUntil = Date.now() + 3000
}

// doc_update handler: another user saved this doc. Set a non-blocking flag only —
// NEVER advance doc.value.modified here, or the save guard (which sends the loaded
// modified) would send the fresh timestamp and the clobber returns.
function onDocUpdated(data) {
	if (!data || !doc.value) return
	if (Date.now() < rtSuppressUntil) return // our own write echo
	const incoming = data.modified
	const have = doc.value.modified
	// Frappe `modified` is an ISO-ish string → lexicographic compare = chronological.
	if (incoming && have && String(incoming) > String(have)) {
		staleNotice.value = true
	}
}
// Q5: the required field that blocked the last save attempt — drives the inline
// "missing field" banner that complements the toast and lives until resolved.
const missingField = ref(null) // { label, fieldname } | null
// Q6: edit/create dirty tracking. Set true on the first real user edit; gates the
// Discard confirm + the route-leave / beforeunload guards so 15 typed cells
// aren't lost to a mis-tap on a tablet. `dirtyArmed` suppresses the programmatic
// form-building / autofill mutations so only genuine user edits mark dirty.
const isDirty = ref(false)
const dirtyArmed = ref(false)

const registry = computed(() => getRegistryByRoute(props.docRoute))
const doctype = computed(() => registry.value?.doctype || "")
const isWorkOrder = computed(() => doctype.value === "Work Order")
const isDeliveryChallan = computed(() => doctype.value === "Delivery Challan")
const isGoodsReceivedNote = computed(() => doctype.value === "Goods Received Note")
const isItem = computed(() => doctype.value === "Item")
const isLot = computed(() => doctype.value === "Lot")
// A transferred Lot's order editors are LOCKED (Desk parity — lot.js hides the
// LotOrder edit/delete icons and CutPlanItems goes read-only once is_transferred;
// downstream Cutting Plans reference the rebuilt items/lot_order_details, so a
// save must not rebuild them). We render both editors read-only and omit the
// item_details/order_item_details payload (see buildPayload) when transferred.
const isLotTransferred = computed(() => isLot.value && !!(form.is_transferred || doc.value?.is_transferred))
const hasAttributeValuesEditor = computed(() => isItem.value)
const isSubmittable = computed(() => registry.value?.isSubmittable || false)
const isWorkflow = computed(() => registry.value?.isWorkflow || false)
const DUPLICATE_DRAFT_STORAGE_PREFIX = "essdee_yrp:duplicate_draft:"

// ── doc state ──
// doctype is captured once at setup; correct only because AppLayout keys <router-view> by $route.path, remounting per doctype/record. Do not remove that :key.
const docState = useDoc(doctype.value)
const doc = docState.doc
const meta = docState.meta
const metaBundle = docState.metaBundle
const loading = docState.loading
const metaLoading = docState.metaLoading
const linkedLoading = docState.linkedLoading
const activityLoading = docState.activityLoading
const saving = docState.saving
const error = docState.error

// ── mode: "view" | "edit" | "create" ──
const isCreate = computed(() => props.id === "new")
const mode = ref("view")
const isFormMode = computed(() => mode.value === "edit" || mode.value === "create")
const acting = ref(null) // "submit" | "cancel" | "delete" | "amend" | "duplicate" | "convert" | null

// Prompt-named doctypes (autoname="prompt" / naming_rule="Set by user", e.g. Item
// Master Template, FG Item Master Template) require the USER to supply the document
// name at creation — Frappe's REST insert otherwise throws "Please set Document
// Name". The Desk shows a name prompt; the SPA didn't, so CREATE silently failed.
// We surface a required Name input (create mode only) and pass `name` in the insert
// body. autoname/naming_rule are top-level keys on the getdoctype meta (same source
// as title_field / default_print_format used elsewhere here). Compared lower-cased
// so "prompt"/"Prompt" both match.
const isPromptNaming = computed(() => {
	const m = meta.value
	if (!m) return false
	return (
		String(m.autoname || "").toLowerCase() === "prompt" ||
		String(m.naming_rule || "") === "Set by user"
	)
})
// User-supplied document name for prompt-named creates (bound to the Name input).
const newName = ref("")
// ── Prev/Next document navigation (Frappe v15 form-arrow parity) ──
// Left arrow → previous document, right arrow → next, stepping through EXACTLY
// the list the user came from (same active tab/filters/sort, captured in
// useListContext on row-click). Neighbour resolution + the get_next calls live in
// useDocNav; here we just feed it reactive doctype/route/name + a view-mode gate
// and hand it the router push. Resolved after each doc load (see loadAll).
const {
	prevName: docPrevName,
	nextName: docNextName,
	hasPrev: docHasPrev,
	hasNext: docHasNext,
	goPrev: docGoPrev,
	goNext: docGoNext,
	resolve: resolveDocNav,
} = useDocNav(
	{
		doctype,
		docRoute: () => props.docRoute,
		name: () => props.id,
		enabled: () => mode.value === "view" && !isCreate.value && !!doc.value,
	},
	(route, name) => router.push(`/${route}/${encodeURIComponent(name)}`),
)
// Arrows render only on a loaded, saved document in view mode.
const showDocNav = computed(() => mode.value === "view" && !isCreate.value && !!doc.value)

// ── Header action hierarchy ──────────────────────────────────────────────
// Submitted-state "create next" actions, ordered. The FIRST renders as the one
// prominent primary CTA; the rest collapse into the "More" overflow menu so the
// submitted header stops being a wall of equal teal buttons. Gating mirrors the
// previous per-button v-if conditions exactly.
const forwardActions = computed(() => {
	const d = doc.value
	if (!d || mode.value !== "view" || docstatus.value !== 1) return []
	const woGated = d.open_status !== "Open"
	const woTip = woGated
		? `This Work Order is ${d.open_status} — reopen to create deliveries`
		: ""
	const out = []
	if (isWorkOrder.value && canCreate("Delivery Challan"))
		out.push({ key: "wo-dc", label: "Create Delivery Challan", icon: "pi pi-send", handler: onCreateDcFromWo, disabled: woGated, tooltip: woTip })
	if (isWorkOrder.value && canCreate("Goods Received Note"))
		out.push({ key: "wo-grn", label: "Create Goods Received Note", icon: "pi pi-plus-circle", handler: onCreateGrnFromWo, disabled: woGated, tooltip: woTip })
	if (isDeliveryChallan.value && canCreate("Goods Received Note"))
		out.push({ key: "dc-grn", label: "Create Goods Received Note", icon: "pi pi-plus-circle", handler: onCreateGrnFromDc, disabled: false, tooltip: "" })
	return out
})
const primaryForward = computed(() => forwardActions.value[0] || null)
const secondaryForwards = computed(() => forwardActions.value.slice(1))
const moreMenu = ref(null)
// Overflow menu: secondary forward actions + Print + (admin) Open in Desk.
const moreMenuModel = computed(() => {
	if (mode.value !== "view" || !doc.value || isCreate.value) return []
	const items = secondaryForwards.value.map((a) => ({
		label: a.disabled && a.tooltip ? `${a.label} — reopen WO first` : a.label,
		icon: a.icon,
		disabled: a.disabled,
		command: () => a.handler(),
	}))
	if (isLot.value && canWrite(doctype.value)) {
		items.push({ label: "Calculate Order Items", icon: "pi pi-refresh", command: () => onCalculateOrderItems() })
		items.push({ label: "Calculate BOM", icon: "pi pi-calculator", command: () => onCalculateBom() })
	}
	if (canCreate(doctype.value)) {
		items.push({ label: "Duplicate", icon: "pi pi-copy", command: () => onDuplicate() })
	}
	items.push({ label: "Print", icon: "pi pi-print", command: () => openPrintDialog() })
	if (isAdmin.value || hasRole("System Manager"))
		items.push({ label: "Open in Desk", icon: "pi pi-external-link", url: deskUrl.value, target: "_blank" })
	return items
})

const activeTab = ref("details")

// Reactive form model for edit/create (built fresh on entering those modes).
const form = reactive({})
// Per-field Link autocomplete suggestion buffers (parent fields).
const linkSuggestions = reactive({})
// Shared buffer for the child-grid Link cell autocomplete (one cell edits at a time).
const childLinkSuggestions = ref([])
// Child-DocType meta indexed by DocType name (from the getdoctype bundle tail).
// Gives the edit/create child grids typed columns (esp. in create, no rows).
const childMetaCache = ref({})

// Q6: a deep watch flags the form dirty on any change once armed. Building the
// form + the create-from-parent autofill mutate `form` programmatically, so we
// arm only AFTER those settle (armDirty) and reset on entering a fresh form.
watch(
	form,
	() => {
		if (dirtyArmed.value) isDirty.value = true
	},
	{ deep: true },
)
function resetDirty() {
	dirtyArmed.value = false
	isDirty.value = false
}
async function armDirty() {
	await nextTick()
	dirtyArmed.value = true
}
// Native browser-close / refresh guard while a form has unsaved edits.
function beforeUnloadGuard(e) {
	if (isFormMode.value && isDirty.value) {
		e.preventDefault()
		e.returnValue = ""
	}
}
// Q6: stock-pivot grid edits (qty/rate/add/delete row) live in the child editor,
// not `form`, so the deep form watch never sees them. The grids emit `change` on
// genuine user edits; mark the record dirty (once armed) so the guards fire.
function onGridChange() {
	if (dirtyArmed.value) isDirty.value = true
}

// docstatus convenience.
const docstatus = computed(() => Number(doc.value?.docstatus) || 0)
const printDialogOpen = ref(false)
const selectedPrintFormat = ref("")

const printFormatOptions = computed(() => {
	const formats = ["Standard"]
	const printFormats = Array.isArray(meta.value?.__print_formats)
		? [...meta.value.__print_formats]
		: []
	printFormats
		.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")))
		.forEach((pf) => {
			const name = pf?.name
			if (!name || formats.includes(name)) return
			if (String(pf.print_format_type || "").toUpperCase() === "JS") return
			if (Number(pf.raw_printing) === 1) return
			formats.push(name)
		})

	const defaultFormat = meta.value?.default_print_format
	if (defaultFormat && defaultFormat !== "Standard") {
		const idx = formats.indexOf(defaultFormat)
		if (idx >= 0) formats.splice(idx, 1)
		formats.unshift(defaultFormat)
	}
	return formats
})

function defaultPrintFormat() {
	return printFormatOptions.value[0] || "Standard"
}

function openPrintDialog() {
	selectedPrintFormat.value = selectedPrintFormat.value || defaultPrintFormat()
	printDialogOpen.value = true
}

function printViewUrl() {
	const url = new URL("/printview", window.location.origin)
	url.searchParams.set("doctype", doctype.value)
	url.searchParams.set("name", props.id)
	url.searchParams.set("trigger_print", "1")
	url.searchParams.set("format", selectedPrintFormat.value || "Standard")
	url.searchParams.set("no_letterhead", "0")
	url.searchParams.set("settings", "{}")
	return url.toString()
}

function submitPrintDialog() {
	const opened = window.open(printViewUrl(), "_blank", "noopener")
	if (!opened) {
		toast.warn("Pop-up blocked", "Allow pop-ups for this site to open the print page.")
		return
	}
	printDialogOpen.value = false
}

// ── Delivery Challan e-Waybill (GST e-Way Bill) + SMS — yrp_ewaybill_api ──
// Header actions for a submitted DC. The overflow-style Menu is context-gated
// on doc.ewaybill: generate/fetch when none exists, print/update/cancel once it
// does. Each modal posts its own whitelisted action and we reloadView() on
// success so the ewaybill / e_waybill_status header fields refresh.
const ewbGenerateOpen = ref(false)
const ewbFetchOpen = ref(false)
const ewbCancelOpen = ref(false)
const ewbVehicleOpen = ref(false)
const sendSmsOpen = ref(false)
const ewbMenu = ref(null)

// ── WhatsApp — yrp.whatsapp_notification (any WhatsApp-enabled doctype) ──
// Which doctypes have WhatsApp wired up is server-configured, so the header
// button is gated on a small map fetched once (name -> supplier_key), NOT
// hardcoded to a single doctype the way isDeliveryChallan gates Send SMS today.
const sendWhatsAppOpen = ref(false)
const whatsAppEnabledDoctypes = ref({}) // { DocType: supplier_key }

async function loadWhatsAppEnabledDoctypes() {
	try {
		const r = await callMethod("yrp.whatsapp_notification.get_enabled_whatsapp_doctypes", {})
		whatsAppEnabledDoctypes.value = r?.doctypes || {}
	} catch (_) {
		// Non-fatal: the Send WhatsApp button just stays hidden for every doctype.
	}
}

const isWhatsAppEnabled = computed(() =>
	Object.prototype.hasOwnProperty.call(whatsAppEnabledDoctypes.value, doctype.value),
)
// Which link field on THIS doctype names the supplier to message (DC/GRN/PO
// use "supplier"; Stock Entry passes "to_supplier"/"from_supplier") — mirrors
// SendSmsModal's supplierKey convention, server-declared per doctype.
const whatsAppSupplierKey = computed(() => whatsAppEnabledDoctypes.value[doctype.value] || "supplier")

const ewbMenuModel = computed(() => {
	if (!doc.value) return []
	if (!doc.value.ewaybill) {
		return [
			{ label: "Generate e-Waybill", icon: "pi pi-plus", command: () => (ewbGenerateOpen.value = true) },
			{ label: "Fetch existing", icon: "pi pi-download", command: () => (ewbFetchOpen.value = true) },
		]
	}
	return [
		{ label: "Print e-Waybill", icon: "pi pi-print", command: () => printEwaybill() },
		{ label: "Update Vehicle", icon: "pi pi-truck", command: () => (ewbVehicleOpen.value = true) },
		{ label: "Cancel e-Waybill", icon: "pi pi-ban", command: () => (ewbCancelOpen.value = true) },
	]
})

// Refresh the stored EWB payload, then open the print view in a new tab (same
// pop-up-blocked fallback as submitPrintDialog). Prints the YRP E-Waybill Log
// record named by doc.ewaybill via the "YRP e-Waybill" print format.
async function printEwaybill() {
	if (!doc.value?.ewaybill) return
	// Refresh the stored payload, but never block the print if it errors (e.g. a
	// transient GST-resolve issue) — open the print with possibly-stale data.
	try {
		await callMethod("yrp_ewaybill_api.ewaybill.actions.fetch_ewaybill_data", {
			doctype: doctype.value,
			docname: props.id,
		})
	} catch (e) {
		toast.warn("Couldn't refresh e-Waybill", e.message)
	}
	const url =
		"/printview?doctype=YRP E-Waybill Log&name=" +
		encodeURIComponent(doc.value.ewaybill) +
		"&format=YRP e-Waybill&no_letterhead=1&trigger_print=1"
	const opened = window.open(url, "_blank", "noopener")
	if (!opened) {
		toast.warn("Pop-up blocked", "Allow pop-ups for this site to open the print page.")
	}
}

// "<ewaybill> · <status>" chip shown beside the title once the EWB exists.
const ewbStatusTag = computed(() =>
	doc.value?.ewaybill ? `${doc.value.ewaybill} · ${doc.value.e_waybill_status || "Generated"}` : "",
)

// Modal success handlers — each reloads the doc so the header EWB fields refresh.
async function onEwbGenerated() {
	await reloadView()
}
async function onEwbFetched() {
	await reloadView()
}
async function onEwbCancelled() {
	await reloadView()
}
async function onEwbUpdated() {
	await reloadView()
}
async function onSmsSent() {
	await reloadView()
}
async function onWhatsAppSent() {
	await reloadView()
}

// System fields we never surface in the Details grid / Quick Info / form.
const SYSTEM_FIELDS = new Set([
	"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
	"doctype", "parent", "parentfield", "parenttype", "_user_tags", "_comments",
	"_assign", "_liked_by", "_seen", "_comment_count", "title_field",
	"deliverable_details", "receivable_details", "amended_from",
])
const META_HIDDEN_FIELDTYPES = new Set([
	"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Button",
	"Fold", "Image", "Geolocation", "Signature", "Table", "Table MultiSelect",
	// Internal data blobs — never useful in a read-only Details view (e.g. Work
	// Order's *_json fields). Hidden everywhere so no DocType leaks them.
	"JSON", "Code",
])
// Hidden grouped-JSON fields — NEVER editable / sent (the flat-rows contract).
const GROUPED_JSON_FIELDS = new Set([
	"item_details", "deliverable_details", "receivable_details",
])
// Child tables with a dedicated surface elsewhere → kept out of the generic
// per-child-table tabs AND the edit grids. Work Order's tracking_logs and
// track_pieces are server-side bookkeeping the floor users don't need surfaced
// on /web (user, 2026-05-29).
const CHILD_TABLE_EXCLUDE = new Set([
	"work_order_tracking_logs",
	"work_order_track_pieces",
])

// ── R3a: stock size-pivot (grouped item_details) opt-in ──────────────────────
// For these stock-voucher doctypes ONLY, edit/create renders the grouped pivot
// editor (StockItemGridEditor) INSTEAD of the flat child grid, and buildPayload
// emits grouped JSON into the grouped field + sends an EMPTY flat child array
// (the OPPOSITE of the flat path — each voucher's before_validate then runs
// ungroup_items_from_ui to resolve/create variants server-side).
//
// `ungroupKey` is the parent_doctype string PARENT_CHILD_MAP keys on; valueFields/
// entryFields are mirrored from PARENT_CHILD_MAP so the per-cell / per-row extra
// fields round-trip. Each entry = one pivot section in the form.
// Every OTHER doctype is untouched (flat grid + empty grouped JSON, as before).
const STOCK_GROUPED_MAP = {
	"Stock Entry": [{
		childField: "items", groupedField: "item_details", ungroupKey: "Stock Entry",
		label: "Items", valueFields: ["rate", "secondary_qty", "secondary_uom"],
		entryFields: ["allow_zero_valuation_rate", "make_qty_zero"],
		// rate is editable PER cell (matches Desk Stock/StockEntry/StockEntry.vue
		// tableFields: rate uses_primary_attribute + qty_fields includes rate).
		cellFields: [{ name: "rate", label: "Rate", editable: true }],
		showAllowZeroRate: true,
		showSecondaryToggle: true,
	}],
	"Delivery Challan": [{
		childField: "items", groupedField: "item_details", ungroupKey: "Delivery Challan",
		label: "Items",
		valueFields: [
			"rate", "valuation_rate", "pending_quantity", "delivered_quantity",
			"received_quantity", "stock_qty", "amount", "ref_doctype", "ref_docname",
			"secondary_qty", "secondary_uom",
		],
		entryFields: ["stock_uom", "conversion_factor", "set_combination", "comments"],
		showSecondaryToggle: true,
		// DC is always against a WO; items derive from the WO and the user
		// only edits per-cell qty/rate/Sec Qty — no Add Item, no per-row
		// delete/edit (preference 2026-05-29).
		lockedItems: true,
	}],
	"Goods Received Note": [{
		childField: "items", groupedField: "item_details", ungroupKey: "Goods Received Note",
		label: "Items",
		valueFields: [
			"rate", "pending_quantity", "max_receivable_quantity", "stock_qty", "amount",
			"ref_doctype", "ref_docname", "delivery_challan_item",
			"secondary_qty", "secondary_uom",
		],
		entryFields: [
			"stock_uom", "conversion_factor", "ref_doctype", "ref_docname",
			"delivery_challan_item", "set_combination", "comments",
		],
		showSecondaryToggle: true,
	}],
	"Work Order": [
		{
			childField: "deliverables", groupedField: "deliverable_details",
			ungroupKey: "Work Order Deliverables", label: "Deliverables",
			cellFields: [{ name: "pending_quantity", label: "Pending" }],
			valueFields: ["pending_quantity", "stock_update", "valuation_rate"],
			entryFields: [
				"comments", "secondary_qty", "secondary_uom", "cancelled_quantity",
				"additional_parameters", "set_combination", "grn_detail_no", "item_type",
				"is_calculated", "source_grn", "source_grn_item", "source_inspection_entry_item",
			],
		},
		{
			childField: "receivables", groupedField: "receivable_details",
			ungroupKey: "Work Order Receivables", label: "Receivables",
			cellFields: [{ name: "cost", label: "Cost" }, { name: "pending_quantity", label: "Pending" }],
			valueFields: ["cost", "pending_quantity", "total_cost"],
			entryFields: [
				"comments", "secondary_qty", "secondary_uom", "process_cost",
				"additional_parameters", "set_combination",
			],
		},
	],
}

// The pivot sections to render for the current doctype (empty ⇒ flat path).
const stockPivots = computed(() => STOCK_GROUPED_MAP[doctype.value] || [])
const useStockPivot = computed(() => isFormMode.value && stockPivots.value.length > 0)

// ── Connections (Desk's `links` panel equivalent — preference 2026-05-29) ──
// Each entry: { doctype, route, label?, filters(name) → [[field, op, value], …] }.
// filters() takes the parent doc's name (e.g. WO-00010-1) and returns the
// Frappe filter triples to apply on the child list. For DC the relationship
// is direct (Link field `work_order`); for GRN it's a Dynamic Link so we
// constrain BOTH `against` (the controlling Select) and `against_id` (the
// value). The route matches the registry slug — DynamicListPage reads
// route.query.filters and seeds them as the base filter on first fetch.
const CONNECTIONS_MAP = {
	"Work Order": [
		{
			doctype: "Delivery Challan",
			route: "/delivery-challan",
			filters: (name) => [["work_order", "=", name]],
		},
		{
			doctype: "Goods Received Note",
			route: "/goods-received-note",
			filters: (name) => [
				["against", "=", "Work Order"],
				["against_id", "=", name],
			],
		},
	],
	// Q9: a Delivery Challan's downstream GRNs (GRN.delivery_challan Link → DC),
	// so the chain no longer dead-ends at the DC.
	"Delivery Challan": [
		{
			doctype: "Goods Received Note",
			route: "/goods-received-note",
			filters: (name) => [["delivery_challan", "=", name]],
		},
	],
}

const connections = ref([])

// Live counts for the Connections card. Renders only when CONNECTIONS_MAP
// has an entry for this doctype and we have a doc loaded.
async function loadConnections() {
	const configs = CONNECTIONS_MAP[doctype.value]
	if (!configs?.length || !doc.value) {
		connections.value = []
		return
	}
	const items = configs.map((c) => ({
		doctype: c.doctype,
		route: c.route,
		label: c.label || c.doctype,
		filterTriples: c.filters(doc.value.name),
		count: null,
	}))
	connections.value = items
	// Fetch counts in parallel; each call updates its own slot reactively.
	await Promise.all(
		items.map(async (item, i) => {
			const filterObj = {}
			for (const [field, op, value] of item.filterTriples) {
				filterObj[field] = op === "=" ? value : [op, value]
			}
			try {
				const n = await getCount(item.doctype, filterObj)
				const next = connections.value.slice()
				next[i] = { ...next[i], count: Number(n) || 0 }
				connections.value = next
			} catch (_) {
				/* leave count as null on failure */
			}
		}),
	)
}

function navigateConnection(c) {
	router.push({
		path: c.route,
		query: { filters: JSON.stringify(c.filterTriples) },
	})
}

// R3b: Goods Received Note against a Work Order uses the received-type-SPLIT
// editor (GRNReceivedTypeEditor) instead of the generic size-pivot — mirrors the
// Desk's useReceivedTypeGrnEditor gate (editorType === goods_received_note &&
// against === "Work Order"). GRN-against-Purchase-Order (or a GRN with no source
// yet, e.g. create mode where doc.against is unset) keeps the generic pivot.
// `against` comes from the loaded doc; both editors share the gridRefs surface so
// hydratePivotsForEdit + buildPayload work for either.
const useGrnSplit = computed(
	() => doctype.value === "Goods Received Note" && (form.against || doc.value?.against) === "Work Order",
)

// Per-section refs to the mounted grid editors (keyed by childField), so onSave
// can pull each section's grouped JSON via getItems(). Plain object (not reactive)
// — we only call imperative methods on the instances, never render them.
const gridRefs = {}
function setGridRef(childField, el) {
	if (el) gridRefs[childField] = el
	else delete gridRefs[childField]
}

// The set of flat child fields the pivot replaces — used to drop their flat
// editors AND to blank them in the payload so the server rebuilds from grouped.
const pivotChildFields = computed(
	() => new Set(stockPivots.value.map((p) => p.childField)),
)

// VIEW mode (#B): render the read-only grouped pivot (same shape as edit) instead
// of flat item_variant rows. The grouped JSON comes from the doc's onload.
const viewGrouped = ref({})
function pivotFor(fieldname) {
	return stockPivots.value.find((p) => p.childField === fieldname) || null
}
// An entry has no value (for the READ-ONLY view) when every size cell is zero
// qty AND every read-only cell value (Pending/Cost…) is zero too. The server pads
// grouped item_details with extra entries (e.g. one per GRN received type) so the
// EDIT split-editor can offer them — those padded all-zero entries are NOT stored,
// so we drop them from the view rather than render empty rows. A pending-only row
// (WO receivable: qty 0 but Pending > 0) is kept.
function entryHasNoValue(entry, cellFields) {
	const vals = entry?.values || {}
	for (const pv of Object.keys(vals)) {
		const cell = vals[pv] || {}
		if (Number(cell.qty)) return false
		for (const cf of cellFields || []) {
			if (Number(cell[cf.name])) return false
		}
	}
	return true
}

async function hydratePivotsForView() {
	if (!stockPivots.value.length) return
	try {
		const loaded = await getDocWithOnload(doctype.value, props.id)
		const onload = loaded?.__onload || {}
		const next = {}
		for (const pv of stockPivots.value) {
			const grouped = onload[pv.groupedField]
			const groups = grouped != null ? grouped : []
			// Drop padded all-zero entries (e.g. GRN received types with no qty)
			// so the read-only view shows only what's actually recorded — EXCEPT
			// for locked-items vouchers (DC against WO), where user-zeroed rows
			// are intentional draft state the user expects to see (so they can
			// re-edit them later). The submit pass strips those server-side.
			const keepAll = !!pv.lockedItems
			next[pv.childField] = groups
				.map((grp) => ({
					...grp,
					items: (grp.items || []).filter(
						(e) => keepAll || !entryHasNoValue(e, pv.cellFields || []),
					),
				}))
				.filter((grp) => (grp.items || []).length)
		}
		viewGrouped.value = next
	} catch (_) {
		viewGrouped.value = {}
	}
}

// ── Lot: custom order editors (Desk LotOrder / CutPlanItems parity) ─────────
// The two grids are the Lot's real data-entry surfaces. View mode feeds them
// from the doc's onload (read-only); edit mode hydrates the mounted editors
// imperatively; create mode hydrates the items editor when the user picks an
// Item Production Detail (runDocAutofill). buildPayload serializes them into
// item_details / order_item_details ONLY when hydrated — the Lot controller's
// before_validate rebuilds `items` / `lot_order_details` server-side and
// preserves cut/stitch/pack progress by merging against the sent child rows,
// so the children themselves are NEVER blanked here (Desk contract).
const lotItemsGrid = ref(null)
const lotOrderGrid = ref(null)
// null = unknown (fall through to meta); true/false = check_enabled_po result.
const lotPoEnabled = ref(null)
async function loadLotPoEnabled() {
	try {
		const r = await callMethod("essdee_yrp.essdee_yrp.doctype.lot.lot.check_enabled_po", {})
		lotPoEnabled.value = !!r
	} catch (_) {
		lotPoEnabled.value = null
	}
}
const lotOnload = ref({})
const lotItemsHydrated = ref(false)
const lotOrderHydrated = ref(false)

async function hydrateLotForView() {
	try {
		const loaded = await getDocWithOnload(doctype.value, props.id)
		lotOnload.value = loaded?.__onload || {}
	} catch (_) {
		lotOnload.value = {}
	}
}

async function hydrateLotForEdit() {
	lotItemsHydrated.value = false
	lotOrderHydrated.value = false
	try {
		const loaded = await getDocWithOnload(doctype.value, props.id)
		const onload = loaded?.__onload || {}
		lotOnload.value = onload
		await nextTick()
		if (lotItemsGrid.value?.loadData && onload.item_details != null) {
			lotItemsGrid.value.loadData(onload.item_details)
			lotItemsHydrated.value = true
		}
		if (lotOrderGrid.value?.loadData) {
			lotOrderGrid.value.loadData(onload.order_item_details || [])
			lotOrderHydrated.value = true
		}
	} catch (_) {
		toast.warn("Could not load the Lot's order items", "Re-open the page before saving, or edit in Desk.")
	}
}

// Create/edit: (re)load the items editor from get_item_details after the IPD
// changes — the same call chain lot.js runs on production_detail change.
async function reloadLotItemsEditor() {
	if (!form.item || !form.production_detail) {
		lotItemsGrid.value?.loadData?.([])
		lotItemsHydrated.value = mode.value === "create"
		return
	}
	try {
		const structure = await callMethod(
			"essdee_yrp.essdee_yrp.doctype.lot.lot.get_item_details",
			{
				item_name: form.item,
				uom: form.uom || undefined,
				production_detail: form.production_detail,
				dependent_attr_mapping: form.dependent_attribute_mapping || undefined,
				ppo: form.production_order || undefined,
			},
		)
		lotItemsGrid.value?.loadData?.(structure || [])
		lotItemsHydrated.value = true
		if (mode.value === "create") lotOrderHydrated.value = true
	} catch (e) {
		toast.error("Couldn't load order items", e.message)
	}
}

// Lot view actions (Desk custom buttons): re-run the size/colour explosion, and
// recalculate the BOM summary from the current order details.
function onCalculateOrderItems() {
	if (!doc.value) return
	confirm.require({
		header: "Calculate Order Items",
		message: `Recalculate the order details of ${doc.value.name} from its order items?`,
		acceptLabel: "Yes",
		rejectLabel: "No",
		accept: async () => {
			acting.value = "calc-order"
			try {
				await callMethod(
					"essdee_yrp.essdee_yrp.doctype.lot.lot.update_order_details",
					{ doc_name: doc.value.name },
				)
				toast.success("Order items calculated")
				await reloadView()
				await hydrateLotForView()
			} catch (e) {
				showActionError("Calculate Order Items failed", e)
			} finally {
				acting.value = null
			}
		},
	})
}

function onCalculateBom() {
	if (!doc.value) return
	if (!doc.value.item || !doc.value.production_detail) {
		toast.warn("Not ready", "Set the Item and Item Production Detail first.")
		return
	}
	confirm.require({
		header: "Calculate BOM",
		message: `Recalculate the Bill of Materials of ${doc.value.name}?`,
		acceptLabel: "Calculate",
		rejectLabel: "Cancel",
		accept: async () => {
			acting.value = "calc-bom"
			try {
				await callMethod(
					"yrp.yrp.doctype.item_production_detail.item_production_detail.get_calculated_bom",
					{
						item_production_detail: doc.value.production_detail,
						items: doc.value.lot_order_details || [],
						lot_name: doc.value.name,
					},
				)
				toast.success("BOM calculated")
				await reloadView()
			} catch (e) {
				showActionError("Calculate BOM failed", e)
			} finally {
				acting.value = null
			}
		},
	})
}

// ── load orchestration ──
async function loadAll() {
	if (!doctype.value) return
	acting.value = null

	if (isCreate.value) {
		// Create mode: meta only, then build a blank form. No doc/linked/activity.
		mode.value = "create"
		await docState.loadMeta()
		await loadChildMetas()
		buildCreateForm()
		if (isLot.value) loadLotPoEnabled()
		return
	}

	mode.value = "view"
	activeTab.value = "details"
	// Meta first (gives field labels + child-table descriptors), then doc.
	//
	// EMPTY-META RACE: the view body (and its child-table panels) renders as soon
	// as `doc` resolves. If `childMetaCache` is still empty at that first paint,
	// childColumnsFromMeta returns [] and useVisibleColumns would seed a (guarded
	// against, but still undesirable) empty visible Set. So we load the child
	// metas IN PARALLEL with the doc but AWAIT BOTH before proceeding — mirroring
	// the create path — guaranteeing childMetaCache is populated on first paint of
	// a non-empty childTables. loadMeta and loadChildMetas share one underlying
	// getdoctype fetch (see loadChildMetas), so this is a single network round-trip.
	const metaReady = loadChildMetas() // awaits loadMeta internally; populates childMetaCache
	await Promise.all([metaReady, docState.load(props.id)])
	if (!docState.doc.value) return
	// Realtime: (re)subscribe to this doc's room for live "modified" notices.
	// Dispose any prior subscription first (the :key remount usually unmounts us,
	// but the [docRoute,id] watcher can re-run loadAll without an unmount).
	if (rtDispose) { rtDispose(); rtDispose = null }
	staleNotice.value = false
	rtDispose = realtime.onDocUpdate(doctype.value, props.id, onDocUpdated)
	// Open on the redesigned Details tab (default) so it's the first impression.
	// Still hydrate the stock pivots so their child tables render instantly when
	// the user switches to them.
	if (stockPivots.value.length) {
		hydratePivotsForView()
	}
	if (isLot.value) {
		hydrateLotForView()
		loadLotPoEnabled()
	}
	docState.loadLinked(props.id)
	docState.loadActivity(props.id)
	loadConnections()
	// Resolve prev/next neighbours for the header arrows, stepping through the
	// list the user came from (captured list context) — fire-and-forget.
	resolveDocNav()
}

// The getdoctype bundle is [parentMeta, ...childMetas] keyed by DocType name.
// useDoc.loadMeta keeps only the parent; we index the child metas here so the
// edit/create child-table grids get proper, typed columns (esp. in create mode
// where no rows exist to infer columns from). Fetched once per doctype.
//
// DEDUPE: loadChildMetas no longer fires its own getdoctype request. It awaits
// useDoc.loadMeta() (which DocDetail also calls for the parent meta) and reuses
// the SAME bundle that call fetched, exposed as docState.metaBundle. loadMeta
// shares one in-flight promise, so the two former duplicate getdoctype requests
// per load collapse into one. Falls back to a direct getMeta only if the bundle
// is somehow unavailable (e.g. loadMeta failed but the endpoint later succeeds).
const childMetasLoaded = ref(false)
async function loadChildMetas() {
	if (childMetasLoaded.value || !doctype.value) return
	try {
		await docState.loadMeta()
		let bundle = metaBundle.value
		if (!Array.isArray(bundle) || !bundle.length) {
			bundle = await getMeta(doctype.value)
		}
		const cache = {}
		for (const m of bundle) {
			if (m?.name) cache[m.name] = m
		}
		childMetaCache.value = cache
		childMetasLoaded.value = true
	} catch (_) {
		// Non-fatal: child grids fall back to row-inferred columns.
	}
}

watch(
	() => [props.docRoute, props.id],
	() => loadAll(),
	{ immediate: false },
)
onMounted(loadAll)

// ── Keyboard shortcuts (permission-gated) ──
// Ctrl/Cmd+S: in edit/create → Save; on a saved draft (view) → Submit (confirm).
// Ctrl/Cmd+D: on a submitted doc (view) → Cancel (confirm). Each fires only when
// the user holds the matching permission; the Submit/Cancel popups are the same
// confirm dialogs the buttons use.
function onShortcut(e) {
	if (!(e.ctrlKey || e.metaKey)) return
	const key = (e.key || "").toLowerCase()
	// Shift+Ctrl+< (prev) / Shift+Ctrl+> (next) document — Frappe v15 form-arrow
	// parity. View mode only, and never while the user is typing in a field (so a
	// Shift+Ctrl+. in a search/text input doesn't yank the page away). "<" is
	// Shift+comma, ">" is Shift+period — accept the shifted symbol and the base
	// punctuation key across layouts.
	const t = e.target
	const typing = !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)
	if (e.shiftKey && showDocNav.value && !typing) {
		if (key === ">" || key === ".") {
			e.preventDefault()
			docGoNext()
			return
		}
		if (key === "<" || key === ",") {
			e.preventDefault()
			docGoPrev()
			return
		}
	}
	if (key === "s") {
		e.preventDefault()
		if (saving.value || acting.value) return
		if (isFormMode.value) {
			const allowed = mode.value === "create" ? canCreate(doctype.value) : canWrite(doctype.value)
			if (allowed) onSave()
		} else if (doc.value && docstatus.value === 0 && isSubmittable.value && canSubmit(doctype.value)) {
			// Workflow doctypes (isSubmittable=false) are excluded here by design —
			// they submit via workflow transitions, never a plain docstatus PUT.
			onSubmit()
		}
	} else if (key === "d") {
		e.preventDefault()
		if (acting.value || isFormMode.value || !doc.value) return
		if (docstatus.value === 1 && isSubmittable.value && canCancel(doctype.value)) {
			onCancel() // submitted → Cancel confirmation
		} else if (docstatus.value === 0 && canDelete(doctype.value)) {
			onDelete() // saved draft → Delete confirmation
		}
	}
}
onMounted(() => {
	window.addEventListener("keydown", onShortcut)
	window.addEventListener("beforeunload", beforeUnloadGuard)
	loadWhatsAppEnabledDoctypes()
})
onBeforeUnmount(() => {
	window.removeEventListener("keydown", onShortcut)
	window.removeEventListener("beforeunload", beforeUnloadGuard)
	if (rtDispose) { rtDispose(); rtDispose = null }
})

// Q6: SPA route-leave guard — confirm before navigating away from a dirty
// edit/create form (sidebar tap, breadcrumb, link). Resolves the navigation
// only if the user confirms; otherwise stays put.
onBeforeRouteLeave((to, from, next) => {
	if (isFormMode.value && isDirty.value) {
		confirm.require({
			header: "Discard unsaved changes?",
			message: "You have unsaved changes on this form. Leave without saving?",
			icon: "pi pi-exclamation-triangle",
			acceptLabel: "Leave",
			acceptClass: "p-button-danger",
			rejectLabel: "Stay",
			accept: () => {
				isDirty.value = false
				next()
			},
			reject: () => next(false),
		})
	} else {
		next()
	}
})

// ── meta field map ──
const metaFieldMap = computed(() => {
	const map = {}
	for (const f of meta.value?.fields || []) map[f.fieldname] = f
	return map
})

function linkTypeFor(fieldname) {
	const mf = metaFieldMap.value[fieldname]
	return mf?.fieldtype === "Link"
}

// ════════════════ EDIT / CREATE: editable field descriptors ════════════════

// Map a meta fieldtype to an input kind + formatting hints.
function inputDescriptor(mf) {
	const ft = mf.fieldtype
	const base = {
		fieldname: mf.fieldname,
		// Q18: SPA label override (e.g. supplier → "Job-worker") wins over meta.
		label: getFieldLabel(doctype.value, mf.fieldname) || mf.label || humanize(mf.fieldname),
		// Q13: inline help — SPA override first, else the meta description the Desk
		// shows but /web users never see. Empty string = no help line rendered.
		help: getFieldHelp(doctype.value, mf.fieldname) || mf.description || "",
		reqd: !!mf.reqd,
		readOnly: !!mf.read_only,
		fieldtype: ft,
		input: "text",
		wide: false,
		dependsOn: mf.depends_on || "",
		mandatoryDependsOn: mf.mandatory_depends_on || "",
		readOnlyDependsOn: mf.read_only_depends_on || "",
		fetchFrom: mf.fetch_from || "",
	}
	if (ft === "Data" || ft === "Small Text") return { ...base, input: "text" }
	if (ft === "Text" || ft === "Long Text" || ft === "Code" || ft === "Text Editor" || ft === "Markdown Editor") {
		return { ...base, input: "textarea", wide: true }
	}
	if (ft === "Int") return { ...base, input: "number", minFraction: 0, maxFraction: 0 }
	if (ft === "Float") return { ...base, input: "number", minFraction: 0, maxFraction: 6 }
	if (ft === "Percent") return { ...base, input: "number", minFraction: 0, maxFraction: 2, suffix: " %" }
	if (ft === "Currency") return { ...base, input: "number", minFraction: 2, maxFraction: 2 }
	if (ft === "Date") return { ...base, input: "date" }
	if (ft === "Datetime") return { ...base, input: "datetime" }
	if (ft === "Time") return { ...base, input: "time" }
	if (ft === "Check") return { ...base, input: "check" }
	if (ft === "Select") {
		const options = String(mf.options || "")
			.split("\n")
			.map((s) => s.trim())
			.filter((s) => s !== "")
		return { ...base, input: "select", options }
	}
	if (ft === "Link" || ft === "Dynamic Link") {
		// Dynamic Link: `options` is the FIELDNAME holding the target doctype
		// (resolved from the form at search time), not a fixed doctype.
		const dynamic = ft === "Dynamic Link"
		return {
			...base,
			input: "link",
			linkTarget: dynamic ? "" : (mf.options || ""),
			isDynamic: dynamic,
			dynamicField: dynamic ? (mf.options || "") : "",
		}
	}
	// Unhandled-but-editable scalar fieldtypes fall back to a text input.
	return base
}

// Per-DocType set of fieldnames to never render in EDIT/CREATE (e.g. WO's
// `includes_packing`). Empty Set for doctypes without overrides — safe to
// `.has()` unconditionally.
const hiddenFormFieldSet = computed(() => getHiddenFormFields(doctype.value))

// The ordered, editable field list for the form. Drives create + edit.
// Order: per-doctype `formOrder` (when present) → meta order. Either way the
// fieldtype/required/read-only come from meta. Fields in the doctype's
// hide list are silently dropped (irrespective of where they sit in order).
const formFields = computed(() => {
	if (!isFormMode.value) return []
	const mfMap = metaFieldMap.value
	if (!Object.keys(mfMap).length) return []

	const out = []
	const seen = new Set()
	const hidden = hiddenFormFieldSet.value
	const pushByFieldname = (fn) => {
		if (seen.has(fn)) return
		if (hidden.has(fn)) return
		const mf = mfMap[fn]
		if (!mf) return
		if (!isEditableMetaField(mf)) return
		seen.add(fn)
		out.push(inputDescriptor(mf))
	}

	const order = getFormFieldOrder(doctype.value)
	if (order) {
		for (const fn of order) pushByFieldname(fn)
		// Append any remaining editable meta fields not covered by the order,
		// so nothing required is silently un-editable.
		for (const mf of meta.value.fields) pushByFieldname(mf.fieldname)
		return out
	}

	for (const mf of meta.value.fields) pushByFieldname(mf.fieldname)
	return out
})

// Evaluate a Frappe depends_on / mandatory_depends_on expression against a parent
// state object (`parent`, default the live `form` model). `eval:<js>` runs the JS
// with `doc` = parent; a bare fieldname is truthy when that field is set. A bad/odd
// expression fails open (shows the field). View-mode callers pass `doc.value` so
// the same rule evaluates against the loaded document.
function evalCondition(expr, parent = form) {
	const raw = String(expr || "").trim()
	if (!raw) return true
	const src = parent || {}
	if (raw.startsWith("eval:")) {
		try {
			return !!Function("doc", `"use strict"; return (${raw.slice(5)});`)(src)
		} catch (_) {
			return true
		}
	}
	return !!src[raw]
}

// reqd is the static meta flag OR a currently-satisfied mandatory_depends_on.
function isReqd(f) {
	if (f.reqd) return true
	return f.mandatoryDependsOn ? evalCondition(f.mandatoryDependsOn) : false
}

// read_only = the static meta flag OR a satisfied read_only_depends_on (e.g.
// posting_date/time stay read-only until "Edit Posting Date and Time" is ticked).
// Reads `form` so it re-evaluates reactively as the user toggles.
function isReadOnly(f) {
	// Lot mirrors lot.js's check_enabled_po gating: with Production-Order mode
	// ON, `item` is read-only (fetched from the PO) and `production_order` is
	// pickable; with it OFF, `item` is typed directly and `production_order`
	// locks. An item without a PO also locks `production_order` (Desk parity).
	if (isLot.value && f.fieldname === "item") {
		if (lotPoEnabled.value != null) return lotPoEnabled.value === true
	}
	if (isLot.value && f.fieldname === "production_order") {
		if (form.item && !form.production_order) return true
		if (lotPoEnabled.value != null) return lotPoEnabled.value === false
	}
	if (f.readOnly) return true
	return f.readOnlyDependsOn ? evalCondition(f.readOnlyDependsOn) : false
}

// The form fields actually shown: drop any whose depends_on is currently false,
// AND drop READ-ONLY fields with no value. Reactive on `form` so the filter
// re-runs as the user edits.
//
// Read-only rule (uniform across CREATE + EDIT): a read-only field with no
// value is derived/auto-filled and must not clutter the form; it reappears the
// instant it carries a value. This keeps system-managed fields hidden in
// create (status / approved_by / start_date / end_date — all empty by default)
// while letting fetch-from previews (supplier_name, delivery_location_name)
// surface as soon as their source field resolves, AND letting fields with a
// real default (wo_date = Today) show with that default. (The earlier
// blanket-hide-on-create was overly broad — it masked wo_date and the fetched
// names. User flagged on 2026-05-29.)
const visibleFormFields = computed(() =>
	formFields.value.filter((f) => {
		if (f.dependsOn && !evalCondition(f.dependsOn)) return false
		if (isReadOnly(f)) {
			const mfType = metaFieldMap.value[f.fieldname]?.fieldtype
			if (isEmptyForHide(form[f.fieldname], mfType)) return false
		}
		return true
	}),
)

// Group the visible form fields into titled cards by Section Break, mirroring the
// read-view detailSections. Pure presentational partition — preserves the exact
// visibleFormFields order + filtering; only adds the section a field belongs to.
// Each field's section is looked up from the meta field order (Section Break =
// boundary). Fields outside any meta section (or with a custom order that has no
// section breaks) fall into the first "Details" card, so nothing is dropped.
const visibleFormSections = computed(() => {
	const fields = visibleFormFields.value
	if (!fields.length) return []

	// Build fieldname → { key, label } section assignment from meta order.
	const sectionByField = {}
	let firstSection = null
	let cur = { key: "details", label: "Details" }
	let sectionCount = 0
	for (const mf of meta.value?.fields || []) {
		if (mf.fieldtype === "Section Break") {
			cur = {
				key: mf.fieldname || `sec-${sectionCount}`,
				label: mf.label || (sectionCount === 0 ? "Details" : "More"),
			}
			sectionCount++
			continue
		}
		if (!firstSection) firstSection = cur
		sectionByField[mf.fieldname] = cur
	}
	if (!firstSection) firstSection = { key: "details", label: "Details" }

	// Partition visibleFormFields into ordered sections, preserving field order.
	const out = []
	const byKey = {}
	for (const f of fields) {
		const sec = sectionByField[f.fieldname] || firstSection
		let bucket = byKey[sec.key]
		if (!bucket) {
			bucket = { key: sec.key, label: sec.label, fields: [] }
			byKey[sec.key] = bucket
			out.push(bucket)
		}
		bucket.fields.push(f)
	}
	return out
})

function isEditableMetaField(mf) {
	if (META_HIDDEN_FIELDTYPES.has(mf.fieldtype)) return false
	if (SYSTEM_FIELDS.has(mf.fieldname)) return false
	if (GROUPED_JSON_FIELDS.has(mf.fieldname)) return false
	if (mf.hidden) return false
	return true
}

// Missing-required check (used to mark inputs invalid + block save).
function isMissing(f) {
	if (!isReqd(f)) return false
	const v = form[f.fieldname]
	return v === null || v === undefined || v === ""
}

// ── form builders ──
function blankValueFor(mf) {
	// Honour meta default when present.
	if (mf.default !== undefined && mf.default !== null && mf.default !== "") {
		if (mf.fieldtype === "Check") return Number(mf.default) ? 1 : 0
		if (["Int", "Float", "Percent", "Currency"].includes(mf.fieldtype)) {
			const n = Number(mf.default)
			return Number.isNaN(n) ? null : n
		}
		// Resolve Frappe dynamic defaults so date/time inputs get a real value,
		// not the literal "Today"/"Now" string (the posting_time="Now" bug).
		if (mf.fieldtype === "Date" && mf.default === "Today") return fromDateObj(new Date(), false)
		if (mf.fieldtype === "Datetime" && mf.default === "Now") return fromDateObj(new Date(), true)
		if (mf.fieldtype === "Time" && mf.default === "Now") return nowTimeStr()
		return mf.default
	}
	if (mf.fieldtype === "Check") return 0
	if (["Int", "Float", "Percent", "Currency"].includes(mf.fieldtype)) return null
	return ""
}

function clearForm() {
	for (const k of Object.keys(form)) delete form[k]
}

function buildCreateForm() {
	clearForm()
	resetDirty()
	// Prompt-named create: start with an empty user-supplied name each time.
	newName.value = ""
	// Mirror Frappe's `doc.__islocal = 1` for new docs. Several yrp fields
	// gate on it (e.g. Item.name1's `read_only_depends_on:"eval:!doc.__islocal"`
	// means "read-only after first save"). Without this set, `!doc.__islocal`
	// in create mode would evaluate to true and treat those fields as
	// read-only, which the read-only-empty visibility rule then hides — and
	// the user couldn't enter the Item Name.
	form.__islocal = 1
	for (const mf of meta.value?.fields || []) {
		if (META_HIDDEN_FIELDTYPES.has(mf.fieldtype)) continue
		if (SYSTEM_FIELDS.has(mf.fieldname)) continue
		if (GROUPED_JSON_FIELDS.has(mf.fieldname)) continue
		if (mf.hidden) continue
		form[mf.fieldname] = blankValueFor(mf)
	}
	// Initialise editable child tables to empty arrays.
	for (const ct of editableChildTables.value) {
		form[ct.fieldname] = []
	}
	const duplicateApplied = applyPendingDuplicateDraft()
	// Pre-fill from route query (Create-from-parent buttons like WO → Create
	// DC / Create GRN). Async: trigger the autofill source once everything is
	// seeded so get_work_order_defaults / get_purchase_order_defaults run and
	// fill the header + items grid. nextTick lets the editor mount first.
	// Arm dirty-tracking only AFTER the query seed + autofill settle, so a
	// create-from-parent form doesn't open already "dirty".
	const seed = duplicateApplied ? Promise.resolve() : applyCreateFormQuery()
	seed.finally(armDirty)
}

function duplicateDraftStorageKey() {
	return `${DUPLICATE_DRAFT_STORAGE_PREFIX}${doctype.value}`
}

function stashDuplicateDraft(data) {
	try {
		sessionStorage.setItem(
			duplicateDraftStorageKey(),
			JSON.stringify({ doctype: doctype.value, data }),
		)
		return true
	} catch (_) {
		return false
	}
}

function applyPendingDuplicateDraft() {
	if (router.currentRoute.value.query?.duplicate !== "1") return false
	let payload = null
	try {
		const key = duplicateDraftStorageKey()
		const raw = sessionStorage.getItem(key)
		sessionStorage.removeItem(key)
		payload = raw ? JSON.parse(raw) : null
	} catch (_) {
		payload = null
	}
	if (!payload || payload.doctype !== doctype.value || !payload.data) return false
	for (const [key, value] of Object.entries(payload.data)) {
		if (!(key in form) || SYSTEM_FIELDS.has(key)) continue
		if (Array.isArray(value)) form[key] = value.map((row) => ({ ...row }))
		else if (value && typeof value === "object") form[key] = { ...value }
		else form[key] = value
	}
	form.__islocal = 1
	newName.value = ""
	return true
}

async function applyCreateFormQuery() {
	const qp = router.currentRoute.value.query || {}
	const keys = Object.keys(qp)
	if (!keys.length) return
	// Seed every query key that maps onto a form field. Coerce Check fields
	// to 0/1 (the query string carries them as "0"/"1").
	for (const [k, v] of Object.entries(qp)) {
		if (!(k in form)) continue
		const mf = metaFieldMap.value[k]
		if (mf?.fieldtype === "Check") form[k] = Number(v) ? 1 : 0
		else form[k] = v
	}
	// Fire the doctype's primary header+items autofill exactly once. The
	// fields are already set on `form`, so onFieldChanged → runDocAutofill
	// reads the right state. (For GRN, `against` is set BEFORE `against_id`
	// in the loop above because that's the JS object iteration order from
	// `onCreateGrnFromWo`; the against handler resets sources only on user
	// flip, not on the initial seed.)
	await nextTick()
	const dt = doctype.value
	if (dt === "Delivery Challan" && form.work_order) {
		await onFieldChanged("work_order")
	} else if (dt === "Goods Received Note" && form.against_id) {
		await onFieldChanged("against_id")
	} else if (dt === "Inspection Entry" && form.against_id) {
		await onFieldChanged("against_id")
	}
}

function buildEditForm() {
	clearForm()
	resetDirty()
	const src = doc.value || {}
	// Deep copy scalar + child-table values from the doc.
	for (const [k, v] of Object.entries(src)) {
		if (Array.isArray(v)) {
			form[k] = v.map((row) => ({ ...row }))
		} else if (v && typeof v === "object") {
			form[k] = { ...v }
		} else {
			form[k] = v
		}
	}
}

async function enterEdit() {
	if (!doc.value) return
	serverError.value = null
	missingField.value = null
	buildEditForm()
	mode.value = "edit"
	// R3a: for stock-pivot doctypes, hydrate each grid from the doc's grouped
	// onload JSON (frappe.client.get used for `doc` does NOT carry __onload, so
	// we fetch via getdoc — the same path the Desk uses). Without this the grid
	// would start empty and saving would wipe the existing rows.
	if (useStockPivot.value) await hydratePivotsForEdit()
	if (isLot.value) await hydrateLotForEdit()
	// Q6: arm dirty tracking after the form + grids settle (grid hydration is on
	// the child editor, not `form`, so it never marks dirty).
	armDirty()
}

// Fetch the grouped item_details/deliverable_details/receivable_details from the
// server onload and push them into the mounted grid editors. Best-effort: a load
// failure leaves the grids empty (the user can re-enter), but we keep the flat
// rows on the doc untouched until an actual save.
async function hydratePivotsForEdit() {
	try {
		const loaded = await getDocWithOnload(doctype.value, props.id)
		const onload = loaded?.__onload || {}
		await nextTick()
		for (const pv of stockPivots.value) {
			const grid = gridRefs[pv.childField]
			const grouped = onload[pv.groupedField]
			if (grid?.loadData && grouped != null) grid.loadData(grouped)
		}
	} catch (e) {
		toast.warn("Could not load existing items", "Re-enter the items before saving, or edit in Desk.")
	}
}

// ════════════════ EDITABLE CHILD TABLES ════════════════

// Editable child tables = meta Table fields, minus the hidden grouped-JSON
// twins. Columns come from the child DocType's meta (in the bundle) when
// available, else from the first existing row.
const editableChildTables = computed(() => {
	if (!isFormMode.value) return []
	const pivotFields = pivotChildFields.value
	const metaTables = (meta.value?.fields || []).filter(
		(f) =>
			f.fieldtype === "Table" &&
			!f.hidden &&
			!GROUPED_JSON_FIELDS.has(f.fieldname) &&
			!CHILD_TABLE_EXCLUDE.has(f.fieldname) &&
			// Honor depends_on on the CHILD-TABLE field itself (e.g. Process'
			// `process_details` depends_on="eval:doc.is_group == 1"): a table whose
			// condition is currently false must not render in edit/create. Evaluated
			// against the live `form`, so toggling the controlling field shows/hides
			// the grid reactively.
			(!f.depends_on || evalCondition(f.depends_on, form)) &&
			// Lot: bom_summary is calculated (Desk locks add/delete) — view-tab only.
			!(isLot.value && f.fieldname === "bom_summary") &&
			// R3a: stock-pivot doctypes edit these child tables through the grouped
			// pivot editor, not the flat grid — drop them here for those doctypes only.
			!pivotFields.has(f.fieldname),
	)
	const out = []
	for (const tf of metaTables) {
		const columns = childEditColumns(tf)
		out.push({
			fieldname: tf.fieldname,
			label: tf.label || humanize(tf.fieldname),
			childDoctype: tf.options || "",
			columns,
			// No columns ⇒ neither child meta nor existing rows gave us a reliable
			// shape. The editor disables Add Row and points the user to Desk.
			columnsAvailable: columns.length > 0,
		})
	}
	return out
})

// Work Order: the `comments` field, excluded from the regular form-field grid
// (work-order.js hideFormFields) so it renders as the LAST element of the WO
// form — below the deliverables/receivables pivots. Built
// via inputDescriptor so its label / help / read-only behaviour matches the rest
// of the form. Null for every other doctype / view mode.
const woCommentsField = computed(() => {
	if (!isFormMode.value || !isWorkOrder.value) return null
	const mf = metaFieldMap.value.comments
	if (!mf || mf.hidden) return null
	return inputDescriptor(mf)
})

// ════════════════ CHILD-TABLE COLUMNS (fixed width · resize · chooser) ════════
// Shared across the child-table render sites (the generic
// editableChildTables edit grids, the view-mode childTables tabs):
//   • FIXED table layout + per-column explicit width → no expand/shrink on
//     focus/edit. PrimeVue's columnResizeMode="fixed" + resizableColumns gives
//     the drag UX, but we DO NOT use stateStorage="local" for widths — PrimeVue
//     persists widths POSITIONALLY (one CSV restored by nth-child), which corrupts
//     widths across this table's differing view/edit column sets and after any
//     visibility toggle. Instead we apply each column's width via :style from a
//     FIELDNAME-keyed store and capture the user's drags via @column-resize-end.
//   • A compact "Columns" chooser (Button → Popover with checkboxes) toggles
//     which columns are visible; the selection persists per user too.
// The functions below are thin wrappers over the useChildTableColumns composable
// so the template stays declarative and the three sites share ONE source of truth.

// Width (CSS length) to apply to a column: the user's field-keyed resize override
// for (this doctype, table, column-fieldname) if present, else the per-fieldtype
// default. Immune to mode differences and visibility-toggle column-count changes.
function childColWidth(tableFieldname, col) {
	return resolvedColumnWidth(doctype.value, tableFieldname, col)
}
const childActionColWidth = `${ACTION_COL_WIDTH}px`

function childColWidthUnits(tableFieldname, col) {
	return resolvedColumnWidthUnits(doctype.value, tableFieldname, col)
}

function childColumnsForWidthTotal(tableFieldname, columns) {
	return (columns || []).filter(
		(c) => isColumnVisible(tableFieldname, columns, c.fieldname) && !childColumnHiddenBy(tableFieldname, c.fieldname),
	)
}

function childWidthUnitsTotal(tableFieldname, columns) {
	return childColumnsForWidthTotal(tableFieldname, columns).reduce(
		(total, col) => total + childColWidthUnits(tableFieldname, col),
		0,
	)
}

function childWidthUnitMax(tableFieldname, columns, col) {
	const visible = isColumnVisible(tableFieldname, columns, col.fieldname)
	const current = visible ? childColWidthUnits(tableFieldname, col) : 0
	const others = Math.max(0, childWidthUnitsTotal(tableFieldname, columns) - current)
	return Math.max(1, MAX_TABLE_WIDTH_UNITS - others)
}

function setChildColWidthUnits(tableFieldname, columns, col, value) {
	const requested = Number(value)
	if (!Number.isFinite(requested)) return
	const units = Math.max(1, Math.round(requested))
	const max = childWidthUnitMax(tableFieldname, columns, col)
	if (units > max) {
		toast.warn("Column width limit", `Visible columns can use ${MAX_TABLE_WIDTH_UNITS} total units.`)
	}
	persistColumnWidthUnits(doctype.value, tableFieldname, col.fieldname, Math.min(units, max))
}

// Capture a user resize. PrimeVue's column-resize-end payload is { element, delta }
// where `element` is the resized header <th> and `delta` is the drag distance in px
// (no column object is provided). With columnResizeMode="fixed" PrimeVue does NOT
// itself rewrite cell widths — our :style binding owns them — so the new width is
// the <th>'s current width + delta. We map the <th> to a fieldname by its index in
// the header row: these grids render shownColumns (in order) followed by ONE action
// column, with no leading selection/expander cell, so header index N → shownColumns
// (..., columns)[N]. The trailing action <th> (index === length) is ignored.
function onChildColumnResizeEnd(tableFieldname, columns, e, forceFieldnames) {
	const el = e?.element
	if (!el || !el.parentElement) return
	const idx = Array.prototype.indexOf.call(el.parentElement.children, el)
	if (idx < 0) return
	// Mirror the rendered column set (incl. the edit grids' forced required
	// columns) so header index N maps to the same column the user resized.
	const shown = shownColumns(tableFieldname, columns, forceFieldnames)
	const col = shown[idx]
	if (!col?.fieldname) return // out of range (e.g. the trailing action column)
	const px = el.offsetWidth + (Number(e.delta) || 0)
	if (px > 0) persistColumnWidth(doctype.value, tableFieldname, col.fieldname, px)
}

// The reactive visible-column Set for a table (seeded from the persisted
// selection, else the default-visible set). Keyed by (user, doctype, fieldname).
function visibleSetFor(tableFieldname, columns) {
	return useVisibleColumns(doctype.value, tableFieldname, columns)
}
// Live parent state a child-column rule evaluates against: the edit `form`
// (edit/create) or the loaded `doc` (view). Reading these reactive sources makes
// parent-aware column hides re-evaluate as the controlling field toggles.
function parentStateForRules() {
	return isFormMode.value ? form : doc.value || {}
}

// Per-(doctype) child-column hide rules keyed by parent doctype. None of the
// essdee /web doctypes declare one today; add entries here when a child column
// must hide based on parent state (see the reference app's Process Cost precedent).
const CHILD_COLUMN_RULE_CONFIGS = {}

// True ⇒ this child-table column must be HIDDEN for the current parent state.
// Scoped: only fires for a (doctype, childTable, column) that has a declared rule;
// everything else falls through (never hidden). Reactive via parentStateForRules.
function childColumnHiddenBy(tableFieldname, columnFieldname) {
	const rule = CHILD_COLUMN_RULE_CONFIGS[doctype.value]?.[tableFieldname]?.[columnFieldname]
	if (typeof rule !== "function") return false
	try {
		return !!rule(parentStateForRules())
	} catch (_) {
		return false // a misbehaving rule fails open (column shown)
	}
}

// Columns actually rendered = the table's columns filtered by its visible Set.
// EDIT grids pass `forceFieldnames` (the table's REQUIRED fields) so a required
// cell is always rendered — even when it isn't in_list_view and the user hasn't
// opted it in — keeping it fillable so save isn't blocked with no way to fill it.
// The forced columns render in their natural column order (not appended). View
// grids omit the arg, so this is a no-op there.
//
// A declared parent-aware hide rule (childColumnHiddenBy) always wins — even over
// `forced` — so e.g. Process Cost's `attribute_value` stays hidden while
// `depends_on_attribute` is off, regardless of in_list_view / required status.
function shownColumns(tableFieldname, columns, forceFieldnames) {
	const vis = visibleSetFor(tableFieldname, columns)
	const forced = forceFieldnames && forceFieldnames.length ? new Set(forceFieldnames) : null
	return columns.filter(
		(c) =>
			!childColumnHiddenBy(tableFieldname, c.fieldname) &&
			(vis.has(c.fieldname) || (forced && forced.has(c.fieldname))),
	)
}
// Chooser toggle: flip a column's visibility, keeping at least one column shown,
// then persist the selection for this user.
function toggleColumn(tableFieldname, columns, fieldname) {
	const vis = visibleSetFor(tableFieldname, columns)
	if (vis.has(fieldname)) {
		if (vis.size <= 1) return // never hide the last column
		vis.delete(fieldname)
	} else {
		const col = columns.find((c) => c.fieldname === fieldname)
		const nextTotal = childWidthUnitsTotal(tableFieldname, columns) + (col ? childColWidthUnits(tableFieldname, col) : 1)
		if (nextTotal > MAX_TABLE_WIDTH_UNITS) {
			toast.warn("Column width limit", `Visible columns can use ${MAX_TABLE_WIDTH_UNITS} total units.`)
			return
		}
		vis.add(fieldname)
	}
	persistVisibleColumns(doctype.value, tableFieldname, vis)
}
function isColumnVisible(tableFieldname, columns, fieldname) {
	return visibleSetFor(tableFieldname, columns).has(fieldname)
}

// Per-table refs to the "Columns" chooser Popover instances, keyed by the child
// table fieldname (a table can appear once per render site, so the fieldname is
// a unique-enough key within a single mode).
const colChooserRefs = {}
function setColChooserRef(fieldname, el) {
	if (el) colChooserRefs[fieldname] = el
	else delete colChooserRefs[fieldname]
}
function toggleColChooser(fieldname, event) {
	colChooserRefs[fieldname]?.toggle(event)
}

// ── Shared child-column derivation (META-DRIVEN — never row-derived) ──────────
// ONE source of truth for the column set of EVERY child table, used by BOTH the
// view-mode tabs (childColumns) and the edit grids (childEditColumns). Columns
// come from the child DocType's META (via the cached getdoctype bundle), so they
// are present even when the child table has ZERO rows — an empty table renders
// proper headers instead of a blank column, and the column set never depends on
// row data.
//
// The returned list is the CHOOSER UNIVERSE: every display-worthy field (all
// non-hidden, non-layout fields), so the user can opt any extra column in. Each
// column carries the meta flags `in_list_view` / `hidden` / `read_only` / `reqd`
// so useChildTableColumns' defaultVisibleFieldnames can compute the DEFAULT
// visible set as: in_list_view fields (field order), else the first 5
// non-hidden/non-read-only fields. (A user's saved selection still wins.)
//
// Each column also carries the edit-cell hints (input/linkTarget/fractions/
// readonly) so the same objects drive the edit grid without a second pass.
const CHILD_COL_LAYOUT_TYPES = new Set([
	"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Button",
	"Fold", "Image", "Geolocation", "Signature", "Table", "Table MultiSelect",
	// Large/structured text fieldtypes: never editable in the flat v1 grid and
	// pointless as read-only grid columns (they'd surface a wall of code/markup in
	// a narrow cell). Exclude them from the child-column universe entirely.
	"Code", "JSON", "Text Editor",
])
// Cell input kind for the edit grid: only scalar / link cells are editable in
// the flat v1 grid; everything else renders as a (read-only) text cell.
const CHILD_EDITABLE_FIELDTYPES = new Set([
	"Data", "Small Text", "Int", "Float", "Percent", "Currency", "Link", "Select", "Check",
])

function childColumnsFromMeta(childDt) {
	const cmeta = childDt ? childMetaCache.value[childDt] : null
	if (!cmeta?.fields?.length) return []
	const readonlySet = getReadOnlyChildFields(doctype.value, childDt)
	const cols = []
	for (const mf of cmeta.fields) {
		// Display-worthy universe: skip layout/system fieldtypes, system/internal
		// fieldnames, and meta-hidden fields. Everything else is selectable in the
		// chooser (and a subset is visible by default — see defaultVisibleFieldnames).
		if (CHILD_COL_LAYOUT_TYPES.has(mf.fieldtype)) continue
		if (CHILD_HIDDEN.has(mf.fieldname)) continue
		if (mf.hidden) continue
		const d = inputDescriptor(mf)
		const editable = CHILD_EDITABLE_FIELDTYPES.has(mf.fieldtype)
		cols.push({
			fieldname: mf.fieldname,
			label: mf.label || humanize(mf.fieldname),
			// edit-cell hints
			input: editable ? childInputKind(d.input) : "text",
			reqd: !!mf.reqd,
			type: mfTypeToDisplay(mf.fieldtype),
			fieldtype: mf.fieldtype, // raw meta type → default column width
			isLink: mf.fieldtype === "Link",
			linkTarget: mf.options || "",
			minFraction: d.minFraction,
			maxFraction: d.maxFraction,
			// A field the parent pins read-only, OR a non-editable fieldtype:
			// render a static cell (no input) so the user can't edit it.
			readonly: readonlySet.has(mf.fieldname) || !editable,
			// meta flags consumed by defaultVisibleFieldnames (the DEFAULT visible
			// set) — NOT a render filter; every column here is chooser-selectable.
			in_list_view: !!mf.in_list_view,
			hidden: !!mf.hidden,
			read_only: !!mf.read_only,
		})
	}
	return cols
}

// EDIT-grid columns for a child table: the shared meta-derived universe. Present
// even with zero rows (create / empty edit). No meta ⇒ empty list ⇒ the editor
// disables "Add Row" and points the user to Desk (columnsAvailable=false), so we
// never persist wrong/incomplete data from guessed columns.
function childEditColumns(tableField) {
	return childColumnsFromMeta(tableField.options)
}

// Child cells only support scalar / link inputs in the flat v1 grid.
function childInputKind(parentInput) {
	if (parentInput === "number") return "number"
	if (parentInput === "link") return "link"
	return "text"
}

// Required child fieldnames (always force-shown in EDIT grids — see shownColumns'
// `forceFieldnames`) so a required cell stays fillable even when it isn't
// in_list_view and the user hasn't opted it in. View grids don't need this.
function reqdFieldnames(columns) {
	return (columns || []).filter((c) => c.reqd).map((c) => c.fieldname)
}

function addChildRow(ct) {
	if (!Array.isArray(form[ct.fieldname])) form[ct.fieldname] = []
	const row = {}
	for (const col of ct.columns) {
		row[col.fieldname] = col.input === "number" ? null : ""
	}
	form[ct.fieldname].push(row)
}

function removeChildRow(ct, index) {
	if (Array.isArray(form[ct.fieldname])) form[ct.fieldname].splice(index, 1)
}

function onCellEditComplete(ct, e) {
	// PrimeVue cell edit: commit the new value onto the row.
	const { data, newValue, field } = e
	if (data) data[field] = newValue
}

function childCellDisplay(val, col) {
	if (val === null || val === undefined || val === "") return "—"
	if (col.input === "number") return formatNumber(val)
	return String(val)
}

// ── Link autocomplete (parent fields) ──
// ════════════════ FIELD-CHANGE AUTO-FILL (mirror the Desk client scripts) ════
// (a) fetch_from — when a source field changes, copy source_doc.<field> into the
//     target (respecting fetch_if_empty); chained fetches cascade.
// (b) per-doctype header+items auto-fill via the same server methods the Desk
//     forms call (e.g. DC work_order → get_work_order_defaults → load deliverables).

// Targets whose fetch_from references `srcField`.
function fetchTargetsFor(srcField) {
	const out = []
	for (const mf of meta.value?.fields || []) {
		if (!mf.fetch_from) continue
		const dot = String(mf.fetch_from).indexOf(".")
		if (dot < 1 || mf.fetch_from.slice(0, dot) !== srcField) continue
		out.push({
			target: mf.fieldname,
			srcDocField: mf.fetch_from.slice(dot + 1),
			fetchIfEmpty: !!mf.fetch_if_empty,
		})
	}
	return out
}

// The doctype a (Dynamic) Link field points at.
function linkDoctypeOf(fieldname) {
	const mf = metaFieldMap.value[fieldname]
	if (!mf) return ""
	return mf.fieldtype === "Dynamic Link" ? (form[mf.options] || "") : (mf.options || "")
}

// Replicate Frappe's fetch_from for one source field, cascading to chained fetches.
async function applyFetchFrom(srcField) {
	const targets = fetchTargetsFor(srcField)
	if (!targets.length) return
	const srcValue = form[srcField]
	const srcDoctype = linkDoctypeOf(srcField)
	for (const t of targets) {
		if (!srcValue || !srcDoctype) {
			if (!t.fetchIfEmpty) form[t.target] = "" // source cleared → clear fetched
			continue
		}
		if (t.fetchIfEmpty && form[t.target]) continue // don't overwrite existing
		try {
			const r = await callMethod("frappe.client.get_value", {
				doctype: srcDoctype,
				filters: srcValue,
				fieldname: t.srcDocField,
			})
			form[t.target] = (r && r[t.srcDocField]) || ""
		} catch (_) {
			/* leave target as-is on lookup failure */
		}
		await applyFetchFrom(t.target) // cascade (warehouse → supplier → terms…)
	}
}

// Per-doctype header+items auto-fill (the heavy "pick a link → fill header + load
// the item grid" handlers). The server methods return { …header fields, items,
// item_details(grouped) }.
// Zero every cell qty in a grouped item_details payload (keeps pending/max so the
// clamp + display still work). Used so a GRN starts blank for data entry.
function zeroGroupedQtys(itemDetails) {
	for (const g of itemDetails || []) {
		for (const it of g.items || []) {
			for (const cell of Object.values(it.values || {})) {
				if (cell && typeof cell === "object") cell.qty = 0
			}
		}
	}
}

async function runDocAutofill(fieldname) {
	const dt = doctype.value
	// Lot mirrors lot.js's field handlers: production_order fills item;
	// production_detail fills the UOM/stage header fields (get_isfinal_uom,
	// note the response key is dependent_attr_mapping) then reloads the
	// order-items editor via get_item_details; clearing resets everything.
	if (dt === "Lot" && fieldname === "production_order") {
		if (form.production_order) {
			try {
				const r = await callMethod("frappe.client.get_value", {
					doctype: "Production Order",
					filters: form.production_order,
					fieldname: "item",
				})
				if (r?.item) form.item = r.item
			} catch (_) { /* keep whatever the user had */ }
		} else {
			form.production_detail = ""
			form.item = ""
			lotItemsGrid.value?.loadData?.([])
		}
		return
	}
	if (dt === "Lot" && fieldname === "production_detail") {
		const LOT_IPD_FIELDS = [
			"uom", "pack_in_stage", "packing_uom", "pack_out_stage",
			"dependent_attribute_mapping", "tech_pack_version", "pattern_version",
			"packing_combo",
		]
		if (!form.production_detail) {
			for (const f of LOT_IPD_FIELDS) form[f] = ""
			lotItemsGrid.value?.loadData?.([])
			return
		}
		try {
			const r = await callMethod(
				"essdee_yrp.essdee_yrp.doctype.lot.lot.get_isfinal_uom",
				{ item_production_detail: form.production_detail, get_pack_stage: 1 },
			)
			// When the IPD has no dependent-attribute mapping the server returns
			// ONLY {uom} — clear the other header fields (lot.js else-branch).
			for (const f of LOT_IPD_FIELDS) form[f] = ""
			if (r) {
				form.uom = r.uom || ""
				form.pack_in_stage = r.pack_in_stage || ""
				form.packing_uom = r.packing_uom || ""
				form.pack_out_stage = r.pack_out_stage || ""
				form.dependent_attribute_mapping = r.dependent_attr_mapping || ""
				form.tech_pack_version = r.tech_pack_version || ""
				form.pattern_version = r.pattern_version || ""
				form.packing_combo = r.packing_combo ?? ""
			}
		} catch (e) {
			toast.error("Couldn't read the IPD", e.message)
			return
		}
		await reloadLotItemsEditor()
		return
	}
	if (dt === "Lot" && fieldname === "item" && !form.item) {
		lotItemsGrid.value?.loadData?.([])
		return
	}
	// Item Production Detail mirrors production_api's item-change handler
	// (apps/production_api/.../item_production_detail.js line 665) — picking
	// the parent Item auto-fills primary/dependent attribute + item_attributes
	// child rows. Maps Item fields → IPD fields (different names), so it
	// short-circuits the generic copy-by-key loop below.
	if (dt === "Item Production Detail" && fieldname === "item") {
		if (!form.item) {
			form.primary_item_attribute = ""
			form.dependent_attribute = ""
			form.dependent_attribute_mapping = ""
			form.item_attributes = []
			return
		}
		try {
			const r = await callMethod("yrp.yrp.doctype.item.item.get_complete_item_details", {
				item_name: form.item,
			})
			if (r && typeof r === "object") {
				form.primary_item_attribute = r.primary_attribute || ""
				form.dependent_attribute = r.dependent_attribute || ""
				form.dependent_attribute_mapping = r.dependent_attribute_mapping || ""
				form.item_attributes = Array.isArray(r.attributes) ? r.attributes : []
			}
		} catch (e) {
			toast.error("Auto-fill failed", e.message)
		}
		return
	}
	// Inspection Entry mirrors the Desk against_id handler: fetch the source
	// (GRN / Stock Entry) items as the source-bin grouped payload and load the
	// split editor. get_initial_payload returns the array directly (no header
	// dict), so it short-circuits the header-copy path below.
	if (dt === "Inspection Entry" && (fieldname === "against_id" || fieldname === "against")) {
		if (!form.against || !form.against_id) return
		try {
			const payload = await callMethod(
				"yrp.yrp.doctype.inspection_entry.inspection_entry.get_initial_payload",
				{ against: form.against, against_id: form.against_id },
			)
			await nextTick()
			if (gridRefs.items?.loadData) gridRefs.items.loadData(payload || [])
		} catch (e) {
			toast.error("Auto-fill failed", e.message)
		}
		return
	}
	let method = ""
	let args = null
	if (dt === "Delivery Challan" && fieldname === "work_order") {
		if (!form.work_order) return
		method = "yrp.yrp.doctype.delivery_challan.delivery_challan.get_work_order_defaults"
		args = { work_order: form.work_order, posting_date: form.posting_date, posting_time: form.posting_time }
	} else if (dt === "Goods Received Note" && (fieldname === "against_id" || fieldname === "delivery_challan")) {
		if (!form.against_id) return
		if (form.against === "Work Order") {
			method = "yrp.yrp.doctype.goods_received_note.goods_received_note.get_work_order_defaults"
			args = { work_order: form.against_id, delivery_challan: form.delivery_challan || "" }
		} else if (form.against === "Purchase Order") {
			method = "yrp.yrp.doctype.goods_received_note.goods_received_note.get_purchase_order_defaults"
			args = { purchase_order: form.against_id }
		} else return
	} else {
		return
	}
	// Per-doctype fields to drop from the autofill response so the user has
	// to pick them manually (preference 2026-05-29 — DC's from_warehouse is
	// the floor's pick, not WO-derived). The server-side `set_missing_values`
	// fallback still rescues an empty value on save.
	const AUTOFILL_SKIP = {
		"Delivery Challan": new Set(["from_warehouse"]),
	}
	try {
		const r = await callMethod(method, args)
		if (!r || typeof r !== "object") return
		const skip = AUTOFILL_SKIP[dt] || new Set()
		for (const [k, v] of Object.entries(r)) {
			if (k === "items" || k === "item_details") continue
			if (skip.has(k)) continue
			if (k in form) form[k] = v // apply returned header fields
		}
		// GRN: start every received type at 0 so the user types the actual received
		// qty per row (total still clamped to pending) — no "all accepted" pre-fill.
		if (dt === "Goods Received Note") zeroGroupedQtys(r.item_details)
		await nextTick()
		for (const pv of stockPivots.value) {
			const grid = gridRefs[pv.childField]
			if (grid?.loadData && r.item_details != null) grid.loadData(r.item_details)
		}
	} catch (e) {
		toast.error("Auto-fill failed", e.message)
	}
}

// GRN: flipping `against` (Work Order ↔ Purchase Order) resets the source-derived
// header fields + the item grid (mirrors goods_received_note.js `against` handler).
function resetGrnSource() {
	for (const k of ["against_id", "delivery_challan", "process_name", "item", "production_detail", "supplier", "delivery_location", "from_warehouse", "to_warehouse", "is_rework"]) {
		if (k in form) form[k] = k === "is_rework" ? 0 : ""
	}
	for (const pv of stockPivots.value) gridRefs[pv.childField]?.loadData?.([])
}

// Per-field custom Link search (e.g. Work Order's address fields filter by the
// selected party). Returns null when no override applies → LinkField falls
// back to the default name-like search. Reactive on `form` — when the
// controlling field (supplier / delivery_location) changes the factory re-runs
// and the autocomplete picks up the new filter on next open.
function linkSearchHandlerFor(f) {
	return getLinkSearchHandler(doctype.value, f.fieldname, form)
}

// Wired on editable link/select inputs: cascade fetch_from + clear dependent
// address fields + run doctype auto-fill.
async function onFieldChanged(fieldname) {
	await applyFetchFrom(fieldname)
	// Work Order: changing the party invalidates any address picked under the
	// previous party (the address autocomplete is filtered by party — keeping a
	// stale value would let the user submit an address that doesn't belong).
	if (doctype.value === "Work Order") {
		if (fieldname === "supplier") form.supplier_address = ""
		if (fieldname === "delivery_location") form.delivery_address = ""
	}
	if (doctype.value === "Goods Received Note" && fieldname === "against") {
		resetGrnSource()
		return
	}
	if (doctype.value === "Inspection Entry" && fieldname === "against") {
		form.against_id = ""
		for (const pv of stockPivots.value) gridRefs[pv.childField]?.loadData?.([])
		return
	}
	await runDocAutofill(fieldname)
}

async function onLinkComplete(field, e) {
	// For a Dynamic Link the target doctype is whatever the controlling field
	// currently holds (e.g. against_id → form.against === "Work Order").
	const target = field.isDynamic ? (form[field.dynamicField] || "") : field.linkTarget
	if (!target) {
		linkSuggestions[field.fieldname] = []
		return
	}
	try {
		const rows = await searchLink(target, e.query || "")
		linkSuggestions[field.fieldname] = rows.map((r) => r.name)
	} catch (_) {
		linkSuggestions[field.fieldname] = []
	}
}

// ── Link autocomplete (child cells) ──
async function onChildLinkComplete(col, e, row = null) {
	const target = col.linkTarget
	if (!target) {
		childLinkSuggestions.value = []
		return
	}
	try {
		// Lot fabric rows mirror the Desk set_query rules: cloth_item offers only
		// cloth-flagged Items; production_detail offers only the row's cloth
		// item's IPDs (no suggestions until a cloth item is picked).
		let filters
		if (isLot.value && col.fieldname === "cloth_item" && target === "Item") {
			filters = { is_cloth_item: 1 }
		} else if (isLot.value && col.fieldname === "production_detail" && target === "Item Production Detail") {
			if (!row?.cloth_item) {
				childLinkSuggestions.value = []
				return
			}
			filters = { item: row.cloth_item }
		}
		const rows = await searchLink(target, e.query || "", filters)
		childLinkSuggestions.value = rows.map((r) => r.name)
	} catch (_) {
		childLinkSuggestions.value = []
	}
}

// ════════════════ SAVE / SUBMIT / CANCEL / DELETE / AMEND ════════════════

// Build the payload sent to the server.
//
// FLAT PATH (every non-stock-pivot doctype — unchanged): drop the hidden
// grouped-JSON fields so the flat child rows persist (before_validate skips
// ungroup when the grouped field is empty).
//
// STOCK-PIVOT PATH (R3a, stock vouchers only): emit each section's grouped JSON
// into its grouped field AND send an EMPTY flat child array, so the voucher's
// before_validate runs ungroup_items_from_ui → resolves/creates variants and
// rebuilds the flat child table server-side. This is the OPPOSITE of the flat
// path. Only the fields in stockPivots are affected; all others stay flat.
function buildPayload() {
	const payload = {}
	for (const [k, v] of Object.entries(form)) {
		if (GROUPED_JSON_FIELDS.has(k)) continue
		if (k === "__islocal") continue
		payload[k] = v
	}
	// Ensure the grouped-JSON twins are NOT sent by default (extra safety).
	for (const g of GROUPED_JSON_FIELDS) delete payload[g]

	// Stock-pivot doctypes only: write grouped JSON + blank the flat child.
	for (const pv of stockPivots.value) {
		const grid = gridRefs[pv.childField]
		const grouped = grid?.getItems ? grid.getItems() : []
		const isEmpty = grouped.length === 0
		// EDIT mode safety: if the grid is empty (e.g. the grouped onload hydration
		// failed), do NOT send empty grouped + empty flat — that would wipe the
		// doc's existing rows. Leave both fields out so the server keeps them.
		// CREATE mode: always send (an empty doc legitimately has no items).
		if (mode.value === "edit" && isEmpty) continue
		payload[pv.groupedField] = JSON.stringify(grouped)
		// Empty flat child → before_validate clears + rebuilds it from grouped.
		payload[pv.childField] = []
	}
	// Lot: add the two editor payloads ONLY when the matching editor hydrated
	// (omit the key entirely otherwise — a "[]" string would wipe the items and
	// their Production Ordered Detail links server-side). The `items` /
	// `lot_order_details` child rows stay in the payload verbatim:
	// save_order_item_details preserves cut/stitch/pack by merging against them.
	// A transferred Lot's order tables are frozen (Desk parity) — never send the
	// rebuild JSON so the controller keeps items/lot_order_details untouched.
	if (isLot.value && !isLotTransferred.value) {
		if (lotItemsHydrated.value && lotItemsGrid.value?.getItems) {
			payload.item_details = JSON.stringify(lotItemsGrid.value.getItems())
		}
		if (lotOrderHydrated.value && lotOrderGrid.value?.getItems) {
			const blocks = lotOrderGrid.value.getItems()
			if (blocks.length) payload.order_item_details = JSON.stringify(blocks)
		}
	}
	// Prompt-named create: include the user-supplied name in the insert body.
	// createDoc POSTs JSON.stringify(payload) to /api/resource/<doctype>, and
	// Frappe's REST insert honours a provided `name` for autoname="prompt" /
	// naming_rule="Set by user". Only added in create mode for prompt naming — a
	// series/field/hash-named doctype's payload is left byte-identical, and edit
	// mode (where the name already exists) is untouched.
	if (mode.value === "create" && isPromptNaming.value && newName.value.trim()) {
		payload.name = newName.value.trim()
	}
	// Stale-write guard: send the `modified` the user LOADED so Frappe's
	// check_if_latest() rejects a concurrent edit (TimestampMismatchError, HTTP
	// 417) instead of silently overwriting it. Edit only — never on create.
	// INVARIANT: the realtime layer must NEVER advance doc.value.modified (it only
	// flags staleNotice); doc.value.modified changes only on Refresh or a
	// successful save. If that invariant breaks, this guard sends the fresh
	// timestamp and the clobber returns.
	if (mode.value === "edit" && doc.value?.modified) {
		payload.modified = doc.value.modified
	}
	return payload
}

// Returns { label, fieldname } of the first missing required field (fieldname is
// null for a child-table cell — there's no scroll target on the parent form), or
// null when everything required is filled. The fieldname drives Q5's scroll+focus.
function firstMissingRequired() {
	// 1) Parent fields (only those currently visible — a depends_on-hidden field
	// is not required).
	for (const f of visibleFormFields.value) {
		if (isMissing(f)) return { label: f.label, fieldname: f.fieldname }
	}
	// 2) Editable child-table rows: any required cell left empty blocks the save
	// here (inline) instead of letting the server reject the round-trip. The
	// returned label names the child table + field + row so the toast is actionable.
	for (const ct of editableChildTables.value) {
		const reqdCols = ct.columns.filter((c) => c.reqd)
		if (!reqdCols.length) continue
		const rows = Array.isArray(form[ct.fieldname]) ? form[ct.fieldname] : []
		for (let i = 0; i < rows.length; i++) {
			for (const col of reqdCols) {
				const v = rows[i][col.fieldname]
				if (v === null || v === undefined || v === "") {
					return { label: `${ct.label} → ${col.label} (row ${i + 1})`, fieldname: null }
				}
			}
		}
	}
	return null
}

// Q5: bring the offending field into view and focus its control so the user
// isn't told "X is required" about a field 3 screens down they can't see.
async function focusMissingField(fieldname) {
	if (!fieldname) return
	await nextTick()
	const wrap = document.getElementById(`field-${fieldname}`)
	if (!wrap) return
	wrap.scrollIntoView({ behavior: "smooth", block: "center" })
	const input = wrap.querySelector("input, textarea, select, [tabindex]")
	if (input && typeof input.focus === "function") input.focus()
}

// Q15: a failed high-stakes action (submit/cancel/delete/amend) both toasts and
// pins the full server message in the closable banner so the user can read the
// (often multi-line) validation/stock error while deciding what to do.
function showActionError(title, e) {
	// Stale-write conflict on a high-stakes action (submit/cancel/delete/amend):
	// surface the friendly Refresh banner rather than the raw server text.
	if (isConflictError(e)) {
		serverError.value = {
			title: "Document changed by someone else",
			lines: ["This document was changed after you opened it. Refresh to load the latest version, then try again."],
			refresh: true,
		}
		toast.warn("Document changed", "Refresh to get the latest version.")
		return
	}
	serverError.value = { title, lines: errorLines(e) }
	toast.error(title, e?.message)
}

// Conflict recovery (v1): discard any local edits and reload the latest doc.
// Triggered by the Refresh button on the conflict banner. reloadView() clears
// serverError and re-fetches doc/linked/activity; in form mode we first drop
// the edit copy and return to view (a field-level merge is out of scope for v1).
async function refreshFromConflict() {
	isDirty.value = false
	staleNotice.value = false
	if (isFormMode.value) {
		clearForm()
		mode.value = "view"
	}
	await reloadView()
}

async function onSave() {
	// Prompt-named create guard: block here with a clear toast rather than letting
	// the server return "Please set Document Name" after the round-trip. Only fires
	// for prompt-named doctypes in create mode; non-prompt doctypes skip this.
	if (mode.value === "create" && isPromptNaming.value && !newName.value.trim()) {
		missingField.value = { label: `${registry.value?.label || doctype.value} Name`, fieldname: "__newname" }
		toast.warn("Name is required", "Set a unique name for this document before saving.")
		focusMissingField("__newname")
		return
	}
	const missing = firstMissingRequired()
	if (missing) {
		missingField.value = missing
		toast.warn("Missing required field", `“${missing.label}” is required.`)
		focusMissingField(missing.fieldname)
		return
	}
	missingField.value = null
	serverError.value = null
	markLocalWrite()
	const payload = buildPayload()
	try {
		if (mode.value === "create") {
			const result = await docState.save(payload)
			const newName = result?.name
			// Clear dirty BEFORE navigating so the route-leave guard stays silent.
			isDirty.value = false
			toast.success("Created", newName ? `${doctype.value} ${newName} created` : "Document created")
			if (newName) {
				router.push(`/${props.docRoute}/${encodeURIComponent(newName)}`)
			} else {
				mode.value = "view"
			}
		} else {
			await docState.save(payload, props.id)
			isDirty.value = false
			toast.success("Saved", `${props.id} updated`)
			mode.value = "view"
			await docState.load(props.id)
			// Re-hydrate the read-only stock-pivot grid; the Details fields and
			// child tables refresh reactively from doc.value, but viewGrouped
			// is fed from a separate getDocWithOnload call (only invoked in
			// loadAll on mount/route-change). Without this re-hydration a WO /
			// DC / GRN's Deliverables/Receivables tab kept showing the pre-save
			// rows until the user reloaded the page (reported 2026-05-29 for
			// WO-00010-1).
			if (stockPivots.value.length) hydratePivotsForView()
			docState.loadLinked(props.id)
			docState.loadActivity(props.id)
			loadConnections()
		}
	} catch (e) {
		// Q15: keep the full (often multi-line) server message visible in a
		// closable banner — the toast alone vanishes before the user can read it.
		// Stale-write conflict: another user changed this doc after we loaded it.
		// Show a friendly banner + Refresh action instead of the raw server text.
		// Detected via exc_type (status-agnostic), never a numeric HTTP code.
		if (isConflictError(e)) {
			serverError.value = {
				title: "Document changed by someone else",
				lines: ["This document was changed after you opened it. Refresh to load the latest version, then re-apply your changes."],
				refresh: true,
			}
			toast.warn("Document changed", "Refresh to get the latest version.")
			return
		}
		serverError.value = {
			title: mode.value === "create" ? "Could not create" : "Could not save",
			lines: errorLines(e),
		}
		toast.error("Save failed", e.message)
	}
}

// Q6: actually drop the form. Clears the dirty flag FIRST so the create-mode
// router.push doesn't re-trigger the route-leave confirm (double prompt).
function doDiscard() {
	isDirty.value = false
	serverError.value = null
	missingField.value = null
	if (mode.value === "create") {
		router.push(`/${props.docRoute}`)
		return
	}
	// edit → drop the form copy, back to view.
	clearForm()
	mode.value = "view"
}
function onDiscard() {
	if (isDirty.value) {
		confirm.require({
			header: "Discard changes?",
			message: "Discard your unsaved changes on this form?",
			icon: "pi pi-exclamation-triangle",
			acceptLabel: "Discard",
			acceptClass: "p-button-danger",
			rejectLabel: "Keep editing",
			accept: doDiscard,
		})
		return
	}
	doDiscard()
}

function onSubmit() {
	confirm.require({
		header: "Submit document",
		message: `Submit ${props.id}? This runs the server validations and posts stock movements.`,
		acceptLabel: "Submit",
		acceptClass: "p-button-primary",
		accept: async () => {
			acting.value = "submit"
			try {
				markLocalWrite()
				await docState.submit(props.id)
				toast.success("Submitted", `${props.id} submitted`, 6000)
				await reloadView()
			} catch (e) {
				showActionError("Submit failed", e)
			} finally {
				acting.value = null
			}
		},
	})
}

function onCancel() {
	confirm.require({
		header: "Cancel document",
		message: `Cancel ${props.id}? This reverses its stock movements.`,
		acceptLabel: "Cancel Document",
		acceptClass: "p-button-danger",
		rejectLabel: "Keep",
		accept: async () => {
			acting.value = "cancel"
			try {
				markLocalWrite()
				await docState.cancel(props.id)
				toast.success("Cancelled", `${props.id} cancelled`, 6000)
				await reloadView()
			} catch (e) {
				showActionError("Cancel failed", e)
			} finally {
				acting.value = null
			}
		},
	})
}

function onDelete() {
	confirm.require({
		header: "Delete document",
		message: `Permanently delete ${props.id}? This cannot be undone.`,
		acceptLabel: "Delete",
		acceptClass: "p-button-danger",
		accept: async () => {
			acting.value = "delete"
			try {
				await docState.remove(props.id)
				toast.success("Deleted", `${props.id} deleted`, 6000)
				router.push(`/${props.docRoute}`)
			} catch (e) {
				showActionError("Delete failed", e)
				acting.value = null
			}
		},
	})
}

// "Create DC" / "Create GRN" buttons on a submitted, Open Work Order —
// mirror production_api/work_order.js (Make DC / Make GRN). We pass the
// pre-fill values as route query params and let the target create page's
// applyCreateFormQuery seed them + fire the doctype's existing
// runDocAutofill (DC: get_work_order_defaults; GRN: same, via against_id).
function todayStr() {
	const d = new Date()
	const pad = (n) => String(n).padStart(2, "0")
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function nowTimeStrLocal() {
	const d = new Date()
	const pad = (n) => String(n).padStart(2, "0")
	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function onCreateDcFromWo() {
	if (!doc.value) return
	router.push({
		path: "/delivery-challan/new",
		query: {
			work_order: doc.value.name,
			posting_date: todayStr(),
			posting_time: nowTimeStrLocal(),
			is_rework: doc.value.is_rework ? 1 : 0,
			includes_packing: doc.value.includes_packing ? 1 : 0,
		},
	})
}
// Calculate Deliverables — essdee fabric processes (knitting / dyeing /
// compacting). The modal fetches its own context from
// essdee_yrp.api.work_order.get_fabric_deliverable_context when opened and
// posts calculate_fabric_deliverables on Apply; we just open it here and
// refresh the doc + pivots on success.
const calcDeliverablesOpen = ref(false)
function onCalculateDeliverables() {
	if (!doc.value) return
	calcDeliverablesOpen.value = true
}

// After calculate_deliverables succeeds: reload the doc so deliverables /
// receivables are current, re-hydrate the stock pivots that render them, then
// toast the counts and let the modal close itself.
async function onDeliverablesCalculated(res) {
	markLocalWrite()
	await docState.load(props.id)
	await hydratePivotsForView()
	toast.success(
		"Deliverables calculated",
		`${res?.deliverables ?? 0} deliverable(s) and ${res?.receivables ?? 0} receivable(s).`,
		6000,
	)
}

async function onCreateGrnFromWo() {
	if (!doc.value) return
	const query = {
		against: "Work Order",
		against_id: doc.value.name,
		supplier: doc.value.supplier || "",
		supplier_address: doc.value.supplier_address || "",
		posting_date: todayStr(),
		delivery_date: todayStr(),
		posting_time: nowTimeStrLocal(),
		is_rework: doc.value.is_rework ? 1 : 0,
		includes_packing: doc.value.includes_packing ? 1 : 0,
	}
	// Q12: if the WO has exactly ONE submitted Delivery Challan, pre-seed it so
	// the GRN receives against the obvious DC with no re-pick (a wrong DC → wrong
	// qty is a real error source). With several, leave blank — the autofill still
	// scopes items by the WO and the user picks the DC.
	try {
		const { data } = await getList("Delivery Challan", {
			fields: ["name"],
			filters: [["work_order", "=", doc.value.name], ["docstatus", "=", 1]],
			limit_page_length: 5,
		})
		if (Array.isArray(data) && data.length === 1) query.delivery_challan = data[0].name
	} catch (_) {
		/* non-fatal: leave delivery_challan unset */
	}
	router.push({ path: "/goods-received-note/new", query })
}
// Q9: "Create GRN" on a submitted Delivery Challan — seed against its parent Work
// Order AND the DC itself, so the GRN receives exactly this challan's items.
function onCreateGrnFromDc() {
	if (!doc.value) return
	router.push({
		path: "/goods-received-note/new",
		query: {
			against: "Work Order",
			against_id: doc.value.work_order || "",
			delivery_challan: doc.value.name,
			supplier: doc.value.supplier || "",
			posting_date: todayStr(),
			delivery_date: todayStr(),
			posting_time: nowTimeStrLocal(),
			is_rework: doc.value.is_rework ? 1 : 0,
			includes_packing: doc.value.includes_packing ? 1 : 0,
		},
	})
}
// deferred: amend flow left as-is by decision — useDoc.amend already routes
// through the standard Frappe amend (copy → new draft); a rewrite is out of scope.
function onAmend() {
	confirm.require({
		header: "Amend document",
		message: `Create a new draft amending ${props.id}?`,
		acceptLabel: "Amend",
		acceptClass: "p-button-primary",
		accept: async () => {
			acting.value = "amend"
			try {
				const result = await docState.amend(props.id)
				const newName = result?.name
				toast.success("Amended", newName ? `Draft ${newName} created` : "Amendment created", 6000)
				if (newName) router.push(`/${props.docRoute}/${encodeURIComponent(newName)}`)
			} catch (e) {
				showActionError("Amend failed", e)
			} finally {
				acting.value = null
			}
		},
	})
}

function onDuplicate() {
	if (!doc.value) return
	confirm.require({
		header: "Duplicate document",
		message: `Create an unsaved draft copy of ${props.id}?`,
		acceptLabel: "Duplicate",
		acceptClass: "p-button-primary",
		accept: async () => {
			acting.value = "duplicate"
			try {
				const draft = await docState.duplicate(props.id)
				if (!stashDuplicateDraft(draft)) {
					toast.error("Duplicate failed", "Could not prepare the draft copy in this browser.")
					return
				}
				toast.success("Duplicated", "Unsaved draft copy ready", 6000)
				router.push({ path: `/${props.docRoute}/new`, query: { duplicate: "1" } })
			} catch (e) {
				showActionError("Duplicate failed", e)
			} finally {
				acting.value = null
			}
		},
	})
}

async function reloadView() {
	markLocalWrite()
	// Q15: a successful submit/cancel/approval-change clears any pinned error
	// banner from a prior failed attempt (else a stale red banner contradicts the
	// success toast on a retry that worked). reloadView is the chokepoint for those.
	serverError.value = null
	missingField.value = null
	// A deliberate reload adopts the latest `modified`, so any "modified by another
	// user" notice (incl. a race from our OWN write's realtime echo) is now moot.
	staleNotice.value = false
	await docState.load(props.id)
	// See the note in onSave: viewGrouped doesn't refresh from a plain
	// doc.load, so submit/cancel/amend/approval-change would leave the
	// stock-pivot grid stale (e.g. receivables get process_cost stamped on
	// WO submit) until a manual page reload.
	if (stockPivots.value.length) hydratePivotsForView()
	docState.loadLinked(props.id)
	docState.loadActivity(props.id)
	loadConnections()
	// A submit/cancel/amend changes `modified` (and may move the doc within the
	// list's sort), so re-resolve the prev/next neighbours.
	resolveDocNav()
}

// ── Details field list (config → meta → doc keys) — VIEW mode ──
// Hide rule (applies in BOTH the Details view AND the edit/create form): a
// READ-ONLY field with no value is dropped — it's derived/auto-filled, so an empty
// one is just clutter, and it reappears the moment it gets a value (reactive).
// Empty = null/undefined/"" for any field; numeric (Int/Float/Currency/Percent)
// also counts 0 as empty. A Check always has a value (0/1) so it is never hidden.
function isEmptyForHide(v, fieldtype) {
	if (fieldtype === "Check") return false
	if (["Int", "Float", "Currency", "Percent"].includes(fieldtype))
		return v === null || v === undefined || v === "" || Number(v) === 0
	return v === null || v === undefined || v === ""
}

const detailFields = computed(() => {
	if (!doc.value) return []
	const out = []

	// 1) explicit per-doctype config
	const cfg = getDetailFieldConfig(doctype.value)
	if (cfg) {
		for (const f of cfg) {
			if (!(f.fieldname in doc.value)) continue
			const cmf = metaFieldMap.value[f.fieldname]
			if (cmf?.read_only && isEmptyForHide(doc.value[f.fieldname], cmf?.fieldtype)) continue
			out.push({
				fieldname: f.fieldname,
				label: f.label || humanize(f.fieldname),
				type: f.type || null,
				isLink: f.type === "Link" || linkTypeFor(f.fieldname),
			})
		}
		return out
	}

	// 2) meta-driven (preferred fallback)
	if (meta.value?.fields?.length) {
		for (const mf of meta.value.fields) {
			if (META_HIDDEN_FIELDTYPES.has(mf.fieldtype)) continue
			if (SYSTEM_FIELDS.has(mf.fieldname)) continue
			if (mf.hidden) continue
			if (!(mf.fieldname in doc.value)) continue
			// Hide read-only empty/zero fields (any type; numeric 0 counts as empty).
			if (mf.read_only && isEmptyForHide(doc.value[mf.fieldname], mf.fieldtype)) continue
			out.push({
				fieldname: mf.fieldname,
				label: getFieldLabel(doctype.value, mf.fieldname) || mf.label || humanize(mf.fieldname),
				type: mfTypeToDisplay(mf.fieldtype),
				isLink: mf.fieldtype === "Link",
			})
		}
		return out
	}

	// 3) bare fallback — the doc's own scalar keys
	for (const [k, v] of Object.entries(doc.value)) {
		if (SYSTEM_FIELDS.has(k)) continue
		if (Array.isArray(v) || (v && typeof v === "object")) continue
		out.push({ fieldname: k, label: humanize(k), type: null, isLink: false })
	}
	return out
})

// ── Details tab, grouped into titled cards by Section Break ──
// Same skip rules as detailFields (kept above because quickInfo needs the flat
// list). The only addition here is partitioning meta.fields on Section Break so
// the Details tab renders one accent-header card per logical section. Empty
// groups are dropped so we never render a naked teal header.
const detailSections = computed(() => {
	if (!doc.value) return []

	// 0) curated per-doctype GROUPS → multiple titled cards (for DocTypes whose
	//    own section layout is flat/unnamed, e.g. Work Order). Wins over the
	//    single-card config + meta grouping. Empty groups (all fields dropped)
	//    are not rendered.
	const groups = getDetailGroups(doctype.value)
	if (groups) {
		const out = []
		for (const g of groups) {
			const fields = []
			for (const raw of g.fields) {
				const fn = typeof raw === "string" ? raw : raw.fieldname
				if (!fn || !(fn in doc.value)) continue
				if (SYSTEM_FIELDS.has(fn)) continue
				const mf = metaFieldMap.value[fn]
				if (mf && META_HIDDEN_FIELDTYPES.has(mf.fieldtype)) continue
				if (mf?.hidden) continue
				if (mf?.read_only && isEmptyForHide(doc.value[fn], mf?.fieldtype)) continue
				const label = getFieldLabel(doctype.value, fn) || (typeof raw === "object" && raw.label) || mf?.label || humanize(fn)
				const type = (typeof raw === "object" && raw.type) || (mf ? mfTypeToDisplay(mf.fieldtype) : null)
				fields.push({
					fieldname: fn,
					label,
					type,
					isLink: type === "Link" || mf?.fieldtype === "Link" || !!linkTypeFor(fn),
				})
			}
			// Q16: don't render a card whose every field is empty (e.g. an empty
			// Notes / Logistics group) — whole cards of em-dashes are pure noise.
			if (fields.length && !fields.every((fl) => isEmptyValue(doc.value[fl.fieldname]))) {
				out.push({
					key: g.key || g.label.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
					label: g.label,
					fields,
				})
			}
		}
		if (out.length) return out
	}

	// 1) explicit per-doctype config → single "Details" card
	const cfg = getDetailFieldConfig(doctype.value)
	if (cfg) {
		const fields = []
		for (const f of cfg) {
			if (!(f.fieldname in doc.value)) continue
			const cmf = metaFieldMap.value[f.fieldname]
			if (cmf?.read_only && isEmptyForHide(doc.value[f.fieldname], cmf?.fieldtype)) continue
			fields.push({
				fieldname: f.fieldname,
				label: f.label || humanize(f.fieldname),
				type: f.type || null,
				isLink: f.type === "Link" || linkTypeFor(f.fieldname),
			})
		}
		return fields.length ? [{ key: "details", label: "Details", fields }] : []
	}

	// 2) meta-driven → partition on Section Break
	if (meta.value?.fields?.length) {
		const sections = []
		let cur = { key: "details", label: null, fields: [] }
		const flush = () => {
			// Q16: drop a section whose visible fields are all empty.
			if (cur.fields.length && !cur.fields.every((fl) => isEmptyValue(doc.value[fl.fieldname]))) sections.push(cur)
		}
		for (const mf of meta.value.fields) {
			if (mf.fieldtype === "Section Break") {
				flush()
				cur = { key: mf.fieldname || `sec-${sections.length}`, label: mf.label || null, fields: [] }
				continue
			}
			if (META_HIDDEN_FIELDTYPES.has(mf.fieldtype)) continue
			if (SYSTEM_FIELDS.has(mf.fieldname)) continue
			if (mf.hidden) continue
			if (!(mf.fieldname in doc.value)) continue
			if (mf.read_only && isEmptyForHide(doc.value[mf.fieldname], mf.fieldtype)) continue
			cur.fields.push({
				fieldname: mf.fieldname,
				label: getFieldLabel(doctype.value, mf.fieldname) || mf.label || humanize(mf.fieldname),
				type: mfTypeToDisplay(mf.fieldtype),
				isLink: mf.fieldtype === "Link",
			})
		}
		flush()
		return sections.map((s, i) => ({ ...s, label: s.label || (i === 0 ? "Details" : "More") }))
	}

	// 3) bare fallback → one "Details" card
	const fields = []
	for (const [k, v] of Object.entries(doc.value)) {
		if (SYSTEM_FIELDS.has(k)) continue
		if (Array.isArray(v) || (v && typeof v === "object")) continue
		fields.push({ fieldname: k, label: humanize(k), type: null, isLink: false })
	}
	return fields.length ? [{ key: "details", label: "Details", fields }] : []
})

// Q1: resolve Link titles whenever the rendered Details fields change (doc load,
// meta load, save). Cheap — prime() skips already-cached values.
watch(detailSections, primeDetailLinks, { immediate: true })

// ── Child tables (from meta Table fields) — VIEW mode ──
const childTables = computed(() => {
	if (!doc.value) return []
	const tables = []
	// Keep a pivot child field even when its meta Table is hidden:1 (e.g.
	// Inspection Entry's `items`) — it renders via the grouped editor, not the
	// flat grid, so the hidden flag must not drop it from the view tabs (don't
	// rely on the bare doc-key fallback below to surface it).
	const pivotFields = pivotChildFields.value
	const metaTables = (meta.value?.fields || []).filter(
		(f) => f.fieldtype === "Table" && !CHILD_TABLE_EXCLUDE.has(f.fieldname)
			&& (!f.hidden || pivotFields.has(f.fieldname))
			// Honor depends_on on the child-table field (view mode): evaluate the
			// condition against the loaded `doc` so e.g. Process' `process_details`
			// is hidden when is_group is off and shown when on — matching Desk.
			&& (!f.depends_on || evalCondition(f.depends_on, doc.value)),
	)
	if (metaTables.length) {
		for (const tf of metaTables) {
			const rows = doc.value[tf.fieldname]
			if (!Array.isArray(rows)) continue
			tables.push({
				fieldname: tf.fieldname,
				// columns are META-DRIVEN (childColumns ignores rows), so an empty
				// child table still renders its proper headers — never a blank column.
				label: tf.label || humanize(tf.fieldname),
				columns: childColumns(rows, tf.options),
			})
		}
		// Work Order: DETERMINISTIC view-tab order — Items → Deliverables →
		// Receivables FIRST (immediately after the Details tab), then every other
		// child table in its existing order. We sort by an explicit priority list
		// (NOT meta field_order, which has proven cache-sensitive). Array.sort is
		// stable, so non-priority tables keep their relative order. Other doctypes
		// keep the generic pivot-first ordering below.
		if (isWorkOrder.value) {
			const PRIORITY = ["deliverables", "receivables"]
			const rank = (fn) => {
				const i = PRIORITY.indexOf(fn)
				return i === -1 ? PRIORITY.length : i
			}
			tables.sort((a, b) => rank(a.fieldname) - rank(b.fieldname))
			return tables
		}
		// U2: every other doctype — surface the primary content tables
		// (Deliverables/Receivables/Items) FIRST, ahead of low-traffic logs.
		if (pivotFields.size) {
			tables.sort((a, b) => (pivotFields.has(a.fieldname) ? 0 : 1) - (pivotFields.has(b.fieldname) ? 0 : 1))
		}
		return tables
	}
	// Degenerate fallback — only when the parent meta has NO Table fields at all
	// (essentially never for a real doctype). With no child-DocType meta to drive
	// columns we fall back to row-key inference here, since childColumns is meta-only.
	for (const [k, v] of Object.entries(doc.value)) {
		if (!Array.isArray(v) || !v.length || typeof v[0] !== "object") continue
		tables.push({ fieldname: k, label: humanize(k), columns: childColumnsFromRows(v) })
	}
	return tables
})

// Row-key column inference — the LAST-RESORT path (no child-DocType meta cached).
// Used only by the degenerate childTables fallback above. Headers are humanized
// row keys; fieldtype is guessed from the value so widths/format still resolve.
// All inferred columns are visible by default (no in_list_view info to filter on).
function childColumnsFromRows(rows) {
	if (!rows.length) return []
	const keys = []
	for (const k of Object.keys(rows[0])) {
		if (CHILD_HIDDEN.has(k)) continue
		const val = rows[0][k]
		if (val && typeof val === "object") continue
		keys.push(k)
	}
	return keys.slice(0, 8).map((k) => ({
		fieldname: k,
		label: humanize(k),
		type: typeof rows[0][k] === "number" ? "Float" : null,
		fieldtype: typeof rows[0][k] === "number" ? "Float" : "Data",
		isLink: false,
		reqd: false,
		in_list_view: true,
		hidden: false,
		read_only: false,
	}))
}

const CHILD_HIDDEN = new Set([
	"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
	"parent", "parentfield", "parenttype", "doctype", "__islocal", "__unsaved",
])

// VIEW-mode columns for a child table — META-DRIVEN (shared with the edit grids),
// so the columns (and their headers) show even when the table has ZERO rows. The
// old row-key derivation rendered a blank/empty column for an empty table; this
// derives the same chooser universe from child meta regardless of row data. The
// `rows` arg is intentionally ignored (kept for call-site compatibility / intent).
function childColumns(_rows, childDt) {
	return childColumnsFromMeta(childDt)
}

function rowsFor(ct) {
	const rows = doc.value?.[ct.fieldname]
	return Array.isArray(rows) ? rows : []
}

// U3: badge the count the user actually SEES. For size-pivot child tables the
// grid shows grouped rows (item → attributes), not the flat child rows — so
// badge the grouped entry count; otherwise the flat row count.
function tabBadge(ct) {
	if (pivotChildFields.value.has(ct.fieldname)) {
		const groups = viewGrouped.value?.[ct.fieldname]
		if (Array.isArray(groups)) return groups.reduce((n, g) => n + (g.items?.length || 0), 0)
	}
	return rowsFor(ct).length
}

// ── Linked documents ──
const linkedGroups = computed(() => {
	const raw = docState.linked.value || {}
	const groups = []
	for (const [dt, rows] of Object.entries(raw)) {
		if (!Array.isArray(rows) || !rows.length) continue
		groups.push({ doctype: dt, rows })
	}
	groups.sort((a, b) => a.doctype.localeCompare(b.doctype))
	return groups
})
const linkedTotal = computed(() =>
	linkedGroups.value.reduce((n, g) => n + g.rows.length, 0),
)

function linkedRowMeta(row) {
	const bits = []
	for (const k of ["title", "supplier", "supplier_name", "item", "status", "grand_total"]) {
		if (row[k] != null && row[k] !== "" && k !== "name") bits.push(String(row[k]))
	}
	return bits.slice(0, 2).join(" · ")
}

// ── Activity (comments + versions) ──
const activityEvents = computed(() => {
	const events = []
	const d = doc.value
	const info = docState.docInfo.value

	if (d?.creation) {
		events.push({
			when: d.creation,
			who: shortUser(d.owner),
			text: "Created",
			tone: "good",
			icon: "pi pi-plus",
		})
	}

	const comments = info?.comments
	if (Array.isArray(comments) && comments.length) {
		for (const c of comments) {
			events.push({
				when: c.creation,
				who: shortUser(c.owner),
				text: stripHtml(c.content || ""),
				tone: "muted",
				icon: "pi pi-comment",
			})
		}
	} else if (d?._comments) {
		try {
			const parsed = JSON.parse(d._comments)
			for (const c of parsed) {
				events.push({
					when: c.creation || d.modified,
					who: shortUser(c.by),
					text: stripHtml(c.comment || ""),
					tone: "muted",
					icon: "pi pi-comment",
				})
			}
		} catch (_) { /* ignore */ }
	}

	const versions = info?.versions
	if (Array.isArray(versions)) {
		for (const v of versions) {
			events.push({
				when: v.creation,
				who: shortUser(v.owner),
				text: "Edited",
				tone: "info",
				icon: "pi pi-pencil",
			})
		}
	}

	if (d?.docstatus === 1) {
		events.push({
			when: d.modified,
			who: shortUser(d.modified_by),
			text: "Submitted",
			tone: "good",
			icon: "pi pi-check-circle",
		})
	} else if (d?.docstatus === 2) {
		events.push({
			when: d.modified,
			who: shortUser(d.modified_by),
			text: "Cancelled",
			tone: "danger",
			icon: "pi pi-ban",
		})
	}

	return events.sort((a, b) =>
		String(b.when || "").localeCompare(String(a.when || "")),
	)
})

// ── Header derivations ──
const titleLine = computed(() => {
	const d = doc.value
	if (!d) return ""
	const bits = []
	for (const f of ["item", "supplier_name", "supplier", "process_name", "total_quantity"]) {
		if (d[f] != null && d[f] !== "") bits.push(String(d[f]))
	}
	if (bits.length) return bits.slice(0, 4).join(" · ")
	const tf = meta.value?.title_field
	if (tf && d[tf]) return String(d[tf])
	return ""
})

const DOCSTATUS_LABELS = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }
const statusLabel = computed(() => {
	const d = doc.value
	if (!d) return ""
	if (isWorkflow.value && d.workflow_state) return d.workflow_state
	return d.status || DOCSTATUS_LABELS[d.docstatus] || "—"
})
const statusSeverity = computed(() => {
	const d = doc.value
	if (isWorkflow.value && d?.workflow_state) return WORKFLOW_SEVERITY[d.workflow_state] || "warn"
	const ds = d?.docstatus
	if (ds === 1) return "success"
	if (ds === 2) return "danger"
	return "warn"
})

// ── Quick Info (key meta pairs) ──
// Hero-facts strip = the first 4 Quick Info entries (same data, promoted to
// the record header). Skips ID-ish duplicates of the title the user already sees.
const heroFacts = computed(() => quickInfo.value.slice(0, 4))

const quickInfo = computed(() => {
	const d = doc.value
	if (!d) return []
	const out = []
	const push = (label, val) => {
		if (val != null && val !== "") out.push({ label, value: String(val) })
	}
	const pref = isWorkOrder.value
		? [["process_name", "Process"], ["supplier", "Job-worker"], ["total_quantity", "Qty"], ["wo_date", "WO Date"]]
		: detailFields.value.slice(0, 5).map((f) => [f.fieldname, f.label])
	for (const [fn, label] of pref) {
		const f = detailFields.value.find((x) => x.fieldname === fn)
		// Q1: a Link in Quick Info resolves to the human name too (else the WO
		// Job-worker line shows S-0003 next to the resolved name in the card).
		const val = f
			? (f.isLink && !isEmptyValue(d[fn]) ? linkPartsFor(f, d[fn]).primary : displayValue(d[fn], f.type, fn))
			: d[fn]
		push(label, val)
	}
	// Q17: "Created by" / "Last updated" intentionally dropped — they're audit
	// metadata, available on the Activity tab. Quick Info keeps only the
	// decision facts (what / how-many / by-when). Status lives in the header tag.
	return out
})

// ── Navigation ──
const deskUrl = computed(() => {
	const slug = doctype.value.toLowerCase().replace(/ /g, "-")
	return `/app/${encodeURIComponent(slug)}/${encodeURIComponent(props.id)}`
})

function goHome() {
	router.push("/home")
}
function goList() {
	router.push(`/${props.docRoute}`)
}
function navigateDoc(dt, name) {
	const reg = getRegistryByDoctype(dt)
	if (reg) {
		router.push(`/${reg.route}/${encodeURIComponent(name)}`)
		return
	}
	// Non-registry doctype: with only 8 registered doctypes this fires for
	// everyday links (supplier, process, UOM…). Desk fallback is admin-only
	// (HARD RULE 2026-05-29: a restricted /web user is never sent to Desk) —
	// everyone else gets a toast instead of a dead Desk tab.
	if (isAdmin.value || hasRole("System Manager")) {
		const slug = dt.toLowerCase().replace(/ /g, "-")
		window.open(`/app/${encodeURIComponent(slug)}/${encodeURIComponent(name)}`, "_blank")
	} else {
		toast.info("Not available here", `${dt} records are managed outside /web — ask an administrator.`)
	}
}
function navigateLink(field, value) {
	if (!value) return
	const targetDt = linkTargetFor(field)
	if (targetDt) navigateDoc(targetDt, value)
}

// ── Q1: Link code → human name ───────────────────────────────────────────────
// The target doctype of a Details Link field (Dynamic Links resolve from their
// controlling field on the loaded doc).
function linkTargetFor(field) {
	const mf = metaFieldMap.value[field.fieldname]
	if (!mf) return ""
	return mf.fieldtype === "Dynamic Link" ? (doc.value?.[mf.options] || "") : (mf.options || "")
}
// { primary, code } for a Link value: sibling `<field>_name` → resolved title →
// raw code. `code` is "" when the primary already IS the code (no duplication).
function linkPartsFor(field, value) {
	const sibling = doc.value?.[`${field.fieldname}_name`]
	return linkTitles.linkParts(linkTargetFor(field), value, sibling)
}
// Batch-resolve titles for the Details links that lack a `_name` sibling, so
// codes like `S-0003` / `PC-00007` render as the human name. No-ops for values
// already cached, so it's cheap to re-run on every (re)load.
function primeDetailLinks() {
	if (!doc.value) return
	const pairs = []
	for (const s of detailSections.value) {
		for (const f of s.fields) {
			if (!f.isLink) continue
			const val = doc.value[f.fieldname]
			if (!val) continue
			if (doc.value[`${f.fieldname}_name`]) continue // sibling already names it
			const target = linkTargetFor(f)
			if (target) pairs.push({ doctype: target, name: val })
		}
	}
	if (pairs.length) linkTitles.prime(pairs)
}
function goToFirst(group) {
	if (group.rows[0]) navigateDoc(group.doctype, group.rows[0].name)
}

// ── date helpers (form ↔ Frappe string) ──
// Parse date / datetime strings as LOCAL time (constructing from parts) so a
// pure "YYYY-MM-DD" doesn't shift a day in negative-offset timezones (the
// classic `new Date("2026-05-25")`-is-UTC pitfall).
function toDateObj(val) {
	if (!val) return null
	const s = String(val).trim()
	const [datePart, timePart] = s.split(/[ T]/)
	const [y, m, d] = (datePart || "").split("-").map(Number)
	if (!y || !m || !d) return null
	let hh = 0, mm = 0, ss = 0
	if (timePart) {
		const [h, mi, se] = timePart.split(":").map(Number)
		hh = h || 0
		mm = mi || 0
		ss = se || 0
	}
	const obj = new Date(y, m - 1, d, hh, mm, ss)
	return Number.isNaN(obj.getTime()) ? null : obj
}
function fromDateObj(d, withTime) {
	if (!d) return ""
	const pad = (n) => String(n).padStart(2, "0")
	const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
	if (!withTime) return date
	return `${date} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// Time field (HH:MM:SS string) ↔ Date object for the timeOnly DatePicker.
function toTimeObj(val) {
	if (!val) return null
	const [h, mi, s] = String(val).split(":").map(Number)
	const d = new Date()
	d.setHours(h || 0, mi || 0, s || 0, 0)
	return d
}
function fromTimeObj(d) {
	if (!d) return ""
	const pad = (n) => String(n).padStart(2, "0")
	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function nowTimeStr() {
	return fromTimeObj(new Date())
}

// ── formatting helpers ──
function humanize(s) {
	return String(s)
		.replace(/_/g, " ")
		.replace(/\b\w/g, (c) => c.toUpperCase())
}
// Empty for display purposes — drives the quiet "—" placeholder styling in the
// Details cards (matches displayValue's own empty check).
function isEmptyValue(v) {
	return v === null || v === undefined || v === ""
}
function mfTypeToDisplay(ft) {
	if (ft === "Date") return "Date"
	if (ft === "Datetime") return "Datetime"
	if (ft === "Currency") return "Currency"
	if (ft === "Float" || ft === "Percent") return "Float"
	if (ft === "Int") return "Int"
	if (ft === "Check") return "Check"
	if (ft === "Link") return "Link"
	return null
}
// Q20: the edit-mode toggle's word — positive labels for negatively-named flags
// ("Disabled"/"Active") via the field-config override, else plain Yes/No.
function checkWord(f) {
	const bl = getBoolLabels(doctype.value, f.fieldname)
	return form[f.fieldname] ? (bl?.on ?? "Yes") : (bl?.off ?? "No")
}
function displayValue(val, type, fieldname) {
	if (val === null || val === undefined || val === "") return "—"
	if (type === "Check") {
		// Q20: positive boolean display — show the effective state ("Active") for
		// negatively-named flags instead of the double-negative "Disabled: No".
		const bl = fieldname ? getBoolLabels(doctype.value, fieldname) : null
		if (bl) return val ? bl.on : bl.off
		return val ? "Yes" : "No"
	}
	if (type === "Date") return formatDate(val)
	if (type === "Datetime") return formatDateTime(val)
	if (type === "Currency") return formatNumber(val)
	if (type === "Float" || type === "Int") return formatNumber(val)
	return String(val)
}
function formatDate(val) {
	if (!val) return "—"
	const datePart = String(val).split(" ")[0]
	const [y, m, d] = datePart.split("-")
	return y && m && d ? `${d}-${m}-${y}` : val
}
function formatDateTime(val) {
	if (!val) return "—"
	const [datePart, timePart] = String(val).split(" ")
	const [y, m, d] = (datePart || "").split("-")
	const dateStr = y && m && d ? `${d}-${m}-${y}` : datePart
	const timeStr = timePart ? timePart.slice(0, 5) : ""
	return timeStr ? `${dateStr} ${timeStr}` : dateStr
}
function formatNumber(val) {
	const n = Number(val)
	return Number.isNaN(n) ? String(val) : n.toLocaleString("en-IN")
}
function shortUser(u) {
	if (!u) return "—"
	return String(u).split("@")[0]
}
function stripHtml(s) {
	return String(s).replace(/<[^>]*>/g, "").trim()
}
</script>

<style scoped>
.doc-detail {
	display: flex;
	flex-direction: column;
	gap: 12px;
}

/* Breadcrumb */
.crumbs {
	display: flex;
	align-items: center;
	gap: 7px;
	font-size: 12.5px;
	color: var(--esd-muted);
}
.crumbs a {
	cursor: pointer;
	color: var(--esd-muted);
}
.crumbs a:hover {
	color: var(--esd-accent-700);
}
.crumbs .sep {
	color: var(--esd-muted-2);
}
.crumbs .crumb-cur {
	font-size: 12.5px;
}

/* Header */
.detail-head {
	display: flex;
	align-items: flex-start;
	gap: 14px;
}
.id-block {
	display: flex;
	flex-direction: column;
	gap: 3px;
}
/* Prev/Next document navigation arrows — vertically centred against the (taller)
   id-block, subtle until hovered. */
.doc-nav {
	display: flex;
	align-items: center;
	gap: 2px;
	align-self: center;
}
.doc-nav__btn.p-button {
	width: 30px;
	height: 30px;
	color: var(--esd-muted);
}
.doc-nav__btn.p-button:not(:disabled):hover {
	color: var(--esd-accent-700);
}
.doc-id {
	font-size: 18px;
	letter-spacing: -0.01em;
}
.doc-title {
	font-size: 13px;
	color: var(--esd-muted);
}
.doc-title.edit-hint {
	color: var(--esd-accent-700);
	font-weight: 600;
}
.head-status {
	align-self: center;
}
.head-actions {
	margin-left: auto;
	display: flex;
	gap: 8px;
	align-items: center;
}
.desk-link {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	font-size: 12.5px;
	color: var(--esd-accent-700);
	padding: 6px 10px;
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
}
.desk-link:hover {
	background: var(--esd-accent-50);
}

.print-form {
	display: flex;
	flex-direction: column;
	gap: 6px;
	padding-top: 2px;
}
.print-form .fld {
	width: 100%;
}

/* States */
.state-block {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 10px;
	padding: 40px 0;
	color: var(--esd-muted);
}
.state-block.sm {
	flex-direction: row;
	padding: 22px 0;
	font-size: 13px;
}

/* Two-column layout */
.detail-layout {
	display: grid;
	grid-template-columns: minmax(0, 1fr) 288px;
	gap: 16px;
	align-items: start;
}
@media (max-width: 980px) {
	.detail-layout {
		grid-template-columns: 1fr;
	}
}

.detail-main {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	overflow: hidden;
}

/* ── Form (edit / create) ── */
.form-layout {
	display: block;
}
/* The edit/create form is a stack of titled .esd-card sections, so its outer
   container drops its own card chrome (border/bg) and just owns the rhythm. */
.detail-main.form-card {
	background: transparent;
	border: none;
	border-radius: 0;
	overflow: visible;
}
.form-card {
	display: flex;
	flex-direction: column;
	gap: var(--space-4);
}
.form-section .form-grid {
	margin: 0;
}
.form-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 16px 28px;
}
@media (max-width: 700px) {
	.form-grid {
		grid-template-columns: 1fr;
	}
}
.form-field {
	display: flex;
	flex-direction: column;
	gap: 5px;
	min-width: 0;
}
.form-field.wide {
	grid-column: 1 / -1;
}
/* Form labels match the Details label scale — uppercase muted, ABOVE the input
   (the form's natural order is preserved; the value-as-hero order swap is
   scoped to .field in the read view only). */
.form-field > label.field-label {
	font-size: 12px;
	font-weight: 600;
	color: var(--esd-muted);
	text-transform: uppercase;
	letter-spacing: 0.03em;
}
.form-field .fld {
	width: 100%;
}
.form-field .req {
	color: var(--esd-danger);
	margin-left: 2px;
}
.fld-check {
	display: flex;
	align-items: center;
	gap: 10px;
	padding-top: 2px;
}
.check-label {
	font-size: 13px;
	color: var(--esd-ink-2);
}
.time-fld {
	display: flex;
	align-items: center;
	gap: 8px;
}
.time-fld .time-input {
	flex: 1;
	min-width: 0;
}
.time-fld .time-now {
	flex-shrink: 0;
}

/* Child-table editor */
.child-editor {
	display: flex;
	flex-direction: column;
	gap: 8px;
}
.child-editor-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
}
.child-editor-head h4 {
	margin: 0;
	font-size: 13.5px;
	font-weight: 600;
	color: var(--esd-ink);
}
.child-cols-note {
	font-size: 12px;
	color: var(--esd-muted);
	font-style: italic;
}
.child-head-actions {
	display: flex;
	align-items: center;
	gap: 8px;
}
/* View-mode child-table column chooser bar (no head row to hang it on). */
.child-view-toolbar {
	display: flex;
	justify-content: flex-end;
	margin-bottom: 8px;
}
/* "Columns" chooser popover body */
.col-chooser {
	display: flex;
	flex-direction: column;
	gap: 6px;
	min-width: 260px;
	max-height: 320px;
	overflow-y: auto;
	padding: 2px;
}
.col-chooser__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	margin-bottom: 2px;
}
.col-chooser__title {
	font-size: 11px;
	letter-spacing: 0.03em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
}
.col-chooser__total {
	font-size: 12px;
	font-weight: 700;
	color: var(--esd-ink);
	font-variant-numeric: tabular-nums;
}
.col-chooser__row {
	display: flex;
	align-items: center;
	gap: 8px;
}
.col-chooser__row label {
	flex: 1 1 auto;
	min-width: 0;
	font-size: 13px;
	color: var(--esd-ink);
	cursor: pointer;
	user-select: none;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.col-chooser__width {
	flex: 0 0 64px;
	width: 64px;
}
.col-chooser__width :deep(.col-chooser__width-input) {
	width: 64px;
	text-align: center;
	padding-inline: 6px;
}
.child-cols-note.pivot-note {
	color: var(--esd-accent-700);
	font-style: normal;
	font-size: 11.5px;
}
.lot-locked-note {
	color: var(--esd-warn, #b45309);
	font-style: normal;
	font-size: 12px;
	margin: 0 0 8px;
}
.edit-dt :deep(.cell-input) {
	width: 100%;
}
/* PrimeVue's `fluid` sets the InputNumber/AutoComplete inner <input> to
   width:1% (a flex trick that needs a flex host), but our .cell-input host
   renders display:block, so the inner input collapses to ~26px and the user
   can't see the value being typed. Force the inner input to fill the host. */
.edit-dt :deep(.cell-input input) {
	width: 100%;
}
.edit-dt :deep(.p-datatable-tbody > tr > td) {
	padding: 6px 10px;
}
/* Fixed-layout child tables: clip overflowing cell content so a long value or an
   in-cell editor can't force a column wider than its set width (the old
   focus/edit jitter). The editor inputs are width:100% so they fit the cell. */
.child-dt :deep(.p-datatable-tbody > tr > td),
.child-dt :deep(.p-datatable-thead > tr > th) {
	overflow: hidden;
	text-overflow: ellipsis;
}
.child-dt :deep(.p-datatable-tbody > tr > td > span) {
	display: block;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
/* EDIT grids only: do NOT clip the cell while an in-cell editor (InputNumber /
   AutoComplete) is mounted — the ellipsis clipping otherwise hides the caret and
   the just-typed digit until blur (cell still uses the fixed column width, so the
   layout doesn't jitter — the editor inputs are width:100% and fit the cell).
   Higher specificity than the .child-dt clip rule above (.edit-dt.child-dt) AND
   ordered after it, so it wins for edit grids; view-mode .child-dt keeps the clip. */
.edit-dt.child-dt :deep(.p-datatable-tbody > tr > td) {
	overflow: visible;
	text-overflow: clip;
}

/* Tab badge */
.tab-badge {
	margin-left: 6px;
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
	font-size: 11px;
	font-weight: 600;
	padding: 1px 7px;
	border-radius: 999px;
}

/* Details tab — grouped accent-header cards */
.details-stack {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
	gap: 16px;
	align-items: start;
}
@media (min-width: 1400px) {
	.details-stack {
		grid-template-columns: repeat(auto-fill, minmax(460px, 1fr));
	}
}

.detail-card {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	overflow: hidden;
	box-shadow: var(--esd-shadow-card);
}
.detail-card__head {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 10px 16px;
	/* Light band: pale tint + teal title (AA ~4.6:1), header recedes so data leads. */
	background: var(--esd-accent-50); border-bottom: 1px solid var(--esd-line);
}
.detail-card__dot {
	width: 6px;
	height: 6px;
	border-radius: 999px;
	background: var(--esd-accent-ink);
	opacity: 0.85;
	flex: 0 0 auto;
}
.detail-card__title {
	font-size: 13px;
	font-weight: 700;
	letter-spacing: 0.02em;
	color: var(--esd-accent-ink);
}
.detail-card__body {
	padding: 16px 18px 18px;
}

.field-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 4px 28px;
}
@media (max-width: 640px) {
	.field-grid {
		grid-template-columns: 1fr;
	}
}
.field {
	display: flex;
	flex-direction: column;
	gap: 2px;
	padding: 9px 0;
	min-width: 0;
	border-bottom: 1px solid var(--esd-line);
}
.field-label {
	font-size: 11px;
	letter-spacing: 0.03em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
}
.field-value {
	font-size: 16px;
	line-height: 1.35;
	font-weight: 600;
	color: var(--esd-ink);
	word-break: break-word;
}
.field-value.link {
	color: var(--esd-accent-700);
	cursor: pointer;
}
.field-value.link:hover {
	text-decoration: underline;
}
.field-value.esd-mono {
	font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
	font-size: 15px;
	letter-spacing: -0.01em;
}
.field-value.is-empty {
	color: var(--esd-muted-2);
	font-weight: 500;
}
/* Value-as-hero ordering — SCOPED to Details cards (.field) only, so the
   create/edit form (.form-field .field-label) keeps its label ABOVE the input.
   A global .field-label{order:2} inverted the edit form. */
.field > .field-value {
	order: 1;
}
.field > .field-label {
	order: 2;
}

.empty-inline {
	color: var(--esd-muted);
	font-size: 13px;
	padding: 18px 2px;
}
.empty-inline.sm {
	padding: 6px 0;
	font-size: 12.5px;
}

/* Child table */
.child-dt {
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	overflow: hidden;
}

/* Timeline */
.esd-timeline {
	padding: 6px 0;
}
.tl-dot {
	display: grid;
	place-items: center;
	width: 24px;
	height: 24px;
	border-radius: 50%;
	background: var(--esd-card);
	border: 2px solid var(--esd-line);
	color: var(--esd-muted);
	font-size: 11px;
}
.tl-dot.good {
	border-color: var(--esd-success);
	color: var(--esd-success);
}
.tl-dot.danger {
	border-color: var(--esd-danger);
	color: var(--esd-danger);
}
.tl-dot.info {
	border-color: var(--esd-accent);
	color: var(--esd-accent);
}
.tl-when {
	font-size: 11.5px;
	color: var(--esd-muted);
	margin-bottom: 2px;
}
.tl-msg {
	font-size: 13px;
	color: var(--esd-ink);
	padding-bottom: 12px;
}
.txt-danger {
	color: var(--esd-danger);
}
.txt-good {
	color: var(--esd-success);
}
.tab-footnote {
	margin: 14px 2px 0;
	font-size: 12px;
	color: var(--esd-muted);
}
.tab-footnote code,
.tl-msg code {
	font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
	font-size: 11.5px;
	background: var(--esd-slate-50);
	padding: 1px 4px;
	border-radius: 3px;
}

/* Linked panel */
.linked-panel {
	display: flex;
	flex-direction: column;
	gap: 10px;
}
.linked-group {
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	overflow: hidden;
}
.linked-group-head {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 9px 14px;
	background: var(--esd-slate-50);
	border-bottom: 1px solid var(--esd-line);
}
.linked-group-head h5 {
	margin: 0;
	font-size: 12.5px;
	font-weight: 600;
	color: var(--esd-ink);
}
.linked-group-head .count {
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
	font-size: 11px;
	font-weight: 600;
	padding: 1px 7px;
	border-radius: 999px;
}
.linked-row {
	display: grid;
	grid-template-columns: 200px 1fr auto;
	gap: 12px;
	align-items: center;
	padding: 11px 14px;
	border-bottom: 1px solid var(--esd-line);
	cursor: pointer;
	transition: background 0.1s;
}
.linked-row:last-child {
	border-bottom: 0;
}
.linked-row:hover {
	background: var(--esd-slate-50);
}
.linked-row .lr-id {
	font-size: 12.5px;
}
.linked-row .lr-meta {
	font-size: 12.5px;
	color: var(--esd-ink-2);
}
.linked-row .lr-arrow {
	color: var(--esd-muted-2);
	transition: transform 0.12s, color 0.12s;
}
.linked-row:hover .lr-arrow {
	color: var(--esd-accent);
	transform: translateX(2px);
}

/* Side panel */
.detail-side {
	display: flex;
	flex-direction: column;
	gap: 12px;
}
.side-card {
	border: 1px solid var(--esd-line);
	box-shadow: var(--esd-shadow-card);
	overflow: hidden;
}
/* Band head is full-bleed; the body owns the inset. Matches the Details cards. */
:deep(.side-card .p-card-body) {
	padding: 0;
	gap: 0;
}
:deep(.side-card .p-card-caption) {
	margin: 0;
}
:deep(.side-card .p-card-content) {
	padding: 14px 16px;
}
.meta-row {
	display: flex;
	justify-content: space-between;
	gap: 10px;
	font-size: 12.5px;
	padding: 6px 0;
	border-bottom: 1px solid var(--esd-line);
}
.meta-row:last-child {
	border-bottom: 0;
}
.meta-row.col {
	flex-direction: column;
	gap: 3px;
}
.meta-row .k {
	color: var(--esd-muted);
	flex-shrink: 0;
}
.meta-row .v {
	color: var(--esd-ink);
	font-weight: 500;
	text-align: right;
	max-width: 65%;
	word-break: break-word;
}
.meta-row.col .v {
	max-width: 100%;
	text-align: left;
}
.meta-row .v.reason {
	font-weight: 400;
	font-style: italic;
	color: var(--esd-ink-2);
}
.link-row {
	cursor: pointer;
}
.link-row:hover .k {
	color: var(--esd-accent-700);
}
.count-pill {
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
	font-size: 11px;
	font-weight: 600;
	padding: 1px 8px;
	border-radius: 999px;
}

/* ════════════ UX quick-wins (2026-06-01) ════════════ */

/* Q2: the human title is the page hero; the serial is a small mono chip. */
.doc-hero {
	font-size: 20px;
	font-weight: 700;
	letter-spacing: -0.01em;
	color: var(--esd-ink);
	line-height: 1.2;
}
.id-block .doc-id {
	font-size: 12px;
	color: var(--esd-muted);
}
.doc-subtle.edit-hint {
	font-size: 12px;
	font-weight: 600;
	color: var(--esd-accent-700);
}

/* Q4: status is the visual anchor — bigger, bolder tag (beats .p-tag padding). */
.head-status.p-tag {
	font-size: 13px;
	font-weight: 700;
	padding: 5px 12px;
}

/* Q11: the forward action (Create …) is the primary next step, set apart from
   the danger-styled Cancel beside it. */
.cta-wrap {
	display: inline-flex;
}
.forward-cta {
	/* The one filled-teal primary among outlined neighbours — a subtle lift so
	   the next step reads as the clear call to action. */
	box-shadow: 0 1px 2px var(--esd-shadow);
}

/* Q1: a Link value = human name (normal weight) + muted mono code beside it. */
.field-value .lv-name {
	color: inherit;
}
.field-value .lv-code {
	margin-left: 8px;
	font-size: 12px;
	font-weight: 500;
	color: var(--esd-muted-2);
}
/* Q8: persistent affordance — dotted underline + trailing ↗, no hover needed. */
.field-value.link .lv-name {
	text-decoration: underline dotted;
	text-underline-offset: 2px;
}
.field-value.link::after {
	content: " ↗";
	font-size: 12px;
	color: var(--esd-accent);
	opacity: 0.85;
}

/* Q13: inline field help under the input. */
.field-help {
	font-size: 11.5px;
	color: var(--esd-muted);
	line-height: 1.35;
}

/* Q5 + Q15: top-of-content banners (missing field / server error). */
.form-banner {
	margin: 0 0 4px;
}
.srv-err__title {
	font-weight: 600;
	margin-bottom: 2px;
}
.srv-err__line {
	font-size: 12.5px;
	white-space: pre-wrap;
}
.srv-err__actions {
	margin-top: 8px;
}
</style>
