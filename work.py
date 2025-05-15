# This file is part of project_activity module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import html
import humanize
import re
import mimetypes
from itertools import chain
try:
    from http import HTTPStatus
except ImportError:
    from http import client as HTTPStatus
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval, Bool
from trytond.i18n import gettext
from trytond.wsgi import app
from trytond.transaction import Transaction
from werkzeug.wrappers import Response
from werkzeug.exceptions import abort
from trytond.protocols.wrappers import with_pool, with_transaction
from trytond.url import URLAccessor
from trytond.wizard import (
    Button, StateAction, StateView, Wizard)
from trytond.modules.electronic_mail_activity.activity import SendActivityMailMixin
from trytond.exceptions import UserWarning

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


class Project(SendActivityMailMixin, metaclass=PoolMeta):
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
    def copy(cls, project_works, default=None):
        pool = Pool()
        Configuration = pool.get('work.configuration')
        config = Configuration(1)

        if default is None:
            default = {}
        else:
            default = default.copy()
        if config.synchronize_activity_time:
            default.setdefault('activities', None)
        return super().copy(project_works, default=default)

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
            res.append((_type.model.name, _type.model.string))
        return res

    def get_conversation(self, name):
        summary = self.get_conversation_activities(self.activities) or ''
        # TODO supports str as value of Binary field so sao should also
        # https://bugs.tryton.org/issue11534
        return summary.encode()

    def get_conversation_filename(self, name):
        return 'conversation.html'

    @classmethod
    def get_conversation_activities(cls, activities, include_attachments=True):
        pool = Pool()
        Attachment = pool.get('ir.attachment')

        transaction = Transaction()
        database = transaction.database.name

        result = []
        for activity in activities:
            description_text = (activity.description or '').strip()
            previous = []
            body_mail = []
            if len(description_text) > 0:
                for line in description_text.replace('\\n', '\n').split('\n'):
                    if line.startswith('>'):
                        previous.append(line)
                    else:
                        body_mail += previous
                        previous = []
                        body_mail.append(line)

            attachments = Attachment.search([
                ('resource.id', '=', activity.id, 'activity.activity') ])
            attachment_names = ['<a href="%s/%s/ir/attachment/%s">%s</a>' % (
                URLAccessor.http_host(), database, x.id, x.name)
                for x in attachments]

            if include_attachments:
                attachs_str = ('<div style="line-height: 2">' +
                    ' '.join(attachment_names) + '</div>')
            else:
                attachs_str = ''

            body_str = '\n'.join(body_mail)
            body_str = html.escape(body_str)
            body_str = create_anchors(body_str)
            body_str = '<br/>'.join(body_str.splitlines())

            previous_str = '\n'.join(previous)
            if previous_str.strip():
                previous_str = html.escape(previous_str)
                previous_str = create_anchors(previous_str)
                previous_str = '<br/>'.join(previous_str.splitlines())
                dots =  f'''<a href="javascript:toggle('{activity.id}');" class="dots">...</a>'''
                dots += '<hr/>'
                dots += f'<div id="{activity.id}" style="display:none; font-family: Sans-serif;"><br/>{previous_str}</div>'
            else:
                dots = ''

            body = gettext('project_activity.msg_conversation',
                type=activity.activity_type.name,
                code=activity.code,
                subject=activity.subject or '',
                date=activity.date,
                time=activity.time or '',
                date_human=humanize.naturaltime(activity.dtstart),
                contact=(activity.contacts and activity.contacts[0].name or ''),
                employee=(activity.employee and activity.employee.party.name
                    or ''),
                dots=dots,
                activity=activity.state,
                attachs_str=attachs_str,
                body_str=body_str,
            )
            result.append(body)
        if not result:
            return None
        return '''<!DOCTYPE html>
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
            ''' % '<br/>'.join(result)


