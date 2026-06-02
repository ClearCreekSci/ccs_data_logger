import argparse
import os
import subprocess
import sys
import zipfile

import datetime as dt
import xml.etree.ElementTree as et

from glob import glob

DEFAULT_VERSION         = '1'
DEFAULT_PREFIX          = 'ccs_data_logger'

MANIFEST_NAME           = 'manifest.xml'
ZIP_SUFFIX              = '.zip'
SCRIPT_SUFFIX           = '.sh'

SCRIPT_LEN_REPLACE_STR  = '<***>'

TAG_BASE                = 'base'
TAG_INTERNAL            = 'internal'
TAG_NAME                = 'name'
TAG_PATHS               = 'paths'
TAG_ROOT                = 'ccs-config'
TAG_SENSOR              = 'sensor'
TAG_SENSORS             = 'sensors'
TAG_VERSION             = 'version'

TOPLEVEL_DST            = '/opt/ccs'
DATALOGGER_DST          = TOPLEVEL_DST + '/DataLogger'
SYSTEMD_SERVICE_DST     = '/etc/systemd/system'
UNZIP_DST               = './unzip'
SETTINGS_FILE_NAME      = 'settings.cfg'
SERVICE_FILE_NAME       = 'ccsdatalogger.service'

class InvalidSettingsFileException(Exception):
    pass

class Settings(object):

    def __init__(self):
        self.paths = dict()
        self.sensors = list()
        self.version = None

    def read(self,path):
        tree = et.parse(path)
        root = tree.getroot()
        if root.tag == TAG_ROOT:
            paths_node = root.find(TAG_PATHS)
            if None is not paths_node:
                for path_node in paths_node:
                    name = path_node.tag.strip()
                    value = path_node.text.strip()
                    self.paths[name] = value
            else:
                raise InvalidSettingsFileException('No paths element in settings file: ' + str(path)) 
            sensors_node = root.find(TAG_SENSORS)
            if None is not sensors_node:
                sensor_nodes = sensors_node.findall(TAG_SENSOR)
                for sensor_node in sensor_nodes:
                    name_node = sensor_node.find(TAG_NAME)
                    if None is not name_node:
                        name = name_node.tag.strip()
                        self.sensors.append(name)
                    else:
                        raise InvalidSettingsFileException('Sensor has no name element in ' + str(path)) 
            else:
                raise InvalidSettingsFileException('No sensors element in settings file: ' + str(path))
            internal_node = root.find(TAG_INTERNAL)
            if None is not internal_node:
                version_node = internal_node.find(TAG_VERSION)
                if None is not version_node:
                    self.version = version_node.text.strip()
        else:
            raise InvalidSettingsFileException(path + ' is not a valid settings file') 

    def __repr__(self):
        rv = ''
        rv += 'paths: ' + str(self.paths) + '\n'
        rv += 'sensors: ' + str(self.sensors) + '\n'
        rv += 'version: ' + str(self.version) + '\n'
        return rv

def get_settings(path):
    rv = None
    if os.path.exists(path):
        try:
            rv = Settings()
            rv.read(path)
        except Exception as ex:
            rv = None
            sys.stderr.write('Exception reading settings file: ' + str(ex))
    else:
        sys.stderr.write("Couldn't find settings file: " + str(path))
    return rv

def add_glob_to_zip(zf,src,dst,glob_str):
    files = glob(os.path.join(src,glob_str))
    for f in files:
        basename = os.path.basename(f)
        dst_path = os.path.join(dst,basename)
        zf.write(f,dst_path)

# FIXME: WHAT ABOUT UNINSTALL?
def create_base_script(zip_size,settings):
    rv = ''
    # Create the base script
    rv = '#!/usr/bin/bash\n'
    rv += 'if [ ! $EUID -eq 0 ]; then\n'
    rv += '    echo "Please run this install script as root"\n'
    rv += '    exit\n'
    rv += 'fi\n'
    rv += '# Make sure I2C is turned on...\n'
    rv += 'echo "Enabling I2C..."\n'
    rv += 'raspi-config nonint do_i2c 0\n'
    rv += 'ME=$(basename "$0")\n'
    rv += 'mkdir ' + UNZIP_DST + '\n'
        # Extract the zip file from the install script
    rv += 'dd bs=1 if="$ME" of=script.zip skip=' + SCRIPT_LEN_REPLACE_STR + ' count=' + str(zip_size) + '\n'
    rv += 'echo "Extracting files..."\n'
    rv += 'rm -rf ${UNZIP_DST}\n'
    rv += 'mkdir ${UNZIP_DST}\n'
    rv += 'unzip -q -d ' + UNZIP_DST + ' script.zip\n'
    rv += '# Setup up the data logger files...\n'

    for key in settings.paths.keys():
        rv += 'mkdir -p ' + settings.paths[key] + '\n'

    rv += 'echo "Copying data logger files..."\n'
    rv += 'cp ' + UNZIP_DST + '/data_logger.py ' + DATALOGGER_DST + '\n'
    rv += 'cp ' + UNZIP_DST + '/manifest.xml '  + DATALOGGER_DST + '\n'
    rv += 'cp ' + UNZIP_DST + '/settings.cfg '  + DATALOGGER_DST + '\n'
    rv += 'cp -r ' + UNZIP_DST + '/sensormods ' + DATALOGGER_DST + '\n'
    rv += 'cp -r ' + UNZIP_DST + '/ccs_base ' + DATALOGGER_DST + '\n'
    rv += 'cp -r ' + UNZIP_DST + '/ccs_dlconfig ' + DATALOGGER_DST + '\n'
    rv += 'cp -r ' + UNZIP_DST + '/system/ccsdatalogger.service ' + SYSTEMD_SERVICE_DST + '\n'

    rv += 'echo "Creating ccsdatalogger systemd service..."\n'
    rv += 'systemctl daemon-reload\n'
    rv += 'systemctl enable ccsdatalogger.service\n'
    rv += 'systemctl start ccsdatalogger.service\n'

    rv += 'rm -rf ' + UNZIP_DST + '\n'
    rv += 'rm -rf script.zip\n'
    rv += 'echo "Installation completed succesfully."\n'
    rv += 'exit\n'
    return rv

