# SD YRP Master Sync Plan

## Goal

Sync approved master data from the Frappe 15 `production_api` site into the
Frappe 16 `essdee_yrp.site` site without affecting the existing ERP sync.

The target app is `essdee_yrp`, which customizes the base `yrp` app. Runtime
code in `essdee_yrp` must not call `production_api` APIs, because
`production_api` may be disabled later.

## Transport

- Use Kafka/Spine with a separate topic: `sd_yrp_master`.
- Do not reuse the existing ERP topic or handler mappings.
- Source side publishes events from `production_api`.
- Target side consumes and applies events inside `essdee_yrp`.
- Initial sync must send all records for the selected DocTypes.
- Runtime sync must support create, update, rename, submit, cancel, and delete.
- Do not publish on validation-only hooks.

## Scope

Sync these DocTypes, with child tables included:

- `Item Attribute`
- `Item Attribute Value`
- `Item`
- `Item Item Attribute Mapping`
- `Item Dependent Attribute Mapping`
- `Item Variant`
- `Supplier`
- `Address`
- `Contact`
- `Lot`
- `Production Order`
- `Item Production Detail`
- `UOM`
- `Item Group`
- `Brand`
- `Product Category`
- `Additional Parameter Key`
- `Additional Parameter Value`
- `Department`
- `Terms and Condition`
- `Country`
- `Lot Template`
- `Product Season`
- `Process`
- `Production Term`
- `User`

## Out Of Scope

Do not sync these transaction DocTypes in this feature:

- `Work Order`
- `Purchase Order`
- `Stock Entry`
- `Delivery Challan`
- `Goods Received Note`

## Sync Order

Use this order for initial sync and retry planning:

1. Foundation masters:
   `Country`, `UOM`, `Item Group`, `Brand`, `Department`,
   `Terms and Condition`, `Product Season`, `Product Category`,
   `Additional Parameter Key`, `Additional Parameter Value`,
   `Item Attribute`, `Item Attribute Value`, `Process`, `Production Term`,
   `User`
2. Attribute mappings:
   `Item Item Attribute Mapping`, `Item Dependent Attribute Mapping`
3. Item masters:
   `Item`, `Item Variant`
4. Party masters:
   `Supplier`, `Address`, `Contact`
5. Templates:
   `Lot Template`
6. Production structure:
   `Item Production Detail`, `Production Order`
7. Final dependent document:
   `Lot`

## Implementation Blueprint

This section is the file-by-file implementation map. Follow it from top to
bottom.

### 1. Kafka And Site Config

Kafka is not per bench. It is a server service. Both benches connect to the
same broker using site config.

Source site config:

- File: `/home/anas/frappe-15/sites/<production_api_site>/site_config.json`
- Configure the existing `kafka` block.
- Use the same broker address already used by production_api.
- Keep a source-specific `client.id`, for example `mrp.prod`.
- Runtime events are published to topic `sd_yrp_master`.

Target site config:

- File: `/home/anas/frappe-16/sites/essdee_yrp.site/site_config.json`
- Configure `kafka.bootstrap.servers` with the same broker address.
- Use a target-specific `client.id`, for example `sd_yrp.prod`.
- Use a target-specific `group.id`, for example
  `spine-client-sd-yrp-production`.
- Do not reuse the existing ERP consumer `group.id`.

Message separation:

- Use `Header.Topic = sd_yrp_master`.
- Existing ERP sync remains on its current topic.
- No new `Message Log` field is required unless we later find the existing
  topic-based filtering is insufficient.

### 2. Source Producer Code In Frappe 15

Main source file:

- File:
  `/home/anas/frappe-15/apps/production_api/production_api/sd_yrp_sync.py`

Constants to keep or add:

- `SD_YRP_TOPIC = "sd_yrp_master"`
- `SD_YRP_EXACT_MATCH_DOCTYPES`
  - exact field-copy doctypes
