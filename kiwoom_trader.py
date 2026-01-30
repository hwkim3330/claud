#!/usr/bin/env python3
"""
키움증권 OpenAPI 자동매매 시스템
- 실시간 시세 조회
- 자동 매매 (조건 기반)
- Telegram/Dooray 알림 연동
"""

import os
import json
import time
import requests
import threading
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv('/home/kim/dooray-claude-bot/.env.kiwoom')

# 설정
KIWOOM_APP_KEY = os.getenv('KIWOOM_APP_KEY')
KIWOOM_SECRET_KEY = os.getenv('KIWOOM_SECRET_KEY')
KIWOOM_API_URL = os.getenv('KIWOOM_API_URL', 'https://api.kiwoom.com')
MOCK_API_URL = 'https://mockapi.kiwoom.com'  # 모의투자

# Telegram 설정
TELEGRAM_TOKEN = "8492678625:AAHEmQQAwRyfI9K1d6n_ubigVnrNLAbUzH0"
TELEGRAM_CHAT_ID = "8341524797"

# 상태 파일
STATE_FILE = Path("/home/kim/dooray-claude-bot/kiwoom_state.json")
TOKEN_FILE = Path("/home/kim/dooray-claude-bot/.kiwoom_token")


class KiwoomTrader:
    def __init__(self, use_mock=True):
        self.app_key = KIWOOM_APP_KEY
        self.secret_key = KIWOOM_SECRET_KEY
        self.base_url = MOCK_API_URL if use_mock else KIWOOM_API_URL
        self.access_token = None
        self.token_expires = None
        self.state = self.load_state()

    def load_state(self):
        """상태 로드"""
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except:
                pass
        return {
            "watchlist": ["005930", "000660", "035720"],  # 삼성전자, SK하이닉스, 카카오
            "positions": {},
            "orders": [],
            "alerts": [],
            "strategy": {
                "buy_threshold": -3.0,   # -3% 이하면 매수
                "sell_threshold": 5.0,   # +5% 이상이면 매도
                "stop_loss": -7.0,       # -7% 손절
                "max_position": 1000000  # 종목당 최대 100만원
            }
        }

    def save_state(self):
        """상태 저장"""
        STATE_FILE.write_text(json.dumps(self.state, ensure_ascii=False, indent=2, default=str))

    def get_token(self):
        """OAuth 토큰 발급"""
        # 캐시된 토큰 확인
        if TOKEN_FILE.exists():
            try:
                token_data = json.loads(TOKEN_FILE.read_text())
                expires = datetime.fromisoformat(token_data['expires'])
                if expires > datetime.now():
                    self.access_token = token_data['token']
                    self.token_expires = expires
                    return self.access_token
            except:
                pass

        # 새 토큰 발급
        url = f"{self.base_url}/oauth2/token"
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        data = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.secret_key
        }

        try:
            resp = requests.post(url, json=data, headers=headers, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                self.access_token = result.get('token')
                expires_in = result.get('expires_in', 86400)
                self.token_expires = datetime.now() + timedelta(seconds=expires_in)

                # 토큰 캐시
                TOKEN_FILE.write_text(json.dumps({
                    'token': self.access_token,
                    'expires': self.token_expires.isoformat()
                }))
                TOKEN_FILE.chmod(0o600)

                return self.access_token
            else:
                print(f"토큰 발급 실패: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            print(f"토큰 발급 오류: {e}")
            return None

    def api_request(self, method, endpoint, data=None):
        """API 요청"""
        if not self.access_token:
            self.get_token()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.secret_key
        }

        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, params=data, timeout=10)
            else:
                resp = requests.post(url, headers=headers, json=data, timeout=10)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"API 오류: {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"API 요청 오류: {e}")
            return None

    def get_stock_price(self, stock_code):
        """주식 현재가 조회"""
        # 키움 API 또는 네이버 백업
        try:
            # 네이버 API (백업)
            url = f"https://m.stock.naver.com/api/stock/{stock_code}/basic"
            resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "code": stock_code,
                    "name": data.get("stockName", stock_code),
                    "price": int(data.get("closePrice", "0").replace(",", "")),
                    "change": float(data.get("fluctuationsRatio", "0")),
                    "volume": int(data.get("accumulatedTradingVolume", "0").replace(",", ""))
                }
        except Exception as e:
            print(f"시세 조회 오류 {stock_code}: {e}")
        return None

    def check_buy_signal(self, stock):
        """매수 신호 체크"""
        if not stock:
            return False

        strategy = self.state["strategy"]

        # 급락 매수 전략
        if stock["change"] <= strategy["buy_threshold"]:
            return True

        return False

    def check_sell_signal(self, stock, position):
        """매도 신호 체크"""
        if not stock or not position:
            return False

        strategy = self.state["strategy"]
        buy_price = position.get("avg_price", 0)
        current_price = stock["price"]

        if buy_price <= 0:
            return False

        profit_rate = ((current_price - buy_price) / buy_price) * 100

        # 익절
        if profit_rate >= strategy["sell_threshold"]:
            return "profit"

        # 손절
        if profit_rate <= strategy["stop_loss"]:
            return "stop_loss"

        return False

    def send_alert(self, message):
        """Telegram 알림"""
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message[:4000],
                "parse_mode": "Markdown"
            }, timeout=10)
        except:
            pass

    def run_strategy(self):
        """전략 실행"""
        now = datetime.now()

        # 장 시간 체크 (9:00 ~ 15:30)
        if now.weekday() >= 5:
            return  # 주말
        if not (9 <= now.hour < 16):
            return  # 장외 시간

        alerts = []

        for code in self.state["watchlist"]:
            stock = self.get_stock_price(code)
            if not stock:
                continue

            position = self.state["positions"].get(code)

            # 매수 신호
            if self.check_buy_signal(stock) and not position:
                alerts.append(f"🟢 **매수 신호**: {stock['name']} ({code})\n"
                            f"현재가: {stock['price']:,}원 ({stock['change']:+.2f}%)")

            # 매도 신호
            if position:
                sell_signal = self.check_sell_signal(stock, position)
                if sell_signal == "profit":
                    alerts.append(f"🔴 **익절 신호**: {stock['name']} ({code})\n"
                                f"현재가: {stock['price']:,}원 ({stock['change']:+.2f}%)")
                elif sell_signal == "stop_loss":
                    alerts.append(f"⚠️ **손절 신호**: {stock['name']} ({code})\n"
                                f"현재가: {stock['price']:,}원 ({stock['change']:+.2f}%)")

        if alerts:
            message = "📊 **키움 자동매매 알림**\n\n" + "\n\n".join(alerts)
            self.send_alert(message)
            print(f"[{now.strftime('%H:%M:%S')}] 알림 전송: {len(alerts)}건")

    def get_watchlist_status(self):
        """감시 종목 현황"""
        status = []
        for code in self.state["watchlist"]:
            stock = self.get_stock_price(code)
            if stock:
                emoji = "🔴" if stock["change"] < 0 else "🟢" if stock["change"] > 0 else "⚪"
                status.append(f"{emoji} {stock['name']}: {stock['price']:,}원 ({stock['change']:+.2f}%)")
        return "\n".join(status) if status else "데이터 없음"

    def add_watchlist(self, code):
        """감시 종목 추가"""
        if code not in self.state["watchlist"]:
            self.state["watchlist"].append(code)
            self.save_state()
            return True
        return False

    def remove_watchlist(self, code):
        """감시 종목 제거"""
        if code in self.state["watchlist"]:
            self.state["watchlist"].remove(code)
            self.save_state()
            return True
        return False


