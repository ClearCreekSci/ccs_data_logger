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
from datetime import datetime

from ccs_dlconfig import config

import xml.etree.ElementTree as et

SHARED_OBJECT_DIR                   = 'plugins'
# For the default period of 30 minutes between events, collecting 48 events gives
# a one day default file rollover...
DEFAULT_COLLECT_PERIOD              = 30
DEFAULT_COLLECT_EVENTS              = 48
COLLECT_SUFFIX                      = '_ccs_logger.csv'


logging.basicConfig(filename='/tmp/data_logger.log')
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
g_done = False
g_config = None

class CcsLogger(object):

    def __init__(self):
        self.load_plugins()


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
                        obj = mod.load()
                        self.plugins.append(obj)
                        log.info('Loaded plugin: ' + name)
                    except Exception:
                        log.error('Failed to load plugin: ' + name)
                        pass

    def collect(self,dstpath):
        timestamp = datetime.utcnow()
        s = timestamp.strftime('%Y%m%d %I:%M:%S')
        path = os.path.join(dstpath)
        header_written = True
        with open(path,'a') as fd:
            if 0 == os.path.getsize(path):
                header_written = False
            for plugin in self.plugins:
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

def get_path(dst):
    ts = datetime.utcnow()
    name = ts.strftime('%Y%m%d%I%M%S') + COLLECT_SUFFIX
    return os.path.join(dst,name)

def run(args):
    global g_done
    global g_config

    try:
        g_config = config.Settings(args.config,raise_exceptions=True)
        args.period = g_config.frequency
        args.events = g_config.package_rate
    except FileNotFoundError as e:
        print('Ignoring exception: ' + str(e))

    data_logger = CcsLogger()
    count = 0
    path = get_path(args.destination)
    print('path: ' + path + ', period: ' + str(args.period) + ', events: ' + str(args.events))
    while False == g_done:
        data_logger.collect(path)
        time.sleep(60 * args.period)
        count += 1
        if count >= args.events:
            path = get_path(args.destination)
            count = 0


if '__main__' == __name__:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-c','--config',required=True,help='Path to config file')
    arg_parser.add_argument('-d','--destination',required=True,help='Directory into which data is stored')
    arg_parser.add_argument('-p','--period',type=int,help='Number of minutes between collection events, default is 30')
    arg_parser.add_argument('-e','--events',type=int,help='Number of collection events to store in each file, default is 48')
    args = arg_parser.parse_args()
    if None is args.period:
        args.period = int(DEFAULT_COLLECT_PERIOD)
    if None is args.events:
        args.events = int(DEFAULT_COLLECT_EVENTS)

    run(args)




