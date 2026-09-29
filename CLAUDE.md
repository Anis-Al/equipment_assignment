# equipment_assignment

Base module depends on `hr` only. **Keep it that way.** Stock integration goes in
the bridge module below, never in this module.

## Plan — Level 2: inventory link (NOT STARTED)

Goal: equipment that arrives on a validated receipt with serial numbers becomes
`equipment.item` records in one click, with product, serial, vendor, date and value
filled in. Assignment/return/transfer are **unchanged**: no stock moves, no pickings
on handover (that's level 3, rejected: two sources of truth, pickings blocking
handovers, reservations fighting the `_unique_open_assignment` concurrency guard).

### Module

`server/odoo/mnt/equipment_assignment_stock/`

```python
{
    'name': 'Equipment Assignment - Inventory',
    'version': '19.0.1.0.0',
    'depends': ['equipment_assignment', 'stock'],
    'auto_install': True,
    'data': ['views/product_template_views.xml', 'views/equipment_item_views.xml',
             'views/stock_lot_views.xml', 'views/stock_picking_views.xml'],
    'license': 'LGPL-3',
}
```

Depends on `stock`, not `purchase`: vendor = `picking.partner_id`, value =
`move.price_unit`. Both are stock fields, and both are filled from the PO when purchase
is installed. No `purchase` dependency until a PO field is truly needed.

No new models, so no `ir.model.access.csv`. Existing officer/manager ACLs cover
`equipment.item`, and stock ACLs cover lots/pickings.

### Files

```
equipment_assignment_stock/
  __init__.py  __manifest__.py
  models/  __init__.py  product_template.py  equipment_item.py  stock_lot.py  stock_picking.py
  views/   product_template_views.xml  equipment_item_views.xml  stock_lot_views.xml  stock_picking_views.xml
  tests/   __init__.py  test_receipt_to_equipment.py
```

### Step 1 — mark which products are equipment

`product.template.equipment_category_id = Many2one('equipment.category')`.
Set = "this product is equipment, and here is its category". This is the only switch.
It also supplies the required `category_id` so the create action asks nothing.

View: add it to the product form's Inventory tab (inherit `product.product_template_form_view`),
`groups="equipment_assignment.group_equipment_manager"`.

### Step 2 — fields on `equipment.item`

```python
product_id = fields.Many2one('product.product', check_company=True, tracking=True)
lot_id = fields.Many2one(
    'stock.lot', string='Lot/Serial', copy=False, index='btree_not_null',
    ondelete='restrict', check_company=True, domain="[('product_id', '=', product_id)]",
)
_lot_uniq = models.UniqueIndex('(lot_id) WHERE lot_id IS NOT NULL',
                               'This serial number is already linked to another equipment.')
```

- `serial_number` stays in the base module. In `create`/`write`, when `lot_id` is in
  vals, set `serial_number = lot.name`. Don't redefine the base field as a compute.
- `@api.constrains('lot_id', 'product_id')`: `lot.product_id == product_id`.
- Form: `product_id` and `lot_id` next to `serial_number` (inherit
  `equipment_assignment.equipment_item_view_form`). Make `serial_number` readonly when `lot_id` is set.
- `ondelete='restrict'` on the lot means a lot with equipment can't be deleted. That's intended.
- Lifecycle guard is untouched: `product_id`/`lot_id` aren't in `LIFECYCLE_FIELDS`.

### Step 3 — lot → equipment smart button

`stock.lot.equipment_ids = One2many('equipment.item', 'lot_id')` and
`equipment_count` (`_read_group` pattern, like `_compute_assignment_count`).
Smart button on `stock.view_production_lot_form` shows the holder at a glance,
`groups="equipment_assignment.group_equipment_officer"`.

### Step 4 — "Create Equipment" on receipts (the core)

`stock.picking.action_create_equipment()`:

```python
lines = self.move_line_ids.filtered(lambda ml:
    ml.picking_code == 'incoming' and ml.state == 'done' and ml.lot_id
    and ml.product_id.tracking == 'serial'          # one lot = one physical item
    and ml.product_id.equipment_category_id
    and not ml.lot_id.equipment_ids)                # idempotent: re-click creates nothing
items = self.env['equipment.item'].create([{
    'name': ml.product_id.display_name,
    'category_id': ml.product_id.equipment_category_id.id,
    'product_id': ml.product_id.id,
    'lot_id': ml.lot_id.id,
    'company_id': ml.company_id.id,
    'vendor_id': ml.picking_id.partner_id.commercial_partner_id.id,
    'purchase_date': ml.picking_id.date_done.date(),
    'purchase_value': ml.move_id.price_unit,
} for ml in lines])
```

Then return an action on `equipment.item` with domain `[('id', 'in', items.ids)]`.
If `lines` is empty, raise `UserError`: "nothing new to create".

- `purchase_value` has `groups=manager` in the base module. Write it `sudo()` only for
  that field, or skip it for non-managers. **Decide during implementation**; don't
  silently sudo the whole create.
- Items are created `available`, so `_check_lifecycle_create` passes as-is.
- Button in the picking header (inherit `stock.view_picking_form`), visible when
  `picking_type_code == 'incoming' and state == 'done'`,
  `groups="equipment_assignment.group_equipment_officer"`.
- Lot-tracked products (`tracking == 'lot'`, qty > 1) are **skipped**, because one lot
  ≠ one item. Mention this in the UserError when everything was skipped.

### Step 5 — tests (`tests/test_receipt_to_equipment.py`)

Reuse `equipment_assignment.tests.common.EquipmentCase`. One product with
`tracking='serial'` and `equipment_category_id`, and one without. Receipt with 2 serials +
1 non-equipment line, then validate.

Assert:
1. 2 items created, with serial = lot name, category/product/vendor/date set, state `available`.
2. Second click → `UserError`, still 2 items (idempotent).
3. Linking the same lot to a 2nd item → `UniqueViolation`/`ValidationError`.
4. Lot with a mismatched product → `ValidationError`.
5. Officer (not manager) can run it; `purchase_value` behaves as decided in step 4.

### Run

Target DB is `equipment` (see Decisions).

```powershell
& "C:\Program Files\Odoo 19.0.20260724\python\python.exe" `
  "C:\Program Files\Odoo 19.0.20260724\server\odoo-bin" `
  -c "C:\Program Files\Odoo 19.0.20260724\server\odoo.conf" `
  -d equipment -i equipment_assignment_stock --test-tags /equipment_assignment_stock `
  --stop-after-init --no-http --logfile=- --log-level=warn
```

### Out of scope (add when asked)

- Auto-create on receipt validation (`_action_done` override). Manual button first.
- Stock moves on assign/return (level 3).
- `account_asset` link (`asset_id`). It's a separate bridge if finance wants it.
- Backfill for items created before the bridge. Link lots by hand on the form.

### Decisions (2026-09-29)

- Target DB: **`equipment`**. `equipment_assignment` is installed there; `stock` is
  **uninstalled**, so `-i equipment_assignment_stock` will install stock too.
- `purchase_value` for officers: **fill it via `sudo()`**, scoped to that one field
  (a separate `sudo().write({'purchase_value': ...})` after the normal create).
