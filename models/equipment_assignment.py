from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from .equipment_item import SERVICE_CONTEXT_KEY

CONDITIONS = [
    ('new', 'New'),
    ('good', 'Good'),
    ('fair', 'Fair'),
    ('damaged', 'Damaged'),
]
NOTE_FIELDS = frozenset({'note_in', 'note_out'})
CORRECTABLE_DATE_FIELDS = frozenset({'date_start', 'date_end'})


class EquipmentAssignment(models.Model):
    _name = 'equipment.assignment'
    _description = 'Equipment Assignment'
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    name = fields.Char(compute='_compute_name', store=True, readonly=True)
    equipment_id = fields.Many2one(
        'equipment.item', string='Equipment', required=True, ondelete='restrict', check_company=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='restrict', check_company=True,
    )
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    category_id = fields.Many2one('equipment.category', string='Category', readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    date_start = fields.Date(string='Handover Date', required=True)
    date_end = fields.Date(string='Return Date')
    expected_return_date = fields.Date()
    state = fields.Selection(
        [('ongoing', 'Ongoing'), ('returned', 'Returned')], string='Status',
        compute='_compute_state', store=True, precompute=True, index=True,
    )
    is_overdue = fields.Boolean(string='Overdue', compute='_compute_is_overdue', search='_search_is_overdue')
    can_correct_dates = fields.Boolean(compute='_compute_can_correct_dates')
    duration_days = fields.Integer(
        string='Duration (days)', compute='_compute_duration_days', store=True, precompute=True, aggregator='avg',
    )
    condition_out = fields.Selection(CONDITIONS, string='Condition at Handover', default='good')
    condition_in = fields.Selection(CONDITIONS, string='Condition at Return')
    note_out = fields.Text(string='Handover Note')
    note_in = fields.Text(string='Return Note')
    assigned_by_id = fields.Many2one('res.users', string='Assigned By', readonly=True, default=lambda self: self.env.user)
    returned_by_id = fields.Many2one('res.users', string='Return Received By', readonly=True)

    _unique_open_assignment = models.UniqueIndex(
        '(equipment_id) WHERE date_end IS NULL',
        'This equipment already has an ongoing assignment.',
    )
    _date_order = models.Constraint(
        'CHECK(date_end IS NULL OR date_end >= date_start)',
        'The return date cannot be earlier than the handover date.',
    )
    _equipment_history_idx = models.Index('(equipment_id, date_start DESC, id DESC)')
    _employee_history_idx = models.Index('(employee_id, date_start DESC, id DESC)')
    _company_date_idx = models.Index('(company_id, date_start DESC)')
    _open_expected_return_idx = models.Index('(expected_return_date) WHERE date_end IS NULL')

    @api.depends('date_start')
    def _compute_name(self):
        for assignment in self:
            assignment.name = (
                f'ASG/{assignment.date_start.year}/{assignment.id:06d}'
                if assignment.id and assignment.date_start else False
            )

    @api.depends('date_end')
    def _compute_state(self):
        for assignment in self:
            assignment.state = 'returned' if assignment.date_end else 'ongoing'

    @api.depends('date_start', 'date_end')
    def _compute_duration_days(self):
        for assignment in self:
            assignment.duration_days = (
                (assignment.date_end - assignment.date_start).days
                if assignment.date_end and assignment.date_start else False
            )

    @api.depends('date_end', 'expected_return_date')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for assignment in self:
            assignment.is_overdue = bool(
                not assignment.date_end
                and assignment.expected_return_date
                and assignment.expected_return_date < today
            )

    @api.depends('state')
    def _compute_can_correct_dates(self):
        is_manager = self.env.user.has_group('equipment_assignment.group_equipment_manager')
        for assignment in self:
            assignment.can_correct_dates = is_manager and assignment.state == 'returned'

    def _search_is_overdue(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        overdue = Domain('date_end', '=', False) & Domain(
            'expected_return_date', '<', fields.Date.context_today(self),
        )
        return overdue if (True in value) == (operator == 'in') else ~overdue

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(SERVICE_CONTEXT_KEY):
            raise UserError(self.env._('Assignments are created with the Assign and Transfer actions on equipment.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get(SERVICE_CONTEXT_KEY):
            allowed = NOTE_FIELDS
            if self.env.user.has_group('equipment_assignment.group_equipment_manager') and all(
                assignment.state == 'returned' for assignment in self
            ):
                allowed |= CORRECTABLE_DATE_FIELDS
            if set(vals) - allowed or ('date_end' in vals and not vals['date_end']):
                raise UserError(self.env._(
                    'Assignment history is read-only except for notes. '
                    'Equipment Managers may correct the dates of returned assignments.'
                ))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_current(self):
        if current := self & self.equipment_id.current_assignment_id:
            raise UserError(self.env._(
                'Ongoing assignments cannot be deleted; return the equipment first: %(items)s',
                items=current.equipment_id._labels(),
            ))

    def _service(self):
        return self.with_context(**{SERVICE_CONTEXT_KEY: True})

    def action_open_return_wizard(self):
        return self.equipment_id.action_open_return_wizard()
