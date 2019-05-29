# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, ModelSingleton, fields
from trytond.pool import Pool
from trytond.pyson import Eval
from trytond.modules.company.model import (
    CompanyMultiValueMixin, CompanyValueMixin)

__all__ = ['WorkConfiguration', 'ConfigurationEmployee']


class WorkConfiguration(ModelSingleton, ModelSQL, ModelView,
        CompanyMultiValueMixin):
    'Work Configuration'
    __name__ = 'work.configuration'

    email_activity_type = fields.Many2One('activity.type',
        'E-mail Activity Type', required = True)
    email_activity_employee = fields.MultiValue(fields.Many2One(
            'company.employee', 'E-mail Activity Employee', help='Default'
            'employee for activities created from incoming e-mails if sender '
            'e-mail does not correspond to any employee', required = True))
    email_activity_mailbox = fields.Many2One('electronic.mail.mailbox',
        'E-mail Activity Mailbox', required = True)

    @classmethod
    def multivalue_model(cls, field):
        pool = Pool()
        if field in {'email_activity_employee'}:
            return pool.get('work.configuration.activity_employee')
        return super(WorkConfiguration, cls).multivalue_model(field)


class ConfigurationEmployee(ModelSQL, CompanyValueMixin):
    "Activity Employee"
    __name__ = 'work.configuration.activity_employee'

    email_activity_employee = fields.Many2One('company.employee',
        'Activity Employee', domain=[
                        ('company', 'in',
                    [Eval('company', -1), None]),
            ], depends=['company'])
