#!/usr/bin/env python3
"""
몰트봇 자동 스케줄러 v2 - 완전 자동화
- 뉴스 기반 프로 분석
- 지정학적 리스크 모니터링
- 자동 브리핑 & 알림
"""

import requests
import time
import schedule
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, '/home/kim/dooray-claude-bot')

TELEGRAM_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"
TELEGRAM_CHAT_ID = "8341524797"
HAIKU_URL = "http://127.0.0.1:8180/v1/messages"
STATE_FILE = Path("/mnt/data/claude-memory/scheduler_state.json")


def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except:
        pass
    return {"last_alerts": {}, "last_report": None}


def save_state(state):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str))
    except:
        pass


def get_ai_response(prompt, model="sonnet"):
    """AI 응답 받기"""
    try:
        resp = requests.post(
            HAIKU_URL,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 3000
            },
            timeout=180
        )
        if resp.status_code == 200:
            data = resp.json()
            if "content" in data and len(data["content"]) > 0:
                return data["content"][0].get("text", "")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M')}] AI 오류: {e}")
    return None


def send_telegram(message, parse_mode="Markdown"):
    """텔레그램 전송"""
    try:
        max_len = 4000
        parts = [message[i:i+max_len] for i in range(0, len(message), max_len)]
        for part in parts:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": parse_mode},
                timeout=10
            )
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M')}] 텔레그램 오류: {e}")
        return False


def get_stock_prices():
    """주요 종목 시세"""
    try:
        from kiwoom_trader import KiwoomTrader
        trader = KiwoomTrader(use_mock=False, test_mode=True)

        stocks = {
            '005930': '삼성전자', '000660': 'SK하이닉스',
            '035720': '카카오', '005380': '현대차',
            '035420': 'NAVER', '051910': 'LG화학',
            '006400': '삼성SDI', '003670': '포스코퓨처엠'
        }

        results = []
        for code, name in stocks.items():
            try:
                price = trader.get_stock_price(code)
                if price:
                    emoji = "📈" if price['change'] > 0 else "📉" if price['change'] < 0 else "➡️"
                    results.append(f"{emoji} {name}: {price['price']:,}원 ({price['change']:+.2f}%)")
            except:
                pass
        return "\n".join(results)
    except Exception as e:
        return f"시세 조회 실패: {e}"


def get_news_analysis(topic):
    """뉴스 기반 분석"""
    try:
        from pro_analyzer import ProAnalyzer
        analyzer = ProAnalyzer()

        if topic == "themes":
            result = analyzer.get_hot_themes()
            return result.get("analysis", "분석 실패")
        elif topic == "geopolitical":
            # 지정학적 리스크
            import urllib.parse
            from bs4 import BeautifulSoup

            keywords = ['이란 미국', '중국 대만', '러시아 우크라이나', '북한 미사일']
            news = []

            for kw in keywords:
                query = urllib.parse.quote(kw)
                url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR"
                try:
                    resp = requests.get(url, timeout=5)
                    soup = BeautifulSoup(resp.text, 'xml')
                    for item in soup.find_all('item')[:3]:
                        title = item.find('title')
                        if title:
                            news.append(f"- {title.get_text()}")
                except:
                    pass

            if not news:
                return "지정학 뉴스 없음"

            prompt = f"""지정학적 리스크 전문가로서 분석하세요.

=== 최신 뉴스 ===
{chr(10).join(news[:12])}

## 🚨 리스크 레벨 (1-10)
## 📊 주요 이슈 3개
## 📈 수혜 섹터
## 📉 피해 섹터
## 💡 투자 전략 (간략히)
"""
            return get_ai_response(prompt, "sonnet")
        else:
            return None
    except Exception as e:
        return f"분석 오류: {e}"


# ============== 스케줄 함수들 ==============