- `SD_YRP_CUSTOM_MAPPER_DOCTYPES`
  - `Item`
  - `Supplier`
  - `User`
  - `Lot Template`
  - `Item Production Detail`
  - `Production Order`
  - `Lot`
- `SD_YRP_SYNC_DOCTYPES`
  - combined exact and custom lists
- `SD_YRP_INITIAL_SYNC_ORDER`
  - same order as the Sync Order section above

Runtime event functions:

- `handle_existing_spine_and_sd_yrp(doc, event, *args)`
  - use only for DocTypes that already publish to existing ERP sync
  - first calls existing Spine `handle_event` for ERP sync
  - then calls `enqueue_sd_yrp_publish`
  - currently needed for `Item Variant` and `Item Group`
- `handle_item_event(doc, event, *args)`
  - preserves existing `Item` update behavior
  - calls `sync_updated_item_variant` on `on_update`
  - then calls `enqueue_sd_yrp_publish`
- `handle_sd_yrp_event(doc, event, *args)`
  - used for DocTypes that only need SD YRP topic publishing
  - does not call the existing ERP Spine handler
- `enqueue_sd_yrp_publish(doc, event, args=None)`
  - enqueues after commit outside developer mode
  - directly publishes in developer mode
- `publish_sd_yrp_event(doc, docevent, extra_args=())`
  - checks `doc.doctype in SD_YRP_SYNC_DOCTYPES`
  - checks `frappe.local.conf.get("kafka")`
  - calls Spine `publish_doc_event`
  - passes `target_topic=SD_YRP_TOPIC`
  - passes `args=extra_args` so `after_rename` includes `rename_meta`
- `clean_doc_for_publish(doc)`
  - converts Document to dict
  - removes transient keys like `__onload` and `_doc_before_save`
- `prepare_sd_yrp_doc_for_publish(doc, event)`
  - create this wrapper before publishing
  - for most DocTypes it returns `clean_doc_for_publish(doc)`
  - for `Lot`, remove Time and Action fields/child tables before publishing
  - for custom DocTypes, keep the source field names; target mapper handles
    conversion

Initial sync functions:

- `trigger_initial_sync(doctype, filters=None, event="first_sync")`
  - runs one DocType
  - validates that the DocType is in `SD_YRP_SYNC_DOCTYPES`
- `trigger_all_initial_sync(event="first_sync")`
  - runs all DocTypes in `SD_YRP_INITIAL_SYNC_ORDER`
- `process_initial_sync(doctype, docnames, event)`
  - loads each source doc and calls `publish_sd_yrp_event`
- `process_all_initial_sync(event)`
  - loops through `SD_YRP_INITIAL_SYNC_ORDER`

Optional helper to add for controlled runs:

- `trigger_ordered_initial_sync(doctypes=None, event="first_sync")`
  - if `doctypes` is empty, use `SD_YRP_INITIAL_SYNC_ORDER`
  - if `doctypes` is passed, preserve the defined dependency order
  - useful for testing a subset like `UOM`, `Item`, `Item Production Detail`

Source hook configuration:

- File:
  `/home/anas/frappe-15/apps/production_api/production_api/hooks.py`

Configure these events only:

- `after_insert`
- `on_update`
- `on_update_after_submit`
- `after_rename`
- `on_submit`
- `on_cancel`
- `on_trash`

Do not configure validation hooks.

Hook groups:

- `Item`
  - handler: `production_api.sd_yrp_sync.handle_item_event`
- `Item Variant`, `Item Group`
  - handler: `production_api.sd_yrp_sync.handle_existing_spine_and_sd_yrp`
  - reason: preserve existing ERP sync and also publish SD YRP topic
- all other scoped DocTypes
  - handler: `production_api.sd_yrp_sync.handle_sd_yrp_event`

The other scoped DocTypes include:

- `User`
- `Country`
- `UOM`
- `Brand`
- `Product Category`
- `Additional Parameter Key`
- `Additional Parameter Value`
- `Department`
- `Terms and Condition`
- `Item Attribute`
- `Item Attribute Value`
- `Item Item Attribute Mapping`
- `Item Dependent Attribute Mapping`
- `Supplier`
- `Address`
- `Contact`
- `Product Season`
- `Process`
- `Production Term`
- `Lot Template`
- `Item Production Detail`
- `Production Order`
- `Lot`

