#!/usr/bin/env python3
"""
Claude Code 작업 완료 알림
- 텔레그램/두레이로 알림 전송
- 버튼으로 후속 작업 선택
"""

import requests
import sys
import json
from datetime import datetime

# 설정
TELEGRAM_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"
TELEGRAM_CHAT_ID = "8341524797"
DOORAY_WEBHOOK = "https://keti.dooray.com/services/3711006199900720461/4145226571364668339/1QmQmcTCTMKf3FyF1OemZA"

def send_telegram(message, buttons=None):
    """텔레그램 알림 + 버튼"""
    if not TELEGRAM_CHAT_ID:
        print("텔레그램 chat_id 미설정")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    if buttons:
        keyboard = {
            "inline_keyboard": [
                [{"text": btn["text"], "callback_data": btn["data"]} for btn in row]
                for row in buttons
            ]
        }
        payload["reply_markup"] = json.dumps(keyboard)

    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"텔레그램 오류: {e}")
        return False

def send_dooray(message):
    """두레이 알림"""
    try:
        requests.post(DOORAY_WEBHOOK, json={
            "botName": "🤖 Claude 알림",
            "text": message
        }, timeout=10)
        return True
    except Exception as e:
        print(f"두레이 오류: {e}")
        return False

def notify_completion(task_summary="작업 완료"):
    """작업 완료 알림"""
    now = datetime.now().strftime("%H:%M")

    message = f"""✅ **Claude Code 작업 완료**

⏰ {now}
📋 {task_summary}

다음 작업을 선택하세요:"""

    # 버튼 옵션
    buttons = [
        [
            {"text": "📊 시세 조회", "data": "cmd_prices"},
            {"text": "💰 포트폴리오", "data": "cmd_portfolio"}
        ],
        [
            {"text": "📈 시장 분석", "data": "cmd_analysis"},
            {"text": "🔄 계속 작업", "data": "cmd_continue"}
        ]
    ]

    # 두레이 알림 (버튼 없음)
    dooray_msg = f"""## ✅ Claude Code 작업 완료

⏰ {now}
📋 {task_summary}

두레이에서 `/s 시세` 또는 `/s 투자`로 확인하세요!"""

    send_dooray(dooray_msg)
    send_telegram(message, buttons)

    print(f"[{now}] 알림 전송 완료: {task_summary}")

if __name__ == "__main__":
    # 커맨드라인 인자로 작업 요약 받기
    summary = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "작업 완료"
    notify_completion(summary)
