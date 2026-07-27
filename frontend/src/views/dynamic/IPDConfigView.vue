<!--
  IPDConfigView — dedicated detail view for Item Production Detail (R1a).

  Richer than the generic DocDetail: it surfaces the production-config flow the
  Desk IPD drives. Three working sections:

    1. Item BOM        — the bill-of-materials rows. Rows flagged
                         `based_on_attribute_mapping` link out to the Item BOM
                         Attribute Mapping editor (R1b — route exists, view lands
                         later; the link guards a null mapping).
    2. IPD Processes   — process rows (process_name / in_stage / out_stage). Each
                         row has "Configure combinations" → the synthesized
                         redirect into the IPD Process Matrix editor (find-or-new).
    3. Process Matrices — the existing IPD Process Matrices for THIS IPD, with
                         "Open" into the editor.

  Reads only (this view does not write the IPD itself — edits go through the
  generic DocDetail at /web/item-production-detail/:id in edit mode is NOT wired
  here; this is the rich config surface). Loads via getDoc (frappe.client.get)
  so child arrays (item_bom, ipd_processes) come back inline.

  The "Configure combinations" redirect mirrors the Desk's 3-doctype split:
  yrp ships no auto-redirect, so we synthesize it (RICH_FLOWS_PLAN.md). We look
  for an existing matrix for {ipd, process_name}; found → open it; else → create
  route (`/ipd-process-matrix/new?ipd=&process=`) where the editor seeds via
  generate_cross_product.
