#!/usr/bin/env python3
"""
MoltBot Cron Runner - Claude CLI 기반 자동화
Telegram + Dooray 동시 전송
"""

import subprocess
import requests
import sys
import os
from datetime import datetime

# 설정
DOORAY_WEBHOOK = "https://keti.dooray.com/services/3711006199900720461/4145226571364668339/1QmQmcTCTMKf3FyF1OemZA"
TELEGRAM_CHAT_ID = "8341524797"
MOLTBOT_PATH = "/home/kim/dooray-claude-bot/moltbot/moltbot.mjs"


def ask_claude(prompt: str) -> str:
    """Claude CLI 호출"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        if result.returncode == 0:
            return result.stdout.strip()[:4000]
        return f"Claude 오류: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "시간 초과 (120초)"
    except Exception as e:
        return f"오류: {e}"


TELEGRAM_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"

def send_telegram(message: str) -> bool:
    """Telegram으로 메시지 전송 (직접 API)"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4000],
            "parse_mode": "Markdown"
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram 전송 실패: {e}")
        return False


def send_dooray(message: str, title: str = "") -> bool:
    """Dooray 웹훅으로 메시지 전송"""
    try:
        payload = {
            "botName": "Moltbot",
            "text": message[:4000]
        }
        if title:
            payload["attachments"] = [{
                "title": title,
                "text": message[:2000],
                "color": "blue"
            }]

        resp = requests.post(DOORAY_WEBHOOK, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Dooray 전송 실패: {e}")
        return False


def send_both(message: str, title: str = ""):
    """Telegram + Dooray 둘 다 전송"""
    formatted = f"**{title}**\n\n{message}" if title else message

    tg_ok = send_telegram(formatted)
    dr_ok = send_dooray(message, title)

    status = []
    if tg_ok:
        status.append("Telegram ✓")
    else:
        status.append("Telegram ✗")
    if dr_ok:
        status.append("Dooray ✓")
    else:
        status.append("Dooray ✗")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {' | '.join(status)}")
    return tg_ok or dr_ok


# 자동화 작업 정의
JOBS = {
    "news": {
        "title": "🗞️ 아침 뉴스",
        "prompt": "GeekNews(https://news.hada.io)에서 오늘의 주요 기술 뉴스 5개를 가져와서 한국어로 간략히 요약해줘. 각 뉴스는 제목과 핵심 내용 1-2문장으로. 마크다운 형식."
    },
    "investment": {
        "title": "💰 투자 리마인더",
        "prompt": "오늘의 투자 리마인더: 1) 미국 증시 마감 현황 (S&P500, 나스닥), 2) 원달러 환율, 3) 오늘 주시해야 할 이벤트. 간략히 마크다운 형식으로."
    },
    "stock": {
        "title": "📊 주식 시장 분석",
        "prompt": "오늘 한국 주식시장 분석: 1) 코스피/코스닥 지수 동향, 2) 주요 이슈 3개, 3) 주목할 섹터. 간결하게 마크다운으로."
    },
    "lunch": {
        "title": "🍽️ 점심 추천",
        "prompt": "오늘 점심 뭐 먹을까? 날씨와 계절을 고려해서 3가지 추천해줘. 간단한 이유도 함께. 마크다운 형식."
    }
}


def run_job(job_name: str):
    """작업 실행"""
    if job_name not in JOBS:
        print(f"알 수 없는 작업: {job_name}")
        print(f"사용 가능: {', '.join(JOBS.keys())}")
        return False

    job = JOBS[job_name]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 실행: {job['title']}")

    # Claude에게 질문
    response = ask_claude(job["prompt"])

    # 결과 전송
    return send_both(response, job["title"])


def run_custom(prompt: str, title: str = "📝 Custom"):
    """커스텀 프롬프트 실행"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 실행: {title}")
    response = ask_claude(prompt)
    return send_both(response, title)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법:")
        print(f"  {sys.argv[0]} <job_name>")
        print(f"  {sys.argv[0]} custom <prompt>")
        print(f"\n작업 목록: {', '.join(JOBS.keys())}")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "custom" and len(sys.argv) > 2:
        run_custom(" ".join(sys.argv[2:]))
    elif cmd in JOBS:
        run_job(cmd)
    else:
        print(f"알 수 없는 명령: {cmd}")
        sys.exit(1)
