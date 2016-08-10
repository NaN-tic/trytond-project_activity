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
        'get_activity_fields')
    channel = fields.Function(fields.Many2One('activity.type', 'Channel'),
        'get_activity_fields')
    contact_name = fields.Function(fields.Char('Contact Name'),
        'get_activity_fields')
    resource = fields.Reference('Resource', selection='get_resource')

    @classmethod
    def get_activity_fields(self, works, names):
        result = {}
        work_ids = [w.id for w in works]
        for name in ['last_action_date', 'channel', 'contact_name']:
            result[name] = {}.fromkeys(work_ids, None)
        for w in works:
            max_date, min_date = None, None
            for activity in w.activities:
                if not min_date or activity.dtstart <= min_date:
                    min_date = activity.dtstart
                    result['channel'][w.id] = (activity.activity_type.id
                        if activity.activity_type else None)
                    result['contact_name'][w.id] = (
                        activity.contacts[0].rec_name if activity.contacts
                        else None)
                if not max_date or activity.dtstart >= max_date:
                    max_date = activity.dtstart
                    result['last_action_date'][w.id] = activity.dtstart
        for name in ['last_action_date', 'channel', 'contact_name']:
            if name not in names:
                del result[name]
        return result

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