-->
<template>
	<div class="ipd-config">
		<!-- Breadcrumb -->
		<nav class="crumbs">
			<a @click="goHome">Home</a>
			<span class="sep">/</span>
			<a @click="goList">Item Production Detail</a>
			<span class="sep">/</span>
			<span class="crumb-cur" :class="{ 'esd-mono': !itemLabel }">{{ itemLabel || id }}</span>
		</nav>

		<!-- Header (Q2: the produced item is the hero; the IPD code is a chip). -->
		<div class="detail-head">
			<div class="id-block">
				<div class="doc-hero">{{ itemLabel || id }}</div>
				<div v-if="headerLine" class="doc-sub">{{ headerLine }}</div>
				<div class="doc-id esd-mono">{{ id }}</div>
			</div>
			<Tag
				v-if="doc"
				class="head-status"
				:value="doc.approval_status || 'Draft'"
				:severity="approvalSeverity"
				rounded
			/>
			<div class="head-actions">
				<!-- DOCUMENT-level edit mode (2026-07-10, user mandate): ONE Edit
				     puts every tab into edit mode; ONE Save persists all tabs in a
				     single request; ONE Cancel reverts everything. Never a separate
				     Edit button per tab. -->
				<template v-if="doc && editableDoc">
					<Button
						v-if="!editing"
						label="Edit"
						icon="pi pi-pencil"
						size="small"
						data-testid="ipd-edit"
						@click="enterEditAll"
					/>
					<template v-else>
						<Button
							label="Save"
							icon="pi pi-check"
							size="small"
							:loading="savingAll"
							data-testid="ipd-save"
							@click="saveAll"
						/>
						<Button
							label="Cancel"
							size="small"
							text
							severity="secondary"
							:disabled="savingAll"
							data-testid="ipd-cancel"
							@click="cancelAll"
						/>
					</template>
				</template>
				<Button
					v-if="doc && !editing && canApprove"
					label="Approve"
					icon="pi pi-check-circle"
					size="small"
					severity="success"
					:loading="approvalBusy"
					data-testid="ipd-approve"
					@click="onApprove"
				/>
				<Button
					v-if="doc && !editing && canRevertApproval"
					label="Revert Approval"
					icon="pi pi-undo"
					size="small"
					severity="danger"
					outlined
					:loading="approvalBusy"
					data-testid="ipd-revert-approval"
					@click="onRevertApproval"
				/>
				<Button
					v-if="doc && !editing && canCreate('Item Production Detail')"
					label="Duplicate IPD"
					icon="pi pi-copy"
					size="small"
					severity="secondary"
					outlined
					data-testid="ipd-duplicate"
					@click="openDuplicateDialog"
				/>
				<Button
					v-if="doc && !editing && canDelete('Item Production Detail')"
					label="Delete"
					icon="pi pi-trash"
					size="small"
					severity="danger"
					outlined
					:loading="deleting"
					@click="onDelete"
				/>
				<a
					v-if="isAdmin || hasRole('System Manager')"
					class="desk-link"
					:href="deskUrl"
					target="_blank"
					rel="noopener"
				>
					<i class="pi pi-external-link" /> Open in Desk
				</a>
			</div>
		</div>

		<!-- Loading -->
		<div v-if="loading" class="state-block">
			<i class="pi pi-spin pi-spinner" style="font-size: 1.5rem" />
			<span>Loading…</span>
		</div>

		<!-- Error -->
		<Message v-else-if="error && !doc" severity="error" :closable="false">
			{{ error }}
		</Message>

		<template v-else-if="doc">
			<!-- Attribute summary strip -->
			<div class="attr-strip">
				<div class="attr-cell">
					<span class="al">Item</span>
					<a class="av esd-mono" @click="navigateDoc('Item', doc.item)">{{ doc.item || "—" }}</a>
				</div>
				<div class="attr-cell">
					<span class="al">Primary Attribute</span>
					<span class="av">{{ doc.primary_item_attribute || "—" }}</span>
				</div>
				<div class="attr-cell">
					<span class="al">Dependent Attribute</span>
					<span class="av">
						{{ doc.dependent_attribute || "—" }}
						<i
							v-if="doc.dependent_attribute"
							class="pi pi-info-circle dep-hint"
							v-tooltip.bottom="'Stamped onto matrix combinations by the engine from each process in/out stage — it is intentionally NOT an editable matrix column.'"
						/>
					</span>
				</div>
			</div>

			<!-- Tabbed shell (2026-07-09). Cloth IPD = Item Details + Fabric
			     Processes only — the Knitting/Dyeing/Compacting tabs were removed
			     from the form; the generic Fabric Processes tab supersedes them.
			     Garment IPD = the full Desk tab set in Desk order: Item Details,
			     Packing, Set Item, Stiching, Emblishment, Cutting, Cloth
			     Accessory, Advance Settings (phases 1+2, 2026-07-10). The Set
			     Item tab additionally needs packing_attribute (Desk depends_on). -->
			<Tabs v-model:value="activeTab" class="ipd-tabs">
				<TabList>
					<Tab value="details">Item Details</Tab>
					<Tab v-if="doc.is_cloth_item" value="fabric">Fabric Processes</Tab>
					<Tab v-if="doc.is_cloth_item" value="compacting">Compacting Details</Tab>
					<Tab v-if="!doc.is_cloth_item" value="packing">Packing</Tab>
					<Tab v-if="!doc.is_cloth_item && doc.packing_attribute" value="setitem">Set Item</Tab>
					<Tab v-if="!doc.is_cloth_item" value="stiching">Stiching</Tab>
					<Tab v-if="!doc.is_cloth_item" value="emblishment">Emblishment</Tab>
					<Tab v-if="!doc.is_cloth_item" value="cutting">Cutting</Tab>
					<Tab v-if="!doc.is_cloth_item" value="accessory">Cloth Accessory</Tab>
					<Tab v-if="!doc.is_cloth_item" value="advanced">Advance Settings</Tab>
				</TabList>
				<TabPanels class="ipd-tabpanels">
					<TabPanel value="details" class="ipd-tabpanel">

			<!-- One user-facing cloth definition. The old global yarn-ratio table
			     is derived server-side from the first colour for compatibility. -->
			<section v-if="doc.is_cloth_item" class="panel">
				<div class="panel-head">
					<h3>Cloth Colours &amp; Yarn Recipes</h3>
					<span class="panel-meta">{{ colourYarnGroups.length }} colour recipe(s)</span>
				</div>
				<div class="recipe-help">
					One card owns a finished cloth colour and its yarn blend. Ratio % is each yarn's share of that
					colour's blend; there is no second yarn-ratio entry. Maintain Dia and Colour conversions only in
					<strong>Fabric Processes</strong>.
				</div>
				<div v-if="editing" class="recipe-list">
					<div
						v-for="group in colourYarnGroups"
						:key="group.key"
						class="recipe-card recipe-card--edit"
					>
						<div class="recipe-group-head">
							<div class="recipe-colour-field">
								<span class="recipe-field-label">Finished Colour</span>
								<LinkField
									:modelValue="group.colour"
									target-doctype="Item Attribute Value"
									:search-handler="searchColour"
									placeholder="Select finished colour"
									@update:modelValue="(v) => setRecipeGroupColour(group, v)"
								/>
							</div>
							<strong class="recipe-total" :class="{ invalid: Math.abs(group.total - 100) > 0.001 }">
								{{ group.total }}%
							</strong>
							<Button
								icon="pi pi-trash"
								severity="danger"
								text
								v-tooltip.top="'Remove this finished-colour recipe'"
								@click="removeColourYarnGroup(group)"
							/>
						</div>
						<div class="recipe-yarn-head" aria-hidden="true">
							<span>Yarn Item</span><span>Blend Share %</span><span></span>
						</div>
						<div v-for="(row, rowIndex) in group.rows" :key="row.name || rowIndex" class="recipe-yarn-row">
							<LinkField
								:modelValue="row.yarn_item || ''"
								target-doctype="Item"
								placeholder="Select yarn item"
								@update:modelValue="(v) => (row.yarn_item = v || '')"
							/>
							<InputNumber
								v-model="row.ratio"
								:min="0"
								:max="100"
								:maxFractionDigits="3"
								suffix="%"
								fluid
							/>
							<Button
								icon="pi pi-trash"
								severity="danger"
								text
								:disabled="group.rows.length === 1"
								@click="removeColourYarnFromGroup(group, rowIndex)"
							/>
						</div>
						<Button
							label="Add Yarn"
							icon="pi pi-plus"
							severity="secondary"
							size="small"
							text
							@click="addColourYarnToGroup(group)"
						/>
					</div>
					<Button label="Add Finished Colour" icon="pi pi-plus" severity="secondary" text @click="addColourYarnGroup" />
				</div>
				<div v-else-if="colourYarnRows.length" class="recipe-view">
					<div v-for="group in colourYarnGroups" :key="group.key" class="recipe-card">
						<div class="recipe-card__title">
							<span>
								{{ group.colour }}
							</span>
							<span>{{ group.total }}%</span>
						</div>
						<div v-for="row in group.rows" :key="row.name || row.yarn_item" class="yarn-ratio-view-row">
							<span class="pv">{{ row.yarn_item }}</span>
							<strong>{{ Number(row.ratio || 0) }}%</strong>
						</div>
					</div>
				</div>
				<div v-else class="panel-empty">No colour-wise yarn recipe maintained.</div>
			</section>

			<!-- ── Details (Desk Item Details tab plain fields, Desk order:
			     tech_pack_version, pattern_version, approved_by; item/primary/
			     dependent live in the header facts; entry stays IN the tab —
			     the flat "Edit fields" list is no longer the IPD entry path). ── -->
			<section class="panel">
				<div class="panel-head">
					<h3>Details</h3>
				</div>
				<div class="hdr-facts">
					<div class="pf">
						<span class="pl">Tech pack version</span>
						<input v-if="editing" v-model="hdrForm.tech_pack_version" class="hdr-text" data-testid="hdr-techpack" />
						<span v-else class="pv">{{ doc.tech_pack_version || "—" }}</span>
					</div>
					<div class="pf">
						<span class="pl">Pattern version</span>
						<input v-if="editing" v-model="hdrForm.pattern_version" class="hdr-text" data-testid="hdr-pattern" />
						<span v-else class="pv">{{ doc.pattern_version || "—" }}</span>
					</div>
					<div class="pf">
						<span class="pl">Approved by</span>
						<span class="pv">{{ doc.approved_by || "—" }}</span>
					</div>
				</div>
			</section>

			<!-- ── Item Attributes (mirrors the Desk AttributeList) ── -->
			<section class="panel">
				<div class="panel-head">
					<h3>Item Attributes</h3>
					<span class="panel-meta">
						{{ itemAttrCards.length }} attribute(s)
						<span v-if="itemAttrLoading"> · loading…</span>
						<span v-else-if="doc.is_cloth_item"> · generated from the cloth routes above</span>
					</span>
				</div>
				<div v-if="!itemAttrCards.length" class="panel-empty">
					No attributes on this IPD.
				</div>
				<div v-else class="ipd-attr-grid">
					<div
						v-for="(card, idx) in itemAttrCards"
						:key="card.attr_name"
						class="ipd-attr-card"
						:class="{ editing: editingAttrIdx === idx }"
					>
						<div class="ipd-attr-head">
							<span class="ipd-attr-title">{{ card.attr_name }}</span>
							<Button
								v-if="!doc.is_cloth_item && editableDoc && editingAttrIdx !== idx && card.mapping"
								icon="pi pi-pencil"
								text
								rounded
								size="small"
								class="ipd-attr-edit-btn"
								v-tooltip.top="'Edit values'"
								@click="enterAttrEdit(idx)"
							/>
						</div>
						<!-- VIEW: chips -->
						<template v-if="editingAttrIdx !== idx">
							<div v-if="card.values.length" class="ipd-chip-row">
								<span
									v-for="v in card.values"
									:key="v"
									class="ipd-attr-chip"
								>{{ v }}</span>
							</div>
							<div v-else class="ipd-attr-empty">No values configured.</div>
						</template>
						<!-- EDIT: removable chips + add input -->
						<template v-else>
							<div class="ipd-chip-row">
								<span
									v-for="(v, i) in attrDraftValues"
									:key="'d-' + i"
									class="ipd-attr-chip removable"
								>
									{{ v }}
									<button
										class="ipd-chip-x"
										type="button"
										@click="removeAttrAt(i)"
									>×</button>
								</span>
								<span v-if="!attrDraftValues.length" class="ipd-attr-empty">
									No values — add one below.
								</span>
							</div>
							<div class="ipd-add-row">
								<AutoComplete
									v-model="attrNewValue"
									:suggestions="attrValueSuggestions"
									@complete="onAttrNewComplete(card, $event)"
									@item-select="addAttrValue"
									@keydown.enter="addAttrValue"
									placeholder="Pick or type new value…"
									dropdown
									completeOnFocus
									class="ipd-add-input"
									fluid
								/>
								<Button
									label="Add"
									icon="pi pi-plus"
									size="small"
									severity="secondary"
									outlined
									:disabled="!String(attrNewValue || '').trim()"
									@click="addAttrValue"
								/>
							</div>
							<div class="ipd-edit-actions">
								<Button
									label="Cancel"
									icon="pi pi-times"
									size="small"
									severity="secondary"
									outlined
									:disabled="attrSaving"
									@click="cancelAttrEdit"
								/>
								<Button
									label="Save"
									icon="pi pi-check"
									size="small"
									:loading="attrSaving"
									@click="saveAttrCard(card)"
								/>
							</div>
						</template>
					</div>
				</div>
			</section>

			<!-- ── Item BOM ── -->
			<section class="panel">
				<div class="panel-head">
					<h3>Item BOM</h3>
					<span class="panel-meta">{{ (doc.item_bom || []).length }} row(s)</span>
					<!-- Instant-CRUD editors (attribute pencil, BOM rows, process rows)
					     save immediately and sit OUTSIDE the global edit transaction;
					     their affordances still respect the same Approved/canWrite gate. -->
					<Button
						v-if="editableDoc && bomFormMode === 'off'"
						label="Add row"
						icon="pi pi-plus"
						size="small"
						severity="secondary"
						outlined
						class="panel-add-btn"
						@click="openAddBom"
					/>
				</div>
				<DataTable :value="doc.item_bom || []" class="esd-table cfg-dt" :rowHover="false" dataKey="name">
					<Column field="item" header="Item">
						<template #body="{ data }">
							<a class="cell-link esd-mono" @click="navigateDoc('Item', data.item)">{{ data.item || "—" }}</a>
						</template>
					</Column>
					<Column field="qty_of_product" header="Qty of Product">
						<template #body="{ data }">{{ fmtNum(data.qty_of_product) }}</template>
					</Column>
					<Column field="qty_of_bom_item" header="Qty of BOM Item">
						<template #body="{ data }">{{ fmtNum(data.qty_of_bom_item) }}</template>
					</Column>
					<Column field="uom" header="UOM">
						<template #body="{ data }">{{ data.uom || "—" }}</template>
					</Column>
					<Column field="process_name" header="Process">
						<template #body="{ data }">{{ data.process_name || "—" }}</template>
					</Column>
					<Column v-if="doc.dependent_attribute" field="dependent_attribute_value" :header="doc.dependent_attribute">
						<template #body="{ data }">{{ data.dependent_attribute_value || "—" }}</template>
					</Column>
					<Column header="Mapping">
						<template #body="{ data }">
							<Tag
								v-if="data.based_on_attribute_mapping"
								value="Attribute-mapped"
								severity="primary"
								icon="pi pi-sitemap"
								rounded
							/>
							<span v-else class="muted-dash">Flat qty</span>
						</template>
					</Column>
					<Column header="" :style="{ width: '280px' }">
						<template #body="{ data, index }">
							<div class="row-actions">
								<Button
									v-if="data.based_on_attribute_mapping"
									:label="data.attribute_mapping ? 'Open mapping' : 'Configure mapping'"
									icon="pi pi-arrow-up-right"
									size="small"
									text
									@click="openMapping(data)"
								/>
								<Button
									v-if="editableDoc"
									icon="pi pi-pencil"
									size="small"
									text
									severity="secondary"
									v-tooltip.top="'Edit row'"
									:disabled="bomFormMode !== 'off'"
									@click="openEditBom(index)"
								/>
								<Button
									v-if="editableDoc"
									icon="pi pi-trash"
									size="small"
									text
									severity="danger"
									v-tooltip.top="'Delete row'"
									:disabled="bomFormMode !== 'off'"
									@click="deleteBomRow(index)"
								/>
							</div>
						</template>
					</Column>
					<template #empty>
						<div class="esd-empty">
							<i class="pi pi-table" />
							<p class="esd-empty__text">No BOM rows.</p>
						</div>
					</template>
				</DataTable>

				<!-- Inline add/edit form for Item BOM -->
				<div v-if="bomFormMode !== 'off'" class="add-row-form">
					<div class="form-title">
						<i :class="bomFormMode === 'edit' ? 'pi pi-pencil' : 'pi pi-plus'" />
						{{ bomFormMode === 'edit' ? `Edit BOM row #${editingBomIdx + 1}` : "Add BOM row" }}
					</div>
					<div class="form-grid">
						<div class="form-field">
							<label>Item *</label>
							<AutoComplete
								v-model="bomDraft.item"
								:suggestions="bomItemSuggestions"
								@complete="onBomItemComplete($event)"
								@item-select="onBomItemPick($event)"
								placeholder="Search Item…"
								dropdown
								completeOnFocus
								fluid
							/>
						</div>
						<div class="form-field">
							<label>Qty of Product *</label>
							<InputNumber
								v-model="bomDraft.qty_of_product"
								:minFractionDigits="0"
								:maxFractionDigits="3"
								fluid
							/>
						</div>
						<div class="form-field">
							<label>Qty of BOM Item *</label>
							<InputNumber
								v-model="bomDraft.qty_of_bom_item"
								:minFractionDigits="0"
								:maxFractionDigits="3"
								fluid
							/>
						</div>
						<div class="form-field">
							<label>UOM</label>
							<InputText
								v-model="bomDraft.uom"
								readonly
								placeholder="Auto from item"
								fluid
							/>
							<small class="field-hint">Fetched from the item's default UOM.</small>
						</div>
						<div class="form-field">
							<label>Process</label>
							<AutoComplete
								v-model="bomDraft.process_name"
								:suggestions="processSuggestions"
								@complete="onProcessComplete($event)"
								placeholder="Search Process…"
								dropdown
								completeOnFocus
								fluid
							/>
						</div>
						<div v-if="doc.dependent_attribute" class="form-field">
							<label>{{ doc.dependent_attribute }} *</label>
							<AutoComplete
								v-model="bomDraft.dependent_attribute_value"
								:suggestions="depAttrValueSuggestions"
								@complete="onDepAttrValueComplete($event)"
								:placeholder="`Select ${doc.dependent_attribute}…`"
								dropdown
								completeOnFocus
								fluid
							/>
							<small class="field-hint">Stage at which this BOM item is consumed.</small>
						</div>
						<div class="form-field toggle-field">
							<label>Based on Attribute Mapping</label>
							<ToggleSwitch
								:modelValue="!!bomDraft.based_on_attribute_mapping"
								@update:modelValue="bomDraft.based_on_attribute_mapping = $event ? 1 : 0"
							/>
						</div>
					</div>
					<div class="add-row-actions">
						<Button
							label="Cancel"
							icon="pi pi-times"
							size="small"
							severity="secondary"
							outlined
							:disabled="bomSaving"
							@click="cancelAddBom"
						/>
						<Button
							:label="bomFormMode === 'edit' ? 'Save changes' : 'Add row'"
							icon="pi pi-check"
							size="small"
							:loading="bomSaving"
							@click="saveBomRow"
						/>
					</div>
				</div>
			</section>

			<!-- ── IPD Processes ── -->
			<section class="panel">
				<div class="panel-head">
					<h3>IPD Processes</h3>
					<span class="panel-meta">{{ (doc.ipd_processes || []).length }} process(es)</span>
					<Button
						v-if="editableDoc && processFormMode === 'off'"
						label="Add row"
						icon="pi pi-plus"
						size="small"
						severity="secondary"
						outlined
						class="panel-add-btn"
						@click="openAddProcess"
					/>
				</div>
				<DataTable :value="doc.ipd_processes || []" class="esd-table cfg-dt" :rowHover="false" dataKey="name">
					<Column field="process_name" header="Process">
						<template #body="{ data }">
							<span class="strong">{{ data.process_name || "—" }}</span>
						</template>
					</Column>
					<Column field="in_stage" header="In Stage">
						<template #body="{ data }">{{ data.in_stage || "—" }}</template>
					</Column>
					<Column field="out_stage" header="Out Stage">
						<template #body="{ data }">{{ data.out_stage || "—" }}</template>
					</Column>
					<Column header="" :style="{ width: '340px' }">
						<template #body="{ data, index }">
							<div class="row-actions">
								<Button
									label="Configure combinations"
									icon="pi pi-sliders-h"
									size="small"
									:loading="configuring === data.process_name"
									:disabled="!data.process_name || !!configuring"
									@click="configureCombinations(data)"
								/>
								<Button
									v-if="editableDoc"
									icon="pi pi-pencil"
									size="small"
									text
									severity="secondary"
									v-tooltip.top="'Edit row'"
									:disabled="processFormMode !== 'off'"
									@click="openEditProcess(index)"
								/>
								<Button
									v-if="editableDoc"
									icon="pi pi-trash"
									size="small"
									text
									severity="danger"
									v-tooltip.top="'Delete row'"
									:disabled="processFormMode !== 'off'"
									@click="deleteProcessRow(index)"
								/>
							</div>
						</template>
					</Column>
					<template #empty>
						<div class="esd-empty">
							<i class="pi pi-cog" />
							<p class="esd-empty__text">No processes defined.</p>
						</div>
					</template>
				</DataTable>

				<!-- Inline add/edit form for IPD Processes -->
				<div v-if="processFormMode !== 'off'" class="add-row-form">
					<div class="form-title">
						<i :class="processFormMode === 'edit' ? 'pi pi-pencil' : 'pi pi-plus'" />
						{{ processFormMode === 'edit' ? `Edit process row #${editingProcessIdx + 1}` : "Add process row" }}
					</div>
					<div class="form-grid">
						<div class="form-field">
							<label>Process *</label>
							<AutoComplete
								v-model="processDraft.process_name"
								:suggestions="processSuggestions"
								@complete="onProcessComplete($event)"
								placeholder="Search Process…"
								dropdown
								completeOnFocus
								fluid
							/>
						</div>
						<div class="form-field">
							<label>In Stage</label>
							<AutoComplete
								v-model="processDraft.in_stage"
								:suggestions="stageSuggestions"
								@complete="onStageComplete($event)"
								placeholder="Pick stage…"
								dropdown
								completeOnFocus
								fluid
							/>
						</div>
						<div class="form-field">
							<label>Out Stage</label>
							<AutoComplete
								v-model="processDraft.out_stage"
								:suggestions="stageSuggestions"
								@complete="onStageComplete($event)"
								placeholder="Pick stage…"
								dropdown
								completeOnFocus
								fluid
							/>
						</div>
					</div>
					<div class="add-row-actions">
						<Button
							label="Cancel"
							icon="pi pi-times"
							size="small"
							severity="secondary"
							outlined
							:disabled="processSaving"
							@click="cancelAddProcess"
						/>
						<Button
							:label="processFormMode === 'edit' ? 'Save changes' : 'Add row'"
							icon="pi pi-check"
							size="small"
							:loading="processSaving"
							@click="saveProcessRow"
						/>
					</div>
				</div>
			</section>

			<!-- ── Process Matrices ── -->
			<section class="panel">
				<div class="panel-head">
					<h3>Process Matrices</h3>
					<span class="panel-meta">
						<i v-if="matricesLoading" class="pi pi-spin pi-spinner" />
						<template v-else>{{ matrices.length }} matri{{ matrices.length === 1 ? "x" : "ces" }}</template>
					</span>
				</div>
				<div v-if="doc.is_cloth_item" class="matrix-route-summary">
					<span>
						<strong>{{ doc.item }}</strong>: Knitting creates one matrix for every finished Colour × Dia route.
					</span>
					<div class="matrix-counts">
						<span v-for="row in matrixProcessCounts" :key="row.process">
							{{ row.process }} <strong>{{ row.count }}</strong>
						</span>
					</div>
				</div>
				<DataTable :value="matrices" class="esd-table cfg-dt" :rowHover="false" dataKey="name" :loading="matricesLoading">
					<Column field="name" header="Matrix">
						<template #body="{ data }"><span class="esd-mono">{{ data.name }}</span></template>
					</Column>
					<Column field="process_name" header="Process">
						<template #body="{ data }">{{ data.process_name || "—" }}</template>
					</Column>
					<Column field="reference_item_variant" header="Reference Variant">
						<template #body="{ data }">
							<span class="esd-mono" v-if="data.reference_item_variant">{{ data.reference_item_variant }}</span>
							<span v-else class="muted-dash">Generic</span>
						</template>
					</Column>
					<Column v-if="doc.is_cloth_item" header="Input">
						<template #body="{ data }">{{ matrixInputLabel(data) }}</template>
					</Column>
					<Column header="" :style="{ width: '110px' }">
						<template #body="{ data }">
							<Button label="Open" icon="pi pi-arrow-right" iconPos="right" size="small" text @click="openMatrix(data.name)" />
						</template>
					</Column>
					<template #empty>
						<div class="esd-empty">
							<i class="pi pi-sitemap" />
							<p class="esd-empty__text">No process matrices for this IPD yet. Use “Configure combinations” above.</p>
						</div>
					</template>
				</DataTable>
			</section>
					</TabPanel>

					<!-- Fabric Processes tab (cloth IPDs only). Master-detail entry
					     over the fabric_processes + fabric_value_mappings sibling
					     tables; matrices regenerate server-side on save, so a save
					     reloads this whole view. -->
					<TabPanel v-if="doc.is_cloth_item" value="fabric" class="ipd-tabpanel">
						<FabricProcessesSection
							:doc="doc"
							:disabled="editing"
							@saved="load"
						/>
					</TabPanel>

					<TabPanel v-if="doc.is_cloth_item" value="compacting" class="ipd-tabpanel">
						<section class="panel">
							<div class="panel-head">
								<h3>Compacting Details</h3>
								<span class="panel-meta">Data only · no matrix, calculation, or Work Order</span>
							</div>
							<div class="recipe-help">
								Choose how colours share a compacting Dia, prepare the rows, then enter only the
								compacting Dia. The available colours and input Dias come from Fabric Processes.
							</div>
							<div v-if="editing || editableDoc" class="compacting-generator">
								<div class="compacting-generator__field">
									<label>Generation Scope</label>
									<Select
										v-model="compactingGenerationMode"
										:options="compactingGenerationModes"
										optionLabel="label"
										optionValue="value"
										fluid
									/>
								</div>
								<div
									v-if="compactingGenerationMode === 'group'"
									class="compacting-generator__field compacting-generator__colours"
								>
									<label>Colour Group</label>
									<MultiSelect
										v-model="compactingSelectedColours"
										:options="compactingAvailableColours"
										display="chip"
										filter
										placeholder="Select colours"
										fluid
									/>
								</div>
								<Button
									label="Prepare Dia Entries"
									icon="pi pi-list"
									severity="secondary"
									outlined
									@click="generateCompactingWithEdit"
								/>
							</div>
							<div v-if="editing" class="compacting-list">
								<div
									v-if="compactingGenerationMode === 'group' && compactingSelectedColours.length"
									class="compacting-group-summary"
								>
									<span>Selected colour group</span>
									<div>
										<strong v-for="colour in compactingSelectedColours" :key="colour">{{ colour }}</strong>
									</div>
								</div>
								<div v-if="compactingDisplayRows.length" class="compacting-simple-table">
									<div
										class="compacting-simple-head"
										:class="{ 'is-separate': compactingGenerationMode === 'separate' }"
										aria-hidden="true"
									>
										<span>Knitting / Input Dia</span>
										<span v-if="compactingGenerationMode === 'separate'">Colour</span>
										<span>Compacting Dia</span>
										<span v-if="compactingGenerationMode === 'separate'"></span>
									</div>
									<div
										v-for="entry in compactingDisplayRows"
										:key="entry.key"
										class="compacting-simple-row"
										:class="{
											'is-separate': compactingGenerationMode === 'separate',
											'compacting-row--invalid': compactingEntryInvalid(entry),
										}"
									>
										<div class="compacting-simple-value">
											<small>Knitting / Input Dia</small>
											<strong>{{ entry.input_dia || "—" }}</strong>
										</div>
										<div
											v-if="compactingGenerationMode === 'separate'"
											class="compacting-simple-value"
										>
											<small>Colour</small>
											<strong>{{ entry.row.colour }}</strong>
										</div>
										<div class="compacting-simple-field">
											<small>Compacting Dia</small>
											<LinkField
												:modelValue="compactingEntryOutput(entry)"
												target-doctype="Item Attribute Value"
												:search-handler="searchDia"
												:forceSelection="true"
												:invalid="compactingEntryInvalid(entry)"
												placeholder="Select compacting Dia"
												@update:modelValue="(v) => updateCompactingEntry(entry, v)"
											/>
										</div>
										<Button
											v-if="compactingGenerationMode === 'separate'"
											icon="pi pi-times"
											severity="danger"
											text
											rounded
											:aria-label="`Remove ${entry.row.colour} / ${entry.input_dia}`"
											v-tooltip.top="`Remove ${entry.row.colour} / ${entry.input_dia}`"
											@click="removeCompactingRowObject(entry.row)"
										/>
										<small v-if="compactingEntryInvalid(entry)" class="compacting-row-error">
											Select a valid Compacting Dia for {{ compactingEntryLabel(entry) }}.
										</small>
									</div>
								</div>
								<div v-else class="panel-empty">
									Choose a generation scope above, then click Generate Combinations.
								</div>
							</div>
							<div v-else-if="compactingRows.length" class="compacting-view">
								<div v-for="row in compactingRows" :key="row.name || `${row.colour}-${row.input_dia}`" class="compacting-view-row">
									<strong>{{ row.colour || "All Colours" }}</strong>
									<span>{{ row.input_dia }} → {{ row.compacting_dia }}</span>
									<small v-if="row.notes">{{ row.notes }}</small>
								</div>
							</div>
							<div v-else class="panel-empty">No Compacting Details maintained.</div>
						</section>
					</TabPanel>

					<!-- Garment tabs (phases 1+2, 2026-07-10): Desk-parity sections.
					     `editing` is the DOCUMENT-level edit mode owned by this view;
					     each section exposes validate()/apply(ipd) and the header's
					     single Save persists every tab in one request. -->
					<TabPanel v-if="!doc.is_cloth_item" value="packing" class="ipd-tabpanel">
						<PackingSection ref="packingRef" :doc="doc" :editing="editing" />
					</TabPanel>
					<TabPanel v-if="!doc.is_cloth_item && doc.packing_attribute" value="setitem" class="ipd-tabpanel">
						<SetItemSection ref="setItemRef" :doc="doc" :editing="editing" />
					</TabPanel>
					<TabPanel v-if="!doc.is_cloth_item" value="stiching" class="ipd-tabpanel">
						<StichingSection ref="stichingRef" :doc="doc" :editing="editing" />
					</TabPanel>
					<TabPanel v-if="!doc.is_cloth_item" value="emblishment" class="ipd-tabpanel">
						<EmblishmentSection ref="emblishmentRef" :doc="doc" :editing="editing" />
					</TabPanel>
					<TabPanel v-if="!doc.is_cloth_item" value="cutting" class="ipd-tabpanel">
						<CuttingSection ref="cuttingRef" :doc="doc" :editing="editing" />
					</TabPanel>
					<TabPanel v-if="!doc.is_cloth_item" value="accessory" class="ipd-tabpanel">
						<ClothAccessorySection ref="accessoryRef" :doc="doc" :editing="editing" />
					</TabPanel>
					<TabPanel v-if="!doc.is_cloth_item" value="advanced" class="ipd-tabpanel">
						<AdvanceSettingsSection ref="advanceRef" :doc="doc" :editing="editing" />
					</TabPanel>
				</TabPanels>
			</Tabs>
		</template>

		<Dialog
			v-model:visible="duplicateOpen"
			modal
			header="Duplicate IPD"
			:style="{ width: 'min(520px, calc(100vw - 32px))' }"
		>
			<div class="duplicate-form">
				<label for="duplicate-ipd-item">Item</label>
				<LinkField
					id="duplicate-ipd-item"
					:model-value="duplicateItem"
					target-doctype="Item"
					:filters="duplicateItemFilters"
					placeholder="Select item"
					@update:model-value="duplicateItem = $event || ''"
				/>
			</div>
			<template #footer>
				<Button label="Cancel" severity="secondary" text :disabled="duplicating" @click="duplicateOpen = false" />
				<Button
					label="Duplicate"
					icon="pi pi-copy"
					:disabled="!duplicateItem"
					:loading="duplicating"
					data-testid="ipd-duplicate-confirm"
					@click="onDuplicate"
				/>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from "vue"
import { useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router"
import "../ipd/ipd-sections.css"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import AutoComplete from "primevue/autocomplete"
import InputNumber from "primevue/inputnumber"
import ToggleSwitch from "primevue/toggleswitch"
import Select from "primevue/select"
import MultiSelect from "primevue/multiselect"
import Tag from "primevue/tag"
import Message from "primevue/message"
import Dialog from "primevue/dialog"
import Tooltip from "primevue/tooltip"
import Tabs from "primevue/tabs"
import TabList from "primevue/tablist"
import Tab from "primevue/tab"
import TabPanels from "primevue/tabpanels"
import TabPanel from "primevue/tabpanel"
import LinkField from "@/components/LinkField.vue"
import FabricProcessesSection from "@/views/fabric/FabricProcessesSection.vue"
import PackingSection from "@/views/ipd/PackingSection.vue"
import SetItemSection from "@/views/ipd/SetItemSection.vue"
import StichingSection from "@/views/ipd/StichingSection.vue"
import EmblishmentSection from "@/views/ipd/EmblishmentSection.vue"
import CuttingSection from "@/views/ipd/CuttingSection.vue"
import ClothAccessorySection from "@/views/ipd/ClothAccessorySection.vue"
import AdvanceSettingsSection from "@/views/ipd/AdvanceSettingsSection.vue"
import { getDoc, getList, deleteDoc, callMethod, searchLink } from "@/api/client"
import { useAppToast } from "@/composables/useToast"
import { useAppConfirm } from "@/composables/useConfirm"
import { usePermissions } from "@/composables/usePermissions"
import { getRegistryByDoctype } from "@/config/doctypes"

// Local directive registration (components import their own deps in this app).
const vTooltip = Tooltip

const props = defineProps({
	id: { type: String, required: true },
})

const router = useRouter()
const toast = useAppToast()
const confirm = useAppConfirm()
const { canCreate, canDelete, canWrite, isAdmin, hasRole } = usePermissions()
const deleting = ref(false)
const approvalBusy = ref(false)
const approvalRoles = ref([])
const duplicateOpen = ref(false)
const duplicateItem = ref("")
const duplicateItemGroups = ref([])
const duplicating = ref(false)

const doc = ref(null)
const loading = ref(false)
const error = ref(null)
const matrices = ref([])
const matricesLoading = ref(false)
// Tabbed shell (2026-07-09). "details" is always present; "fabric" only for
// cloth IPDs. Reset to "details" on every (re)load so a cloth→garment switch
// never strands the user on a now-absent Fabric Processes tab.
const activeTab = ref("details")
const colourYarnRows = ref([])
const fabricRouteRows = ref([])
const compactingRows = ref([])
const compactingGenerationMode = ref("all")
const compactingSelectedColours = ref([])
const compactingInvalidRows = ref(new Set())
const compactingGenerationModes = [
	{ label: "Same Dia for All Colours", value: "all" },
	{ label: "Each Colour Separately", value: "separate" },
	{ label: "Selected Colour Group", value: "group" },
]
const compactingAvailableColours = computed(() =>
	[...new Set(
		compactingRoutePairs()
			.map((row) => row.colour)
			.filter(Boolean),
	)].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true })),
)
const compactingDisplayRows = computed(() => {
	let rows = compactingRows.value
	if (compactingGenerationMode.value === "all") {
		rows = rows.filter((row) => !row.colour)
	} else {
		rows = rows.filter((row) => Boolean(row.colour))
		if (compactingGenerationMode.value === "group") {
			const selected = new Set(compactingSelectedColours.value)
			rows = rows.filter((row) => selected.has(row.colour))
		}
	}

	const sorted = [...rows].sort(
		(a, b) =>
			String(a.input_dia || "").localeCompare(String(b.input_dia || ""), undefined, { numeric: true }) ||
			String(a.colour || "").localeCompare(String(b.colour || ""), undefined, { numeric: true }),
	)
	if (compactingGenerationMode.value !== "group") {
		return sorted.map((row) => ({
			key: row.name || `${row.colour || "__all__"}-${row.input_dia}`,
			input_dia: row.input_dia || "",
			row,
			rows: [row],
		}))
	}

	const groups = new Map()
	for (const row of sorted) {
		const dia = row.input_dia || ""
		if (!groups.has(dia)) groups.set(dia, [])
		groups.get(dia).push(row)
	}
	return [...groups.entries()].map(([input_dia, groupedRows]) => ({
		key: `group-${input_dia}`,
		input_dia,
		row: groupedRows[0],
		rows: groupedRows,
	}))
})
const matrixProcessCounts = computed(() => {
	const counts = new Map()
	for (const row of matrices.value) {
		const process = row.process_name || "Unspecified"
		counts.set(process, (counts.get(process) || 0) + 1)
	}
	return [...counts.entries()].map(([process, count]) => ({ process, count }))
})
const colourYarnGroups = computed(() => {
	const groups = {}
	for (const row of colourYarnRows.value) {
		const key = `${row.cloth_item || ""}\u0000${row.colour || ""}`
		if (!groups[key]) {
			groups[key] = {
				cloth_item: row.cloth_item || "",
				colour: row.colour || "",
				rows: [],
				total: 0,
			}
		}
		groups[key].rows.push(row)
		groups[key].total = Math.round(
			(groups[key].total + (Number(row.ratio) || 0)) * 1000,
		) / 1000
	}
	return Object.entries(groups).map(([key, group]) => ({
		...group,
		key,
		routes: fabricRouteRows.value.filter(
			(route) => route.finished_colour === group.colour,
		),
	}))
})
// ── DOCUMENT-level edit mode (2026-07-10, user mandate) ─────────────────────
// ONE Edit puts every tab into edit mode, ONE Save collects every section's
// payload into a single frappe.client.save (one staleness guard, one server
// validate), ONE Cancel reverts all sections. The garment sections expose
// validate() + apply(ipd); the Details panel's two plain fields live here.
// The Fabric Processes section (cloth) keeps its own step editor — its save
// regenerates matrices server-side and was approved as-is; the global mode
// still governs the Details panel for cloth IPDs.
const editing = ref(false)
const savingAll = ref(false)
const hdrForm = ref({ tech_pack_version: "", pattern_version: "" })
const editableDoc = computed(
	() => doc.value?.approval_status !== "Approved" && canWrite("Item Production Detail"),
)
const canApprove = computed(
	() =>
		doc.value?.approval_status !== "Approved" &&
		(isAdmin.value || approvalRoles.value.some((role) => hasRole(role))),
)
const canRevertApproval = computed(
	() =>
		doc.value?.approval_status &&
		doc.value.approval_status !== "Not Approved" &&
		(isAdmin.value || approvalRoles.value.some((role) => hasRole(role))),
)
const duplicateItemFilters = computed(() =>
	duplicateItemGroups.value.length ? { item_group: ["in", duplicateItemGroups.value] } : { disabled: 0 },
)
const packingRef = ref(null)
const setItemRef = ref(null)
const stichingRef = ref(null)
const emblishmentRef = ref(null)
const cuttingRef = ref(null)
const accessoryRef = ref(null)
const advanceRef = ref(null)