Producer config note:

- Runtime publishing should be hook-based in `hooks.py` for this feature.
- If the existing `Spine Producer Config` UI is used for manual/bulk producer
  setup, the producer handler path is:
  `production_api.sd_yrp_sync.produce_exact_doc`
- The SD YRP runtime path must still publish to `sd_yrp_master` so it does not
  disturb the existing ERP topic.

### 3. Target Consumer Code In Frappe 16

Main target file:

- File:
  `apps/essdee_yrp/essdee_yrp/sd_yrp_sync.py`

Constants to keep or add:

- `SD_YRP_TOPIC = "sd_yrp_master"`
- `EXACT_MATCH_DOCTYPES`
  - exact field-copy doctypes
- `CUSTOM_MAPPER_DOCTYPES`
  - `Item`
  - `Supplier`
  - `User`
  - `Lot Template`
  - `Item Production Detail`
  - `Production Order`
  - `Lot`
- `SYNC_DOCTYPES`
  - combined exact and custom lists
- `HANDLER_PATH = "essdee_yrp.sd_yrp_sync.handle_sd_yrp_message"`

Consumer entry point:

- `handle_sd_yrp_message(payload)`
  - validates `Header.Topic == SD_YRP_TOPIC`
  - validates `Header.DocType in SYNC_DOCTYPES`
  - routes by event:
    - `after_insert`, `first_sync`, `on_update`,
      `on_update_after_submit` -> `upsert_doc`
    - `after_rename`, `rename` -> `rename_synced_doc`
    - `on_trash` -> `delete_synced_doc`
    - `on_submit` -> `submit_synced_doc`
    - `on_cancel` -> `cancel_synced_doc`
- `handle_exact_match(payload)`
  - keep as a backward-compatible wrapper:
    `return handle_sd_yrp_message(payload)`
  - after consumer config is migrated, new rows should use
    `handle_sd_yrp_message`

Generic write helpers:

- `upsert_doc(payload)`
  - calls custom mapper when DocType needs one
  - otherwise calls exact mapper
- `upsert_filtered_doc(data)`
  - generic insert/update after field filtering
- `clean_payload(payload)`
  - removes source audit/transient fields
- `filter_doc_fields(data)`
  - keeps only fields that exist in target metadata
- `filter_child_row(row, child_doctype)`
  - keeps only child fields that exist in target metadata
- `replace_child_table(doc, fieldname, rows)`
  - add this helper for custom mappers that must fully replace rows
- `get_item_default_uom(item_code)`
  - add this helper for `Item BOM` row fallback
- `validate_required_link(doctype, name, source_context)`
  - add this helper to raise clear missing dependency errors

Existing custom mappers:

- `upsert_user(data)`
  - skips `Administrator` and `Guest`
  - syncs safe profile fields and roles
  - sets `send_welcome_email = 0`
- `get_user_roles(roles)`
  - filters missing roles and logs skipped roles
- `upsert_supplier(data)`
  - ignores source `terms_and_condition`
  - ignores source `price_html`
  - saves target `Supplier`
  - calls `sync_supplier_warehouse`
- `sync_supplier_warehouse(supplier, supplier_data, supplier_users)`
  - creates/updates one warehouse for the supplier
  - maps source `supplier_users` into `Warehouse.warehouse_users`
- `get_warehouse_users(supplier_users)`
  - filters duplicate/missing users
- `rename_supplier_warehouse(old_supplier, new_supplier)`
  - renames or relinks the auto-created warehouse
- `upsert_country(data)`
  - skips creating new target Country when Frappe 16 requires missing `code`

New custom mappers to add:

- `upsert_item(data)`
  - syncs target Item fields after filtering
  - maps custom `product_category`
  - keeps `over_delivery_receipt_allowance`, `price_section`, and `price_html`
    because they exist in base `yrp`
  - does not create `Item Price`
