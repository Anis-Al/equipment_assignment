from odoo import fields, models

from ..models.equipment_assignment import CONDITIONS


class EquipmentAssignWizard(models.TransientModel):
    _name = 'equipment.assign.wizard'
    _description = 'Assign or Transfer Equipment'

    def _default_equipment_ids(self):
        if self.env.context.get('active_model') == 'equipment.item':
            return self.env['equipment.item'].browse(self.env.context.get('active_ids', []))
        return self.env['equipment.item']

    mode = fields.Selection([('assign', 'Assign'), ('transfer', 'Transfer')], required=True, default='assign')
    equipment_ids = fields.Many2many('equipment.item', string='Equipment', required=True, default=_default_equipment_ids)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
        domain="[('company_id', 'in', allowed_company_ids)]",
    )
    date_start = fields.Date(string='Handover Date', required=True, default=fields.Date.context_today)
    expected_return_date = fields.Date()
    condition_out = fields.Selection(CONDITIONS, string='Condition', required=True, default='good')
    note = fields.Text()

    def action_confirm(self):
        self.ensure_one()
        vals = {
            'employee_id': self.employee_id.id,
            'date_start': self.date_start,
            'expected_return_date': self.expected_return_date,
            'condition_out': self.condition_out,
            'note_out': self.note,
        }
        if self.mode == 'transfer':
            self.equipment_ids._transfer_to(vals)
        else:
            self.equipment_ids._assign_to(vals)
        return {'type': 'ir.actions.act_window_close'}
