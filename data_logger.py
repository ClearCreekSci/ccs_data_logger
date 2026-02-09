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

from importlib import import_module
import datetime

from ccs_dlconfig import config

import xml.etree.ElementTree as et

NAME                                = 'data_logger'
SHARED_OBJECT_DIR                   = 'plugins'

# For the default period of 30 minutes between events, collecting 48 events gives
# a one day default file rollover...
DEFAULT_COLLECT_PERIOD              = 30
DEFAULT_ROLLOVER_COUNT              = 48
COLLECT_SUFFIX                      = '_ccs_logger.csv'
LOG_SUFFIX                          = '_ccs_data_logger.log'

TAG_PERIOD         = 'period'
TAG_PLUGIN         = 'plugin'
TAG_PLUGINS        = 'plugins'
TAG_PLUGIN_CONFIG  = 'plugin-config'
TAG_ROLLOVER_COUNT = 'rollover-count'
TAG_SCHEDULE       = 'schedule'

MAX_PLUGIN_REPORTED_ERRORS = 4

g_done = False
g_config = None

def logmsg(tag,msg):
    global g_config
    if hasattr(g_config,'log_path') and None is not g_config.log_path:
        with open(g_config.log_path,'a') as fd:
            ts = datetime.datetime.now(datetime.UTC)
            s = ts.strftime('%Y-%m-%d %I:%M:%S ') + '[' + tag + '] ' + msg + '\n'
            fd.write(s)

class PluginMeta(object):

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
        self.plugins = list()
        self.log_path = None

    def read(self,path):
        super().read(path)
        if None is not self.log_dir:
            ts = datetime.datetime.now(datetime.UTC)
            name = ts.strftime('%Y%m%d%I%M%S') + LOG_SUFFIX
            self.log_path = os.path.join(g_config.log_dir,name)
        else:
            self.log_path = '/tmp/data_logger.log'

        plugins = self.root.find(TAG_PLUGINS)
        for plugin_node in plugins:
            new_plugin = PluginMeta() 
            new_plugin.name = plugin_node.get('name')
            schedule = plugin_node.find(TAG_SCHEDULE)
            period_node = schedule.find(TAG_PERIOD)
            new_plugin.period = int(period_node.text.strip())
            rcount = schedule.find(TAG_ROLLOVER_COUNT)
            if None is not rcount:
                new_plugin.rollover_max = int(rcount.text.strip())
            config_node = plugin_node.find(TAG_PLUGIN_CONFIG)
            if None is not config_node:
                new_plugin.config = et.tostring(config_node).decode('utf-8') 
            self.plugins.append(new_plugin)

class CcsLogger(object):

    def __init__(self):
        self.load_plugins()

    def get_plugin_metadata(self,name):
        global g_config
        rv = None
        for plugin_meta in g_config.plugins:
            if name == plugin_meta.name:
                rv = plugin_meta
                break
        return rv

    def load_plugins(self):
        self.plugins = list()
        self.most_recent_data = dict()

        if False == os.path.exists(SHARED_OBJECT_DIR):
            os.mkdir(SHARED_OBJECT_DIR,mode=0o755)
        files = os.listdir(SHARED_OBJECT_DIR)
        for f in files:
            if f.endswith('.py'):
                if '__init__.py' != f:
                    f = f[:-3]
                    name = SHARED_OBJECT_DIR + '.' + f
                    try:
                        mod = import_module(name)
                        if hasattr(mod,"load"):
                            obj = mod.load()
                            obj.plugin_name = f
                            if hasattr(obj,'set_log_callback'):
                                obj.set_log_callback(logmsg)
                            plugin_meta = self.get_plugin_metadata(f)
                            if None is not plugin_meta:
                                if hasattr(obj,'set_config'):
                                    obj.set_config(plugin_meta.config)
                            obj.error_count = 0
                            self.plugins.append(obj)
                            logmsg(NAME,'Loaded plugin: ' + f)
                        else:
                            logmsg(NAME,'Plugin has no load function: ' + f)
                    except Exception as ex:
                        logmsg(NAME,'Failed to load plugin (' + f + '): ' + str(ex))


    def collect(self,plugin,plugin_meta):
        plugin_meta.rollover_count += 1

        if (plugin_meta.path == None) or (plugin_meta.rollover_count >= plugin_meta.rollover_max):
            plugin_meta.path = self.get_collect_file_path(plugin.get_label())
            plugin_meta.rollover_count = 0
        timestamp = datetime.datetime.now(datetime.UTC)
        s = timestamp.strftime('%Y%m%d %I:%M:%S')
        header_written = True
        with open(plugin_meta.path,'a') as fd:
            if 0 == os.path.getsize(plugin_meta.path):
                header_written = False
            data = plugin.get_current_values()
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

    def get_collect_file_path(self,label):
        global g_config
        ts = datetime.datetime.now(datetime.UTC)
        name = ts.strftime('%Y%m%d_%I%M%S') + '_' + label + COLLECT_SUFFIX
        return os.path.join(g_config.data_dir,name)

def run(args):
    global g_done
    global g_config

    plugin_error_count = 0
    g_config = LoggerSettings()
    g_config.read(args.config)

    data_logger = CcsLogger()
    total_count = 0
    while False == g_done:
        for plugin in data_logger.plugins:
            meta = data_logger.get_plugin_metadata(plugin.plugin_name)
            if None is not meta:
                meta.ticks += 1
                if meta.ticks >= meta.period:
                    data_logger.collect(plugin,meta)
                    meta.ticks = 0
            else:
                if error_count < MAX_PLUGIN_REPORTED_ERRORS:
                    logmsg(NAME,'Plugin is not configured properly: ' + plugin.get_label())
                    error_count += 1
        # 60 seconds per tick
        time.sleep(60)


if '__main__' == __name__:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-c','--config',required=True,help='Path to config file')
    arg_parser.add_argument('-p','--period',type=int,help='Number of minutes between collection events, default is 30')
    arg_parser.add_argument('-e','--events',type=int,help='Number of collection events to store in each file, default is 48')
    args = arg_parser.parse_args()
    run(args)




