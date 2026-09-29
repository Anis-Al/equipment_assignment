from psycopg2.errors import UniqueViolation

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain

SERVICE_CONTEXT_KEY = 'equipment_service'
POINTER_FIELDS = (
    'current_assignment_id', 'current_employee_id', 'current_department_id',
    'assigned_since', 'expected_return_date', 'last_return_date',
)
LIFECYCLE_FIELDS = frozenset(POINTER_FIELDS + ('state', 'active'))
STATES = [
    ('available', 'Available'),
    ('assigned', 'Assigned'),
    ('maintenance', 'In Maintenance'),
    ('retired', 'Retired'),
]


class EquipmentItem(models.Model):
    _name = 'equipment.item'
    _description = 'Equipment'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'reference desc, id desc'
    _rec_names_search = ['name', 'reference', 'serial_number']
    _check_company_auto = True

    name = fields.Char(required=True, index='trigram', tracking=True)
    reference = fields.Char(
        required=True, readonly=True, copy=False, index='trigram', default=lambda self: self.env._('New'),
    )
    serial_number = fields.Char(copy=False, index='trigram')
    category_id = fields.Many2one('equipment.category', string='Category', required=True, index=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    state = fields.Selection(
        STATES, string='Status', required=True, readonly=True, copy=False, default='available',
        tracking=True, group_expand=True,
    )
    current_assignment_id = fields.Many2one(
        'equipment.assignment', string='Current Assignment', readonly=True, copy=False,
        index='btree_not_null', ondelete='restrict',
    )
    current_employee_id = fields.Many2one(
        'hr.employee', string='Holder', readonly=True, copy=False, index='btree_not_null',
        tracking=True, check_company=True,
    )
    current_department_id = fields.Many2one(
        'hr.department', string='Department', readonly=True, copy=False, index='btree_not_null',
    )
    assigned_since = fields.Date(readonly=True, copy=False)
    expected_return_date = fields.Date(readonly=True, copy=False, index='btree_not_null')
    last_return_date = fields.Date(readonly=True, copy=False, index=True)
    is_overdue = fields.Boolean(string='Overdue', compute='_compute_is_overdue', search='_search_is_overdue')
    purchase_date = fields.Date()
    purchase_value = fields.Monetary(groups='equipment_assignment.group_equipment_manager')
    currency_id = fields.Many2one(related='company_id.currency_id')
    warranty_end_date = fields.Date(index=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', check_company=True)
    note = fields.Html()
    active = fields.Boolean(default=True)
    assignment_count = fields.Integer(string='History', compute='_compute_assignment_count')

    _reference_company_uniq = models.Constraint(
        'UNIQUE(company_id, reference)',
        'The equipment reference must be unique per company.',
    )
    _serial_company_uniq = models.UniqueIndex(
        '(company_id, serial_number) WHERE serial_number IS NOT NULL',
        'This serial number is already used by another equipment of the same company.',
    )
    _assigned_iff_holder = models.Constraint(
        "CHECK((state = 'assigned') = (current_assignment_id IS NOT NULL))",
        'An equipment is assigned if and only if it has a current assignment.',
    )
    _company_state_idx = models.Index('(company_id, state)')

    @api.depends('reference', 'name')
    def _compute_display_name(self):
        for item in self:
            item.display_name = f'[{item.reference}] {item.name}' if item.reference else item.name

    @api.depends('state', 'expected_return_date')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for item in self:
            item.is_overdue = bool(
                item.state == 'assigned' and item.expected_return_date and item.expected_return_date < today
            )

    def _search_is_overdue(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        overdue = Domain('state', '=', 'assigned') & Domain(
            'expected_return_date', '<', fields.Date.context_today(self),
        )
        return overdue if (True in value) == (operator == 'in') else ~overdue

    def _compute_assignment_count(self):
        counts = dict(self.env['equipment.assignment']._read_group(
            [('equipment_id', 'in', self.ids)], ['equipment_id'], ['__count'],
        ))
        for item in self:
            item.assignment_count = counts.get(item, 0)

    @api.model_create_multi
    def create(self, vals_list):
        new_label = self.env._('New')
        for vals in vals_list:
            self._check_lifecycle_create(vals)
            if vals.get('reference', new_label) == new_label:
                vals['reference'] = self.env['ir.sequence'].next_by_code('equipment.item') or new_label
        return super().create(vals_list)

    def write(self, vals):
        if LIFECYCLE_FIELDS.intersection(vals) and not self.env.context.get(SERVICE_CONTEXT_KEY):
            raise UserError(self.env._(
                'The status and holder of an equipment change only through Assign, Return, Transfer, '
                'Send to maintenance and Retire.'
            ))
        return super().write(vals)

    def _check_lifecycle_create(self, vals):
        if self.env.context.get(SERVICE_CONTEXT_KEY):
            return
        if vals.get('state', 'available') != 'available' or not vals.get('active', True) or any(
            vals.get(fname) for fname in POINTER_FIELDS
        ):
            raise UserError(self.env._('New equipment is always created as available; assign it afterwards.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_has_history(self):
        if self.env['equipment.assignment'].search_count([('equipment_id', 'in', self.ids)], limit=1):
            raise UserError(self.env._('Equipment with an assignment history cannot be deleted. Retire it instead.'))

    def _labels(self):
        return ', '.join(self.mapped('display_name'))

    def _service(self):
        return self.with_context(**{SERVICE_CONTEXT_KEY: True})

    def _check_manager(self):
        if not self.env.user.has_group('equipment_assignment.group_equipment_manager'):
            raise AccessError(self.env._('Only Equipment Managers can retire or restore retired equipment.'))

    def _assign_to(self, vals):
        if not self:
            return self.env['equipment.assignment']
        if wrong := self.filtered(lambda item: item.state != 'available'):
            raise UserError(self.env._(
                'Only available equipment can be assigned. Return or restore these first: %(items)s',
                items=wrong._labels(),
            ))
        today = fields.Date.context_today(self)
        date_start = fields.Date.to_date(vals.get('date_start')) or today
        if date_start > today:
            raise UserError(self.env._('The handover date cannot be in the future.'))
        if too_early := self.filtered(lambda item: item.last_return_date and item.last_return_date > date_start):
            raise UserError(self.env._(
                'The handover date cannot be earlier than the last return date of: %(items)s',
                items=too_early._labels(),
            ))
        employee = self.env['hr.employee'].sudo().browse(vals['employee_id'])
        if not employee.active or employee.company_id not in self.env.companies:
            raise UserError(self.env._(
                '%(employee)s is archived or belongs to a company you are not working in.',
                employee=employee.name,
            ))
        if other_company := self.filtered(lambda item: item.company_id != employee.company_id):
            raise UserError(self.env._(
                '%(employee)s cannot receive equipment of another company: %(items)s',
                employee=employee.name, items=other_company._labels(),
            ))
        expected = fields.Date.to_date(vals.get('expected_return_date')) or False
        self.check_access('write')
        try:
            with self.env.cr.savepoint():
                assignments = self.env['equipment.assignment']._service().create([{
                    'equipment_id': item.id,
                    'employee_id': employee.id,
                    'department_id': employee.department_id.id,
                    'category_id': item.category_id.id,
                    'company_id': item.company_id.id,
                    'date_start': date_start,
                    'expected_return_date': expected,
                    'condition_out': vals.get('condition_out') or 'good',
                    'note_out': vals.get('note_out'),
                } for item in self])
        except UniqueViolation:
            raise UserError(self.env._(
                'Someone else assigned some of these items at the same time: %(items)s. Reload and try again.',
                items=self._labels(),
            )) from None
        for item, assignment in zip(self.sudo()._service(), assignments):
            item.write({
                'state': 'assigned',
                'current_assignment_id': assignment.id,
                'current_employee_id': employee.id,
                'current_department_id': employee.department_id.id,
                'assigned_since': date_start,
                'expected_return_date': expected,
            })
        return assignments.with_env(self.env)

    def _return_current(self, date_end=None, condition_in='good', destination='available', note=False):
        if destination not in ('available', 'maintenance'):
            raise UserError(self.env._('Returned equipment goes back to Available or In Maintenance.'))
        if wrong := self.filtered(lambda item: item.state != 'assigned'):
            raise UserError(self.env._(
                'Only assigned equipment can be returned. Not assigned: %(items)s', items=wrong._labels(),
            ))
        date_end = fields.Date.to_date(date_end) or fields.Date.context_today(self)
        if date_end > fields.Date.context_today(self):
            raise UserError(self.env._('The return date cannot be in the future.'))
        assignments = self.current_assignment_id
        if too_early := assignments.filtered(lambda assignment: assignment.date_start > date_end):
            raise UserError(self.env._(
                'The return date cannot be earlier than the handover date of: %(items)s',
                items=too_early.equipment_id._labels(),
            ))
        assignments._service().write({
            'date_end': date_end,
            'condition_in': condition_in,
            'note_in': note,
            'returned_by_id': self.env.uid,
        })
        self._service().write({
            'state': destination,
            'current_assignment_id': False,
            'current_employee_id': False,
            'current_department_id': False,
            'assigned_since': False,
            'expected_return_date': False,
            'last_return_date': date_end,
        })
        return assignments

    def _transfer_to(self, vals):
        if wrong := self.filtered(lambda item: item.state != 'assigned'):
            raise UserError(self.env._(
                'Only assigned equipment can be transferred. Use Assign for: %(items)s', items=wrong._labels(),
            ))
        date_start = fields.Date.to_date(vals.get('date_start')) or fields.Date.context_today(self)
        self._return_current(date_start, vals.get('condition_out') or 'good', 'available', vals.get('note_out'))
        return self._assign_to(dict(vals, date_start=date_start))

    def action_send_to_maintenance(self):
        if wrong := self.filtered(lambda item: item.state != 'available'):
            raise UserError(self.env._(
                'Only available equipment can be sent to maintenance. Return these first: %(items)s',
                items=wrong._labels(),
            ))
        self._service().write({'state': 'maintenance'})

    def action_set_available(self):
        if wrong := self.filtered(lambda item: item.state not in ('maintenance', 'retired')):
            raise UserError(self.env._(
                'Only equipment in maintenance or retired can be set back to available: %(items)s',
                items=wrong._labels(),
            ))
        if 'retired' in self.mapped('state'):
            self._check_manager()
        self._service().write({'state': 'available', 'active': True})

    def action_retire(self):
        self._check_manager()
        if wrong := self.filtered(lambda item: item.state not in ('available', 'maintenance')):
            raise UserError(self.env._(
                'Only available or in-maintenance equipment can be retired. Return these first: %(items)s',
                items=wrong._labels(),
            ))
        self._service().write({'state': 'retired', 'active': False})

    def _open_wizard(self, model, title, **context):
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': model,
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_ids': self.ids, **context},
        }

    def action_open_assign_wizard(self):
        return self._open_wizard('equipment.assign.wizard', self.env._('Assign Equipment'))

    def action_open_transfer_wizard(self):
        return self._open_wizard('equipment.assign.wizard', self.env._('Transfer Equipment'), default_mode='transfer')

    def action_open_return_wizard(self):
        return self._open_wizard('equipment.return.wizard', self.env._('Return Equipment'))

    def action_view_assignments(self):
        action = self.env['ir.actions.act_window']._for_xml_id('equipment_assignment.equipment_assignment_history_action')
        action['domain'] = [('equipment_id', 'in', self.ids)]
        action['context'] = {}
        return action

    def action_view_holder(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id': self.current_employee_id.id,
            'view_mode': 'form',
        }
