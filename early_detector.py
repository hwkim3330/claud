#!/usr/bin/env python3
"""
초기 급등 감지 시스템
- 거래량 급증 감지
- 초기 움직임 포착
- 실시간 모니터링
"""

import requests
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

DATA_DIR = Path("/home/kim/dooray-claude-bot/stock_data")
DATA_DIR.mkdir(exist_ok=True)


@dataclass
class StockSnapshot:
    """종목 스냅샷"""
    code: str
    name: str
    price: int
    change_rate: float
    volume: int
    timestamp: datetime


class EarlyDetector:
    """초기 급등 감지기"""

    def __init__(self):
        # 종목별 이전 데이터 저장
        self.history: Dict[str, List[StockSnapshot]] = defaultdict(list)
        self.alerts: List[Dict] = []
        self.detected_today: set = set()  # 오늘 이미 감지된 종목

    def get_all_stocks(self) -> List[Dict]:
        """전체 종목 현황 - 시총+상승률 상위 모니터링"""
        stocks = []
        seen = set()

        for market in ["KOSPI", "KOSDAQ"]:
            # 1. 상승률 상위 (급등 중인 종목)
            try:
                url = f"https://m.stock.naver.com/api/stocks/up/{market}?page=1&pageSize=30"
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    for item in resp.json().get("stocks", []):
                        try:
                            code = item.get("itemCode", "")
                            if code and code not in seen:
                                seen.add(code)
                                stocks.append({
                                    "code": code,
                                    "name": item.get("stockName", ""),
                                    "price": int(item.get("closePrice", "0").replace(",", "")),
                                    "change": float(item.get("fluctuationsRatio", "0")),
                                    "volume": int(item.get("accumulatedTradingVolume", "0").replace(",", "")),
                                    "market": market
                                })
                        except:
                            pass
            except:
                pass

            # 2. 시가총액 상위 (대형주)
            try:
                url = f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page=1&pageSize=20"
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    for item in resp.json().get("stocks", []):
                        try:
                            code = item.get("itemCode", "")
                            if code and code not in seen:
                                seen.add(code)
                                stocks.append({
                                    "code": code,
                                    "name": item.get("stockName", ""),
                                    "price": int(item.get("closePrice", "0").replace(",", "")),
                                    "change": float(item.get("fluctuationsRatio", "0")),
                                    "volume": int(item.get("accumulatedTradingVolume", "0").replace(",", "")),
                                    "market": market
                                })
                        except:
                            pass
            except:
                pass

        return stocks

    def update_history(self, stocks: List[Dict]):
        """히스토리 업데이트"""
        now = datetime.now()

        for s in stocks:
            snapshot = StockSnapshot(
                code=s["code"],
                name=s["name"],
                price=s["price"],
                change_rate=s["change"],
                volume=s["volume"],
                timestamp=now
            )

            self.history[s["code"]].append(snapshot)

            # 최근 10분만 유지
            cutoff = now - timedelta(minutes=10)
            self.history[s["code"]] = [
                h for h in self.history[s["code"]] if h.timestamp > cutoff
            ]

    def detect_signals(self, stocks: List[Dict]) -> List[Dict]:
        """신호 감지"""
        signals = []
        now = datetime.now()

        for s in stocks:
            code = s["code"]

            # 이미 오늘 감지된 종목은 스킵
            if code in self.detected_today:
                continue

            # 히스토리가 충분하지 않으면 스킵
            if len(self.history[code]) < 2:
                continue

            # 1분 전 데이터
            one_min_ago = now - timedelta(minutes=1)
            old_data = [h for h in self.history[code] if h.timestamp < one_min_ago]

            if not old_data:
                continue

            prev = old_data[-1]
            current_price = s["price"]
            current_volume = s["volume"]

            # === 신호 1: 가격 급등 시작 ===
            # 1분 내 1% 이상 상승 + 현재 전일 대비 상승
            if prev.price > 0:
                short_change = ((current_price - prev.price) / prev.price) * 100

                if short_change >= 1.0 and s["change"] > 0 and s["change"] < 5:
                    signals.append({
                        "type": "price_surge_start",
                        "code": code,
                        "name": s["name"],
                        "price": current_price,
                        "short_change": short_change,
                        "daily_change": s["change"],
                        "volume": current_volume,
                        "message": f"🚀 급등 시작! 1분내 +{short_change:.2f}% (전일比 +{s['change']:.2f}%)"
                    })
                    self.detected_today.add(code)

            # === 신호 2: 거래량 급증 ===
            # 이전 거래량 대비 2배 이상 증가
            if prev.volume > 0:
                volume_ratio = current_volume / prev.volume

                if volume_ratio >= 1.5 and s["change"] > 0:
                    signals.append({
                        "type": "volume_spike",
                        "code": code,
                        "name": s["name"],
                        "price": current_price,
                        "volume_ratio": volume_ratio,
                        "daily_change": s["change"],
                        "volume": current_volume,
                        "message": f"📊 거래량 급증! x{volume_ratio:.1f}배 (전일比 +{s['change']:.2f}%)"
                    })
                    self.detected_today.add(code)

            # === 신호 3: 눌림목 돌파 ===
            # 일중 상승 후 눌렸다가 다시 상승
            if len(self.history[code]) >= 3:
                recent = self.history[code][-3:]
                prices = [h.price for h in recent]

                # 가격 패턴: 상승 -> 하락 -> 상승 (V자)
                if prices[0] < prices[1] > prices[2] > prices[0]:
                    signals.append({
                        "type": "v_pattern",
                        "code": code,
                        "name": s["name"],
                        "price": current_price,
                        "daily_change": s["change"],
                        "message": f"📈 V자 반등! (전일比 +{s['change']:.2f}%)"
                    })
                    self.detected_today.add(code)

        return signals

    def run_detection(self, duration_sec: int = 60, interval_sec: int = 5):
        """감지 실행"""
        print("=" * 50)
        print("🔍 초기 급등 감지 시스템 시작")
        print(f"모니터링 시간: {duration_sec}초, 간격: {interval_sec}초")
        print("=" * 50)

        start = datetime.now()
        end = start + timedelta(seconds=duration_sec)

        all_signals = []
        round_num = 0

        while datetime.now() < end:
            round_num += 1
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 라운드 {round_num}")

            # 종목 데이터 가져오기
            stocks = self.get_all_stocks()
            print(f"  모니터링 종목: {len(stocks)}개")

            # 히스토리 업데이트
            self.update_history(stocks)

            # 신호 감지
            signals = self.detect_signals(stocks)

            if signals:
                for sig in signals:
                    print(f"  🚨 {sig['message']}")
                    print(f"     {sig['name']} ({sig['code']}): {sig['price']:,}원")
                    all_signals.append(sig)
            else:
                print(f"  신호 없음")

            time.sleep(interval_sec)

        # 결과 요약
        print("\n" + "=" * 50)
        print("📊 감지 결과 요약")
        print("=" * 50)
        print(f"총 감지된 신호: {len(all_signals)}개")

        if all_signals:
            print("\n감지된 종목:")
            for sig in all_signals:
                print(f"  • {sig['name']}: {sig['message']}")

        return all_signals


