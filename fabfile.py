#!/usr/bin/env python

__author__    = 'WGeng'
__email__     = "gengwg@github.com"
__version__   = '0.1.2'

"""
A Script to back up the F5 configs.
Run as a cronjob to back up the configs daily.
"""

from fabric.api import env, hosts
from fabric.operations import run, put, get, local
from fabric.network import *

import logging
from logging import log
from datetime import date
import requests

import json

# helper function
def _parse_config(conf_file):
    myconfig = {}
    execfile(conf_file, myconfig)
    return myconfig

conf_file = './f5backup.conf'

try:
    config = _parse_config(conf_file)
except IOError as e:
    log(logging.ERROR, "Couldn't open config directory.")
    sys.exit(1)

try:
    if not os.path.exists("./logs/"):
        os.mkdir("logs")
except OSError, e:
    log(logging.ERROR, "Couldn't create logs directory.")
logging.basicConfig(level=logging.INFO, filename=config["log_file"])

env.user = config['f5_user']
env.hosts = [ config['f5_prod'], config['f5_dev'], config['f5_bench'] ]
env.timeout = config['timeout']
env.key_filename = config['key_filename']
env.warn_only = True
env.skip_bad_hosts = True
#env.parallel=True


#def save_ucs(f5_url='', api_user='', api_passwd=''):
def save_ucs():
    """Create ucs backup files on F5."""
    try:
        r_prod = requests.post(config['f5_url_prod'], verify=config['ssl_certificate'], auth=(config['api_user_prod'], config['api_passwd_prod']), headers=config['headers'], data=json.dumps(config['payload']))
        r_dev = requests.post(config['f5_url_dev'], verify=config['ssl_certificate'], auth=(config['api_user_dev'], config['api_passwd_dev']), headers=config['headers'], data=json.dumps(config['payload']))
        r_bench = requests.post(config['f5_url_bench'], verify=config['ssl_certificate'], auth=(config['api_user_bench'], config['api_passwd_bench']), headers=config['headers'], data=json.dumps(config['payload']))
    except requests.exceptions.RequestException as e:
        #print e
        log(logging.ERROR, e)
        sys.exit(1)

def backup():
    """Dowload ucs backup files on F5 to local."""
    log( logging.INFO, "Starting backup at " + date.today().strftime("%m/%d/%Y") )

    # make sure the directory is there!
    try:
        if not os.path.exists(config['backup_dir']):
            #os.mkdir(config['backup_dir'])
            os.system('mkdir -p ' + config['backup_dir'])
    except OSError, e:
        log(logging.ERROR, "Couldn't create backup directory: " + config['backup_dir'])
        sys.exit(1)

    # our local 'testdirectory' - it may contain files or subdirectories ...
    #get('/var/local/ucs/*.ucs', config['backup_dir'])


    # Construct different back up dir for each F5
    if env.host == config['f5_prod']:
        #print '==> Hi, Im prod!!'
        mybackup_dir = config['backup_dir'] + '/prod/f5-backup-' + date.today().strftime("%Y%m%d")
    if env.host == config['f5_dev']:
        env.user = config['api_user_dev']
        env.password = config['api_passwd_dev']
        mybackup_dir = config['backup_dir'] + '/dev/f5-backup-' + date.today().strftime("%Y%m%d")
    if env.host == config['f5_bench']:
        env.user = config['api_user_bench']
        env.password = config['api_passwd_bench']
        mybackup_dir = config['backup_dir'] + '/bench/f5-backup-' + date.today().strftime("%Y%m%d")
    else:
        pass
        #log(logging.ERROR, "Something wrong with your F5 host address. Please check!!")
        #sys.exit(1)

    # make sure the directory is there!
    try:
        if not os.path.exists(mybackup_dir):
            os.system('mkdir -p ' + mybackup_dir)
    except OSError, e:
        log(logging.ERROR, "Couldn't create backup directory: " + mybackup_dir)
        sys.exit(1)

    #download = get(config['ucs_files'], config['backup_dir'])
    download = get(config['ucs_files'], mybackup_dir)
    if download.succeeded:
        log( logging.INFO, "Successfully downloaded f5 config at " + date.today().strftime("%m/%d/%Y") + ' in directory: ' + mybackup_dir )
    else:
        log( logging.ERROR, "Failed downloaded f5 config at " + date.today().strftime("%m/%d/%Y") )

    disconnect_all()

    log( logging.INFO, "Done backup at " + date.today().strftime("%m/%d/%Y") )

@hosts('localhost')
def push_gitlab():
    cmd = "cd {} && git add -A && git commit -m \"{}\" && git push".format(config['backup_dir'], config['commit_msg'] )
    local(cmd, capture=True)

"""
def backup():
    save_ucs()
    download_ucs()
    push_gitlab()
"""
