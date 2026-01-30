#!/usr/bin/env python3
"""
매일 투자 리마인더 - 두레이 전송
"""

import requests
import json
from datetime import datetime, timedelta

DOORAY_WEBHOOK = "https://keti.dooray.com/services/3711006199900720461/4145226571364668339/1QmQmcTCTMKf3FyF1OemZA"
PLAN_FILE = "/home/kim/dooray-claude-bot/dooray_data/investment_plan.json"

def load_plan():
    """투자 계획 로드"""
    try:
        with open(PLAN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def get_stock_data():
    """주식 데이터 가져오기"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        # 코스피
        resp = requests.get(
            "https://m.stock.naver.com/api/index/KOSPI/basic",
            headers=headers, timeout=10
        )
        kospi = resp.json()

        # 코스닥
        resp2 = requests.get(
            "https://m.stock.naver.com/api/index/KOSDAQ/basic",
            headers=headers, timeout=10
        )
        kosdaq = resp2.json()

        # 환율
        resp3 = requests.get(
            "https://m.stock.naver.com/api/marketindex/FX_USDKRW/basic",
            headers=headers, timeout=10
        )
        usd = resp3.json() if resp3.status_code == 200 else {}

        return {
            "kospi": kospi.get("closePrice", "N/A"),
            "kospi_rate": kospi.get("fluctuationsRatio", "0"),
            "kosdaq": kosdaq.get("closePrice", "N/A"),
            "kosdaq_rate": kosdaq.get("fluctuationsRatio", "0"),
            "usd": usd.get("closePrice", "N/A"),
            "usd_rate": usd.get("fluctuationsRatio", "0")
        }
    except Exception as e:
        print(f"주식 데이터 오류: {e}")
        return None

def calculate_dday():
    """D-day 계산"""
    today = datetime.now().date()

    # KB증권 이전 마감일
    kb_deadline = datetime(2026, 2, 28).date()
    kb_dday = (kb_deadline - today).days

    # ISA 매수 시작일
    buy_start = datetime(2026, 2, 3).date()
    buy_dday = (buy_start - today).days

    return {
        "kb_transfer": kb_dday,
        "buy_start": buy_dday
    }

def send_reminder():
    """리마인더 전송"""
    now = datetime.now()
    plan = load_plan()
    stock = get_stock_data()
    dday = calculate_dday()

    day_names = ["월", "화", "수", "목", "금", "토", "일"]
    weekday = day_names[now.weekday()]
    # Python weekday(): 월=0, 화=1, 수=2, 목=3, 금=4, 토=5, 일=6

    # 주말이면 간단히
    if now.weekday() >= 5:
        message = f"""## 📅 {now.strftime('%Y-%m-%d')}({weekday}) 주말 리마인더

주말엔 쉬세요! 월요일에 만나요 👋"""
    else:
        # 시장 정보
        market_info = ""
        if stock:
            kospi_emoji = "🔴" if float(stock["kospi_rate"]) > 0 else "🔵" if float(stock["kospi_rate"]) < 0 else "⚪"
            kosdaq_emoji = "🔴" if float(stock["kosdaq_rate"]) > 0 else "🔵" if float(stock["kosdaq_rate"]) < 0 else "⚪"

            market_info = f"""### 📊 시장 현황
{kospi_emoji} 코스피: {stock['kospi']} ({stock['kospi_rate']}%)
{kosdaq_emoji} 코스닥: {stock['kosdaq']} ({stock['kosdaq_rate']}%)
💵 환율: {stock['usd']}원 ({stock['usd_rate']}%)
"""

        # D-day 정보
        dday_info = f"""### ⏰ D-Day
- KB증권 ISA 이전 마감: **D-{dday['kb_transfer']}** (2/28까지)
- ISA 매수 시작: **D-{dday['buy_start']}** (2/3~)
"""

        # 포트폴리오 요약
        portfolio_info = ""
        if plan:
            total = plan['isa_portfolio']['total']
            portfolio_info = f"""### 💰 ISA 투자 계획 ({total/10000:.0f}만원)
| ETF | 비중 | 금액 |
|-----|------|------|
| S&P500 | 40% | 2,640만원 |
| 나스닥100 | 20% | 1,320만원 |
| 배당다우존스 | 15% | 990만원 |
| 금현물 | 10% | 660만원 |
| 단기채권 | 10% | 660만원 |
"""

        # 오늘 할 일
        todo = ""
        if dday['kb_transfer'] <= 30:
            todo = """### ✅ 오늘 체크
- [ ] KB증권 ISA 이전 신청 확인
- [ ] 현대카드 M포인트 잔액 확인
"""

        message = f"""## 📅 {now.strftime('%Y-%m-%d')}({weekday}) 투자 리마인더

{market_info}
{dday_info}
{portfolio_info}
{todo}
좋은 하루 되세요! 💪"""

    # 전송
    try:
        requests.post(DOORAY_WEBHOOK, json={
            "botName": "📈 투자봇",
            "text": message
        }, timeout=10)
        print(f"[{now}] 투자 리마인더 전송 완료")
    except Exception as e:
        print(f"[{now}] 전송 실패: {e}")

if __name__ == "__main__":
    print("=" * 40)
    print("📈 투자 리마인더 전송")
    print("=" * 40)
    send_reminder()
    print("완료!")