def run_trading_loop():
    """자동매매 루프"""
    trader = KiwoomTrader(use_mock=True)

    print("=" * 50)
    print("🤖 키움 자동매매 시스템 시작")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"감시 종목: {trader.state['watchlist']}")
    print("=" * 50)

    # 시작 알림
    status = trader.get_watchlist_status()
    trader.send_alert(f"🤖 **키움 자동매매 시작**\n\n{status}")

    while True:
        try:
            trader.run_strategy()
            time.sleep(60)  # 1분마다 체크
        except KeyboardInterrupt:
            print("\n종료")
            trader.send_alert("🤖 키움 자동매매가 종료되었습니다.")
            break
        except Exception as e:
            print(f"오류: {e}")
            time.sleep(60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        trader = KiwoomTrader(use_mock=True)

        if cmd == "status":
            print(trader.get_watchlist_status())
        elif cmd == "add" and len(sys.argv) > 2:
            code = sys.argv[2]
            if trader.add_watchlist(code):
                print(f"추가됨: {code}")
            else:
                print(f"이미 존재: {code}")
        elif cmd == "remove" and len(sys.argv) > 2:
            code = sys.argv[2]
            if trader.remove_watchlist(code):
                print(f"제거됨: {code}")
        elif cmd == "test":
            trader.run_strategy()
        else:
            print("사용법: kiwoom_trader.py [status|add|remove|test]")
    else:
        run_trading_loop()
