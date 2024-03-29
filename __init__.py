#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool
from . import work
from . import ir
from . import configuration

def register():
    Pool.register(
        work.ProjectReference,
        work.Project,
        work.Activity,
        configuration.WorkConfiguration,
        configuration.ConfigurationEmployee,
        ir.Cron,
        work.CreateResourceStart,
        work.WorkStatus,
        work.ActivityType,
        work.ActivityTimeSheetSync,
        work.TimesheetLine,
        module='project_activity', type_='model')

    Pool.register(
        work.CreateResource,
        module='project_activity', type_='wizard')