function hdrHydrate() {
	hdrForm.value = {
		tech_pack_version: doc.value?.tech_pack_version || "",
		pattern_version: doc.value?.pattern_version || "",
	}
	colourYarnRows.value = (doc.value?.colour_yarn_recipes || []).map((row) => ({
		...row,
		ratio: Number(row.ratio) || 0,
	}))
	fabricRouteRows.value = (doc.value?.fabric_routes || []).map((row) => ({
		...row,
	}))
	compactingRows.value = (doc.value?.compacting_reference_details || []).map((row) => ({
		...row,
		colour_specific: Boolean(row.colour),
	}))
	compactingGenerationMode.value = compactingRows.value.some((row) => Boolean(row.colour))
		? "separate"
		: "all"
	compactingSelectedColours.value = []
	compactingInvalidRows.value = new Set()
}
function addColourYarnGroup() {
	if (colourYarnRows.value.some((row) => !row.colour)) {
		toast.warn("Complete the blank recipe", "Select its finished colour before adding another group.")
		return
	}
	colourYarnRows.value.push({
		doctype: "IPD Colour Yarn Ratio",
		cloth_item: doc.value?.is_cloth_item ? doc.value.item : "",
		colour: "",
		yarn_item: "",
		ratio: 100,
	})
}
function addColourYarnToGroup(group) {
	const splitEvenly = group.rows.length === 1 && Number(group.rows[0].ratio) === 100
	if (splitEvenly) group.rows[0].ratio = 50
	colourYarnRows.value.push({
		doctype: "IPD Colour Yarn Ratio",
		cloth_item: doc.value?.item || "",
		colour: group.colour,
		yarn_item: "",
		ratio: splitEvenly ? 50 : 0,
	})
}
function setRecipeGroupColour(group, value) {
	const colour = value || ""
	for (const row of group.rows) {
		row.cloth_item = doc.value?.item || ""
		row.colour = colour
	}
	for (const route of group.routes || []) {
		route.finished_colour = colour
	}
}
function removeColourYarnFromGroup(group, rowIndex) {
	if (group.rows.length === 1) return
	const target = group.rows[rowIndex]
	const index = colourYarnRows.value.indexOf(target)
	if (index >= 0) colourYarnRows.value.splice(index, 1)
}
function removeColourYarnGroup(group) {
	const rows = new Set(group.rows)
	colourYarnRows.value = colourYarnRows.value.filter((row) => !rows.has(row))
	const routes = new Set(group.routes || [])
	fabricRouteRows.value = fabricRouteRows.value.filter(
		(row) => !routes.has(row),
	)
}
function removeCompactingRowObject(row) {
	const index = compactingRows.value.indexOf(row)
	if (index >= 0) compactingRows.value.splice(index, 1)
	clearCompactingRowError(row)
}
function compactingRoutePairs() {
	const seen = new Set()
	const pairs = []
	const addPair = (colour, dia) => {
		if (!colour || !dia) return
		const key = `${colour}\u0000${dia}`
		if (seen.has(key)) return
		seen.add(key)
		pairs.push({ colour, input_dia: dia })
	}
	for (const route of fabricRouteRows.value) {
		addPair(route.finished_colour || "", route.finished_dia || "")
	}
	if (!pairs.length) {
		const mappings = doc.value?.fabric_value_mappings || []
		const introducedDias = [...new Set(
			mappings
				.filter((row) => row.attribute === "Dia" && row.role === "Introduce")
				.map((row) => row.to_value)
				.filter(Boolean),
		)]
		const groups = new Map()
		for (const row of mappings) {
			const key = `${row.sequence || 0}\u0000${row.mapping_index || 0}`
			if (!groups.has(key)) groups.set(key, [])
			groups.get(key).push(row)
		}
		for (const rows of groups.values()) {
			const colourEntry = rows.find(
				(row) => row.attribute === "Colour" && ["Change", "Introduce"].includes(row.role),
			)
			const diaEntry = rows.find(
				(row) => row.attribute === "Dia" && ["Change", "Pin", "Introduce"].includes(row.role),
			)
			const colour = colourEntry?.to_value || colourEntry?.from_value || ""
			const dia = diaEntry?.to_value || diaEntry?.from_value || ""
			if (colour && dia) addPair(colour, dia)
			else if (colour) introducedDias.forEach((value) => addPair(colour, value))
		}
		if (!pairs.length) {
			const recipeColours = [...new Set(
				colourYarnRows.value.map((row) => row.colour).filter(Boolean),
			)]
			recipeColours.forEach((colour) => {
				introducedDias.forEach((dia) => addPair(colour, dia))
			})
		}
	}
	return pairs.sort(
		(a, b) =>
			String(a.input_dia).localeCompare(String(b.input_dia), undefined, { numeric: true }) ||
			String(a.colour).localeCompare(String(b.colour), undefined, { numeric: true }),
	)
}
async function generateCompactingWithEdit() {
	if (!editing.value) {
		const mode = compactingGenerationMode.value
		const colours = [...compactingSelectedColours.value]
		enterEditAll()
		await nextTick()
		compactingGenerationMode.value = mode
		compactingSelectedColours.value = colours
	}
	generateCompactingCombinations()
}
function generateCompactingCombinations() {
	const routes = compactingRoutePairs()
	if (!routes.length) {
		toast.warn(
			"No Fabric Process combinations",
			"Maintain the cloth Colour + Dia combinations in Fabric Processes first, then generate Compacting combinations.",
		)
		return
	}
	let targets
	if (compactingGenerationMode.value === "all") {
		targets = [...new Set(routes.map((row) => row.input_dia))].map((input_dia) => ({
			colour: "",
			input_dia,
		}))
	} else if (compactingGenerationMode.value === "group") {
		const selected = new Set(compactingSelectedColours.value)
		if (!selected.size) {
			toast.warn("Select colours", "Choose at least one colour for the Compacting group.")
			return
		}
		targets = routes.filter((row) => selected.has(row.colour))
	} else {
		targets = routes
	}

	const targetKeys = new Set(
		targets.map((row) => `${row.colour || ""}\u0000${row.input_dia || ""}`),
	)
	// Scope switching may leave unsaved, empty generated placeholders behind.
	// Remove only those untouched placeholders; persisted or entered mappings
	// are preserved even when they are outside the currently selected scope.
	compactingRows.value = compactingRows.value.filter((row) => {
		const key = `${row.colour || ""}\u0000${row.input_dia || ""}`
		return (
			targetKeys.has(key) ||
			Boolean(row.name) ||
			Boolean(row.compacting_dia) ||
			Boolean(row.notes)
		)
	})
	const existing = new Set(
		compactingRows.value.map((row) => `${row.colour || ""}\u0000${row.input_dia || ""}`),
	)
	let added = 0
	for (const target of targets) {
		const key = `${target.colour || ""}\u0000${target.input_dia || ""}`
		if (existing.has(key)) continue
		existing.add(key)
		compactingRows.value.push({
			doctype: "IPD Compacting Reference",
			colour_specific: Boolean(target.colour),
			colour: target.colour || "",
			input_dia: target.input_dia,
			compacting_dia: "",
			notes: "",
		})
		added += 1
	}
	compactingRows.value.sort(
		(a, b) =>
			String(a.input_dia || "").localeCompare(String(b.input_dia || ""), undefined, { numeric: true }) ||
			String(a.colour || "").localeCompare(String(b.colour || ""), undefined, { numeric: true }),
	)
	if (added) {
		toast.success(
			"Compacting combinations generated",
			`${added} missing combination${added === 1 ? "" : "s"} added. Enter the compacting Dia.`,
		)
	} else {
		toast.info("Already complete", "Every combination in this scope is already present.")
	}
}
function clearCompactingRowError(row) {
	if (!compactingInvalidRows.value.has(row)) return
	const next = new Set(compactingInvalidRows.value)
	next.delete(row)
	compactingInvalidRows.value = next
}
function updateCompactingRow(row, field, value) {
	row[field] = value || ""
	clearCompactingRowError(row)
}
function compactingEntryOutput(entry) {
	const values = [...new Set(entry.rows.map((row) => row.compacting_dia).filter(Boolean))]
	return values.length === 1 ? values[0] : ""
}
function compactingEntryInvalid(entry) {
	return entry.rows.some((row) => compactingInvalidRows.value.has(row))
}
function compactingEntryLabel(entry) {
	if (compactingGenerationMode.value === "all") {
		return `All Colours / ${entry.input_dia || "Input Dia"}`
	}
	if (compactingGenerationMode.value === "group") {
		return `${compactingSelectedColours.value.join(", ")} / ${entry.input_dia || "Input Dia"}`
	}
	return `${entry.row.colour || "Colour"} / ${entry.input_dia || "Input Dia"}`
}
function updateCompactingEntry(entry, value) {
	const dia = value || ""
	for (const row of entry.rows) {
		row.compacting_dia = dia
		clearCompactingRowError(row)
	}
}
async function searchColour(query) {
	return searchLink("Item Attribute Value", query || "", { attribute_name: "Colour" })
}
async function searchDia(query) {
	return searchLink("Item Attribute Value", query || "", { attribute_name: "Dia" })
}
function detailsValidate() {
	if (doc.value?.is_cloth_item) {
		if (!colourYarnRows.value.length) {
			return "Add at least one finished-colour yarn recipe."
		}
		const recipeGroups = {}
		const recipeYarns = {}
		for (const [index, row] of colourYarnRows.value.entries()) {
			if (!row.cloth_item || !row.colour || !row.yarn_item) {
				return `Colour yarn row ${index + 1}: select Cloth, Colour, and Yarn.`
			}
			if (!(Number(row.ratio) > 0)) {
				return `Colour yarn row ${index + 1}: Ratio must be greater than zero.`
			}
			const group = `${row.cloth_item}\u0000${row.colour}`
			const yarnKey = `${group}\u0000${row.yarn_item}`
			if (recipeYarns[yarnKey]) {
				return `Colour yarn row ${index + 1}: duplicate Yarn ${row.yarn_item} in ${row.cloth_item} / ${row.colour}.`
			}
			recipeYarns[yarnKey] = true
			recipeGroups[group] = (recipeGroups[group] || 0) + Number(row.ratio)
		}
		for (const [group, total] of Object.entries(recipeGroups)) {
			if (Math.abs(total - 100) > 0.001) {
				const [cloth, colour] = group.split("\u0000")
				return `${cloth} / ${colour}: yarn recipe must total 100%. Current total is ${Math.round(total * 1000) / 1000}.`
			}
		}
		const recipeColours = new Set(
			colourYarnRows.value.map((row) => row.colour).filter(Boolean),
		)
		const routeKeys = new Set()
		for (const [index, route] of fabricRouteRows.value.entries()) {
			if (
				!route.finished_colour ||
				!route.finished_dia ||
				!route.knitting_output_colour ||
				!route.knitting_output_dia
			) {
				return `Fabric route ${index + 1}: select Finished Colour/Dia and Knitting Output Colour/Dia.`
			}
			if (!recipeColours.has(route.finished_colour)) {
				return `Fabric route ${index + 1}: add a yarn recipe for ${route.finished_colour}.`
			}
			const key = `${route.finished_colour}\u0000${route.finished_dia}`
			if (routeKeys.has(key)) {
				return `Fabric route ${index + 1}: duplicate ${route.finished_colour} / ${route.finished_dia}.`
			}
			routeKeys.add(key)
		}
	}
	return null
}
function compactingValidate() {
	compactingInvalidRows.value = new Set()
	for (const row of compactingRows.value) {
		const scope = row.colour || "All Colours"
		if (row.colour_specific && !row.colour) {
			compactingInvalidRows.value = new Set([row])
			nextTick(() => {
				document.querySelector(".compacting-row--invalid")?.scrollIntoView({
					behavior: "smooth",
					block: "center",
				})
			})
			return `${row.input_dia || "Input Dia not selected"}: select the separate Colour.`
		}
		if (!row.input_dia) {
			compactingInvalidRows.value = new Set([row])
			nextTick(() => {
				document.querySelector(".compacting-row--invalid")?.scrollIntoView({
					behavior: "smooth",
					block: "center",
				})
			})
			return `${scope}: select the Knitting/Input Dia.`
		}
		if (!row.compacting_dia) {
			compactingInvalidRows.value = new Set([row])
			nextTick(() => {
				document.querySelector(".compacting-row--invalid")?.scrollIntoView({
					behavior: "smooth",
					block: "center",
				})
			})
			return `${scope} / ${row.input_dia}: select the Compacting Dia.`
		}
	}
	return null
}
function hdrApply(ipd) {
	ipd.tech_pack_version = hdrForm.value.tech_pack_version || ""
	ipd.pattern_version = hdrForm.value.pattern_version || ""
	if (doc.value?.is_cloth_item) {
		const firstColour = colourYarnRows.value[0]?.colour || ""
		const firstRecipe = colourYarnRows.value.filter(
			(row) => row.colour === firstColour,
		)
		ipd.yarn_ratio_details = firstRecipe.map((row) => ({
			doctype: "IPD Yarn Ratio",
			yarn_item: row.yarn_item,
			ratio: Number(row.ratio) || 0,
		}))
		ipd.yarn_item = firstRecipe[0]?.yarn_item || null
	}
	if (doc.value?.is_cloth_item) {
		ipd.colour_yarn_recipes = colourYarnRows.value.map((row) => ({
			...row,
			doctype: "IPD Colour Yarn Ratio",
			cloth_item: row.cloth_item,
			colour: row.colour,
			yarn_item: row.yarn_item,
			ratio: Number(row.ratio) || 0,
		}))
		ipd.fabric_routes = fabricRouteRows.value.map((row) => ({
			...row,
			doctype: "IPD Fabric Route",
			finished_colour: row.finished_colour,
			finished_dia: row.finished_dia,
			knitting_output_colour: row.knitting_output_colour,
			knitting_output_dia: row.knitting_output_dia,
		}))
		ipd.compacting_reference_details = compactingRows.value.map((row) => ({
			...row,
			doctype: "IPD Compacting Reference",
			colour: row.colour,
			input_dia: row.input_dia,
			compacting_dia: row.compacting_dia,
			notes: row.notes || "",
		}))
	}
}
watch(
	() => editing.value,
	() => hdrHydrate(),
)

