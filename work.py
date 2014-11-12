#This file is part of project_activity module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import PoolMeta, Pool

__metaclass__ = PoolMeta
__all__ = ['ProjectReference', 'Activity', 'Project']


class ProjectReference(ModelSQL, ModelView):
    'Project Reference'
    __name__ = "project.reference"
    _rec_name = 'model'
    model = fields.Many2One('ir.model', 'Model', required=True)


class Project:
    __name__ = 'project.work'
    activities = fields.One2Many('activity.activity', 'resource',
        'Activities')
    last_action_date = fields.Function(fields.DateTime('Last Action'),
        'get_last_action_date')
    channel = fields.Function(fields.Many2One('activity.type', 'Channel'), 'get_channel')
    contact_name = fields.Function(fields.Char('Contact Name'), 'get_contact')

    resource = fields.Reference('Resource', selection='get_resource')

    def get_channel(self, name):
        if not self.activities:
            return None
        Activity = Pool().get('activity.activity')
        act = Activity.search([('resource', '=', 'project.work,%s' % self.id)],
            order=[('dtstart', 'asc')], limit=1)
        return act and act[0].activity_type and act[0].activity_type.id or None

    def get_contact(self, name):
        if not self.activities:
            return None
        Activity = Pool().get('activity.activity')
        act = Activity.search([('resource', '=', 'project.work,%s' %
            self.id)], order=[('dtstart', 'asc')], limit=1)
        return act and act[0].party and act[0].party.name or None

    def get_last_action_date(self, name=None):
        if not self.activities:
            return None
        Activity = Pool().get('activity.activity')
        act = Activity.search([('resource', '=', 'project.work,%s' %
            self.id)], order=[('dtstart', 'desc')], limit=1)
        return act and act[0].dtstart or None

    @classmethod
    def get_resource(cls):
        ProjectReference = Pool().get('project.reference')
        res = [('', '')]
        for _type in ProjectReference.search([]):
            res.append((_type.model.model, _type.model.name))
        return res


class Activity:
    __name__ = 'activity.activity'
    tasks = fields.One2Many('project.work', 'resource', 'Tasks')
