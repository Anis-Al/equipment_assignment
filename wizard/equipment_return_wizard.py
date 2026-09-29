from odoo import fields, models

from ..models.equipment_assignment import CONDITIONS


class EquipmentReturnWizard(models.TransientModel):
    _name = 'equipment.return.wizard'
    _description = 'Return Equipment'

    def _default_equipment_ids(self):
        if self.env.context.get('active_model') == 'equipment.item':
            return self.env['equipment.item'].browse(self.env.context.get('active_ids', []))
        return self.env['equipment.item']

    equipment_ids = fields.Many2many('equipment.item', string='Equipment', required=True, default=_default_equipment_ids)
    date_end = fields.Date(string='Return Date', required=True, default=fields.Date.context_today)
    condition_in = fields.Selection(CONDITIONS, string='Condition', required=True, default='good')
    destination_state = fields.Selection(
        [('available', 'Available'), ('maintenance', 'In Maintenance')], string='Put Back As',
        required=True, default='available',
    )
    note = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        self.equipment_ids._return_current(self.date_end, self.condition_in, self.destination_state, self.note)
        return {'type': 'ir.actions.act_window_close'}