def analyze_surge_potential():
    """급등 가능성 분석"""
    print("=" * 50)
    print("📊 급등 가능성 분석")
    print("=" * 50)

    # 현재 상승 중이지만 아직 초기 단계인 종목 찾기
    potential = []

    for market in ["KOSPI", "KOSDAQ"]:
        url = f"https://m.stock.naver.com/api/stocks/up/{market}?page=1&pageSize=30"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})

        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("stocks", []):
                try:
                    change = float(item.get("fluctuationsRatio", "0"))
                    volume = int(item.get("accumulatedTradingVolume", "0").replace(",", ""))

                    # 조건: 2-10% 상승 + 거래량 10만 이상
                    if 2 <= change <= 10 and volume >= 100000:
                        potential.append({
                            "name": item.get("stockName", ""),
                            "code": item.get("itemCode", ""),
                            "price": item.get("closePrice", "0"),
                            "change": change,
                            "volume": volume,
                            "market": market
                        })
                except:
                    pass

    # 상승률 순 정렬
    potential = sorted(potential, key=lambda x: x["change"], reverse=True)

    print(f"\n🎯 급등 가능성 종목 (2-10% 상승 + 거래량 10만+):\n")

    for i, p in enumerate(potential[:10], 1):
        emoji = "🔥" if p["change"] >= 5 else "📈"
        print(f"{i}. {emoji} {p['name']} ({p['code']})")
        print(f"   현재가: {p['price']}원 (+{p['change']:.2f}%)")
        print(f"   거래량: {p['volume']:,} ({p['market']})")
        print()

    return potential


if __name__ == "__main__":
    # 1. 급등 가능성 종목 분석
    potential = analyze_surge_potential()

    # 2. 실시간 감지 (1분)
    print("\n")
    detector = EarlyDetector()
    signals = detector.run_detection(duration_sec=60, interval_sec=10)

    # 결과 저장
    result = {
        "timestamp": datetime.now().isoformat(),
        "potential_stocks": potential[:10],
        "detected_signals": signals
    }

    result_file = DATA_DIR / "early_detection_result.json"
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\n결과 저장: {result_file}")