function enterEditAll() {
	hdrHydrate()
	editing.value = true
}
function cancelAll() {
	editing.value = false // sections rehydrate via their editing-prop watchers
	hdrHydrate()
}

async function loadApprovalRoles() {
	try {
		approvalRoles.value =
			(await callMethod("essdee_yrp.ipd_ui.get_approval_roles")) || ["System Manager"]
	} catch {
		approvalRoles.value = ["System Manager"]
	}
}
async function onApprove() {
	if (!doc.value || approvalBusy.value) return
	approvalBusy.value = true
	try {
		await callMethod("essdee_yrp.ipd_ui.approve_ipd", {
			doc_name: doc.value.name,
			approval_type: "Approved",
		})
		toast.success("Approved", "Item Production Detail approved")
		await load()
	} catch (e) {
		toast.error("Approval failed", e.message)
	} finally {
		approvalBusy.value = false
	}
}
function onRevertApproval() {
	if (!doc.value || approvalBusy.value) return
	confirm.require({
		header: "Revert approval?",
		message: "Revert this Item Production Detail to Not Approved?",
		icon: "pi pi-exclamation-triangle",
		acceptLabel: "Revert",
		acceptClass: "p-button-danger",
		rejectLabel: "Keep approved",
		accept: async () => {
			approvalBusy.value = true
			try {
				await callMethod("essdee_yrp.ipd_ui.revert_ipd_approval", {
					doc_name: doc.value.name,
				})
				toast.success("Reverted", "Approval returned to Not Approved")
				await load()
			} catch (e) {
				toast.error("Revert failed", e.message)
			} finally {
				approvalBusy.value = false
			}
		},
	})
}
async function openDuplicateDialog() {
	duplicateItem.value = doc.value?.item || ""
	duplicateOpen.value = true
	try {
		duplicateItemGroups.value =
			(await callMethod("essdee_yrp.ipd_ui.get_ipd_item_group")) || []
	} catch {
		duplicateItemGroups.value = []
	}
}
async function onDuplicate() {
	if (!doc.value || !duplicateItem.value || duplicating.value) return
	duplicating.value = true
	try {
		const name = await callMethod("essdee_yrp.ipd_ui.duplicate_ipd", {
			ipd: doc.value.name,
			item: duplicateItem.value,
		})
		duplicateOpen.value = false
		toast.success("Duplicated", `Created ${name}`)
		await router.push(`/item-production-detail/${encodeURIComponent(name)}`)
	} catch (e) {
		toast.error("Duplicate failed", e.message)
	} finally {
		duplicating.value = false
	}
}

// A validation failure names the TAB and jumps to it so the user can find the
// offending row from anywhere.
const TAB_VALUE = {
	Details: "details",
	Compacting: "compacting",
	Packing: "packing",
	"Set Item": "setitem",
	Stiching: "stiching",
	Emblishment: "emblishment",
	Cutting: "cutting",
	"Cloth Accessory": "accessory",
	"Advance Settings": "advanced",
}
async function saveAll() {
	const parts = [
		["Details", { validate: detailsValidate, apply: hdrApply }],
		["Compacting", doc.value?.is_cloth_item ? { validate: compactingValidate, apply: () => {} } : null],
		["Packing", packingRef.value],
		["Set Item", setItemRef.value],
		["Stiching", stichingRef.value],
		["Emblishment", emblishmentRef.value],
		["Cutting", cuttingRef.value],
		["Cloth Accessory", accessoryRef.value],
		["Advance Settings", advanceRef.value],
	].filter(([, s]) => s)
	for (const [tab, s] of parts) {
		const err = s.validate ? s.validate() : null
		if (err) {
			toast.error(tab, err)
			if (TAB_VALUE[tab]) activeTab.value = TAB_VALUE[tab]
			return
		}
	}
	savingAll.value = true
	try {
		const ipd = await callMethod("frappe.client.get", {
			doctype: "Item Production Detail",
			name: props.id,
		})
		if (doc.value?.modified && ipd.modified !== doc.value.modified) {
			toast.error("Save blocked", "This IPD changed since you opened it — reload and retry.")
			return
		}
		for (const [, s] of parts) s.apply(ipd)
		await callMethod("frappe.client.save", { doc: ipd })
		toast.success("Saved", "IPD updated")
		editing.value = false
		await load()
	} catch (e) {
		toast.error("Save failed", e.message)
	} finally {
		savingAll.value = false
	}
}

// Route-leave / reload guards while editing (DocDetail convention).
function beforeUnloadGuard(e) {
	if (editing.value) {
		e.preventDefault()
		e.returnValue = ""
	}
}
// Shared by route-LEAVE and route-UPDATE: onBeforeRouteLeave does NOT fire
// for param-only changes (IPD -> IPD via Back/Forward or a link), so without
// the update guard those navigations would silently drop an in-progress edit.
function guardEditingNavigation(next) {
	if (!editing.value) return next()
	confirm.require({
		header: "Discard unsaved changes?",
		message: "You are editing this IPD. Leave without saving?",
		icon: "pi pi-exclamation-triangle",
		acceptLabel: "Leave",
		acceptClass: "p-button-danger",
		rejectLabel: "Stay",
		accept: () => {
			editing.value = false
			next()
		},
		reject: () => next(false),
	})
}
onBeforeRouteLeave((to, from, next) => guardEditingNavigation(next))
onBeforeRouteUpdate((to, from, next) => guardEditingNavigation(next))
// Item Attributes cards: one per row in doc.item_attributes — { attr_name, mapping, values: [...] }
const itemAttrCards = ref([])
const itemAttrLoading = ref(false)
// Inline-edit state (one card at a time).
const editingAttrIdx = ref(-1)
const attrDraftValues = ref([])
const attrNewValue = ref("")
const attrSaving = ref(false)
// AutoComplete suggestion buffer for the "New value" picker — mirrors
// ItemAttributeListView so the two surfaces share the same UX (lessons-
// learned 2026-05-29: don't downgrade Link pickers when porting components).
const attrValueSuggestions = ref([])

// ── Add/Edit form for Item BOM ──
// bomFormMode: "off" | "add" | "edit". editingBomIdx is the row index when
// in "edit" mode (-1 otherwise). Single form serves both, switched by mode.
const bomFormMode = ref("off")
const editingBomIdx = ref(-1)
const bomSaving = ref(false)
const blankBomDraft = () => ({
	item: "",
	qty_of_product: null,
	qty_of_bom_item: null,
	uom: "",
	process_name: "",
	dependent_attribute_value: "",
	based_on_attribute_mapping: 0,
})
const bomDraft = ref(blankBomDraft())
const bomItemSuggestions = ref([])
const processSuggestions = ref([])
const depAttrValueSuggestions = ref([])

function openAddBom() {
	if (processFormMode.value !== "off") cancelAddProcess()
	bomDraft.value = blankBomDraft()
	editingBomIdx.value = -1
	bomFormMode.value = "add"
}
function openEditBom(idx) {
	const row = (doc.value?.item_bom || [])[idx]
	if (!row) return
	if (processFormMode.value !== "off") cancelAddProcess()
	bomDraft.value = {
		item: row.item || "",
		qty_of_product: row.qty_of_product == null ? null : Number(row.qty_of_product),
		qty_of_bom_item: row.qty_of_bom_item == null ? null : Number(row.qty_of_bom_item),
		uom: row.uom || "",
		process_name: row.process_name || "",
		dependent_attribute_value: row.dependent_attribute_value || "",
		based_on_attribute_mapping: row.based_on_attribute_mapping ? 1 : 0,
	}
	editingBomIdx.value = idx
	bomFormMode.value = "edit"
}
function cancelAddBom() {
	bomFormMode.value = "off"
	editingBomIdx.value = -1
	bomDraft.value = blankBomDraft()
}
async function deleteBomRow(idx) {
	const row = (doc.value?.item_bom || [])[idx]
	if (!row) return
	const label = row.item ? `“${row.item}”` : `row #${idx + 1}`
	confirm.require({
		header: "Delete BOM row?",
		message: `Delete BOM ${label}? This cannot be undone.`,
		acceptLabel: "Delete",
		acceptClass: "p-button-danger",
		accept: async () => {
			try {
				const ipd = await callMethod("frappe.client.get", {
					doctype: "Item Production Detail",
					name: props.id,
				})
				const rows = [...(ipd.item_bom || [])]
				rows.splice(idx, 1)
				ipd.item_bom = rows
				await callMethod("frappe.client.save", { doc: ipd })
				toast.success("Deleted", "BOM row removed")
				await load()
			} catch (e) {
				toast.error("Delete failed", e.message)
			}
		},
	})
}
async function onBomItemComplete(e) {
	try {
		const rows = await searchLink("Item", e.query || "", {})
		bomItemSuggestions.value = (rows || []).map((r) => r.name)
	} catch (_) { bomItemSuggestions.value = [] }
}
// When the BOM item is chosen, auto-fetch its default UOM (mirrors production_api's
// item_bom.uom = fetch_from item.default_unit_of_measure — the UOM is derived from
// the item, never hand-picked).
async function onBomItemPick(e) {
	const name = typeof e?.value === "string" ? e.value : e?.value?.name || bomDraft.value.item
	if (!name) return
	try {
		const r = await callMethod("frappe.client.get_value", {
			doctype: "Item",
			filters: { name },
			fieldname: "default_unit_of_measure",
		})
		bomDraft.value.uom = r?.default_unit_of_measure || ""
	} catch (_) { /* leave uom blank; reqd validation will catch it */ }
}
async function onProcessComplete(e) {
	try {
		const rows = await searchLink("Process", e.query || "", {})
		processSuggestions.value = (rows || []).map((r) => r.name)
	} catch (_) { processSuggestions.value = [] }
}
// Dependent-attribute-value picker: the IPD's dependent attribute's values
// (e.g. Stage → Cut / Stitch / Pack) — the stage at which this BOM item is
// consumed. Filtered to doc.dependent_attribute (mirrors production_api's
// set_query on item_bom.dependent_attribute_value).
async function onDepAttrValueComplete(e) {
	const attrName = doc.value?.dependent_attribute
	if (!attrName) { depAttrValueSuggestions.value = []; return }
	try {
		const rows = await searchLink("Item Attribute Value", e.query || "", { attribute_name: attrName })
		depAttrValueSuggestions.value = (rows || []).map((r) => r.name)
	} catch (_) { depAttrValueSuggestions.value = [] }
}

