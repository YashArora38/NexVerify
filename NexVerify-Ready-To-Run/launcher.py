"""NexVerify Windows local launcher. No installation, publication or chain sending."""
from pathlib import Path
import argparse
from http.client import HTTPConnection, HTTPException
import json
import os
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:3000'


def http(port, path, method='GET', body=None):
    connection = HTTPConnection('127.0.0.1', port, timeout=45)
    headers = {'Origin': URL}
    if body is not None:
        body = json.dumps(body)
        headers['Content-Type'] = 'application/json'
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    status = response.status
    connection.close()
    return status, data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    busy = []
    for port in (3000, 8000):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                busy.append(port)
    if busy:
        try:
            status, body = http(8000, '/api/health')
            health = json.loads(body)
            web_status, page = http(3000, '/')
            same_app = status == 200 and health.get('ok') and health.get('demo_names') and web_status == 200 and b'NexVerify' in page
        except (OSError, HTTPException, ValueError):
            same_app = False
        if same_app:
            print('NexVerify is already running: ' + URL, flush=True)
            if args.self_test:
                print('Existing frontend and API health checks passed; no second server was started.', flush=True)
            if not args.no_browser:
                try:
                    os.startfile(URL)
                except OSError:
                    print('Open this address in your browser: ' + URL, flush=True)
            return
        raise RuntimeError(f'Ports {busy} are already busy with another app. No existing process was stopped.')
    from dotenv import dotenv_values
    settings = dotenv_values(ROOT / 'settings.env')
    env = os.environ.copy()
    env.update({key: value for key, value in settings.items() if value is not None})
    data = ROOT / 'data'
    logs = data / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    env.update({
        'NEXVERIFY_ENV': 'development', 'NEXVERIFY_DATA_DIR': str(data),
        'DATABASE_URL': 'sqlite:///' + str(data / 'nexverify.db').replace('\\', '/'),
        'REDIS_URL': '', 'AI_SUMMARY': 'false', 'ENABLE_SCREENSHOTS': 'false',
        'NEXVERIFY_ALLOW_ACTIVE_BROWSER': 'false', 'NEXVERIFY_ANCHOR_PREPARATION': settings.get('NEXVERIFY_ANCHOR_PREPARATION', 'true'),
        'NEXVERIFY_ANCHOR_CONTRACT': settings.get('NEXVERIFY_ANCHOR_CONTRACT', '0x5FbDB2315678afecb367f032d93F642f64180aa3'),
        'NEXVERIFY_ANCHOR_CHAIN_ID': settings.get('NEXVERIFY_ANCHOR_CHAIN_ID', '11155111'),
        'FRONTEND_ORIGIN': URL, 'CORS_ORIGINS': URL + ',http://localhost:3000',
        'NEXVERIFY_ALLOWED_ORIGINS': URL + ',http://localhost:3000',
        'HOSTNAME': '127.0.0.1', 'PORT': '3000', 'NEXT_TELEMETRY_DISABLED': '1',
        'NEXT_PUBLIC_API_URL': '', 'NEXVERIFY_INTERNAL_API_URL': 'http://127.0.0.1:8000',
        'PYTHON': str(ROOT / 'runtime' / 'python' / 'python.exe'),
    })
    python = ROOT / 'runtime' / 'python' / 'python.exe'
    node = ROOT / 'runtime' / 'node' / 'node.exe'
    code = 'import sys;sys.path.insert(0,' + repr(str(ROOT / 'backend')) + ');import uvicorn;uvicorn.run("app.main:app",host="127.0.0.1",port=8000,access_log=False)'
    children, handles = [], []
    try:
        print('Starting NexVerify locally. Nothing will be deployed or sent to a blockchain.', flush=True)
        for name, command, cwd in (
            ('api', [str(python), '-c', code], ROOT / 'backend'),
            ('web', [str(node), 'server.js'], ROOT / 'frontend'),
        ):
            handle = (logs / f'{name}.log').open('ab')
            handles.append(handle)
            children.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A server could not start. See data/logs/api.log and web.log.')
            try:
                if http(8000, '/api/health')[0] == 200 and http(3000, '/')[0] == 200:
                    break
            except (OSError, HTTPException):
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError('Startup timed out. See data/logs for details.')
        print('READY: ' + URL, flush=True)
        if args.self_test:
            assert http(3000, '/api/health')[0] == 200
            status, body = http(3000, '/api/check', 'POST', {'query': 'QuickRupee', 'fresh': True})
            assert status == 200, body
            check_id = json.loads(body)['check_id']
            status, stream = http(3000, f'/api/check/{check_id}/stream')
            assert status == 200 and b'event: result' in stream
            status, body = http(3000, f'/api/check/{check_id}/verify')
            assert status == 200 and json.loads(body)['ok']
            status, body = http(3000, f'/api/check/{check_id}/bundle.zip')
            assert status == 200 and body[:2] == b'PK'
            status, body = http(3000, f'/api/check/{check_id}/integrity')
            assert json.loads(body)['anchor']['broadcast_enabled'] is False
            print('SELF-TEST PASSED: standalone frontend, proxy, demo stream, integrity and bundle.', flush=True)
            return
        if not args.no_browser:
            try:
                os.startfile(URL)
            except OSError:
                print('Open this address in your browser: ' + URL, flush=True)
        print('Keep this window open. Press Ctrl+C here to stop NexVerify.', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError('A server stopped. Check data/logs.')
    except KeyboardInterrupt:
        print('\nStopping NexVerify...', flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for handle in handles:
            handle.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Could not start NexVerify: ' + str(error), flush=True)
        raise SystemExit(1)
