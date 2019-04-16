# This file is part of project_activity module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import cgi
import humanize

from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['ProjectReference', 'Activity', 'Project']


class ProjectReference(ModelSQL, ModelView):
    'Project Reference'
    __name__ = "project.reference"

    model = fields.Many2One('ir.model', 'Model', required=True)


class Project:
    __name__ = 'project.work'
    __metaclass__ = PoolMeta

    activities = fields.One2Many('activity.activity', 'resource',
        'Activities', context={
            'project_party': Eval('party'),
            }, depends=['party'])
    last_action_date = fields.Function(fields.DateTime('Last Action'),
        'get_activity_fields')
    channel = fields.Function(fields.Many2One('activity.type', 'Channel'),
        'get_activity_fields')
    contact_name = fields.Function(fields.Char('Contact Name'),
        'get_activity_fields')
    resource = fields.Reference('Resource', selection='get_resource')
    conversation = fields.Function(fields.Text('Conversation'),
        'get_conversation')

    @classmethod
    def get_activity_fields(cls, works, names):
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

    def get_conversation(self, name):
        res = []
        for activity in self.activities:
            description_text = activity.description
            description_text = cgi.escape(description_text)
            if not description_text:
                continue
            description_text = u'<br/>'.join(description_text.splitlines())

            # Original Fields
            # type, date, contact, code, subject, description

            body = "\n"
            body += u'<div align="left">'
            body += u'<font size="4"><b>'
            body += u'<font color="">%(type)s</font>'
            body += u', %(date_human)s'
            body += u'</b></font></div>'
            body += u'<div align="left">'
            body += u'<font size="2" color="#778899">'
            body += u'<font color="#00000">Code: </font>%(code)s'
            body += u'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
            body += u'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
            body += u'<font color="#00000">Contact: </font>%(contact)s'
            body += u'<br><font color="#00000">Date: </font>%(date)'
            body += u's&nbsp;&nbsp;&nbsp;'
            body += u'<font color="#00000">State: </font>%(state)s'
            body += u'<br><font color="#00000">Subject: </font>%(subject)s'
            body += u'</font></div>'
            body += u'<div align="left"><br/>%(description)s<hr></div>'
            body = body % ({
                'type': activity.activity_type.name,
                'code': activity.code,
                'subject': activity.subject or "",
                'date': activity.dtstart,
                'date_human': humanize.naturaltime(activity.dtstart),
                'contact': (activity.contacts and activity.contacts[0].name
                    or activity.employee and activity.employee.party.name),
                'description': description_text,
                'state': activity.state,
                })
            res.append(body)
        return ''.join(res)


class Activity:
    __name__ = 'activity.activity'
    __metaclass__ = PoolMeta
    tasks = fields.One2Many('project.work', 'resource', 'Tasks')

    @classmethod
    def default_party(cls):
        project_party_id = Transaction().context.get('project_party')
        if project_party_id:
            return project_party_id
        return super(Activity, cls).default_party()
