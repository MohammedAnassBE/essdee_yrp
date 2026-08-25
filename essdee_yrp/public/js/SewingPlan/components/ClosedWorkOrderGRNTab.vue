<template>
    <div class="closed-wo-grn-tab">
        <div class="filter-card">
            <div class="filter-copy">
                <h3>Closed Work Order GRN</h3>
                <p>Select a closed Work Order for the chosen warehouse and create its GRN.</p>
            </div>
            <div ref="work_order_wrapper" class="work-order-control"></div>
            <button
                class="btn btn-primary create-button"
                :disabled="!selected_work_order || loading"
                @click="openGRNDialog"
            >
                {{ loading ? 'Loading...' : 'Create GRN' }}
            </button>
        </div>

        <div class="notice-card">
            <div class="notice-icon">i</div>
            <div>
                <strong>Closed Work Orders only</strong>
                <p>
                    Material stock was already adjusted while closing the Work Order.
                    This GRN receives the finished items without consuming those materials again.
                </p>
            </div>
        </div>
    </div>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
    selected_supplier: {
        type: String,
        default: null,
    },
    refresh_counter: {
        type: Number,
        default: 0,
    },
})

const work_order_wrapper = ref(null)
const selected_work_order = ref(null)
const loading = ref(false)
let workOrderControl = null

const callServer = (method, args, freeze = false, freezeMessage = null) => {
    return new Promise((resolve, reject) => {
        frappe.call({
            method,
            args,
            freeze,
            freeze_message: freezeMessage,
            callback: (response) => resolve(response.message),
            error: (error) => reject(error),
        })
    })
}

const initializeWorkOrderControl = () => {
    if (!work_order_wrapper.value || workOrderControl) return

    workOrderControl = frappe.ui.form.make_control({
        parent: $(work_order_wrapper.value),
        df: {
            fieldtype: 'Link',
            fieldname: 'closed_work_order',
            label: 'Work Order',
            options: 'Work Order',
            placeholder: 'Select a closed Work Order',
            get_query: () => ({
                query: 'essdee_yrp.sewing.closed_work_order.get_closed_sewing_work_orders',
                filters: {
                    supplier: props.selected_supplier,
                },
            }),
            change: () => {
                selected_work_order.value = workOrderControl.get_value() || null
            },
        },
        render_input: true,
    })
}

const resetWorkOrder = () => {
    selected_work_order.value = null
    if (workOrderControl) {
        workOrderControl.set_value('')
    }
}

const showCreatedMessage = (name) => {
    const safeName = frappe.utils.escape_html(name)
    frappe.msgprint({
        title: 'GRN Created',
        indicator: 'green',
        message: `Goods Received Note <a href="/app/goods-received-note/${encodeURIComponent(name)}"><b>${safeName}</b></a> was created and submitted.`,
    })
}

const itemsHtml = (rows) => {
    const escape = frappe.utils.escape_html
    const body = (rows || []).map((row, index) => `
        <tr>
            <td>${escape(row.item_variant || '')}</td>
            <td>${escape(row.received_type || '-')}</td>
            <td class="text-right">${format_number(row.pending_quantity || 0)}</td>
            <td class="text-right">${format_number(row.max_receivable_quantity || 0)}</td>
            <td style="min-width: 120px">
                <input class="form-control input-sm text-right" type="number" min="0"
                    step="0.001" value="0" data-sewing-row="${index}">
            </td>
        </tr>`).join('')
    return `
        <div class="table-responsive" style="max-height: 52vh; overflow: auto">
            <table class="table table-bordered table-sm">
                <thead class="sticky-top bg-white">
                    <tr><th>Item Variant</th><th>Received Type</th>
                    <th class="text-right">Pending</th><th class="text-right">Allowed</th>
                    <th class="text-right">Receive Qty</th></tr>
                </thead>
                <tbody>${body}</tbody>
            </table>
        </div>`
}

const buildItemDetails = (dialog, details) => {
    const payload = JSON.parse(JSON.stringify(details.item_details || []))
    const quantities = new Map()
    dialog.$wrapper.find('[data-sewing-row]').each((_, input) => {
        const row = details.items[cint(input.dataset.sewingRow)]
        const key = `${row.ref_docname}::${row.received_type || ''}`
        quantities.set(key, flt(input.value))
    })
    for (const group of payload) {
        for (const item of group.items || []) {
            const receivedType = item.dimensions?.received_type || ''
            for (const value of Object.values(item.values || {})) {
                const key = `${value.ref_docname || ''}::${receivedType}`
                value.qty = quantities.get(key) || 0
            }
        }
    }
    return payload
}