def morning_briefing():
    """아침 브리핑 (08:50)"""
    print(f"[{datetime.now().strftime('%H:%M')}] 아침 브리핑 시작")

    prices = get_stock_prices()
    themes = get_news_analysis("themes")

    message = f"""☀️ *{datetime.now().strftime('%m/%d')} 아침 브리핑*

=== 📊 주요 종목 ===
{prices}

=== 🔥 오늘의 테마 ===
{themes[:2500] if themes else '테마 분석 실패'}
"""
    send_telegram(message)


def market_open():
    """장 시작 (09:05)"""
    print(f"[{datetime.now().strftime('%H:%M')}] 장 시작 알림")

    prices = get_stock_prices()
    message = f"""🔔 *장 시작!*

{prices}

_급등락 종목 주시 중..._
"""
    send_telegram(message)


def lunch_briefing():
    """점심 브리핑 (12:00)"""
    print(f"[{datetime.now().strftime('%H:%M')}] 점심 브리핑")

    prices = get_stock_prices()

    prompt = f"""오전장 마감 시황을 분석하세요.

{prices}

## 📊 오전장 요약 (2줄)
## 🔥 급등 종목 & 이유
## 📉 급락 종목 & 이유
## 💡 오후장 전략
"""
    analysis = get_ai_response(prompt, "haiku")

    message = f"""🍽️ *점심 브리핑*

{prices}

{analysis if analysis else ''}
"""
    send_telegram(message)


def afternoon_check():
    """오후 체크 (14:00)"""
    print(f"[{datetime.now().strftime('%H:%M')}] 오후 체크")

    prices = get_stock_prices()
    geopolitical = get_news_analysis("geopolitical")

    message = f"""📊 *오후장 중간점검*

{prices}

=== 🌍 지정학 리스크 ===
{geopolitical[:1500] if geopolitical else '분석 없음'}
"""
    send_telegram(message)


def market_close():
    """장 마감 (15:20)"""
    print(f"[{datetime.now().strftime('%H:%M')}] 장 마감 브리핑")

    prices = get_stock_prices()

    prompt = f"""오늘 시장 마감 분석을 하세요.

{prices}

## 📊 오늘의 승자/패자
## 📰 핵심 뉴스 3개
## 🔮 내일 전망
## 💡 내일 주목 종목 (이유 포함)
"""
    analysis = get_ai_response(prompt, "sonnet")

    message = f"""🔔 *장 마감 리포트*

{prices}

{analysis if analysis else ''}
"""
    send_telegram(message)


def evening_summary():
    """저녁 요약 (18:00)"""
    print(f"[{datetime.now().strftime('%H:%M')}] 저녁 요약")

    themes = get_news_analysis("themes")
    geopolitical = get_news_analysis("geopolitical")

    message = f"""🌙 *{datetime.now().strftime('%m/%d')} 데일리 리포트*

=== 🔥 테마 분석 ===
{themes[:2000] if themes else ''}

=== 🌍 지정학 리스크 ===
{geopolitical[:1500] if geopolitical else ''}
"""
    send_telegram(message)


def risk_monitor():
    """리스크 모니터링 (30분마다)"""
    state = load_state()

    try:
        from bs4 import BeautifulSoup
        import urllib.parse

        # 긴급 뉴스 체크
        urgent_keywords = ['전쟁', '공습', '미사일', '폭락', '서킷브레이커', '긴급']

        for kw in urgent_keywords:
            query = urllib.parse.quote(f"{kw} 주식")
            url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR"

            try:
                resp = requests.get(url, timeout=5)
                soup = BeautifulSoup(resp.text, 'xml')

                for item in soup.find_all('item')[:2]:
                    title = item.find('title')
                    pub_date = item.find('pubDate')

                    if title:
                        title_text = title.get_text()

                        # 이미 알린 뉴스인지 체크
                        if title_text in state.get("last_alerts", {}):
                            continue

                        # 1시간 이내 뉴스만
                        if pub_date:
                            try:
                                from email.utils import parsedate_to_datetime
                                news_time = parsedate_to_datetime(pub_date.get_text())
                                if (datetime.now(news_time.tzinfo) - news_time).seconds > 3600:
                                    continue
                            except:
                                pass

                        # 긴급 알림
                        message = f"""🚨 *긴급 뉴스 감지*

*{kw}* 관련:
{title_text}

_자동 모니터링 알림_
"""
                        send_telegram(message)

                        # 상태 저장
                        state.setdefault("last_alerts", {})[title_text] = datetime.now().isoformat()
                        save_state(state)

                        print(f"[{datetime.now().strftime('%H:%M')}] 긴급 알림: {title_text[:30]}...")
            except:
                pass
    except:
        pass


