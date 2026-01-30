#!/usr/bin/env python3
"""
자율 에이전트 - 알아서 일하고 먼저 말 거는 봇
- Heartbeat: 주기적으로 상태 확인하고 알림
- 자율 작업: 조건에 따라 알아서 실행
- 모니터링: 시스템/주식/뉴스 감시
"""

import subprocess
import requests
import json
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

# 설정
TELEGRAM_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"
TELEGRAM_CHAT_ID = "8341524797"
DOORAY_WEBHOOK = "https://keti.dooray.com/services/3711006199900720461/4145226571364668339/1QmQmcTCTMKf3FyF1OemZA"
STATE_FILE = Path("/home/kim/dooray-claude-bot/agent_state.json")

# 상태 관리
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {
        "last_greeting": None,
        "last_stock_alert": None,
        "last_system_check": None,
        "watched_stocks": {},
        "alerts_sent": []
    }

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str))

STATE = load_state()


# ═══════════════════════════════════════════════════════════════
# 메시지 전송
# ═══════════════════════════════════════════════════════════════

def send_telegram(message: str):
    """Telegram 전송"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4000],
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        print(f"Telegram 오류: {e}")


def send_dooray(message: str):
    """Dooray 전송"""
    try:
        requests.post(DOORAY_WEBHOOK, json={
            "botName": "AutoAgent",
            "text": message[:2000]
        }, timeout=10)
    except:
        pass


def send_both(message: str):
    """둘 다 전송"""
    send_telegram(message)
    send_dooray(message)


def ask_claude(prompt: str) -> str:
    """Claude CLI"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        return result.stdout.strip()[:3000] if result.returncode == 0 else ""
    except:
        return ""


# ═══════════════════════════════════════════════════════════════
# 자율 기능들
# ═══════════════════════════════════════════════════════════════

def check_morning_greeting():
    """아침 인사 (평일 8시)"""
    now = datetime.now()

    # 평일 8시~8시30분
    if now.weekday() >= 5:  # 주말
        return
    if not (8 <= now.hour < 9 and now.minute < 30):
        return

    # 오늘 이미 인사했는지
    last = STATE.get("last_greeting")
    if last and datetime.fromisoformat(last).date() == now.date():
        return

    # Claude에게 아침 인사 생성 요청
    greeting = ask_claude(
        "오늘 날짜와 요일을 확인하고, 짧은 아침 인사를 해줘. "
        "오늘의 주요 일정이나 체크할 것이 있으면 알려줘. 2-3문장으로."
    )

    if greeting:
        send_telegram(f"☀️ **좋은 아침이에요!**\n\n{greeting}")
        STATE["last_greeting"] = now.isoformat()
        save_state(STATE)
        print(f"[{now.strftime('%H:%M')}] 아침 인사 전송")


def check_stock_alerts():
    """주식 급등락 알림"""
    now = datetime.now()

    # 장 시간만 (9시~15시30분)
    if now.weekday() >= 5:
        return
    if not (9 <= now.hour < 16):
        return

    # 10분에 한번만
    last = STATE.get("last_stock_alert")
    if last:
        last_time = datetime.fromisoformat(last)
        if (now - last_time).seconds < 600:
            return

    # 관심종목 체크
    stocks = [
        ("SK하이닉스", "000660"),
        ("삼성전자", "005930"),
        ("한화에어로", "012450"),
    ]

    alerts = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for name, code in stocks:
        try:
            url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            resp = requests.get(url, timeout=5, headers=headers)
            data = resp.json()
            rate = float(data.get("fluctuationsRatio", "0"))
            price = data.get("closePrice", "N/A")

            # 3% 이상 변동시 알림
            if abs(rate) >= 3:
                emoji = "🚀" if rate > 0 else "📉"
                sign = "+" if rate > 0 else ""
                alerts.append(f"{emoji} **{name}**: {price}원 ({sign}{rate}%)")
        except:
            pass

    if alerts:
        message = "⚠️ **주식 알림**\n\n" + "\n".join(alerts)
        send_telegram(message)
        print(f"[{now.strftime('%H:%M')}] 주식 알림: {len(alerts)}건")

    STATE["last_stock_alert"] = now.isoformat()
    save_state(STATE)


