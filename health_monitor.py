#!/usr/bin/env python3
"""
봇 헬스 모니터링 - 간소화 버전
"""
import subprocess
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

# 모니터링할 서비스 (systemd user service)
SERVICES = {
    'moltbot-gateway': {
        'process_name': 'moltbot-gateway',
        'systemd_name': 'moltbot-gateway'
    },
    'claude-api-proxy': {
        'process_name': 'claude_api_proxy.py',
        'systemd_name': 'claude-api-proxy'
    }
}


def check_process(process_name):
    """프로세스 실행 확인"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', process_name],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def check_systemd_service(service_name):
    """systemd 서비스 상태 확인 (cron 환경 지원)"""
    try:
        import os
        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = f"/run/user/{os.getuid()}"
        result = subprocess.run(
            ['systemctl', '--user', 'is-active', service_name],
            capture_output=True,
            text=True,
            env=env
        )
        return result.stdout.strip() == 'active'
    except:
        return False


def restart_service(service_name):
    """systemd 서비스 재시작 (cron 환경 지원)"""
    try:
        import os
        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = f"/run/user/{os.getuid()}"
        subprocess.run(['systemctl', '--user', 'restart', service_name], check=True, env=env)
        logger.info(f"서비스 재시작: {service_name}")
        return True
    except Exception as e:
        logger.error(f"재시작 실패 {service_name}: {e}")
        return False


def send_alert(message):
    """Dooray 알림"""
    try:
        subprocess.run([
            'python3', '/home/kim/dooray-claude-bot/claude_notify.py',
            f'[Health Monitor] {message}'
        ], timeout=30)
    except:
        pass


def main():
    logger.info("헬스 체크 시작")
    issues = []

    for name, config in SERVICES.items():
        process_ok = check_process(config['process_name'])
        systemd_ok = check_systemd_service(config['systemd_name'])

        if not process_ok or not systemd_ok:
            issues.append(name)
            logger.warning(f"서비스 이상: {name} (process={process_ok}, systemd={systemd_ok})")

            # 재시작 시도
            if restart_service(config['systemd_name']):
                import time
                time.sleep(5)
                # 재확인
                if check_process(config['process_name']):
                    logger.info(f"복구 성공: {name}")
                    issues.remove(name)

    if issues:
        send_alert(f"서비스 복구 실패: {issues}")
    else:
        logger.info("모든 서비스 정상")


if __name__ == '__main__':
    main()