// ── Add/Edit form for IPD Processes ──
const processFormMode = ref("off") // "off" | "add" | "edit"
const editingProcessIdx = ref(-1)
const processSaving = ref(false)
const blankProcessDraft = () => ({ process_name: "", in_stage: "", out_stage: "" })
const processDraft = ref(blankProcessDraft())
const stageSuggestions = ref([])

function openAddProcess() {
	if (bomFormMode.value !== "off") cancelAddBom()
	processDraft.value = blankProcessDraft()
	editingProcessIdx.value = -1
	processFormMode.value = "add"
}
function openEditProcess(idx) {
	const row = (doc.value?.ipd_processes || [])[idx]
	if (!row) return
	if (bomFormMode.value !== "off") cancelAddBom()
	processDraft.value = {
		process_name: row.process_name || "",
		in_stage: row.in_stage || "",
		out_stage: row.out_stage || "",
	}
	editingProcessIdx.value = idx
	processFormMode.value = "edit"
}
function cancelAddProcess() {
	processFormMode.value = "off"
	editingProcessIdx.value = -1
	processDraft.value = blankProcessDraft()
}
async function deleteProcessRow(idx) {
	const row = (doc.value?.ipd_processes || [])[idx]
	if (!row) return
	const label = row.process_name ? `“${row.process_name}”` : `row #${idx + 1}`
	confirm.require({
		header: "Delete process row?",
		message: `Delete process ${label}? This cannot be undone.`,
		acceptLabel: "Delete",
		acceptClass: "p-button-danger",
		accept: async () => {
			try {
				const ipd = await callMethod("frappe.client.get", {
					doctype: "Item Production Detail",
					name: props.id,
				})
				const rows = [...(ipd.ipd_processes || [])]
				rows.splice(idx, 1)
				ipd.ipd_processes = rows
				await callMethod("frappe.client.save", { doc: ipd })
				toast.success("Deleted", "Process row removed")
				await load()
			} catch (e) {
				toast.error("Delete failed", e.message)
			}
		},
	})
}
async function onStageComplete(e) {
	// Stages are the IPD's dependent-attribute values (e.g. Cut/Piece/Pack).
	const attrName = doc.value?.dependent_attribute
	if (!attrName) { stageSuggestions.value = []; return }
	try {
		const rows = await searchLink("Item Attribute Value", e.query || "", { attribute_name: attrName })
		stageSuggestions.value = (rows || []).map((r) => r.name)
	} catch (_) { stageSuggestions.value = [] }
}
async function saveProcessRow() {
	const d = processDraft.value
	const proc = typeof d.process_name === "string" ? d.process_name : d.process_name?.name || ""
	if (!proc) {
		toast.warn("Missing required field", "Process is required.")
		return
	}
	processSaving.value = true
	try {
		const ipd = await callMethod("frappe.client.get", {
			doctype: "Item Production Detail",
			name: props.id,
		})
		const rows = [...(ipd.ipd_processes || [])]
		const patch = {
			process_name: proc,
			in_stage: typeof d.in_stage === "string" ? d.in_stage : d.in_stage?.name || "",
			out_stage: typeof d.out_stage === "string" ? d.out_stage : d.out_stage?.name || "",
		}
		if (processFormMode.value === "edit" && editingProcessIdx.value >= 0 && editingProcessIdx.value < rows.length) {
			// Preserve identifiers (name, idx, parent links) so the server updates in place.
			rows[editingProcessIdx.value] = { ...rows[editingProcessIdx.value], ...patch }
		} else {
			rows.push({ doctype: "IPD Process", ...patch })
		}
		ipd.ipd_processes = rows
		await callMethod("frappe.client.save", { doc: ipd })
		toast.success("Saved", processFormMode.value === "edit" ? "Process row updated" : "Process row added")
		cancelAddProcess()
		await load()
	} catch (e) {
		toast.error("Save failed", e.message)
	} finally {
		processSaving.value = false
	}
}

async function saveBomRow() {
	const d = bomDraft.value
	if (!d.item || !d.uom || !(Number(d.qty_of_product) > 0) || !(Number(d.qty_of_bom_item) > 0)) {
		toast.warn("Missing required field", "Item, UOM, and both quantities are required.")
		return
	}
	const depAttr = doc.value?.dependent_attribute
	const depVal = typeof d.dependent_attribute_value === "string"
		? d.dependent_attribute_value
		: d.dependent_attribute_value?.name || ""
	// production_api makes dependent_attribute_value required on the BOM row when
	// the IPD has a dependent attribute (updateChildTableReqd, item_production_detail.js:522).
	if (depAttr && !depVal) {
		toast.warn("Missing required field", `${depAttr} (stage) is required for each BOM row.`)
		return
	}
	bomSaving.value = true
	try {
		const ipd = await callMethod("frappe.client.get", {
			doctype: "Item Production Detail",
			name: props.id,
		})
		const rows = [...(ipd.item_bom || [])]
		const patch = {
			item: typeof d.item === "string" ? d.item : d.item?.name || "",
			qty_of_product: Number(d.qty_of_product) || 0,
			qty_of_bom_item: Number(d.qty_of_bom_item) || 0,
			uom: typeof d.uom === "string" ? d.uom : d.uom?.name || "",
			process_name: typeof d.process_name === "string" ? d.process_name : d.process_name?.name || "",
			dependent_attribute_value: depVal,
			based_on_attribute_mapping: d.based_on_attribute_mapping ? 1 : 0,
		}
		if (bomFormMode.value === "edit" && editingBomIdx.value >= 0 && editingBomIdx.value < rows.length) {
			// Preserve identifiers + the attribute_mapping link so an existing
			// cross-product mapping isn't orphaned when the row is edited. But if
			// the user toggles "based on attribute mapping" OFF, clear the stale
			// link (mirrors production_api unsetting bom.attribute_mapping when
			// the flag is cleared — the engine ignores the mapping once the flag
			// is off, so a dangling link would just be a confusing orphan).
			if (!patch.based_on_attribute_mapping) patch.attribute_mapping = null
			rows[editingBomIdx.value] = { ...rows[editingBomIdx.value], ...patch }
		} else {
			rows.push({ doctype: "Item BOM", ...patch })
		}
		ipd.item_bom = rows
		await callMethod("frappe.client.save", { doc: ipd })
		toast.success("Saved", bomFormMode.value === "edit" ? "BOM row updated" : "BOM row added")
		cancelAddBom()
		await load()
	} catch (e) {
		toast.error("Save failed", e.message)
	} finally {
		bomSaving.value = false
	}
}
const configuring = ref(null) // process_name currently resolving its redirect

const headerLine = computed(() => {
	const d = doc.value
	if (!d) return ""
	const bits = []
	if (d.item) bits.push(d.item)
	return bits.join(" · ")
})

// Q2/Q3: the produced item names the hero + breadcrumb. Item is autonamed from
// name1, so doc.item IS already the human name — no title resolution needed.
const itemLabel = computed(() => doc.value?.item || "")

const approvalSeverity = computed(() => {
	const s = doc.value?.approval_status
	if (s === "Approved") return "success"
	if (s === "Cutting Approved") return "info"
	return "warn"
})

const deskUrl = computed(
	() => `/app/item-production-detail/${encodeURIComponent(props.id)}`,
)

async function load() {
	// This rich view configures an EXISTING IPD. Create goes through the
	// generic DocDetail at /web/item-production-detail/new — the router has an
	// explicit entry BEFORE this view so we should never receive id==="new"
	// here. Defensive guard: surface a friendly error instead of the old
	// silent Desk redirect (`/app/item-production-detail/new`) which broke the
	// strict "no Desk for restricted users" rule.
	if (props.id === "new") {
		error.value = "Use the New button on the Item Production Detail list — this surface is for existing IPDs."
		return
	}
	loading.value = true
	error.value = null
	try {
		doc.value = await getDoc("Item Production Detail", props.id)
		hdrHydrate()
		// A reload after an id change must not leave the user on a tab that no
		// longer exists for this IPD kind (fabric is cloth-only; the garment
		// tab set is garment-only; Set Item additionally needs packing_attribute).
		if (["fabric", "compacting"].includes(activeTab.value) && !doc.value?.is_cloth_item) {
			activeTab.value = "details"
		}
		const garmentTabs = ["packing", "setitem", "stiching", "emblishment", "cutting", "accessory", "advanced"]
		if (garmentTabs.includes(activeTab.value) && doc.value?.is_cloth_item) {
			activeTab.value = "details"
		}
		if (activeTab.value === "setitem" && !doc.value?.packing_attribute) {
			activeTab.value = "details"
		}
		loadMatrices()
		loadItemAttributes()
		if (!approvalRoles.value.length) loadApprovalRoles()
	} catch (e) {
		error.value = e.message || "Failed to load Item Production Detail"
	} finally {
		loading.value = false
	}
}

// Hydrate the "Item Attributes" panel: one card per IPD attribute row,
// showing the actual attribute values (Cut/Piece/Pack, S/M/L/XL, …)
// fetched from each row's mapping doc. Single bulk get_list across every
// mapping name so the panel renders in one round-trip.
async function loadItemAttributes() {
	const rows = doc.value?.item_attributes || []
	if (!rows.length) {
		itemAttrCards.value = []
		return
	}
	itemAttrLoading.value = true
	try {
		// Fetch each mapping's full doc in parallel and read its `values`
		// child rows. frappe.client.get_list strips child-doctype fields
		// like `parent`/`attribute_value` so we can't pull all values in a
		// single query — but typical IPDs have only 4-5 attribute rows so
		// the round-trips are cheap, and the parent get_doc surfaces every
		// child row in order.
		const docs = await Promise.all(
			rows.map((r) =>
				r.mapping
					? callMethod("frappe.client.get", {
							doctype: r.mapping_doctype || "Item Item Attribute Mapping",
							name: r.mapping,
					  }).catch(() => null)
					: Promise.resolve(null),
			),
		)
		itemAttrCards.value = rows.map((r, i) => {
			const m = docs[i]
			const vals = (m?.values || []).map((v) => v.attribute_value).filter(Boolean)
			return {
				attr_name: r.attribute,
				mapping: r.mapping || "",
				values: vals,
			}
		})
	} catch (e) {
		toast.warn("Could not load attribute values", e.message)
		itemAttrCards.value = rows.map((r) => ({
			attr_name: r.attribute,
			mapping: r.mapping || "",
			values: [],
		}))
	} finally {
		itemAttrLoading.value = false
	}
}

async function loadMatrices() {
	matricesLoading.value = true
	try {
		const { data } = await getList("IPD Process Matrix", {
			filters: { ipd: props.id },
			fields: ["name", "process_name", "reference_item_variant", "input_item", "output_item"],
			order_by: "process_name asc, modified desc",
			limit_page_length: 0,
		})
		matrices.value = data
	} catch (e) {
		matrices.value = []
		toast.warn("Matrices", e.message)
	} finally {
		matricesLoading.value = false
	}
}

function matrixInputLabel(matrix) {
	if (matrix.input_item) return matrix.input_item
	if (
		doc.value?.is_cloth_item &&
		matrix.process_name === doc.value?.knitting_process
	) {
		return "Colour recipe blend"
	}
	return doc.value?.item || "—"
}

onMounted(() => {
	window.addEventListener("beforeunload", beforeUnloadGuard)
	load()
})
onBeforeUnmount(() => {
	window.removeEventListener("beforeunload", beforeUnloadGuard)
})

// Load trigger for SPA navigation. vue-router REUSES this component instance
// when only the :id param changes (IPD → IPD), so onMounted does NOT re-fire —
// without this watch the view would keep showing the previous doc. By the time
// this watcher runs, onBeforeRouteUpdate has ALREADY confirmed any in-progress
// edit with the user (route-leave alone never fires for param-only changes),
// so dropping edit mode here is safe. Reset the tab and reload.
watch(
	() => props.id,
	() => {
		editing.value = false
		activeTab.value = "details"
		load()
	},
)