def health_check():
    """서비스 헬스체크"""
    import subprocess
    import os

    env = os.environ.copy()
    env['XDG_RUNTIME_DIR'] = f"/run/user/{os.getuid()}"

    services = ['moltbot-gateway', 'kiwoom-trader', 'dooray-bot', 'claude-api-proxy']
    failed = []

    for svc in services:
        try:
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', svc],
                capture_output=True, text=True, env=env
            )
            if result.stdout.strip() != 'active':
                failed.append(svc)
                subprocess.run(['systemctl', '--user', 'restart', svc], env=env)
        except:
            failed.append(svc)

    if failed:
        send_telegram(f"⚠️ *서비스 이상 감지*\n\n{', '.join(failed)}\n\n_자동 재시작 시도함_")
        print(f"[{datetime.now().strftime('%H:%M')}] 서비스 이상: {failed}")


def is_weekday():
    """평일 체크"""
    return datetime.now().weekday() < 5


def run_scheduler():
    """스케줄러 실행"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 몰트봇 자동 스케줄러 v2 시작")
    print("=" * 50)
    print("스케줄:")
    print("  08:50 - 아침 브리핑 (테마 분석)")
    print("  09:05 - 장 시작")
    print("  12:00 - 점심 브리핑")
    print("  14:00 - 오후 체크 (지정학 리스크)")
    print("  15:20 - 장 마감 리포트")
    print("  18:00 - 저녁 종합 요약")
    print("  30분마다 - 긴급 뉴스 모니터링")
    print("  2시간마다 - 서비스 헬스체크")
    print("=" * 50)

    # 평일 스케줄
    for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
        getattr(schedule.every(), day).at("08:50").do(morning_briefing)
        getattr(schedule.every(), day).at("09:05").do(market_open)
        getattr(schedule.every(), day).at("12:00").do(lunch_briefing)
        getattr(schedule.every(), day).at("14:00").do(afternoon_check)
        getattr(schedule.every(), day).at("15:20").do(market_close)

    # 매일 저녁
    schedule.every().day.at("18:00").do(evening_summary)

    # 30분마다 리스크 모니터링 (장중)
    schedule.every(30).minutes.do(lambda: risk_monitor() if is_weekday() and "09:00" <= datetime.now().strftime("%H:%M") <= "16:00" else None)

    # 2시간마다 헬스체크
    schedule.every(2).hours.do(health_check)

    # 시작 알림
    send_telegram(f"🤖 *자동 스케줄러 시작*\n\n{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n_뉴스 기반 자동 분석 활성화_")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "morning":
            morning_briefing()
        elif cmd == "lunch":
            lunch_briefing()
        elif cmd == "close":
            market_close()
        elif cmd == "evening":
            evening_summary()
        elif cmd == "risk":
            risk_monitor()
        elif cmd == "themes":
            result = get_news_analysis("themes")
            print(result)
        elif cmd == "geo":
            result = get_news_analysis("geopolitical")
            print(result)
        elif cmd == "test":
            prices = get_stock_prices()
            message = f"🧪 *테스트*\n\n{prices}"
            send_telegram(message)
            print("테스트 전송 완료")
    else:
        run_scheduler()