- `upsert_lot_template(data)`
  - exact parent copy
  - maps child `Item BOM` rows through `map_item_bom_row`
- `map_item_bom_row(row, source_context)`
  - ensures target `uom` is filled
  - source `uom` wins
  - fallback is BOM item's `default_unit_of_measure`
  - leaves target-only `wastage_pct` default/blank
- `upsert_item_production_detail(data)`
  - exact parent field copy after filtering
  - replaces `item_attributes`, `item_bom`, and `ipd_processes` through
    mapper helpers
  - copies the replicated packing-to-cloth-accessory fields normally
- `map_ipd_item_attribute_row(row)`
  - source child DocType `Item Item Attribute`
  - target child DocType `IPD Item Attribute`
  - maps `attribute` and `mapping`
- `map_ipd_bom_row(row, source_context)`
  - uses the same UOM fallback rule as `map_item_bom_row`
  - leaves `wastage_pct` default/blank
- `map_ipd_process_row(row)`
  - maps source `stage` into both target fields:
    `in_stage = stage`, `out_stage = stage`
  - maps `process_name` directly when source provides it
- `upsert_production_order(data)`
  - maps one source production order into the target multi-item structure as
    one target production order with one item row
  - calls `validate_yrp_settings_for_production_order`
- `validate_yrp_settings_for_production_order()`
  - confirms YRP Settings has `Size` as grid attribute
  - confirms dependent attributes include the configured `Stage` and `Pack`
- `map_production_order_item_rows(data)`
  - creates the target production-order item rows expected by YRP
- `upsert_lot(data)`
  - strips Time and Action fields/children
  - ensures `Item`, `Item Variant`, `Production Order`,
    `Item Production Detail`, and `Lot Template` exist first
  - then saves the target Lot
- `strip_lot_time_and_action_fields(data)`
  - removes every Lot field and child table related to Time and Action

Delete handlers:

- `delete_synced_doc(payload)`
  - `User`: disable instead of hard delete
  - `Supplier`: disable supplier and mapped warehouse
  - `Lot`, `Production Order`, `Item Production Detail`, `Lot Template`:
    delete only when target links allow it; otherwise raise retryable error
  - exact masters: delete with `frappe.delete_doc` when safe

Submit/cancel handlers:

- `submit_synced_doc(payload)`
  - submit only if target DocType is submittable and docstatus is 0
- `cancel_synced_doc(payload)`
  - cancel only if target DocType is submittable and docstatus is 1

Consumer config setup:

- Function:
  `ensure_consumer_config()`
- File:
  `apps/essdee_yrp/essdee_yrp/sd_yrp_sync.py`
- It must create/update `Spine Consumer Handler Mapping` rows for every
  `SYNC_DOCTYPES` item with:
  - `document_type = <doctype>`
  - `topic = sd_yrp_master`
  - `event_handler = essdee_yrp.sd_yrp_sync.handle_sd_yrp_message`
- It must also call `ensure_consumer_processing_enabled()`.

Patch that calls consumer setup:

- File:
  `apps/essdee_yrp/essdee_yrp/patches/setup_sd_yrp_spine_consumer.py`
- Function:
  `execute()`
- It should call:
  `essdee_yrp.sd_yrp_sync.ensure_consumer_config()`

Patch registration:

- File:
  `apps/essdee_yrp/essdee_yrp/patches.txt`
- Keep `essdee_yrp.patches.setup_sd_yrp_spine_consumer` in
  `[post_model_sync]`.

### 4. Target App Hooks And Fixtures

Target hooks file:

- File:
  `apps/essdee_yrp/essdee_yrp/hooks.py`

Required app:

- `required_apps = ["yrp"]`
- This makes `essdee_yrp` install only when base `yrp` is installed.

Fixtures:

- Keep `Custom Field` fixtures for:
  - `Item-product_category`
  - `Supplier-apply_sewing_plan`
  - `Process-item`
  - `Process-includes_packing`
  - `Process-additional_allowance`
  - all custom fields where `dt = "Item Production Detail"`