// ── Item BOM mapping link (R1b target) ──
async function openMapping(row) {
	if (row.attribute_mapping) {
		router.push(
			`/item-bom-attribute-mapping/${encodeURIComponent(row.attribute_mapping)}`,
		)
		return
	}
	// No mapping yet — auto-create one with the item + bom_item context AND the
	// attribute columns (item-side = IPD primary attribute, bom-side = all BOM
	// item attributes) so the editor's cross-product grid renders immediately.
	// This mirrors production_api's IPD.update_mapping_values; doing the
	// attribute derivation server-side keeps it identical to the Python
	// reference (and avoids the old empty-columns bug where the editor showed
	// "no item-side attributes to map"). Link it back onto the IPD's child row,
	// then navigate. Errors surface as a toast.
	try {
		// create_mapping is idempotent + atomic: it back-links the BOM child row
		// in the same request (passing bom_row), so there's no separate
		// set_value round-trip whose failure could orphan a never-linked
		// mapping. A repeat click returns the existing mapping rather than
		// creating a duplicate.
		const newName = await callMethod(
			"essdee_yrp.api.bom_mapping.create_mapping",
			{ ipd: props.id, bom_item: row.item || "", bom_row: row.name || "" },
		)
		if (!newName) throw new Error("Server did not return a mapping name")
		// Update the local doc so subsequent "Open mapping" clicks use the fast path.
		row.attribute_mapping = newName
		router.push(`/item-bom-attribute-mapping/${encodeURIComponent(newName)}`)
	} catch (e) {
		toast.error("Could not open mapping", e.message)
	}
}

// ── Inline edit for Item Attributes cards ──
function enterAttrEdit(idx) {
	editingAttrIdx.value = idx
	attrDraftValues.value = [...(itemAttrCards.value[idx]?.values || [])]
	attrNewValue.value = ""
}
function cancelAttrEdit() {
	editingAttrIdx.value = -1
	attrDraftValues.value = []
	attrNewValue.value = ""
}
function addAttrValue() {
	const raw = attrNewValue.value
	const v = (typeof raw === "string" ? raw : raw?.name || "").trim()
	if (!v) return
	if (attrDraftValues.value.includes(v)) {
		toast.warn("Duplicate", `"${v}" already in the list.`)
		attrNewValue.value = ""
		return
	}
	attrDraftValues.value.push(v)
	attrNewValue.value = ""
	attrValueSuggestions.value = []
}
// Filtered list of existing Item Attribute Values for this attribute, minus
// the ones already in the draft. Free-text entry still allowed — the
// AutoComplete leaves v-model as the typed string when nothing matches.
async function onAttrNewComplete(card, e) {
	const q = e?.query || ""
	try {
		const rows = await searchLink("Item Attribute Value", q, {
			attribute_name: card.attr_name,
		})
		attrValueSuggestions.value = (rows || [])
			.map((r) => r.name)
			.filter((n) => !attrDraftValues.value.includes(n))
	} catch (_) {
		attrValueSuggestions.value = []
	}
}
function removeAttrAt(i) {
	attrDraftValues.value.splice(i, 1)
}
async function saveAttrCard(card) {
	if (!card.mapping) {
		toast.error("No mapping doc", "Cannot save — the attribute mapping is missing.")
		return
	}
	attrSaving.value = true
	try {
		await callMethod(
			"essdee_yrp.api.item_attribute.update_mapping_values",
			{
				mapping: card.mapping,
				attribute_name: card.attr_name,
				values: attrDraftValues.value,
			},
		)
		toast.success("Saved", `${card.attr_name} values updated`)
		cancelAttrEdit()
		await loadItemAttributes()
	} catch (e) {
		toast.error("Save failed", e.message)
	} finally {
		attrSaving.value = false
	}
}

// ── The synthesized "Configure combinations" redirect ──
async function configureCombinations(proc) {
	const process = proc.process_name
	if (!process) return
	configuring.value = process
	try {
		// Find an existing matrix for {ipd, process}. Prefer a generic one (no
		// reference variant), but any existing matrix is a valid landing spot.
		const { data } = await getList("IPD Process Matrix", {
			filters: { ipd: props.id, process_name: process },
			fields: ["name", "reference_item_variant"],
			order_by: "reference_item_variant asc, modified desc",
			limit_page_length: 1,
		})
		if (data.length) {
			router.push(`/ipd-process-matrix/${encodeURIComponent(data[0].name)}`)
		} else {
			router.push(
				`/ipd-process-matrix/new?ipd=${encodeURIComponent(props.id)}&process=${encodeURIComponent(process)}`,
			)
		}
	} catch (e) {
		toast.error("Could not open combinations", e.message)
	} finally {
		configuring.value = null
	}
}

function openMatrix(name) {
	router.push(`/ipd-process-matrix/${encodeURIComponent(name)}`)
}

// ── Navigation helpers ──
function goHome() {
	router.push("/home")
}
function goList() {
	router.push("/item-production-detail")
}
function navigateDoc(dt, name) {
	if (!name) return
	const reg = getRegistryByDoctype(dt)
	if (reg) {
		router.push(`/${reg.route}/${encodeURIComponent(name)}`)
	} else {
		// Non-registry doctype: don't redirect to Desk — restricted users
		// must stay in /web (conventions.md 2026-05-29). Tell the user
		// instead so they know the link is unsupported here.
		toast.warn(
			"Not available in /web",
			`${dt} doesn't have a /web page yet.`,
		)
	}
}

function onDelete() {
	if (!doc.value) return
	confirm.require({
		header: "Delete document",
		message: `Permanently delete ${props.id}? This cannot be undone.`,
		acceptLabel: "Delete",
		acceptClass: "p-button-danger",
		accept: async () => {
			deleting.value = true
			try {
				await deleteDoc("Item Production Detail", props.id)
				toast.success("Deleted", `${props.id} deleted`)
				router.push("/item-production-detail")
			} catch (e) {
				toast.error("Delete failed", e.message)
				deleting.value = false
			}
		},
	})
}

// ── formatting ──
function fmtNum(v) {
	if (v === null || v === undefined || v === "") return "—"
	const n = Number(v)
	return Number.isNaN(n) ? String(v) : n.toLocaleString("en-IN")
}
</script>

<style scoped>
.ipd-config {
	display: flex;
	flex-direction: column;
	gap: 14px;
	container-type: inline-size;
}

/* Tabbed shell (2026-07-09). The panels used to be direct flex children of
   .ipd-config (14px gap); now they live inside a TabPanel, so re-establish the
   same column/gap rhythm there. */
