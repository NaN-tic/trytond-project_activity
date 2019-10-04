# This file is part of project_activity module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import cgi
import humanize
import re

from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['ProjectReference', 'Activity', 'Project']

EMAIL_PATTERN = r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+"


class ProjectReference(ModelSQL, ModelView):
    'Project Reference'
    __name__ = "project.reference"

    model = fields.Many2One('ir.model', 'Model', required=True)


class Project(metaclass=PoolMeta):
    __name__ = 'project.work'

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
            description_text = activity.description or ''
            description_text = cgi.escape(description_text)
            description_text = u'<br/>'.join(description_text.splitlines())
            uid = activity.write_uid or activity.create_uid

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
            body += u'<br><font color="#00000">Date: </font>%(date)s %(time)'
            body += u's&nbsp;&nbsp;&nbsp;'
            body += u'<font color="#00000">State: </font>%(state)s'
            body += u'<br><font color="#00000">Subject: </font>%(subject)s'
            body += u'<br><font color="#00000">Employee: </font>%(uid)s'
            body += u'</font></div>'
            body += u'<div align="left"><br/>%(description)s<hr/></div>'
            body = body % ({
                'type': activity.activity_type.name,
                'code': activity.code,
                'subject': activity.subject or "",
                'date': activity.date,
                'time': activity.time or "",
                'date_human': humanize.naturaltime(activity.dtstart),
                'contact': (activity.contacts and activity.contacts[0].name
                    or activity.employee and activity.employee.party.name),
                'description': description_text,
                'state': activity.state,
                'uid': uid.name if uid else '',
                })
            res.append(body)
        return ''.join(res)


class Activity(metaclass=PoolMeta):
    __name__ = 'activity.activity'
    tasks = fields.One2Many('project.work', 'resource', 'Tasks')

    @classmethod
    def default_party(cls):
        project_party_id = Transaction().context.get('project_party')
        if project_party_id:
            return project_party_id
        return super(Activity, cls).default_party()

    @classmethod
    def cron_get_mail_activity(cls):
        pool = Pool()
        ElectronicMail = pool.get('electronic.mail')
        ProjectWork = pool.get('project.work')
        Work = pool.get('project.work')
        Configuration = pool.get('work.configuration')
        Employee = pool.get('company.employee')

        def extract_id(reference):
            if not reference:
                return
            get_id = reference.replace('<','')
            get_id = get_id.split('@')
            try:
                return int(get_id[0])
            except ValueError:
                return

        configuration = Configuration(1)
        default_employee = configuration.email_activity_employee
        default_activity_type = configuration.email_activity_type
        mailbox = configuration.email_activity_mailbox

        mails = ElectronicMail.search([
                ('in_reply_to', '!=', None),
                ('flag_seen', '=', False),
                ('mailbox', '=', mailbox.id)
                ])
        new_args = []
        for mail in mails:
            work_ids = []
            if mail.in_reply_to:
                work_id = extract_id(mail.in_reply_to)
                if work_id:
                    work_ids.append(work_id)

            if mail.reference != None:
                # Delete string literal (\r, \n, \t)
                reference = mail.reference
                for char in ('\r', '\n', '\t'):
                    reference = reference.replace(char, ' ')
                for reference in reference.split():
                    work_id = extract_id(reference)
                    if work_id:
                        work_ids.append(work_id)

            if work_ids:
                works = ProjectWork.search([
                        ('id', 'in', work_ids),
                        ], limit=1)

                if works:
                    # Search if the sender is an employee
                    employee = default_employee
                    if mail.from_:
                        from_email = re.findall(EMAIL_PATTERN, mail.from_)
                        if from_email:
                            employees = Employee.search([
                                    ('party.contact_mechanisms.value', '=',
                                        from_email[0])
                                    ], limit=1)
                            if employees:
                                employee = employees[0]

                    activities = {
                        'activities': [
                            ('create', [{
                                    'description': mail.body_plain,
                                    'subject': mail.subject,
                                    'resource': 'project.work,%s' % works[0].id,
                                    # Mandatory fields:
                                    'dtstart': mail.date,
                                    'activity_type': default_activity_type,
                                    'state': 'held',
                                    'employee': employee,
                                    }])
                            ]}

                    new_args.append(works)
                    new_args.append(activities)
                    mail.flag_seen = True

        if new_args:
            Work.write(*new_args)
        if mails:
            ElectronicMail.save(mails)