def check_system_health():
    """시스템 상태 모니터링"""
    now = datetime.now()

    # 30분마다
    last = STATE.get("last_system_check")
    if last:
        last_time = datetime.fromisoformat(last)
        if (now - last_time).seconds < 1800:
            return

    import psutil

    alerts = []

    # CPU 90% 이상
    cpu = psutil.cpu_percent(interval=1)
    if cpu > 90:
        alerts.append(f"🔴 CPU: {cpu}%")

    # 메모리 90% 이상
    mem = psutil.virtual_memory()
    if mem.percent > 90:
        alerts.append(f"🔴 메모리: {mem.percent}%")

    # 디스크 95% 이상
    disk = psutil.disk_usage('/')
    if disk.percent > 95:
        alerts.append(f"🔴 디스크: {disk.percent}%")

    if alerts:
        message = "🚨 **시스템 경고**\n\n" + "\n".join(alerts)
        send_both(message)
        print(f"[{now.strftime('%H:%M')}] 시스템 경고: {alerts}")

    STATE["last_system_check"] = now.isoformat()
    save_state(STATE)


def check_evening_summary():
    """저녁 요약 (평일 18시)"""
    now = datetime.now()

    if now.weekday() >= 5:
        return
    if not (18 <= now.hour < 19 and now.minute < 30):
        return

    last = STATE.get("last_evening")
    if last and datetime.fromisoformat(last).date() == now.date():
        return

    # 오늘 하루 요약
    summary = ask_claude(
        "오늘 하루를 마무리하며 짧은 저녁 인사를 해줘. "
        "내일 체크할 것이 있으면 리마인드해줘. 2-3문장으로."
    )

    if summary:
        send_telegram(f"🌙 **수고하셨어요!**\n\n{summary}")
        STATE["last_evening"] = now.isoformat()
        save_state(STATE)
        print(f"[{now.strftime('%H:%M')}] 저녁 요약 전송")


def proactive_check():
    """주기적으로 뭔가 할 게 있는지 확인"""
    now = datetime.now()

    # 1시간마다
    last = STATE.get("last_proactive")
    if last:
        last_time = datetime.fromisoformat(last)
        if (now - last_time).seconds < 3600:
            return

    # Claude에게 뭔가 할 게 있는지 물어보기 (가끔만)
    if now.minute == 0:  # 정각에만
        response = ask_claude(
            f"지금 시간은 {now.strftime('%Y-%m-%d %H:%M')}이야. "
            "지금 시간에 사용자에게 알려줄 만한 것이 있어? "
            "없으면 '없음'이라고만 답해. 있으면 짧게 알려줘."
        )

        if response and "없음" not in response and len(response) > 10:
            send_telegram(f"💡 {response}")
            print(f"[{now.strftime('%H:%M')}] 자율 알림 전송")

    STATE["last_proactive"] = now.isoformat()
    save_state(STATE)


# ═══════════════════════════════════════════════════════════════
# 메인 루프
# ═══════════════════════════════════════════════════════════════

def run_checks():
    """모든 체크 실행"""
    try:
        check_morning_greeting()
        check_stock_alerts()
        check_system_health()
        check_evening_summary()
        proactive_check()
    except Exception as e:
        print(f"체크 오류: {e}")


def main():
    print("=" * 50)
    print("🤖 자율 에이전트 시작")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 시작 알림
    send_telegram("🤖 **자율 에이전트 시작됨**\n모니터링을 시작합니다.")

    while True:
        try:
            run_checks()
            time.sleep(60)  # 1분마다 체크
        except KeyboardInterrupt:
            print("\n종료")
            send_telegram("🤖 자율 에이전트가 종료되었습니다.")
            break
        except Exception as e:
            print(f"오류: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
