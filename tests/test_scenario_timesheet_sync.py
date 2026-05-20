import datetime
import unittest

from proteus import Model
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules, set_user


class TestTimesheetSync(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules(['project_activity', 'project_contact'])

        _ = create_company()
        company = get_company()

        Activity = Model.get('activity.activity')
        ActivityType = Model.get('activity.type')
        Employee = Model.get('company.employee')
        Mailbox = Model.get('electronic.mail.mailbox')
        Party = Model.get('party.party')
        TimesheetLine = Model.get('timesheet.line')
        User = Model.get('res.user')
        Work = Model.get('project.work')
        WorkConfig = Model.get('work.configuration')
        WorkStatus = Model.get('project.work.status')

        customer = Party(name='Customer')
        customer.save()

        employee_party = Party(name='Employee')
        employee_party.save()
        employee = Employee(party=employee_party, company=company)
        employee.save()

        user = User(config.user)
        user.companies.append(company)
        user.company = company
        user.employees.append(employee)
        user.employee = employee
        user.save()
        set_user(user)

        activity_type = ActivityType(name='Work')
        activity_type.save()
        mailbox = Mailbox(name='Work')
        mailbox.save()

        work_config = WorkConfig(1)
        work_config.email_activity_type = activity_type
        work_config.email_activity_employee = employee
        work_config.email_activity_mailbox = mailbox
        work_config.synchronize_activity_time = True
        work_config.save()

        open_status, = WorkStatus.find([('name', '=', 'Open')])

        def create_task(name):
            task = Work()
            task.name = name
            task.type = 'task'
            task.company = company
            task.party = customer
            task.status = open_status
            task.timesheet_available = True
            task.save()
            task.reload()
            self.assertEqual(len(task.timesheet_works), 1)
            return task

        def create_activity(subject, duration, date):
            activity = Activity()
            activity.activity_type = activity_type
            activity.subject = subject
            activity.date = date
            activity.dtstart = datetime.datetime.combine(
                date, datetime.time(9, 0))
            activity.state = 'planned'
            activity.employee = employee
            activity.party = customer
            activity.duration = duration
            activity.save()
            return activity

        activity_first = create_activity(
            'Activity before task',
            datetime.timedelta(hours=2),
            datetime.date(2026, 5, 20))
        activity_first.reload()
        self.assertIsNone(activity_first.timesheet_line)

        task_after_activity = create_task('Task after activity')
        activity_first.resource = task_after_activity
        activity_first.save()
        activity_first.reload()
        task_after_activity.reload()

        line = activity_first.timesheet_line
        self.assertIsNotNone(line)
        self.assertEqual(line.duration, datetime.timedelta(hours=2))
        self.assertEqual(line.date, datetime.date(2026, 5, 20))
        self.assertEqual(line.employee.id, employee.id)
        self.assertEqual(line.company.id, company.id)
        self.assertEqual(
            line.work.id, task_after_activity.timesheet_works[0].id)

        task_before_activity = create_task('Task before activity')
        activity_after_task = create_activity(
            'Activity after task',
            datetime.timedelta(hours=3),
            datetime.date(2026, 5, 21))
        activity_after_task.resource = task_before_activity
        activity_after_task.save()
        activity_after_task.reload()
        task_before_activity.reload()

        line = activity_after_task.timesheet_line
        self.assertIsNotNone(line)
        self.assertEqual(line.duration, datetime.timedelta(hours=3))
        self.assertEqual(line.date, datetime.date(2026, 5, 21))
        self.assertEqual(
            line.work.id, task_before_activity.timesheet_works[0].id)

        line.duration = datetime.timedelta(hours=4, minutes=30)
        line.date = datetime.date(2026, 5, 22)
        line.save()
        activity_after_task.reload()
        self.assertEqual(
            activity_after_task.duration,
            datetime.timedelta(hours=4, minutes=30))
        self.assertEqual(activity_after_task.date, datetime.date(2026, 5, 22))

        TimesheetLine.delete([line])
        activity_after_task.reload()
        self.assertIsNone(activity_after_task.duration)
        self.assertIsNone(activity_after_task.timesheet_line)
