import datetime
import unittest
from email.message import EmailMessage

from proteus import Model
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.pool import Pool
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules, set_user
from trytond.transaction import Transaction


class TestMailResource(unittest.TestCase):
    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules([
                'project_activity', 'project_contact',
                'electronic_mail_activity'])
        create_company()
        company = get_company()
        Party = Model.get('party.party')
        Employee = Model.get('company.employee')
        User = Model.get('res.user')
        Activity = Model.get('activity.activity')
        ActivityType = Model.get('activity.type')
        Mail = Model.get('electronic.mail')
        Mailbox = Model.get('electronic.mail.mailbox')
        Work = Model.get('project.work')
        Status = Model.get('project.work.status')
        Configuration = Model.get('project.configuration')
        customer = Party(name='Customer')
        customer.save()
        staff = Party(name='Employee')
        staff.contact_mechanisms.new(
            type='email', value='staff@internal.example')
        staff.save()
        employee = Employee(party=staff, company=company)
        employee.save()
        company.party.contact_mechanisms.new(
            type='email', value='support@internal.example')
        company.party.save()
        user = User(config.user)
        user.companies.append(company)
        user.company = company
        user.employees.append(employee)
        user.employee = employee
        user.save()
        set_user(user)
        activity_type = ActivityType(name='Mail',
            update_status_on_stakeholder_action=True)
        activity_type.save()
        mailbox = Mailbox(name='Inbox')
        mailbox.save()
        configuration = Configuration(1)
        configuration.email_activity_type = activity_type
        configuration.email_activity_employee = employee
        configuration.email_activity_mailbox = mailbox
        configuration.save()
        received = Status(name='Received', types=['task'])
        received.save()
        waiting = Status(name='Waiting', types=['task'],
            status_on_stakeholder_action=received)
        waiting.save()
        task = Work(name='Ticket', type='task', party=customer, status=waiting)
        task.save()
        with Transaction().start(config.database_name, config.user,
                context=config.context) as transaction:
            WorkModel = Pool().get('project.work')
            WorkModel.write([WorkModel(task.id)], {'number': '#191555'})
            transaction.commit()

        original = Mail(mailbox=mailbox, from_='staff@internal.example',
            to='customer@example.com', subject='Original request',
            message_id='<original@internal.example>',
            date=datetime.datetime.now())
        original.save()
        previous = Activity(activity_type=activity_type,
            employee=employee, party=customer, origin=original, mail=original,
            resource=task, subject=original.subject, dtstart=original.date,
            state='planned')
        previous.save()

        for mode in ['incoming', 'references', 'outgoing', 'forwarded',
                'unknown']:
            with self.subTest(mode=mode):
                message = EmailMessage()
                message['From'] = ('customer@example.com'
                    if mode in {'incoming', 'references', 'unknown'}
                    else 'staff@internal.example')
                message['To'] = ('customer@example.com' if mode == 'outgoing'
                    else 'support@internal.example')
                # The thread must work without a number in the subject.
                # Conversely, a matching number alone must not link a task.
                message['Subject'] = ('[#191555] Matching number without thread'
                    if mode == 'unknown' else 'Changed description')
                if mode == 'references':
                    message['References'] = original.message_id
                elif mode != 'unknown':
                    message['In-Reply-To'] = original.message_id
                body = 'Reply'
                if mode == 'forwarded':
                    body = ('---------- Forwarded message ---------\n'
                        'From: customer@example.com\n'
                        'To: staff@internal.example\n'
                        'Subject: Original description\n\nReply')
                message.set_content(body)
                mail = Mail(mailbox=mailbox, from_=str(message['From']),
                    to=str(message['To']), subject=str(message['Subject']),
                    in_reply_to=message.get('In-Reply-To'),
                    references=message.get('References'),
                    date=datetime.datetime.now(), mail_file=message.as_bytes())
                mail.save()
                activity = Activity(activity_type=activity_type,
                    employee=employee, origin=mail, mail=mail,
                    subject=mail.subject, dtstart=mail.date, state='planned')
                activity.save()
                activity.click('guess')
                task.reload()
                if mode == 'unknown':
                    self.assertFalse(activity.resource)
                else:
                    self.assertEqual(activity.resource, task)
                    self.assertEqual(activity.party, customer)
                self.assertEqual(task.status,
                    received if mode in {'incoming', 'references', 'forwarded'}
                    else waiting)
                task.status = waiting
                task.save()
                activity.subject = 'Edited later'
                activity.save()
                task.reload()
                self.assertEqual(task.status, waiting)
