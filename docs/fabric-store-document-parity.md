# Fabric Store document parity

This is the compact acceptance inventory for the `/web` Purchase Order, Work Order, Delivery Challan, and Goods Received Note workspaces. The server decides every capability; the browser renders only returned actions. Related DC/GRN work stays inside the maximizable popup and never changes the parent route.

## Purchase Order

| Area | `/web` behavior |
| --- | --- |
| Draft | Create/edit the server-defined fields and item matrix; authoritative item schema and supplier price lookup; Save Draft and Submit only with their capabilities. |
| Approval | Send Request, Approve PO, Reject PO, refresh approval status, and display the live request state. |
| Submitted | Cancel, Amend, Close/Reopen, Refresh Status, Manage Linked Lots with a mandatory reason, and Print. |
| Related documents | Create Delivery Challan and Create GRN in the shared maximizable popup; mutations refresh the PO without navigation. |
| Supplier communication | Send SMS and Send WhatsApp through the shared template/recipient panel when the server returns those capabilities. |

## Work Order

| Area | `/web` behavior |
| --- | --- |
| Draft | Create/edit complete server-projected fields, dimensions, deliverables and receivables; retain garment and fabric calculation flows. |
| Lifecycle | Save, Submit, Cancel, Amend, Close approval, Change Delivery Date, Change Item, Create Debit, and Create Rework according to server capabilities. |
| Related work | Make DC and Make GRN open the same routed document workspaces in a maximizable popup. Existing linked documents reopen there; Save/Submit stays in place and refreshes the WO. |
| Cutting | Make Cutting Plan retains the source Work Order, Lot, Item, and production detail. |

## Delivery Challan

| Area | `/web` behavior |
| --- | --- |
| Draft | Source preview, complete projected fields, item/correction matrices, Save Draft, and permission-gated Submit. |
| Submitted | Cancel, Amend, Return, Complete Transfer, Print, and related document inspection. |
| Supplier communication | Send SMS and Send WhatsApp use the same shared panel and disappear without the server capability. |
| Context | The routed page and WO/PO popup use one component and one server contract. |

## Goods Received Note

| Area | `/web` behavior |
| --- | --- |
| Draft | Work Order or PO source defaults, fields, item/correction matrices, totals, Save Draft, and permission-gated Submit. |
| Calculation | Calculate is available only for a saved, clean, eligible WO GRN; it retains authoritative availability, split rows, Received Type, totals, and stale-snapshot protection. |
| Inspection | Create Inspection Entry supports split quantities and draft/submit permissions independently; the aggregate cannot exceed the source quantity. |
| Submitted | Cancel, Amend, Complete Transfer, Print, and related inspection/completion state. |
| Supplier communication | Send SMS and Send WhatsApp use the shared panel and server-authorized preparation/send commands. |
| Context | The routed page and WO/PO popup use one component; popup saves refresh the parent without navigation. |

## Notification authority

Preparation reuses the existing YRP context builders. Sending delegates unchanged to the logged services:

- SMS: `yrp.notification.send_flow_sms_notification`
- WhatsApp: `yrp.whatsapp_notification.send_whatsapp_notification`

The server requires a saved, non-cancelled eligible document, Supplier/contact number, channel configuration, template availability, and raw document write permission. The client cannot manufacture either action.

## Compatibility

The obsolete `WorkOrderTransactionEditor` and `PurchaseOrderGrnEditor`, their API wrappers, and their four reduced server endpoints were removed. All new and existing DC/GRN flows use the focused domain services and `RelatedDocumentWorkspaceDialog`. Generic stock-operation endpoints and still-used document lifecycle/return/transfer adapters remain for their active callers.

## Acceptance gate

- Focused server tests cover capability/status/permission decisions, authoritative row handling, lifecycle commands, calculation, inspection, and exact notification delegation.
- Browser suites cover routes, popup reuse, no parent navigation, permission-hidden actions, action payloads, stale-state handling, and responsive layouts.
- `verify_fabric_store_workspace.mjs all`, the production frontend build, Python compilation, and the full Fabric Store server suites must all pass before completion.