IPD UI and validation hooks:

- `app_include_js = ["essdee_yrp.bundle.js"]`
- `doctype_js = {"Item Production Detail": "public/js/item_production_detail.js"}`
- `doctype_list_js = {"Item Production Detail": "public/js/item_production_detail_list.js"}`
- `doc_events["Item Production Detail"]`
  - `onload`: `essdee_yrp.ipd_ui.onload`
  - `before_validate`: `essdee_yrp.ipd_validations.before_validate`
  - `validate`: `essdee_yrp.ipd_validations.validate`
  - `on_update`: `essdee_yrp.ipd_validations.on_update`
  - `on_trash`: `essdee_yrp.ipd_validations.on_trash`

The Kafka consumer itself is not configured in `doc_events`; it is configured
through `Spine Consumer Handler Mapping`.

Custom field patches:

- `apps/essdee_yrp/essdee_yrp/patches/setup_sd_yrp_custom_fields_and_consumer.py`
- `apps/essdee_yrp/essdee_yrp/patches/setup_sd_yrp_item_custom_fields.py`
- `apps/essdee_yrp/essdee_yrp/patches/setup_sd_yrp_process_custom_fields.py`
- `apps/essdee_yrp/essdee_yrp/patches/setup_sd_yrp_ipd_custom_fields.py`
- `apps/essdee_yrp/essdee_yrp/patches/sync_sd_yrp_ipd_custom_field_metadata.py`

Fixture file:

- File:
  `apps/essdee_yrp/essdee_yrp/fixtures/custom_field.json`

### 5. Base YRP Changes Needed Before Sync

Base app Item DocType:

- File:
  `apps/yrp/yrp/yrp/doctype/item/item.json`
- Required fields:
  - `over_delivery_receipt_allowance`
  - `price_section`
  - `price_html`

Base app Production Term DocType:

- File:
  `apps/yrp/yrp/yrp/doctype/production_term/production_term.json`
- `production_term_details` must not block sync as mandatory.

Base app Process child table:

- File:
  `apps/yrp/yrp/yrp/doctype/process/process.json`
- `process_details.options` must be `Process Details`.
- Child DocType folder:
  `apps/yrp/yrp/yrp/doctype/process_details`
- Patch:
  `yrp.patches.rename_process_detail_to_process_details`

### 6. Mapper Responsibility Table