.ipd-tabs {
	--p-tabs-tab-padding: 9px 16px;
}
.ipd-tabpanels {
	background: transparent;
}
.ipd-tabpanel {
	display: flex;
	flex-direction: column;
	gap: 14px;
	padding: 16px 0 0;
}
.req {
	color: var(--esd-danger, #d92d20);
}
/* .hdr-facts / .pf / .pl / .pv / .hdr-text come from the shared
   ipd-sections.css so the Details panel matches every other tab. */
.panel-head .spacer {
	flex: 1;
}
.yarn-ratio-list,
.yarn-ratio-view {
	display: flex;
	flex-direction: column;
	gap: 8px;
	padding: 12px 16px;
}
.yarn-ratio-row {
	display: grid;
	grid-template-columns: minmax(240px, 1fr) 150px auto;
	gap: 10px;
	align-items: center;
}
.yarn-ratio-view-row {
	display: flex;
	justify-content: space-between;
	gap: 16px;
	max-width: 560px;
}
.recipe-list,
.recipe-view,
.compacting-list,
.compacting-view {
	display: flex;
	flex-direction: column;
	gap: 10px;
	padding: 12px 16px;
}
.recipe-help {
	margin: 10px 16px 0;
	padding: 9px 11px;
	border: 1px solid color-mix(in srgb, var(--esd-accent) 22%, var(--esd-line));
	border-radius: var(--radius-sm);
	color: var(--esd-muted);
	background: color-mix(in srgb, var(--esd-accent) 5%, transparent);
	font-size: 0.78rem;
	line-height: 1.45;
}
.recipe-card {
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	padding: 10px 12px;
}
.recipe-card--edit {
	max-width: 900px;
}
.recipe-card__title {
	display: flex;
	justify-content: space-between;
	gap: 12px;
	font-weight: 600;
	margin-bottom: 7px;
}
.recipe-card__title > span:first-child {
	display: flex;
	flex-direction: column;
	gap: 2px;
}
.recipe-card__title small {
	color: var(--esd-muted);
	font-size: 0.7rem;
	font-weight: 500;
}
.recipe-group-head {
	display: grid;
	grid-template-columns: minmax(220px, 1fr) auto auto auto;
	gap: 10px;
	align-items: end;
	margin-bottom: 10px;
}
.recipe-colour-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
.recipe-field-label,
.recipe-yarn-head {
	color: var(--esd-muted);
	font-size: 0.7rem;
	font-weight: 600;
}
.recipe-total {
	align-self: center;
	color: var(--esd-accent);
}
.recipe-route-count {
	align-self: center;
	padding: 4px 8px;
	border-radius: 999px;
	background: var(--esd-surface-2);
	color: var(--esd-muted);
	font-size: 0.7rem;
	white-space: nowrap;
}
.recipe-total.invalid {
	color: var(--esd-danger, #d92d20);
}
.recipe-yarn-head,
.recipe-yarn-row {
	display: grid;
	grid-template-columns: minmax(220px, 1fr) 140px auto;
	gap: 8px;
	align-items: center;
}
.recipe-yarn-head {
	padding: 0 2px 4px;
}
.recipe-yarn-row + .recipe-yarn-row {
	margin-top: 7px;
}
.recipe-route-block,
.recipe-route-view {
	margin-top: 12px;
	padding-top: 10px;
	border-top: 1px solid var(--esd-line);
}
.recipe-route-title {
	display: flex;
	justify-content: space-between;
	align-items: baseline;
	gap: 10px;
	margin-bottom: 8px;
}
.recipe-route-title span,
.recipe-route-empty {
	color: var(--esd-muted);
	font-size: 0.72rem;
}
.recipe-bulk-output {
	display: grid;
	grid-template-columns: minmax(240px, 1fr) auto;
	gap: 10px;
	align-items: end;
	margin-bottom: 10px;
	padding: 9px;
	border-radius: var(--radius-xs, 6px);
	background: var(--esd-surface-2);
}
.matrix-route-summary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 9px 16px;
	border-bottom: 1px solid var(--esd-line);
	color: var(--esd-muted);
	font-size: 0.76rem;
}
.matrix-counts {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
}
.matrix-counts span {
	padding: 4px 8px;
	border: 1px solid var(--esd-line);
	border-radius: 999px;
	background: var(--esd-surface-2);
	white-space: nowrap;
}
.recipe-route-head,
.recipe-route-row {
	display: grid;
	grid-template-columns: minmax(130px, 0.75fr) minmax(145px, 0.85fr) minmax(180px, 1fr) minmax(115px, auto) auto;
	gap: 8px;
	align-items: center;
}
.recipe-route-head {
	padding: 0 2px 4px;
	color: var(--esd-muted);
	font-size: 0.7rem;
	font-weight: 600;
}
.recipe-route-row + .recipe-route-row,
.recipe-route-view-row + .recipe-route-view-row {
	margin-top: 7px;
}
.recipe-route-state {
	padding: 5px 8px;
	border-radius: 999px;
	background: color-mix(in srgb, #f79009 12%, transparent);
	color: #b54708;
	font-size: 0.7rem;
	text-align: center;
}
.recipe-route-state.direct {
	background: color-mix(in srgb, #12b76a 12%, transparent);
	color: #027a48;
}
.recipe-route-view-row {
	display: grid;
	grid-template-columns: minmax(120px, 0.8fr) auto minmax(210px, 1.2fr) auto;
	gap: 10px;
	align-items: center;
	padding: 6px 0;
}
.recipe-route-view-row > span:not(.recipe-route-state) {
	display: flex;
	flex-direction: column;
	gap: 2px;
}
.recipe-route-view-row small {
	color: var(--esd-muted);
	font-size: 0.68rem;
}
.compacting-generator {
	display: grid;
	grid-template-columns: minmax(180px, 240px) minmax(260px, 1fr) auto;
	gap: 10px;
	align-items: end;
	padding: 12px;
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	background: color-mix(in srgb, var(--esd-accent) 4%, transparent);
}
.compacting-generator__field {
	display: flex;
	flex-direction: column;
	gap: 5px;
}
.compacting-generator__field > label {
	font-size: 0.7rem;
	font-weight: 700;
	letter-spacing: 0.03em;
	text-transform: uppercase;
	color: var(--esd-muted);
}
.compacting-generator__field:not(.compacting-generator__colours) {
	grid-column: 1;
}
.compacting-generator > .p-button {
	grid-column: 3;
}
.compacting-list {
	display: flex;
	flex-direction: column;
	gap: 12px;
}
.compacting-group-summary {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 10px 12px;
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	background: color-mix(in srgb, var(--esd-accent) 4%, transparent);
}
.compacting-group-summary > span {
	font-size: 0.68rem;
	font-weight: 700;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--esd-muted);
	white-space: nowrap;
}
.compacting-group-summary > div {
	display: flex;
	align-items: center;
	gap: 6px;
	flex-wrap: wrap;
}
.compacting-group-summary strong {
	display: inline-flex;
	padding: 4px 9px;
	border-radius: 999px;
	background: color-mix(in srgb, var(--esd-accent) 11%, transparent);
	color: var(--esd-accent-700);
	font-size: 0.74rem;
	font-weight: 700;
}
.compacting-simple-table {
	overflow: hidden;
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	background: var(--esd-card);
}
.compacting-simple-head,
.compacting-simple-row {
	display: grid;
	grid-template-columns: minmax(160px, 0.7fr) minmax(240px, 1.3fr);
	gap: 12px;
	align-items: center;
}
.compacting-simple-head.is-separate,
.compacting-simple-row.is-separate {
	grid-template-columns: minmax(150px, 0.7fr) minmax(150px, 0.8fr) minmax(240px, 1.3fr) 40px;
}
.compacting-simple-head {
	padding: 8px 12px;
	background: var(--esd-surface-subtle);
	border-bottom: 1px solid var(--esd-line);
	color: var(--esd-muted);
	font-size: 0.68rem;
	font-weight: 700;
	letter-spacing: 0.03em;
	text-transform: uppercase;
}
.compacting-simple-row {
	position: relative;
	padding: 8px 12px;
	border-bottom: 1px solid var(--esd-line);
}
.compacting-simple-row:last-child {
	border-bottom: 0;
}
.compacting-simple-value,
.compacting-simple-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
	min-width: 0;
}
.compacting-simple-value small,
.compacting-simple-field > small {
	display: none;
	color: var(--esd-muted);
	font-size: 0.66rem;
	font-weight: 700;
	letter-spacing: 0.03em;
	text-transform: uppercase;
}
.compacting-simple-value strong {
	display: inline-flex;
	align-items: center;
	width: fit-content;
	max-width: 100%;
	padding: 5px 10px;
	border-radius: 999px;
	background: color-mix(in srgb, var(--esd-accent) 8%, transparent);
	color: var(--esd-text);
	font-size: 0.78rem;
	font-weight: 700;
}
.compacting-row--invalid {
	background: color-mix(in srgb, var(--red-500, #ef4444) 7%, transparent);
	box-shadow: inset 3px 0 0 var(--red-500, #ef4444);
}
.compacting-row-error {
	grid-column: 1 / -1;
	color: var(--red-600, #dc2626);
	font-size: 0.72rem;
}
.compacting-view-row {
	display: grid;
	grid-template-columns: minmax(140px, 1fr) minmax(220px, 1fr) minmax(180px, 2fr);
	gap: 12px;
	padding: 8px 0;
	border-bottom: 1px solid var(--esd-line);
}
@media (max-width: 980px) {
	.recipe-group-head,
	.recipe-bulk-output,
	.compacting-generator {
		grid-template-columns: 1fr;
	}
	.compacting-generator__field,
	.compacting-generator > .p-button {
		grid-column: 1;
	}
	.recipe-total {
		justify-self: start;
	}
	.recipe-route-head {
		display: none;
	}
	.recipe-route-row {
		grid-template-columns: 1fr 1fr;
		padding: 8px;
		border: 1px solid var(--esd-line);
		border-radius: var(--radius-xs, 6px);
	}
}
@media (max-width: 540px) {
	.recipe-list,
	.recipe-view {
		padding: 10px;
	}
	.recipe-help {
		margin-inline: 10px;
	}
	.recipe-yarn-head {
		display: none;
	}
	.recipe-yarn-row {
		grid-template-columns: minmax(0, 1fr) 92px auto;
		gap: 5px;
	}
	.recipe-route-row,
	.recipe-route-view-row {
		grid-template-columns: 1fr;
	}
	.recipe-bulk-output,
	.matrix-route-summary {
		grid-template-columns: 1fr;
		flex-direction: column;
		align-items: stretch;
	}
	.recipe-route-view-row .pi-arrow-right {
		transform: rotate(90deg);
	}
	.recipe-route-state {
		text-align: left;
	}
	.yarn-ratio-row {
		grid-template-columns: minmax(0, 1fr) 92px auto;
		gap: 5px;
	}
	.detail-head {
		flex-wrap: wrap;
	}
	.head-actions {
		width: 100%;
		margin-left: 0;
		flex-wrap: wrap;
	}
}

/* The optional mobile shell is a 440px container even at a desktop viewport.
   Container rules keep the same safe layout in all three shells. */
@container (max-width: 540px) {
	.yarn-ratio-row {
		grid-template-columns: minmax(0, 1fr) 92px auto;
		gap: 5px;
	}
	.recipe-yarn-head,
	.recipe-route-head {
		display: none;
	}
	.recipe-yarn-row {
		grid-template-columns: minmax(0, 1fr) 92px auto;
		gap: 5px;
	}
	.recipe-group-head,
	.recipe-bulk-output,
	.recipe-route-row,
	.recipe-route-view-row,
	.compacting-simple-row {
		grid-template-columns: 1fr;
	}
	.compacting-simple-head {
		display: none;
	}
	.compacting-simple-row,
	.compacting-simple-row.is-separate {
		grid-template-columns: minmax(0, 1fr) 36px;
		gap: 8px;
	}
	.compacting-simple-row:not(.is-separate) {
		grid-template-columns: minmax(90px, 0.6fr) minmax(0, 1.4fr);
	}
	.compacting-simple-row.is-separate > .p-button {
		grid-column: 2;
		grid-row: 1 / span 3;
		align-self: start;
	}
	.compacting-simple-row.is-separate .compacting-simple-value,
	.compacting-simple-row.is-separate .compacting-simple-field {
		grid-column: 1;
	}
	.compacting-simple-value small,
	.compacting-simple-field > small {
		display: block;
	}
	.compacting-group-summary {
		align-items: flex-start;
		flex-direction: column;
		gap: 7px;
	}
	.detail-head {
		flex-wrap: wrap;
	}
	.head-actions {
		width: 100%;
		margin-left: 0;
		flex-wrap: wrap;
	}
}

/* Breadcrumb (mirrors DocDetail) */
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
/* Q2: hero is the produced item; the IPD code drops to a small mono chip. */
.doc-hero {
	font-size: 20px;
	font-weight: 700;
	letter-spacing: -0.01em;
	color: var(--esd-ink);
	line-height: 1.2;
}
.doc-sub {
	font-size: 13px;
	color: var(--esd-muted);
}
.doc-id {
	font-size: 12px;
	color: var(--esd-muted);
}
.doc-title {
	font-size: 13px;
	color: var(--esd-muted);
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

/* States */
.state-block {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 10px;
	padding: 40px 0;
	color: var(--esd-muted);
}

/* Attribute strip */
.attr-strip {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 1px;
	background: var(--esd-line);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	overflow: hidden;
}
@media (max-width: 700px) {
	.attr-strip {
		grid-template-columns: 1fr;
	}
}
.attr-cell {
	background: var(--esd-card);
	padding: 11px 16px;
	display: flex;
	flex-direction: column;
	gap: 3px;
}
.attr-cell .al {
	font-size: 11.5px;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
}
.attr-cell .av {
	font-size: 14px;
	color: var(--esd-ink);
	display: inline-flex;
	align-items: center;
	gap: 6px;
}
a.av {
	color: var(--esd-accent-700);
	cursor: pointer;
}
a.av:hover {
	text-decoration: underline;
}
.dep-hint {
	color: var(--esd-muted-2);
	font-size: 13px;
	cursor: help;
}

/* Panels */
.panel {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	overflow: hidden;
}
/* Section heads share the Bright Workshop band (light tint; mirrors .esd-card__head). */
.panel-head {
	display: flex;
	align-items: center;
	gap: var(--space-2);
	padding: 10px 16px;
	background: var(--esd-accent-50); border-bottom: 1px solid var(--esd-line);
}
.panel-head::before {
	content: "";
	width: 6px;
	height: 6px;
	border-radius: 999px;
	background: var(--esd-accent-ink);
	opacity: 0.85;
	flex: 0 0 auto;
}
.panel-head h3 {
	margin: 0;
	font-size: 13px;
	font-weight: 700;
	letter-spacing: 0.02em;
	text-transform: uppercase;
	color: var(--esd-accent-ink);
}
/* Row-count reads as the right-aligned count pill on the band. */
.panel-meta {
	margin-left: auto;
	background: #fff;
	color: var(--esd-accent-ink);
	font-size: 11px;
	font-weight: 600;
	padding: 1px 8px;
	border-radius: 999px;
}
/* Inline panel actions (Add row) sit after the count, on the band. They get a
   white-on-teal outline so the secondary button stays legible against the band. */
.panel-add-btn {
	margin-left: 0;
}
:deep(.panel-add-btn.p-button-outlined) {
	border-color: var(--esd-accent);
	color: var(--esd-accent-ink);
	background: transparent;
}
:deep(.panel-add-btn.p-button-outlined:hover) {
	border-color: var(--esd-accent-ink);
	background: var(--esd-accent-50);
	color: var(--esd-accent-ink);
}
.panel-empty {
	padding: 18px 14px;
	color: var(--esd-muted);
	font-size: 13px;
}
.ipd-attr-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
	gap: 12px;
	padding: 12px 14px;
}
.ipd-attr-card {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	padding: 10px 12px;
	display: flex;
	flex-direction: column;
	gap: 8px;
	min-width: 0;
}
.ipd-attr-head {
	display: flex;
	align-items: center;
	gap: 8px;
}
.ipd-attr-title {
	font-size: 11.5px;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
	flex: 1;
	min-width: 0;
}
.ipd-chip-row {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
}
.ipd-attr-chip {
	display: inline-flex;
	align-items: center;
	min-height: 28px;
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
	border-radius: 999px;
	font-size: 12px;
	font-weight: 500;
	padding: 3px 11px;
	line-height: 1.3;
}
.ipd-attr-empty {
	color: var(--esd-muted);
	font-size: 12px;
	font-style: italic;
}
.ipd-attr-card.editing {
	border-color: var(--esd-accent);
	box-shadow: 0 0 0 3px var(--esd-accent-50);
}
.ipd-attr-edit-btn {
	color: var(--esd-muted-2);
}
.ipd-attr-edit-btn:hover {
	color: var(--esd-accent-700);
}
.ipd-attr-chip.removable {
	padding-right: 4px;
}
.ipd-chip-x {
	background: transparent;
	border: 0;
	color: var(--esd-accent-700);
	cursor: pointer;
	font-size: 14px;
	line-height: 1;
	padding: 0 4px;
	border-radius: 999px;
	opacity: 0.7;
}
.ipd-chip-x:hover {
	opacity: 1;
	background: var(--esd-accent);
	color: white;
}
.ipd-add-row {
	display: flex;
	gap: 6px;
	align-items: center;
	margin-top: 4px;
}
.ipd-add-input {
	flex: 1;
	min-width: 0;
}
.ipd-edit-actions {
	display: flex;
	gap: 8px;
	justify-content: flex-end;
	margin-top: 6px;
}
.panel-add-btn {
	margin-left: auto;
}
.add-row-form {
	padding: 14px;
	border-top: 1px solid var(--esd-line);
	background: var(--esd-slate-50);
	display: flex;
	flex-direction: column;
	gap: 12px;
}
.add-row-form .form-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
	gap: 12px 16px;
}
.add-row-form .form-field {
	display: flex;
	flex-direction: column;
	gap: 5px;
}
.add-row-form .form-field label {
	font-size: 11.5px;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
}
.add-row-form .toggle-field label {
	margin-bottom: 4px;
}
.add-row-form .field-hint {
	font-size: 10.5px;
	color: var(--esd-muted-2);
	margin-top: 2px;
}
.add-row-actions {
	display: flex;
	gap: 8px;
	justify-content: flex-end;
}
.add-row-form .form-title {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 12.5px;
	font-weight: 600;
	color: var(--esd-muted);
	text-transform: uppercase;
	letter-spacing: 0.04em;
}
.row-actions {
	display: flex;
	align-items: center;
	gap: 4px;
	justify-content: flex-end;
}

/* Tables */
.cfg-dt {
	border: 0;
}
.cell-link {
	color: var(--esd-accent-700);
	cursor: pointer;
}
.cell-link:hover {
	text-decoration: underline;
}
.strong {
	font-weight: 600;
	color: var(--esd-ink);
}
.muted-dash {
	color: var(--esd-muted-2);
	font-size: 12.5px;
}
/* Table headers inherit the PART 1c slate band; only refine the type here. */
:deep(.esd-table .p-datatable-thead > tr > th) {
	font-size: 11.5px;
	letter-spacing: 0.03em;
	text-transform: uppercase;
}
:deep(.esd-table .p-datatable-tbody > tr > td) {
	font-size: 13px;
}
.duplicate-form {
	display: flex;
	flex-direction: column;
	gap: 7px;
}
.duplicate-form label {
	color: var(--esd-muted);
	font-size: 0.75rem;
	font-weight: 650;
	letter-spacing: 0.04em;
	text-transform: uppercase;
}
@container (max-width: 540px) {
	.detail-head {
		flex-wrap: wrap;
	}
	.head-actions {
		width: 100%;
		margin-left: 0;
		flex-wrap: wrap;
	}
}
</style>
