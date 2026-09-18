# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

"""Regression contracts for the 2026-07-27 Essdee code review.

The affected browser paths are Vue single-file components without a unit-test
runner in this app. These tests therefore pin the security/data-integrity seams
in the shipped sources, following the same source-contract approach as
``test_ui_mirror.py``. Runtime compatibility is covered separately by the
frontend production build and the browser verification harness.
"""

import os

import frappe
from frappe.tests import IntegrationTestCase


def _app_root(app):
	return os.path.dirname(frappe.get_app_path(app))


def _read(app, relative_path):
	path = os.path.join(_app_root(app), relative_path)
	with open(path, encoding="utf-8") as source:
		return source.read()


class TestReviewRegressionContracts(IntegrationTestCase):
	def test_web_grn_autofill_uses_the_standard_purchase_order_identity(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/DocDetail.vue")
		self.assertIn('form.against === "Purchase Order"', source)
		self.assertNotIn('form.against === "YRP Purchase Order"', source)

	def test_filtered_prev_next_serializes_tuple_filters(self):
		source = _read("essdee_yrp", "frontend/src/composables/useDocNav.js")
		self.assertIn(
			"Array.isArray(filters) ? JSON.stringify(filters) : filters",
			source,
		)

	def test_lot_ipd_picker_stays_empty_until_item_is_selected(self):
		source = _read("essdee_yrp", "frontend/src/config/fields/lot.js")
		self.assertIn(": async () => []", source)
		self.assertIn('{ item: form.item }', source)

	def test_item_link_pickers_enforce_legal_subsets(self):
		source = _read("essdee_yrp", "frontend/src/config/fields/item.js")
		self.assertIn('searchLink("Item Group", q, { is_group: 0 })', source)
		self.assertIn('searchLink("UOM", q, { secondary_only: 0 })', source)

	def test_guarded_item_bulk_fields_use_controller_save(self):
		source = _read("essdee_yrp", "essdee_yrp/api/bulk_edit.py")
		self.assertIn("'Item': {\"allow_negative_stock\", \"stock_uom\"}", source)
		self.assertIn("CONTROLLER_VALIDATED_PARENT_FIELDS.get(doctype, set())", source)
		self.assertIn("doc.save()", source)

	def test_attribute_value_update_uses_the_locked_standard_attribute_table(self):
		source = _read("essdee_yrp", "essdee_yrp/api/item_attribute.py")
		self.assertIn("ensure_global_attribute_values(attribute_name, clean_values)", source)
		helper = _read("yrp", "yrp/yrp/doctype/yrp_item/yrp_item.py")
		self.assertIn(
			'frappe.db.get_value("Item Attribute", attribute, "name", for_update=True)',
			helper,
		)
		self.assertIn('doc.append("item_attribute_values"', helper)

	def test_lot_onload_is_read_only(self):
		source = _read(
			"essdee_yrp",
			"essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.py",
		)
		onload = source[source.index("\tdef onload(self):") : source.index("\ndef delete_ppo_lot_qty")]
		self.assertNotIn("db_set(", onload)
		self.assertIn("self.set('lot_order_details_json', x)", onload)

	def test_mapping_editors_send_loaded_modified_timestamp(self):
		bom = _read("essdee_yrp", "frontend/src/views/dynamic/BOMMappingEditor.vue")
		matrix = _read("essdee_yrp", "frontend/src/views/dynamic/ProcessMatrixEditor.vue")
		for source in (bom, matrix):
			self.assertIn("loadedModified", source)
			self.assertIn("doc.modified", source)
			self.assertIn("modified:", source)

	def test_ipd_inline_rows_use_fresh_document_and_child_names(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/IPDConfigView.vue")
		self.assertIn("function assertFreshIpd(ipd)", source)
		self.assertIn("function findCurrentChildIndex(rows, childName, fallbackIdx)", source)
		self.assertIn("editingBomName", source)
		self.assertIn("editingProcessName", source)
		self.assertGreaterEqual(source.count("assertFreshIpd(ipd)"), 4)

	def test_desk_ipd_combination_controls_wait_for_vue_matrix_cells(self):
		component = _read(
			"essdee_yrp",
			"essdee_yrp/public/js/Item_Po_detail/CombinationItemDetail.vue",
		)
		plugins = _read("essdee_yrp", "essdee_yrp/public/js/vue_plugins.js")
		self.assertIn("import {nextTick, ref} from 'vue';", component)
		self.assertIn("async function load_data(item)", component)
		self.assertIn("async function set_attributes()", component)
		self.assertGreaterEqual(component.count("await nextTick();"), 2)
		self.assertIn("df['fieldtype'] = 'Data'", component)
		self.assertIn("return this.vue.load_data", plugins)
		self.assertIn("return this.vue.set_attributes", plugins)

	def test_cutting_combination_dia_uses_searchable_data_not_child_link(self):
		component = _read(
			"essdee_yrp",
			"essdee_yrp/public/js/Item_Po_detail/CuttingItemDetail.vue",
		)
		self.assertIn("let fieldtype = 'Autocomplete'", component)
		self.assertNotIn('fieldtype = "Link"', component)
		self.assertIn("params: { attribute: 'Dia' }", component)
		self.assertIn(
			"yrp.yrp.doctype.yrp_item.yrp_item.search_item_attribute_values",
			component,
		)

	def test_stock_pivot_round_trips_entry_fields(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/StockItemGridEditor.vue")
		self.assertIn("function copyEntryFields(source)", source)
		self.assertIn("entryValues: {}", source)
		self.assertIn("draft.entryValues = copyEntryFields(it)", source)
		self.assertGreaterEqual(source.count("...copyEntryFields(it)"), 1)
		self.assertIn("...draft.entryValues", source)

	def test_parent_field_permlevels_are_enforced_in_web_form(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/DocDetail.vue")
		self.assertIn("permlevel: Number(mf.permlevel) || 0", source)
		self.assertIn("function canWriteFieldPermlevel(permlevel)", source)
		self.assertIn("!canWriteFieldPermlevel(f.permlevel)", source)

	def test_attribute_mapping_pencil_requires_mapping_write_permission(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/ItemAttributeListView.vue")
		self.assertIn("canWrite('YRP Item Item Attribute Mapping')", source)
		self.assertIn("const { canWrite } = usePermissions()", source)

	def test_bulk_submit_cancel_carries_loaded_modified(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/DynamicListPage.vue")
		self.assertIn('fields.push("modified")', source)
		self.assertIn("submitDoc(dt, row.name, row.modified)", source)
		self.assertIn("cancelDoc(dt, row.name, row.modified)", source)

	def test_sensitive_delivery_actions_are_permission_gated(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/DocDetail.vue")
		self.assertIn("canWrite(doctype.value) || !!doc.value?.ewaybill", source)
		self.assertGreaterEqual(source.count("canWrite(doctype.value)"), 6)
		self.assertIn('"grn-complete-transfer": "complete_transfer"', source)
		self.assertIn("make_grn_completion", source)
		self.assertIn('canCreate("YRP Stock Entry")', source)

	def test_ewaybill_date_prefill_uses_local_calendar_parts(self):
		source = _read("essdee_yrp", "frontend/src/views/dynamic/EWaybillGenerateModal.vue")
		self.assertIn("function toLocalDate(value)", source)
		self.assertIn("toLocalDate(doc.lr_date)", source)
		self.assertNotIn("doc.lr_date ? new Date(doc.lr_date)", source)

	def test_ui_action_vocabulary_includes_complete_transfer(self):
		from yrp.yrp.api.ui_config import get_registered_action_items

		self.assertIn("complete_transfer", get_registered_action_items())