| Source DocType | Producer hook/function | Consumer mapper/function |
| --- | --- | --- |
| `Country` | `handle_sd_yrp_event` | `upsert_country` |
| `UOM` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Item Group` | `handle_existing_spine_and_sd_yrp` | `upsert_filtered_doc` |
| `Brand` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Product Category` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Additional Parameter Key` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Additional Parameter Value` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Department` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Terms and Condition` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Product Season` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Process` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Production Term` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Item Attribute` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Item Attribute Value` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Item Item Attribute Mapping` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Item Dependent Attribute Mapping` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Item` | `handle_item_event` | `upsert_item` |
| `Item Variant` | `handle_existing_spine_and_sd_yrp` | `upsert_filtered_doc` |
| `User` | `handle_sd_yrp_event` | `upsert_user` |
| `Supplier` | `handle_sd_yrp_event` | `upsert_supplier` |
| `Address` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Contact` | `handle_sd_yrp_event` | `upsert_filtered_doc` |
| `Lot Template` | `handle_sd_yrp_event` | `upsert_lot_template` |
| `Item Production Detail` | `handle_sd_yrp_event` | `upsert_item_production_detail` |
| `Production Order` | `handle_sd_yrp_event` | `upsert_production_order` |
| `Lot` | `handle_sd_yrp_event` | `upsert_lot` |

### 7. Initial Sync Runbook

Run from the source Frappe 15 bench after Kafka config is present:

```bash
bench --site <production_api_site> execute production_api.sd_yrp_sync.trigger_all_initial_sync
```

For a controlled test:

```bash
bench --site <production_api_site> execute production_api.sd_yrp_sync.trigger_initial_sync --kwargs "{'doctype': 'UOM'}"
bench --site <production_api_site> execute production_api.sd_yrp_sync.trigger_initial_sync --kwargs "{'doctype': 'Item Attribute'}"
bench --site <production_api_site> execute production_api.sd_yrp_sync.trigger_initial_sync --kwargs "{'doctype': 'Item'}"
bench --site <production_api_site> execute production_api.sd_yrp_sync.trigger_initial_sync --kwargs "{'doctype': 'Item Production Detail'}"
```

Run target setup/migration from the Frappe 16 bench:

```bash
bench --site essdee_yrp.site migrate
bench build --app essdee_yrp
```

Verify target consumer mapping:

```bash
bench --site essdee_yrp.site execute essdee_yrp.sd_yrp_sync.ensure_consumer_config
```

## Exact Sync DocTypes

These DocTypes can use exact upsert/rename/delete handling after ignoring
target-only extra fields:

- `Item Attribute`
- `Item Attribute Value`
- `UOM`
- `Item Group`
- `Brand`
- `Product Category`
- `Additional Parameter Key`
- `Additional Parameter Value`
- `Department`
- `Terms and Condition`
- `Country`
- `Product Season`
- `Process`
- `Production Term`
- `Item Item Attribute Mapping`
- `Item Dependent Attribute Mapping`
- `Item Variant`
- `Address`
- `Contact`

Notes:

- `Process` target has custom fields from `essdee_yrp`: `item`,
  `includes_packing`, `additional_allowance`.
- `Process.process_details` must use child table `Process Details`.
- Target-only extra fields are not blockers.

## Custom Mapper DocTypes

### User

Rules:

- Do not create or overwrite `Administrator` or `Guest`.
- Sync safe profile fields and roles.
- On delete, disable the target user instead of hard deleting.

### Supplier

Rules:

- Create/update `Supplier`.
- Do not sync source `terms_and_condition` into target supplier.
- Do not treat target-only fields as blockers.
- Create or update the matching target `Warehouse` for the supplier.
- Map source supplier users into the warehouse user table.
- On delete, disable the supplier and matching warehouse instead of hard deleting.
- On rename, rename/update the linked warehouse if it was auto-created for the supplier.

### Item

Rules:

- Sync normal item fields.
- Target extra fields are not blockers.
- `product_category` is an `essdee_yrp` custom field.
- `over_delivery_receipt_allowance`, `price_section`, and `price_html`
  exist in the base `yrp` Item DocType.
- Do not sync `Item Price` as a separate required DocType for this feature.

### Lot Template

Rules:

- Parent `Lot Template` can sync normally.
- Child `Item BOM` must respect target metadata:
  - target `uom` is mandatory Link to `UOM`
  - if source `uom` exists, use it
  - if source `uom` is empty, use the BOM item's `default_unit_of_measure`
- Target extra `wastage_pct` is not a blocker.
- If `attribute_mapping` is used, ensure the referenced `Item BOM Attribute Mapping`
  exists before saving the row.

### Item Production Detail

The production_api packing-to-cloth-accessory section has been replicated in
`essdee_yrp`, including custom fields, fixtures, JS views, Vue widgets, and
server-side validations.

Parent DocType differences are accepted:

- Target has extra `amended_from`; ignore it.

Child mapper rules:

- `item_attributes`
  - Source child table: `Item Item Attribute`
  - Target child table: `IPD Item Attribute`
  - Map same values: `attribute`, `mapping`
- `item_bom`
  - Source `uom` is optional Data.
  - Target `uom` is mandatory Link to `UOM`.
  - Use source `uom` if available.
  - If source `uom` is empty, use BOM item's `default_unit_of_measure`.
  - Target extra `wastage_pct` can remain default/blank.
  - Target default values for `qty_of_product` and `qty_of_bom_item` are fine.
  - Target `attribute_mapping` visibility depends on `based_on_attribute_mapping`;
    this is not a data issue.
- `ipd_processes`
  - Source child table has one field: `stage`.
  - Target child table has `in_stage` and `out_stage`.
  - Map source `stage` into both target fields:
    `in_stage = stage`, `out_stage = stage`.
  - `process_name` maps directly.

No remaining IPD DocType difference blocks sync.

### Production Order

Rules:

- Source production order represents one item.
- Target YRP supports multiple items in one production order.
- Map each source production order into the target production order structure
  as a single-item production order.
- YRP Settings must be configured before sync:
  - `production_order_attributes`: include `Size` and mark it as grid attribute.
  - dependent attribute should use the agreed `Stage` and `Pack` configuration.
- The mapper must create the target rows using YRP's expected production order
  item structure, not a raw exact field copy.

### Lot

Rules:

- The target `Lot` DocType was replicated from production_api, excluding
  Time and Action fields.
- Do not sync Time and Action values.
- Sync `Lot` only after dependencies exist:
  - `Item`
  - `Item Variant`
  - `Production Order`
  - `Item Production Detail`
  - `Lot Template`
- Target-only harmless fields should be ignored.
- Delete should follow the standard target behavior. If linked documents prevent
  delete, mark the sync error and retry after dependency correction.

## Event Handling

For every scoped DocType:

- Create: insert if missing, update if exists.
- Update: update existing target document by source name.
- Rename: rename target document when allowed; otherwise update link references
  using mapper-specific logic.
- Submit: submit target document if target DocType is submittable.
- Cancel: cancel target document if target DocType is submittable.
- Delete: delete when safe; otherwise mapper may disable the document where
  deletion is unsafe or not desired.

DocTypes currently discussed as disable-on-delete:

- `User`
- `Supplier`
- auto-created supplier `Warehouse`

## Error Handling

- Every consumed message should be idempotent.
- Missing dependency errors should leave the message retryable.
- Validation errors should write a clear failure reason in the received message log.
- Mapper errors must include:
  - source DocType
  - source document name
  - event type
  - missing linked DocType/name when applicable
- Do not allow a failed SD YRP sync message to affect existing ERP sync.

## Preflight Checks

Before initial sync:

- Confirm `yrp` is installed before `essdee_yrp`.
- Confirm target custom fields and fixtures are migrated.
- Confirm Spine consumer mapping exists for `sd_yrp_master`.
- Confirm all required child DocTypes exist in target.
- Confirm required foundation masters exist or are included earlier in sync order.
- Confirm `UOM` records exist for all source BOM `uom` values.
- Confirm `YRP Settings` production order attributes are configured.
- Confirm there are no runtime calls from `essdee_yrp` to `production_api`.

## Verification Plan

Run after implementation:

1. Build assets:
   `bench build --app essdee_yrp`
2. Migrate target:
   `bench --site essdee_yrp.site migrate`
3. Verify hooks:
   - source doc events publish to `sd_yrp_master`
   - target consumer handlers exist for all scoped DocTypes
4. Run a small initial sync batch:
   - `Item Attribute`
   - `Item Attribute Value`
   - `UOM`
   - one `Item`
   - one `Item Production Detail`
5. Validate Desk forms:
   - IPD fields appear based on visibility rules
   - IPD JSON views render
   - IPD validation works without production_api dependency
6. Run dependency sync:
   - `Production Order`
   - `Lot Template`
   - `Lot`
7. Confirm no `production_api` import/call exists in target app or built assets:
   `rg "production_api|essdee_production" apps/essdee_yrp sites/assets/essdee_yrp`

## Acceptance Criteria

- Existing ERP sync behavior is unchanged.
- All scoped DocTypes can be initial synced to `essdee_yrp.site`.
- Create, update, rename, submit, cancel, and delete events are handled.
- `Supplier`, `Item Production Detail`, `Production Order`, and `Lot` use their
  custom mapper rules.
- IPD form and validation work without runtime dependency on `production_api`.
- No blocking DocType differences remain.
