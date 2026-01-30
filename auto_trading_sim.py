#!/usr/bin/env python3
"""
자동매매 시뮬레이션 - 실시간 급등주 분석
"""

import sys
sys.path.insert(0, '/home/kim/dooray-claude-bot')

import time
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from stock_simulator import VirtualPortfolio, AutoTrader

# 설정
INITIAL_CAPITAL = 10_000_000  # 1000만원
CHECK_INTERVAL = 15  # 15초마다 체크
RUN_DURATION = 180  # 3분 동안 실행

# 전략 설정
STRATEGY = {
    "buy_threshold": 4.0,      # 4% 이상 급등시 매수
    "sell_profit": 2.0,        # 2% 이상 수익시 익절
    "sell_loss": -1.5,         # 1.5% 이상 손실시 손절
    "max_positions": 5,        # 최대 5종목
    "position_size": 1_000_000, # 종목당 100만원
}

LOG_FILE = Path("/home/kim/dooray-claude-bot/stock_data/trading_log.txt")


def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_surge_stocks():
    """급등주 조회 - 상승률 상위"""
    stocks = []
    try:
        # KOSPI 상승률 상위
        url = "https://m.stock.naver.com/api/stocks/up/KOSPI?page=1&pageSize=20"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("stocks", []):
                try:
                    change = float(item.get("fluctuationsRatio", "0"))
                    if change >= STRATEGY["buy_threshold"]:
                        stocks.append({
                            "code": item.get("itemCode", ""),
                            "name": item.get("stockName", ""),
                            "price": int(item.get("closePrice", "0").replace(",", "")),
                            "change": change,
                            "volume": int(item.get("accumulatedTradingVolume", "0").replace(",", ""))
                        })
                except:
                    pass

        # KOSDAQ 상승률 상위
        url = "https://m.stock.naver.com/api/stocks/up/KOSDAQ?page=1&pageSize=20"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("stocks", []):
                try:
                    change = float(item.get("fluctuationsRatio", "0"))
                    if change >= STRATEGY["buy_threshold"]:
                        stocks.append({
                            "code": item.get("itemCode", ""),
                            "name": item.get("stockName", ""),
                            "price": int(item.get("closePrice", "0").replace(",", "")),
                            "change": change,
                            "volume": int(item.get("accumulatedTradingVolume", "0").replace(",", ""))
                        })
                except:
                    pass

    except Exception as e:
        log(f"급등주 조회 오류: {e}")

    return sorted(stocks, key=lambda x: x["change"], reverse=True)


def get_current_price(code):
    """현재가 조회"""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            return int(data.get("closePrice", "0").replace(",", ""))
    except:
        pass
    return None


def run_simulation():
    """시뮬레이션 실행"""

    # 초기화
    portfolio = VirtualPortfolio()
    portfolio.reset(INITIAL_CAPITAL)

    log("=" * 50)
    log("🚀 자동매매 시뮬레이션 시작")
    log(f"초기 자본: {INITIAL_CAPITAL:,}원")
    log(f"전략: 급등 {STRATEGY['buy_threshold']}%↑ 매수, 익절 {STRATEGY['sell_profit']}%, 손절 {STRATEGY['sell_loss']}%")
    log("=" * 50)

    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=RUN_DURATION)

    trade_count = 0
    round_num = 0

    while datetime.now() < end_time:
        round_num += 1
        log(f"\n--- 라운드 {round_num} ---")

        # 1. 보유 종목 현재가 업데이트 & 매도 체크
        for code in list(portfolio.positions.keys()):
            pos = portfolio.positions[code]
            price = get_current_price(code)

            if price:
                pos.current_price = price
                profit_rate = ((price - pos.buy_price) / pos.buy_price) * 100

                # 익절
                if profit_rate >= STRATEGY["sell_profit"]:
                    result = portfolio.sell(code, price)
                    if result["success"]:
                        log(f"💰 익절 매도: {pos.name} +{profit_rate:.2f}% (+{result['profit_amount']:,}원)")
                        trade_count += 1

                # 손절
                elif profit_rate <= STRATEGY["sell_loss"]:
                    result = portfolio.sell(code, price)
                    if result["success"]:
                        log(f"🛑 손절 매도: {pos.name} {profit_rate:.2f}% ({result['profit_amount']:,}원)")
                        trade_count += 1

                else:
                    log(f"📊 보유중: {pos.name} {profit_rate:+.2f}%")

        # 2. 급등주 조회 & 매수
        if len(portfolio.positions) < STRATEGY["max_positions"]:
            surge_stocks = get_surge_stocks()

            for stock in surge_stocks[:3]:
                # 이미 보유중이면 패스
                if stock["code"] in portfolio.positions:
                    continue

                # 최대 보유 수 체크
                if len(portfolio.positions) >= STRATEGY["max_positions"]:
                    break

                # 자금 체크
                if portfolio.cash < STRATEGY["position_size"]:
                    break

                # 매수
                result = portfolio.buy(
                    code=stock["code"],
                    name=stock["name"],
                    price=stock["price"],
                    amount=STRATEGY["position_size"]
                )

                if result["success"]:
                    log(f"📈 급등 매수: {stock['name']} +{stock['change']:.1f}% @ {stock['price']:,}원 x {result['quantity']}주")
                    trade_count += 1

        # 3. 현황 출력
        portfolio._save()
        total = portfolio.total_value
        ret = portfolio.total_return
        log(f"💰 총자산: {total:,}원 ({ret:+.2f}%)")

        # 대기
        time.sleep(CHECK_INTERVAL)

    # 최종 결과
    log("\n" + "=" * 50)
    log("📊 시뮬레이션 종료")
    log("=" * 50)

    # 남은 포지션 모두 청산
    log("\n🔄 보유 종목 전량 청산...")
    for code in list(portfolio.positions.keys()):
        pos = portfolio.positions[code]
        price = get_current_price(code)
        if price:
            result = portfolio.sell(code, price)
            if result["success"]:
                emoji = "💰" if result["profit_amount"] > 0 else "💸"
                log(f"{emoji} 청산: {pos.name} {result['profit_rate']:+.2f}% ({result['profit_amount']:+,}원)")

    # 최종 결과
    log("\n" + "=" * 50)
    log("📈 최종 결과")
    log("=" * 50)
    log(f"초기 자본: {INITIAL_CAPITAL:,}원")
    log(f"최종 자산: {portfolio.cash:,}원")
    log(f"총 수익: {portfolio.cash - INITIAL_CAPITAL:+,}원")
    log(f"수익률: {((portfolio.cash - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:+.2f}%")
    log(f"총 거래: {trade_count}회")
    log(f"승률: {portfolio.win_rate:.1f}% ({portfolio.win_count}승 {portfolio.loss_count}패)")
    log(f"실행 시간: {(datetime.now() - start_time).seconds}초")

    return {
        "initial": INITIAL_CAPITAL,
        "final": portfolio.cash,
        "profit": portfolio.cash - INITIAL_CAPITAL,
        "return": ((portfolio.cash - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100,
        "trades": trade_count,
        "wins": portfolio.win_count,
        "losses": portfolio.loss_count
    }


if __name__ == "__main__":
    result = run_simulation()

    # 결과 저장
    result_file = Path("/home/kim/dooray-claude-bot/stock_data/sim_result.json")
    result["timestamp"] = datetime.now().isoformat()
    result_file.write_text(json.dumps(result, indent=2))

    print(f"\n결과 저장됨: {result_file}")
