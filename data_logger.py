"""
    data_logger.py
    Records data from various sensors

    Copyright (C) 2025 Clear Creek Scientific

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
import os
import argparse
import logging
import time
from sugarcube import sugarcube
from importlib import import_module
import datetime

from ccs_dlconfig import config

import xml.etree.ElementTree as et

NAME                                = 'data_logger'
SENSOR_MODULE_DIR                   = 'sensormods'

# For the default period of 30 minutes between events, collecting 48 events gives
# a one day default file rollover...
DEFAULT_COLLECT_PERIOD              = 30
DEFAULT_ROLLOVER_COUNT              = 48
COLLECT_SUFFIX                      = '_ccs_data_logger.csv'
LOG_SUFFIX                          = '_ccs_data_logger.log'

PM_PISUGAR2           = 'pisugar2'

TAG_PERIOD            = 'period'
TAG_MANAGER           = 'manager'
TAG_SENSOR            = 'sensor'
TAG_SENSORS           = 'sensors'
TAG_SENSOR_CONFIG     = 'sensor-config'
TAG_POWER             = 'power'
TAG_ROLLOVER_COUNT    = 'rollover-count'
TAG_SCHEDULE          = 'schedule'

INFO_MSG               = 0
ERROR_MSG              = 1
MAX_REPORTED_ERRORS    = 20
MAX_REPORTED_INFO_MSGS = 20
TOO_MANY_ERRORS        = 'Too many errors to report...'
TOO_MANY_INFO_MSGS     = 'Too many non-error messages to report...'

g_done = False
g_collect = True
g_config = None
g_info_count = 0
g_error_count = 0

# level is 0 for information, anything else is error
def logmsg(tag,msg,level=0):
    global g_config
    global g_info_count
    global g_error_count
    if hasattr(g_config,'log_path') and None is not g_config.log_path:
        if (level == 0 and g_info_count <= MAX_REPORTED_INFO_MSGS) or (g_error_count <= MAX_REPORTED_ERRORS):
            with open(g_config.log_path,'a') as fd:
                ts = datetime.datetime.now(datetime.UTC)
                s = ts.strftime('%Y-%m-%d %I:%M:%S ') + '[' + tag + '] ' + msg + '\n'
                fd.write(s)
                if level != 0 and (g_error_count == MAX_REPORTED_ERRORS):
                    fd.write(TOO_MANY_ERRORS)
                if level == 0 and (g_info_count == MAX_REPORTED_INFO_MSGS):
                    fd.write(TOO_MANY_INFO_MSGS)
            if level == 0:
                g_info_count += 1
            else:
                g_error_count += 1

class SensorSettings(object):

    def __init__(self):
        self.name = None
        self.active = False
        self.ticks = 0
        self.period = 0
        self.rollover_max = 0
        self.rollover_count = 0
        self.path = None
        self.config = None

class LoggerSettings(config.Settings):

    def __init__(self):
        super().__init__()
        self.sensor_settings = list()
        self.log_path = None
        self.power_manager = None

    def read(self,path):
        super().read(path)
        if None is not self.log_dir:
            ts = datetime.datetime.now(datetime.UTC)
            name = ts.strftime('%Y%m%d%I%M%S') + LOG_SUFFIX
            self.log_path = os.path.join(g_config.log_dir,name)
        else:
            self.log_path = '/tmp/data_logger.log'

        sensors = self.root.find(TAG_SENSORS)
        for sensor_node in sensors:
            new_sensor_settings = SensorSettings() 
            new_sensor_settings.name = sensor_node.get('name')
            schedule = sensor_node.find(TAG_SCHEDULE)
            period_node = schedule.find(TAG_PERIOD)
            new_sensor_settings.period = int(period_node.text.strip())
            rcount = schedule.find(TAG_ROLLOVER_COUNT)
            if None is not rcount:
                new_sensor_settings.rollover_max = int(rcount.text.strip())
            config_node = sensor_node.find(TAG_SENSOR_CONFIG)
            if None is not config_node:
                new_sensor_settings.config = et.tostring(config_node).decode('utf-8') 
            self.sensor_settings.append(new_sensor_settings)

        power = self.root.find(TAG_POWER)
        if None is not power:
            man = power.find(TAG_MANAGER)
            if None is not man:
                self.power_manager = man.text.strip()

            period = power.find(TAG_PERIOD)
            if None is not period:
                self.power_period = int(period.text.strip())

class CcsLogger(object):

    def __init__(self):
        self.sensors = list()
        self.load_sensor_modules()

    def get_sensor_settings(self,name):
        global g_config
        rv = None
        for ss in g_config.sensor_settings:
            if name == ss.name:
                rv = ss
                break
        return rv

    def load_sensor_modules(self):
        self.sensor_modules = list()
        self.most_recent_data = dict()

        if False == os.path.exists(SENSOR_MODULE_DIR):
            os.mkdir(SENSOR_MODULE_DIR,mode=0o755)
        files = os.listdir(SENSOR_MODULE_DIR)
        for f in files:
            if f.endswith('.py'):
                if '__init__.py' != f:
                    f = f[:-3]
                    name = SENSOR_MODULE_DIR + '.' + f
                    try:
                        mod = import_module(name)
                        if hasattr(mod,"load"):
                            obj = mod.load()
                            obj.sensor_name = f
                            if hasattr(obj,'set_log_callback'):
                                obj.set_log_callback(logmsg)
                            sensor_settings = self.get_sensor_settings(f)
                            if None is not sensor_settings:
                                if hasattr(obj,'set_config'):
                                    obj.set_config(sensor_settings.config)
                            self.sensors.append(obj)
                            logmsg(NAME,'Loaded sensor module: ' + f,INFO_MSG)
                        else:
                            logmsg(NAME,'Sensor module has no load function: ' + f,ERROR_MSG)
                    except Exception as ex:
                        logmsg(NAME,'Failed to load sensor module (' + f + '): ' + str(ex),ERROR_MSG)


    def collect(self,sensor,sensor_settings):
        sensor_settings.rollover_count += 1

        if (sensor_settings.path == None) or (sensor_settings.rollover_count >= sensor_settings.rollover_max):
            sensor_settings.path = self.get_collect_file_path()
            sensor_settings.rollover_count = 0
        timestamp = datetime.datetime.now(datetime.UTC)
        s = timestamp.strftime('%Y%m%d %I:%M:%S')
        header_written = True
        with open(sensor_settings.path,'a') as fd:
            if 0 == os.path.getsize(sensor_settings.path):
                header_written = False
            data = sensor.get_current_values()
            if False == header_written:
                header = self.get_header(data)
                fd.write(header + '\n')
                header_written = True
            for x in data:
                if 2 == len(x):
                    s += ',' + str(x[1])
            fd.write(s + '\n')

    def get_header(self,dataset):
        s = 'Timestamp (UTC)'
        for x in dataset:
            s += ',' + str(x[0])
        return s

    # FIXME: At some point we need to combine sensors with the same schedule 
    def get_collect_file_path(self):
        global g_config
        ts = datetime.datetime.now(datetime.UTC)
        name = ts.strftime('%Y%m%d_%I%M%S') + COLLECT_SUFFIX
        return os.path.join(g_config.csv_dir,name)

def get_pisugar2_manager(cfg):
    power_manager = None
    try:
        power_manager = sugarcube.Connection()
        if None is not power_manager:
            if hasattr(power_manager,'set_log_callback'):
                power_manager.set_log_callback(logmsg)
            # It turns out that when the sugar module is connected and powered
            # off, but the pi is plugged in, the sugar module will respond 
            # properly to some queries, but not to others. We put a
            # 'get_battery_percentage' call in here to force a failure
            # and to let the user now the battery level
            bat = power_manager.get_battery_percentage()
            power_manager.logmsg('Battery: ' + str(bat) + ' %',0)
    except ConnectionRefusedError:
        power_manager = None
        logmsg(NAME,'PiSugar configured, but not found',ERROR_MSG)
    except sugarcube.SugarDisconnected:
        power_manager = None
        logmsg(NAME,'PiSugar configured, but not available',ERROR_MSG)

    if None is cfg.power_period:
        logmsg(NAME,'PiSugar power manager is missing "period" element in configuration file',ERROR_MSG)

    return power_manager


def run(args):
    global g_done
    global g_config

    first_time = True

    power_manager = None
    g_config = LoggerSettings()
    g_config.read(args.config)

    if None is not g_config.power_manager:
        if g_config.power_manager == PM_PISUGAR2:
            power_manager = get_pisugar2_manager(g_config)
        else:
            msg = 'Unknown power manager: ' + g_config.power_manager + ' for ' + sensor_settings.get_label()
            logmsg(NAME,msg,INFO_MSG)
        # If a power manager is configured, but we can't talk to it, the user has probably
        # plugged in the Rasbperry Pi and wants to browse data, rather than collect.
        if None is power_manager:
            logmsg(NAME,'I assume you want to browse data, not collect. Exiting data logger.')
            g_done = True
            return

    data_logger = CcsLogger()
    total_count = 0

    if None is not power_manager:
       for sensor_module in data_logger.sensors:
           settings = data_logger.get_sensor_settings(sensor_module.sensor_name)
           if None is not settings:
               data_logger.collect(sensor_module,settings)
           else:
               logmsg(NAME,"Couldn't find settings for " + sensor_module.sensor_name,ERROR_MSG)
       power_manager.sleep(g_config.power_period) 
    else:
        while True == g_collect:
            for sensor_module in data_logger.sensors:
                settings = data_logger.get_sensor_settings(sensor_module.sensor_name)
                if None is not settings:
                    if settings.ticks >= settings.period or first_time:
                        data_logger.collect(sensor_module,settings)
                        settings.ticks = 0
                    settings.ticks += 1
                    first_time = False
                else:
                    msg = 'Sensor module is missing sensor-config in settings file: ' + sensor_module.get_label()
                    logmsg(NAME,msg,ERROR_MSG)
            # 60 seconds per tick
            time.sleep(60)


if '__main__' == __name__:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-c','--config',required=True,help='Path to config file')
    args = arg_parser.parse_args()
    while False == g_done:
        run(args)




