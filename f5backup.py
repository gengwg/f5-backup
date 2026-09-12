#!/usr/bin/env python3

__author__ = 'WGeng'
__email__ = 'gengwg@github.com'
__version__ = '0.2.0'

"""
A Script to back up the F5 configs.
Run as a cronjob to back up the configs daily.
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import date

import paramiko
import requests


def load_config(conf_file):
    config = {}
    with open(conf_file, encoding='utf-8') as f:
        exec(compile(f.read(), conf_file, 'exec'), config)
    return config


def targets(config):
    return [
        {
            'name': 'prod',
            'host': config['f5_prod'],
            'url': config['f5_url_prod'],
            'api_user': config['api_user_prod'],
            'api_password': config['api_passwd_prod'],
            'ssh_user': config['f5_user'],
            'ssh_password': None,
        },
        {
            'name': 'dev',
            'host': config['f5_dev'],
            'url': config['f5_url_dev'],
            'api_user': config['api_user_dev'],
            'api_password': config['api_passwd_dev'],
            'ssh_user': config['api_user_dev'],
            'ssh_password': config['api_passwd_dev'],
        },
        {
            'name': 'bench',
            'host': config['f5_bench'],
            'url': config['f5_url_bench'],
            'api_user': config['api_user_bench'],
            'api_password': config['api_passwd_bench'],
            'ssh_user': config['api_user_bench'],
            'ssh_password': config['api_passwd_bench'],
        },
    ]


def save_ucs(config):
    """Create UCS backup files on the F5s."""
    for target in targets(config):
        try:
            r = requests.post(
                target['url'],
                auth=(target['api_user'], target['api_password']),
                headers=config['headers'],
                json=config['payload'],
                verify=config['ssl_certificate'],
                timeout=config.get('api_timeout', 60),
            )
            r.raise_for_status()
            logging.info('%s: UCS save requested', target['name'])
        except requests.RequestException as e:
            logging.error('%s: UCS save failed: %s', target['name'], e)
            return 1
    return 0


def download(config):
    """Download the UCS file from each F5 into backup_dir/<name>/f5-backup-<date>/."""
    today = date.today().strftime('%Y%m%d')
    rc = 0
    for target in targets(config):
        local_dir = os.path.join(config['backup_dir'], target['name'], f'f5-backup-{today}')
        os.makedirs(local_dir, exist_ok=True)
        try:
            with paramiko.SSHClient() as client:
                client.load_system_host_keys()
                client.connect(
                    target['host'],
                    username=target['ssh_user'],
                    password=target['ssh_password'],
                    key_filename=config['key_filename'],
                    timeout=config['timeout'],
                )
                sftp = client.open_sftp()
                try:
                    sftp.get(
                        config['ucs_files'],
                        os.path.join(local_dir, os.path.basename(config['ucs_files'])),
                    )
                finally:
                    sftp.close()
            logging.info('%s: downloaded %s to %s', target['name'], config['ucs_files'], local_dir)
        except (paramiko.SSHException, OSError) as e:
            logging.error('%s: download failed: %s', target['name'], e)
            rc = 1
    return rc


def push(config):
    """Commit and push the backups."""
    try:
        subprocess.run(['git', '-C', config['backup_dir'], 'add', '-A'], check=True)
        commit = subprocess.run(
            ['git', '-C', config['backup_dir'], 'commit', '-m', config['commit_msg']],
            capture_output=True, text=True,
        )
        if commit.returncode != 0 and 'nothing to commit' not in commit.stdout:
            logging.error('git commit failed: %s', commit.stdout.strip() or commit.stderr.strip())
            return 1
        subprocess.run(['git', '-C', config['backup_dir'], 'push'], check=True)
    except subprocess.CalledProcessError as e:
        logging.error('git command failed: %s', e)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'command', nargs='?', default='all',
        choices=['all', 'save', 'download', 'push'],
        help='run one step or all of them (default: %(default)s)',
    )
    parser.add_argument('-c', '--config', default='./f5backup.conf')
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except OSError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1

    log_dir = os.path.dirname(config['log_file'])
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=config['log_file'],
        format='%(asctime)s %(levelname)s %(message)s',
    )

    rc = 0
    if args.command in ('all', 'save'):
        rc |= save_ucs(config)
    if args.command in ('all', 'download'):
        rc |= download(config)
    if args.command in ('all', 'push'):
        rc |= push(config)
    return rc


if __name__ == '__main__':
    sys.exit(main())