class Activity(metaclass=PoolMeta):
    __name__ = 'activity.activity'
    tasks = fields.One2Many('project.work', 'resource', 'Tasks')
    timesheet_line = fields.One2One('activity.activity-timesheet.line',
        'activity', 'timesheet_line', "Timesheet Line")

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

    @classmethod
    def create(cls, vlist):
        res = super().create(vlist)
        cls.sync_project_contacts(res)
        cls.update_status_on_stakeholder_action(res)
        cls.sync_timesheetline(res)
        return res

    @classmethod
    def write(cls, *args):
        super().write(*args)
        cls.sync_project_contacts(list(chain(*args[::2])))
        cls.update_status_on_stakeholder_action(list(chain(*args[::2])))
        cls.sync_timesheetline(list(chain(*args[::2])))

    @classmethod
    def update_status_on_stakeholder_action(cls, activities):
        pool = Pool()
        Work = pool.get('project.work')
        to_save = []
        for activity in activities:
            if activity.activity_type or activity.resource:
                if (isinstance(activity.resource, Work)
                        and activity.activity_type.update_status_on_stakeholder_action):
                    work = activity.resource
                    new_status = activity.resource.status.status_on_stakeholder_action
                    if new_status:
                        work.status = new_status
                        to_save.append(work)
        Work.save(to_save)

    @classmethod
    def sync_project_contacts(cls, activities):
        pool = Pool()
        Work = pool.get('project.work')
        to_save = []
        for activity in activities:
            if isinstance(activity.resource, Work):
                for contact in activity.contacts:
                    if contact not in activity.resource.contacts:
                        activity.resource.contacts += (contact,)
                to_save.append(activity.resource)
        Work.save(to_save)

    @classmethod
    def sync_timesheetline(cls, activities):
        pool = Pool()
        Work = pool.get('project.work')
        TimesheetLine = pool.get('timesheet.line')
        Warning = pool.get('res.user.warning')
        Configuration = pool.get('work.configuration')

        config = Configuration(1)
        if not config.synchronize_activity_time:
            return

        to_save = []
        for activity in activities:
            if not isinstance(activity.resource, Work):
                if activity.timesheet_line:
                    key = 'no_resource_assigned_%d'  % activity.id
                    if Warning.check(key):
                        raise UserWarning(key, gettext(
                            'project_activity.msg_no_resource',
                            timesheet=activity.timesheet_line.rec_name))
                    TimesheetLine.delete([activity.timesheet_line])
                continue

            if not activity.timesheet_line:
                if not activity.duration:
                    continue
                if not activity.resource.timesheet_works:
                    key = 'no_timesheet_work_%d' % activity.id
                    if Warning.check(key):
                        raise UserWarning(key, gettext(
                            'project_activity.msg_no_timesheet_works',
                            work=activity.resource.rec_name))
                    continue

                timesheet_line = TimesheetLine()
                timesheet_line.activity = activity
                timesheet_line.work = activity.resource.timesheet_works[0]
            else:
                timesheet_line = activity.timesheet_line
                if not activity.duration and timesheet_line:
                    key = 'no_duration_%d' % activity.id
                    if Warning.check(key):
                        raise UserWarning(key, gettext(
                            'project_activity.msg_no_duration',
                            activity=activity.rec_name,
                            timesheet=timesheet_line.rec_name))
                    TimesheetLine.delete([timesheet_line])
                    continue

            for attribute in ['company', 'employee', 'duration', 'date']:
                value = getattr(activity, attribute)
                if getattr(timesheet_line, attribute, None) != value:
                    setattr(timesheet_line, attribute, value)

            if timesheet_line.work != activity.resource.timesheet_works[0]:
                timesheet_line.work = activity.resource.timesheet_works[0]

            if (hasattr(timesheet_line, 'start')
                    and (timesheet_line.start or timesheet_line.end)):
                timesheet_line.start = None
                timesheet_line.end = None

            to_save.append(timesheet_line)

        TimesheetLine.save(to_save)

    @classmethod
    def delete(cls, activities):
        pool = Pool()
        TimesheetLine = pool.get('timesheet.line')
        Warning = pool.get('res.user.warning')

        to_delete = [x.timesheet_line for x in activities if x.timesheet_line]
        if to_delete:
            key = Warning.format('delete_activity_and_line', to_delete)
            if Warning.check(key):
                activity = ', '.join([x.rec_name for x in activities[:5]])
                raise UserWarning(key, gettext(
                    'project_activity.msg_delete_act_and_tl',
                    activity=activity))
            TimesheetLine.delete(to_delete)
        super().delete(activities)

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
                'create_resource': {
                    'icon': 'tryton-ok',
                    'invisible': ~Bool(Eval('party')) | Bool(Eval('resource'))
                }
                })

    @classmethod
    @ModelView.button_action('project_activity.act_create_resource_wizard')
    def create_resource(cls, activities):
        pass


