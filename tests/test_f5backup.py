import base64
import http.server
import json
import subprocess
import threading

import pytest

import f5backup


def basic_auth(user, password):
    token = base64.b64encode(f'{user}:{password}'.encode()).decode()
    return f'Basic {token}'


def make_config(tmp_path, **overrides):
    config = {
        'f5_prod': '10.0.0.1',
        'f5_dev': '10.0.0.2',
        'f5_bench': '10.0.0.3',
        'f5_url_prod': 'https://10.0.0.1/mgmt/tm/sys/ucs',
        'f5_url_dev': 'https://10.0.0.2/mgmt/tm/sys/ucs',
        'f5_url_bench': 'https://10.0.0.3/mgmt/tm/sys/ucs',
        'api_user_prod': 'admin',
        'api_passwd_prod': 'prodpass',
        'api_user_dev': 'admin',
        'api_passwd_dev': 'devpass',
        'api_user_bench': 'f5backup',
        'api_passwd_bench': 'benchpass',
        'headers': {'content-type': 'application/json'},
        'payload': {'command': 'save', 'name': 'f5backup.ucs'},
        'ssl_certificate': True,
        'api_timeout': 5,
        'f5_user': 'f5backup',
        'timeout': 5,
        'key_filename': str(tmp_path / 'key_files' / 'f5backup'),
        'ucs_files': '/var/local/ucs/f5backup.ucs',
        'commit_msg': 'f5 config daily auto backup',
        'backup_dir': str(tmp_path / 'backups'),
        'log_file': str(tmp_path / 'f5backup.log'),
    }
    config.update(overrides)
    return config


@pytest.fixture
def http_server():
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            seen.append({
                'auth': self.headers['Authorization'],
                'body': json.loads(body),
            })
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd, seen
    httpd.shutdown()


def test_targets_from_config(tmp_path):
    config = make_config(tmp_path)
    assert [t['name'] for t in f5backup.targets(config)] == ['prod', 'dev', 'bench']


def test_save_posts_to_every_host(tmp_path, http_server):
    httpd, seen = http_server
    url = f'http://127.0.0.1:{httpd.server_port}/mgmt/tm/sys/ucs'
    config = make_config(tmp_path, f5_url_prod=url, f5_url_dev=url, f5_url_bench=url)

    assert f5backup.save_ucs(config) == 0
    assert [s['auth'] for s in seen] == [
        basic_auth('admin', 'prodpass'),
        basic_auth('admin', 'devpass'),
        basic_auth('f5backup', 'benchpass'),
    ]
    assert all(s['body'] == {'command': 'save', 'name': 'f5backup.ucs'} for s in seen)


def test_push_commits_and_pushes(tmp_path):
    remote = tmp_path / 'remote.git'
    work = tmp_path / 'work'
    subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(remote)], check=True, capture_output=True)
    subprocess.run(['git', 'clone', str(remote), str(work)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(work), 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', str(work), 'config', 'user.name', 'Test'], check=True)
    (work / 'f5backup.ucs').write_text('one')
    subprocess.run(['git', '-C', str(work), 'add', '-A'], check=True)
    subprocess.run(['git', '-C', str(work), 'commit', '-m', 'initial'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(work), 'push', '-u', 'origin', 'main'], check=True, capture_output=True)

    (work / 'f5backup.ucs').write_text('two')
    config = make_config(tmp_path, backup_dir=str(work))

    assert f5backup.push(config) == 0
    assert subprocess.run(
        ['git', '-C', str(remote), 'show', 'main:f5backup.ucs'],
        capture_output=True, text=True, check=True,
    ).stdout == 'two'

    # nothing new to commit is not an error
    assert f5backup.push(config) == 0
