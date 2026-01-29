#!/bin/bash
# 봇 서비스 설치 스크립트

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"

echo "====================================="
echo "봇 서비스 설치 스크립트"
echo "====================================="

# systemd user 디렉토리 생성
mkdir -p "$SERVICE_DIR"

# 기존 프로세스 종료
echo "[1/5] 기존 프로세스 종료..."
pkill -f "dooray_agi_bot.py" 2>/dev/null || true
pkill -f "telegram_bot.py" 2>/dev/null || true
pkill -f "dooray_git_hook.py" 2>/dev/null || true
sleep 2

# 포트 정리
fuser -k 5000/tcp 2>/dev/null || true
fuser -k 5001/tcp 2>/dev/null || true
sleep 1

# 서비스 파일 복사
echo "[2/5] 서비스 파일 설치..."
cp "$SCRIPT_DIR/services/dooray-agi.service" "$SERVICE_DIR/"
cp "$SCRIPT_DIR/services/telegram-bot.service" "$SERVICE_DIR/"
cp "$SCRIPT_DIR/services/dooray-git-hook.service" "$SERVICE_DIR/"

# systemd 재로드
echo "[3/5] systemd 재로드..."
systemctl --user daemon-reload

# 서비스 활성화 및 시작
echo "[4/5] 서비스 시작..."
systemctl --user enable dooray-agi telegram-bot dooray-git-hook
systemctl --user start dooray-agi telegram-bot dooray-git-hook

# 로그인 없이도 서비스 유지
loginctl enable-linger "$USER" 2>/dev/null || true

# 헬스 모니터 cron 등록
echo "[5/5] 헬스 모니터 cron 등록..."
(crontab -l 2>/dev/null | grep -v "health_monitor.py"; echo "*/5 * * * * /usr/bin/python3 $SCRIPT_DIR/health_monitor.py >> /tmp/health_monitor.log 2>&1") | crontab -

sleep 3

# 상태 확인
echo ""
echo "====================================="
echo "서비스 상태:"
echo "====================================="
systemctl --user status dooray-agi --no-pager | head -5
echo ""
systemctl --user status telegram-bot --no-pager | head -5
echo ""
systemctl --user status dooray-git-hook --no-pager | head -5

echo ""
echo "====================================="
echo "설치 완료!"
echo "====================================="
echo "명령어:"
echo "  상태 확인: systemctl --user status dooray-agi"
echo "  로그 확인: journalctl --user -u dooray-agi -f"
echo "  재시작:    systemctl --user restart dooray-agi"
echo ""