class CreateResource(Wizard):
    'Create Resource'
    __name__ = 'activity.create_resource'
    start = StateView('activity.create_resource.start',
        'project_activity.create_resource_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Next', 'open_task', 'tryton-next')
            ])
    open_task = StateAction('project.act_task_form')

    def default_start(self, fields):
        pool = Pool()
        Work = pool.get('project.work')
        projects = Work.search([
            ('type', '=', 'project'),
            ('party.id', '=', self.record.party.id),
            ['OR',
                [
                    ('status.progress', '!=', '1'),
                ], [
                    ('status.progress', '=', None),
                ],
            ],
            ])
        default = {}
        default['activity'] = self.record.id
        default['party'] = self.record.party.id
        default['project'] = projects[0].id if projects else None
        return default

    def get_task(self):
        pool = Pool()
        Work = pool.get('project.work')
        task = Work()

        task.parent = self.start.project
        task.on_change_parent()
        task.name = self.record.subject
        task.party = self.record.party
        task.comment = self.record.description
        # We do not fill 'activities' field here
        # because it will cause a write() on activity.activity before
        # timesheet.work is created by project.work and this would cause
        # sync_timesheet_line() to be called before timesheet works are created
        return task

    def do_open_task(self, action):
        if not self.start.task:
            task = self.get_task()
            task.save()
        else:
            task = self.start.task
        self.record.resource = task
        self.record.save()
        data = {'res_id': [task.id], 'views': action['views'].reverse()}
        return action, data


class CreateResourceStart(ModelView):
    'Create Resource'
    __name__ = 'activity.create_resource.start'
    activity = fields.Many2One('activity.activity', "Activity", readonly=True)
    party = fields.Many2One('party.party', "Party", readonly=True)
    project = fields.Many2One('project.work', "Project",
        domain=[
            ('type', '=', 'project'),
            ('party', '=', Eval('party', -1)),
            ['OR',
                [
                    ('status.progress', '!=', '1'),
                ], [
                    ('status.progress', '=', None),
                ],
                ],
                ], depends = ['party'])
    task = fields.Many2One('project.work', "Task",
        domain=[
            ('type', '=', 'task'),
            ('party', '=', Eval('party', -1)),
            ['OR',
                [
                    ('status.progress', '!=', '1'),
                ], [
                    ('status.progress', '=', None),
                ],
                ],
                ], depends = ['party'])
    tasks = fields.One2Many('project.work', None, "Tasks", readonly=True)


class WorkStatus(metaclass=PoolMeta):
    'Work Status'
    __name__ = 'project.work.status'

    status_on_stakeholder_action = fields.Many2One('project.work.status',
        'Stakeholder Action')


class ActivityType(metaclass=PoolMeta):
    'Activity Type'
    __name__ = "activity.type"

    update_status_on_stakeholder_action = fields.Boolean(
        "Update Status on StakeHolder Action")


class ActivityTimeSheetSync(ModelSQL):
    'Activity Timesheet Sync'
    __name__ = 'activity.activity-timesheet.line'
    activity = fields.Many2One('activity.activity', 'Activities', required=True,
        ondelete='CASCADE')
    timesheet_line = fields.Many2One('timesheet.line', 'Timesheet Lines',
        required=True, ondelete='CASCADE')


class TimesheetLine(metaclass=PoolMeta):
    __name__ = 'timesheet.line'
    activity = fields.One2One('activity.activity-timesheet.line',
        'timesheet_line', 'activity', "Activity")

    @classmethod
    def write(cls, *args):
        super().write(*args)
        cls.sync_activity(list(chain(*args[::2])))

    @classmethod
    def create(cls, vlist):
        res = super().create(vlist)
        cls.sync_activity(res)
        return res

    @classmethod
    def delete(cls, lines):
        pool = Pool()
        Activity = pool.get('activity.activity')

        to_save = []
        for line in lines:
            if line.activity:
                line.activity.duration = None
                to_save.append(line.activity)

        super().delete(lines)

        Activity.save(to_save)

    @classmethod
    def sync_activity(cls, lines):
        pool = Pool()
        Activity = pool.get('activity.activity')
        Warning = pool.get('res.user.warning')

        to_save = []
        for line in lines:
            if not line.activity:
                continue
            for attribute in ['company', 'employee', 'duration', 'date']:
                value = getattr(line, attribute)
                if getattr(line.activity, attribute) != value:
                    setattr(line.activity, attribute, value)

            if line.work.origin != line.activity.resource:
                key = 'changing_activity_%d'  % line.id
                if Warning.check(key):
                    raise UserWarning(key, gettext(
                        'project_activity.msg_change_activity',
                        activity=line.activity.rec_name,
                        timesheet=line.rec_name))
                line.activity.resource = line.work.origin

            to_save.append(line.activity)
        Activity.save(to_save)
