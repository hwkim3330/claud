#!/usr/bin/env python3
"""
봇 헬스 모니터링 스크립트
1분마다 실행하여 서비스 상태 체크 및 자동 복구
"""
import subprocess
import requests
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/health_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SERVICES = {
    'dooray-agi': {
        'port': 5000,
        'health_url': 'http://localhost:5000/health',
        'process_name': 'dooray_agi_bot.py'
    },
    'telegram-bot': {
        'port': None,  # polling 방식
        'health_url': None,
        'process_name': 'telegram_bot.py'
    },
    'dooray-git-hook': {
        'port': 5001,
        'health_url': 'http://localhost:5001/health',
        'process_name': 'dooray_git_hook.py'
    }
}

def check_process(process_name):
    """프로세스가 실행 중인지 확인"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', process_name],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False

def check_http_health(url):
    """HTTP 헬스체크"""
    try:
        resp = requests.get(url, timeout=5)
        return resp.status_code == 200
    except:
        return False

def restart_service(service_name):
    """systemd 서비스 재시작"""
    try:
        subprocess.run(['systemctl', '--user', 'restart', service_name], check=True)
        logger.info(f"서비스 재시작: {service_name}")
        return True
    except Exception as e:
        logger.error(f"서비스 재시작 실패 {service_name}: {e}")
        return False

def send_alert(message):
    """알림 전송"""
    try:
        subprocess.run([
            'python3', '/home/kim/dooray-claude-bot/claude_notify.py',
            f'[Health Monitor] {message}'
        ])
    except:
        pass

def check_all_services():
    """모든 서비스 체크"""
    issues = []

    for name, config in SERVICES.items():
        process_ok = check_process(config['process_name'])

        if config['health_url']:
            http_ok = check_http_health(config['health_url'])
        else:
            http_ok = process_ok  # HTTP 체크 없으면 프로세스 상태로 판단

        if not process_ok or not http_ok:
            issues.append(name)
            logger.warning(f"서비스 이상: {name} (process={process_ok}, http={http_ok})")

    return issues

def main():
    logger.info("헬스 체크 시작")

    issues = check_all_services()

    if issues:
        logger.warning(f"문제 발견: {issues}")
        for service in issues:
            if restart_service(service):
                time.sleep(5)  # 재시작 대기

        # 재시작 후 다시 체크
        time.sleep(10)
        still_broken = check_all_services()

        if still_broken:
            send_alert(f"서비스 복구 실패: {still_broken}")
    else:
        logger.info("모든 서비스 정상")

if __name__ == '__main__':
    main()