const openGRNDialog = async () => {
    if (!props.selected_supplier || !selected_work_order.value || loading.value) return

    loading.value = true
    try {
        const details = await callServer(
            'essdee_yrp.sewing.closed_work_order.get_closed_work_order_grn_details',
            {
                work_order: selected_work_order.value,
                supplier: props.selected_supplier,
            },
            true,
            'Fetching closed Work Order details...'
        )

        if (!details.has_pending_items || !details.item_details?.length) {
            frappe.msgprint({
                title: 'Nothing Pending',
                indicator: 'orange',
                message: 'This Work Order has no pending receivable quantity.',
            })
            return
        }

        const today = frappe.datetime.get_today()
        const dialog = new frappe.ui.Dialog({
            title: `Create GRN - ${details.work_order}`,
            size: 'extra-large',
            fields: [
                {
                    fieldtype: 'HTML',
                    fieldname: 'work_order_summary',
                    options: `
                        <div class="closed-wo-summary">
                            <span><b>Work Order:</b> ${frappe.utils.escape_html(details.work_order)}</span>
                            <span><b>Unit:</b> ${frappe.utils.escape_html(details.supplier || '-')}</span>
                            <span><b>Item:</b> ${frappe.utils.escape_html(details.item || '-')}</span>
                            <span><b>Lot:</b> ${frappe.utils.escape_html(details.lot || '-')}</span>
                            <span><b>Process:</b> ${frappe.utils.escape_html(details.process || '-')}</span>
                        </div>
                    `,
                },
                {
                    fieldtype: 'Section Break',
                    label: 'GRN Details',
                },
                {
                    fieldtype: 'Check',
                    fieldname: 'edit_posting_date_and_time',
                    label: 'Edit Posting Date and Time',
                    default: 0,
                    change: () => {
                        const editable = Boolean(dialog.get_value('edit_posting_date_and_time'))
                        dialog.set_df_property('posting_date', 'read_only', editable ? 0 : 1)
                        dialog.set_df_property('posting_time', 'read_only', editable ? 0 : 1)
                    },
                },
                {
                    fieldtype: 'Column Break',
                },
                {
                    fieldtype: 'Date',
                    fieldname: 'posting_date',
                    label: 'Posting Date',
                    default: today,
                    reqd: 1,
                    read_only: 1,
                },
                {
                    fieldtype: 'Time',
                    fieldname: 'posting_time',
                    label: 'Posting Time',
                    default: frappe.datetime.now_time(),
                    reqd: 1,
                    read_only: 1,
                },
                {
                    fieldtype: 'Date',
                    fieldname: 'delivery_date',
                    label: 'Delivery Date',
                    default: today,
                    reqd: 1,
                },
                {
                    fieldtype: 'Column Break',
                },
                {
                    fieldtype: 'Data',
                    fieldname: 'supplier_document_no',
                    label: 'Supplier Document Number',
                    reqd: 1,
                },
                {
                    fieldtype: 'Date',
                    fieldname: 'supplier_document_date',
                    label: 'Supplier Document Date',
                    default: today,
                },
                {
                    fieldtype: 'Data',
                    fieldname: 'vehicle_no',
                    label: 'Vehicle Number',
                    reqd: 1,
                },
                {
                    fieldtype: 'Section Break',
                    label: 'Received Items',
                },
                {
                    fieldtype: 'HTML',
                    fieldname: 'item_editor',
                    options: itemsHtml(details.items),
                },
                {
                    fieldtype: 'Section Break',
                },
                {
                    fieldtype: 'Data',
                    fieldname: 'dc_no',
                    label: 'DC No',
                },
                {
                    fieldtype: 'Column Break',
                },
                {
                    fieldtype: 'Small Text',
                    fieldname: 'comments',
                    label: 'Comments',
                },
            ],
            primary_action_label: 'Create & Submit GRN',
            primary_action: async (values) => {
                const itemDetails = buildItemDetails(dialog, details)
                const hasQuantity = itemDetails.some((group) =>
                    (group.items || []).some((item) =>
                        Object.values(item.values || {}).some((value) => flt(value.qty) > 0)
                    )
                )
                if (!hasQuantity) {
                    frappe.msgprint('Enter a received quantity for at least one item.')
                    return
                }

                dialog.disable_primary_action()
                try {
                    const headerValues = {
                        edit_posting_date_and_time: values.edit_posting_date_and_time,
                        posting_date: values.posting_date,
                        posting_time: values.posting_time,
                        delivery_date: values.delivery_date,
                        supplier_document_no: values.supplier_document_no,
                        supplier_document_date: values.supplier_document_date,
                        vehicle_no: values.vehicle_no,
                        dc_no: values.dc_no,
                        comments: values.comments,
                    }
                    const result = await callServer(
                        'essdee_yrp.sewing.closed_work_order.create_closed_work_order_grn',
                        {
                            work_order: details.work_order,
                            supplier: props.selected_supplier,
                            values: headerValues,
                            item_details: itemDetails,
                        },
                        true,
                        'Creating and submitting GRN...'
                    )
                    dialog.hide()
                    resetWorkOrder()
                    showCreatedMessage(result.name)
                } finally {
                    dialog.enable_primary_action()
                }
            },
        })

        dialog.show()
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    nextTick(initializeWorkOrderControl)
})

watch(
    () => props.selected_supplier,
    () => resetWorkOrder()
)

watch(
    () => props.refresh_counter,
    () => resetWorkOrder()
)
</script>

<style scoped>
.closed-wo-grn-tab {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.filter-card {
    display: grid;
    grid-template-columns: minmax(240px, 1fr) minmax(280px, 420px) auto;
    gap: 1.25rem;
    align-items: end;
    padding: 1.5rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.75rem;
    background: #fff;
}

.filter-copy h3 {
    margin: 0 0 0.35rem;
    color: #111827;
    font-size: 1.1rem;
    font-weight: 600;
}

.filter-copy p,
.notice-card p {
    margin: 0;
    color: #6b7280;
    line-height: 1.5;
}

.work-order-control {
    min-width: 0;
}

.create-button {
    min-height: 38px;
    white-space: nowrap;
}

.notice-card {
    display: flex;
    gap: 0.8rem;
    padding: 1rem 1.25rem;
    border: 1px solid #bfdbfe;
    border-radius: 0.75rem;
    background: #eff6ff;
    color: #1e3a8a;
}

.notice-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 24px;
    width: 24px;
    height: 24px;
    border-radius: 999px;
    background: #2563eb;
    color: white;
    font-weight: 700;
}

.notice-card strong {
    display: block;
    margin-bottom: 0.2rem;
}

@media (max-width: 900px) {
    .filter-card {
        grid-template-columns: 1fr;
        align-items: stretch;
    }
}

:global(.closed-wo-summary) {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem 1.5rem;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    background: #f3f4f6;
}
</style>