def run(args):
    global DATALOGGER_DST
    commit = ''
    prefix = DEFAULT_PREFIX
    version = DEFAULT_VERSION
    if None is not args.prefix:
        prefix = args.prefix
    if None is not args.commit:
        commit = args.commit
    else:
        # Popen call example...
        # Source - https://stackoverflow.com/a/92395
        # Posted by Eli Courtwright, modified by community. See post 'Timeline' for change history
        # Retrieved 2026-05-22, License - CC BY-SA 4.0
        commit = subprocess.Popen('git rev-parse HEAD', shell=True, stdout=subprocess.PIPE).stdout.read()
        commit = str(commit).strip()

    settings = get_settings(SETTINGS_FILE_NAME)
    if None is settings:
        sys.stderr.write('[!] settings is NULL!\n')
        return

    if TAG_BASE in settings.paths.keys():
        DATALOGGER_DST = settings.paths[TAG_BASE]
    else:
        sys.stderr.write('[!] Base directory is missing\n')
        return

    if (settings.version is not None) and (len(settings.version) > 0):
        version = settings.version

    cwd = os.getcwd()

    # Create the manifest
    with open(MANIFEST_NAME,'wt') as fd:
        fd.write('<manifest>\n')
        current_time = dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')
        fd.write('<time>' + current_time + '</time>\n')
        fd.write('<commit>' + commit + '</commit>\n')
        fd.write('<version>' + str(version) + '</version>\n')
        fd.write('</manifest>\n')

    # Create the systemd service file
    with open(SERVICE_FILE_NAME,'wt') as fd:
        fd.write('[Unit]\n')
        fd.write('Description=Clear Creek Scientific Data Logger\n')
        fd.write('StartLimitIntervalSec=300\n')
        fd.write('StartLimitBurst=5\n')
        fd.write('[Service]\n')
        fd.write('WorkingDirectory=' + settings.paths[TAG_BASE] + '\n')
        s = 'ExecStart=python ' + settings.paths[TAG_BASE] + '/data_logger.py -c' + settings.paths[TAG_BASE] + '/' + SETTINGS_FILE_NAME + '\n'
        fd.write(s) 
        fd.write('Restart=on-failure\n')
        fd.write('RestartSec=10s\n')
        fd.write('[Install]\n')
        fd.write('WantedBy=default.target\n')
 

    # Create the zip file
    zip_name = str(prefix) + '_v' + str(version) + ZIP_SUFFIX
    with zipfile.ZipFile(zip_name,mode='w') as zf:
        zf.write('settings.cfg','settings.cfg')
        zf.write('manifest.xml','manifest.xml')
        zf.write('../data_logger.py','data_logger.py')
        zf.mkdir('sensormods')
        add_glob_to_zip(zf,'../sensormods','./sensormods','*.py')
        zf.mkdir('ccs_base')
        add_glob_to_zip(zf,'../ccs_base','./ccs_base','*.py')
        zf.mkdir('ccs_dlconfig')
        add_glob_to_zip(zf,'../ccs_dlconfig','./ccs_dlconfig','*.py')
        zf.mkdir('system')
        zf.write('./system/ccsdatalogger.service','system/ccsdatalogger.service')

    zip_size = os.path.getsize(zip_name)

    script = create_base_script(zip_size,settings)

    base_len = len(script)
    idx = script.find(SCRIPT_LEN_REPLACE_STR)
    if idx > 0:
        x = f'{base_len:05d}'
        parts = script.split(SCRIPT_LEN_REPLACE_STR)
        if 2 == len(parts):
            script = parts[0] + x + parts[1]

    # Concatenate the base script and the zip file
    read_buf = ''
    install_script_name = str(prefix) + '_install_v' + str(version) + SCRIPT_SUFFIX
    with open(install_script_name,'wb') as fd:
        script = script.encode('utf-8')
        fd.write(script)
        with open(zip_name,'rb') as zfd:
            zip_buf = zfd.read()
        fd.write(zip_buf) 
    script_path = os.path.join(cwd,install_script_name)
    sys.stdout.write(script_path)
    

if '__main__' == __name__:
    parser = argparse.ArgumentParser()
    # We ignore version in this file
    parser.add_argument('-v','--version',help='version string')
    parser.add_argument('-c','--commit',help='commit string')
    parser.add_argument('-p','--prefix',help='prefix string')
    args = parser.parse_args()
    run(args)



