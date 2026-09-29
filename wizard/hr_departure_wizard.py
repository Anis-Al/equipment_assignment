from odoo import api, fields, models


class HrDepartureWizard(models.TransientModel):
    _inherit = 'hr.departure.wizard'

    held_equipment_item_ids = fields.Many2many(
        'equipment.item', string='Equipment Still Held', compute='_compute_held_equipment_item_ids',
        groups='equipment_assignment.group_equipment_officer',
    )
    return_equipment_items = fields.Boolean(
        string='Return Equipment Items',
        help='Record the return of every item still held, dated on the departure date (or today if later).',
        groups='equipment_assignment.group_equipment_officer',
    )

    @api.depends('employee_ids')
    def _compute_held_equipment_item_ids(self):
        for wizard in self:
            wizard.held_equipment_item_ids = self.env['equipment.item'].search(
                [('current_employee_id', 'in', wizard.employee_ids.ids)],
            )

    def action_register_departure(self):
        if self.env.user.has_group('equipment_assignment.group_equipment_officer') and self.return_equipment_items:
            self.held_equipment_item_ids._return_current(
                min(self.departure_date, fields.Date.context_today(self)), condition_in=False,
            )
        return super().action_register_departure()
