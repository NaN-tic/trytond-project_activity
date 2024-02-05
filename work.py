# This file is part of project_activity module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import html
import humanize
import re
import mimetypes
try:
    from http import HTTPStatus
except ImportError:
    from http import client as HTTPStatus
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval

from trytond.wsgi import app
from trytond.transaction import Transaction
from werkzeug.wrappers import Response
from werkzeug.exceptions import abort
from trytond.protocols.wrappers import with_pool, with_transaction
from trytond.url import URLAccessor

__all__ = ['ProjectReference', 'Activity', 'Project']

EMAIL_PATTERN = r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+"

def create_anchors(text):
    return re.sub(r"((http|https):\/\/\S*)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)


@app.route('/<database_name>/ir/attachment/<int:record>',
    methods={'GET'})
@app.auth_required
@with_pool
@with_transaction(
    user='request', context=dict(_check_access=True, fuzzy_translation=True))
def attachment(request, pool, record):
    Attachment = pool.get('ir.attachment')
    attachments = Attachment.search([('id', '=', record)], limit=1)
    if not attachments:
        abort(HTTPStatus.NOT_FOUND)

    attachment = attachments[0]
    mimetype, _ = mimetypes.guess_type(attachment.name)
    if not mimetype:
        mimetype = 'application/octet-stream'
    response = Response(attachment.data, mimetype=mimetype)
    response.headers.add(
            'Content-Disposition', 'attachment', filename=attachment.name)
    response.headers.add('Content-Length', len(attachment.data))
    return response

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
    conversation = fields.Function(fields.Binary("Conversation",
        filename='conversation_filename'), 'get_conversation')
    conversation_filename = fields.Function(fields.Char("File Name"),
        'get_conversation_filename')

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
        pool = Pool()
        Attachment = pool.get('ir.attachment')

        res = []
        for activity in self.activities:
            description_text = activity.description or ''
            previous = []
            body_mail = []
            for line in description_text.splitlines():
                if line.startswith('>'):
                    previous.append(line)
                else:
                    body_mail += previous
                    previous = []
                    body_mail.append(line)

            attachments = Attachment.search([('resource.id', '=', activity.id,
                    'activity.activity')])
            attachment_names = ['<a href="%s/%s/ir/attachment/%s">%s</a>' %
                (URLAccessor.http_host(), Transaction().database.name, x.id,
                     x.name) for x in attachments]
            attachs_str = ("<div style='line-height: 2'>"
                    + " ".join(attachment_names) + "</div>")
            body_str = "\n".join(body_mail)
            previous_str = "\n".join(previous)
            body_str = html.escape(body_str)
            body_str = create_anchors(body_str)
            body_str = '<br/>'.join(body_str.splitlines())
            previous_str = html.escape(previous_str)
            previous_str = create_anchors(previous_str)
            previous_str = '<br/>'.join(previous_str.splitlines())

            # Original Fields
            # type, date, contact, code, subject, description

            body = "\n"
            body += '<span style="font-size:13px;">'
            body += '<div style="font-family: Sans-serif;">'
            body += '<h1>%(type)s, %(date_human)s</h1>'
            body += '<table style="font-size:13px;"><tr>'
            body += '<td>Code: <span style="color:#778899;">%(code)s</span></td>'
            body += '<td>Contact: <span style="color:#778899;">%(contact)s</span></td></tr>'
            body += '<tr><td>Date: <span style="color:#778899;">%(date)s %(time)s</span></td>'
            body += '<td>State: <span style="color:#778899;">%(state)s</span></td></tr>'
            body += '<tr><td colspan="0">Subject: <span style="color:#778899;">%(subject)s</span></td></tr>'
            body += '<tr><td colspan="0">Employee: <span style="color:#778899;">%(employee)s</span></td></tr>'
            body += '</table></div>'
            body += '<div style="font-family: Sans-serif;">%(attachments)s</div>'
            body += '<div style="font-family: Sans-serif;"><br/>%(description_body)s</div>'
            body += '''<a href="javascript:toggle('%(toggle_id)s');" class="dots">...</a>'''
            body += '<hr/>'
            body += '<div id="%(toggle_id)s" style="display:none; font-family: Sans-serif;"><br/>%(description_previous)s</div>'
            body += '</span>'
            body = body % ({
                'type': activity.activity_type.name,
                'code': activity.code,
                'subject': activity.subject or "",
                'date': activity.date,
                'time': activity.time or "",
                'date_human': humanize.naturaltime(activity.dtstart),
                'contact': (activity.contacts and activity.contacts[0].name
                    or ''),
                'toggle_id': activity.id,
                'attachments': attachs_str,
                'description_body': body_str,
                'description_previous': previous_str,
                'state': activity.state,
                'employee': (activity.employee and activity.employee.party.name
                    or ''),
                })
            res.append(body)
        summary = '''<!DOCTYPE html>
            <html>
            <head>
            <style>
            .dots {
              background-color: lightgray;
              margin-right: 5px;
              padding: 3px;
              border-radius: 6px;
              white-space: nowrap;
            }
            </style>
            <script>
            function toggle(id) {
                div = document.getElementById(id);
                if (div.style.display) {
                    div.style.display = '';
                } else {
                    div.style.display = "none";
                }
            }
            </script>
            </head>
            <body>%s</body></html>
            ''' % ''.join(res)
        # TODO supports str as value of Binary field so sao should also
        # https://bugs.tryton.org/issue11534
        return summary.encode()

    def get_conversation_filename(self, name):
        return 'conversation.html'


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
        if not mailbox:
            return

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
                                    'state': 'done',
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
