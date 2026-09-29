from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    equipment_item_count = fields.Integer(
        string='Equipment Held', compute='_compute_equipment_item_count',
        groups='equipment_assignment.group_equipment_officer',
    )

    def _compute_equipment_item_count(self):
        counts = dict(self.env['equipment.item']._read_group(
            [('current_employee_id', 'in', self.ids)], ['current_employee_id'], ['__count'],
        ))
        for employee in self:
            employee.equipment_item_count = counts.get(employee, 0)

    def action_view_equipment_items(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('equipment_assignment.equipment_item_action')
        action['domain'] = [('current_employee_id', '=', self.id)]
        action['context'] = {}
        return action

    def action_view_equipment_history(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'equipment_assignment.equipment_assignment_history_action',
        )
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {}
        return action
