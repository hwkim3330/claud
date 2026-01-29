#!/usr/bin/env python3
"""
AGI 도구 모음 - API 없이 무료로 가능한 것들
"""
import requests
import json
from datetime import datetime

# 네이버 주식 API (무료)
def get_stock_price(code):
    """종목 현재가 조회"""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        return {
            "name": data.get("stockName"),
            "price": int(data.get("closePrice", "0").replace(",", "")),
            "change": data.get("compareToPreviousClosePrice"),
            "change_pct": data.get("fluctuationsRatio"),
            "high": data.get("highPrice"),
            "low": data.get("lowPrice"),
            "volume": data.get("accumulatedTradingVolume")
        }
    except Exception as e:
        return {"error": str(e)}

def get_watchlist_prices():
    """관심종목 일괄 조회"""
    watchlist = {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "012450": "한화에어로스페이스",
        "005380": "현대차",
        "035420": "NAVER"
    }

    results = []
    for code, name in watchlist.items():
        data = get_stock_price(code)
        if "error" not in data:
            results.append(f"{name}: {data['price']:,}원 ({data['change_pct']}%)")

    return "\n".join(results)

# 환율
def get_exchange_rate():
    """원/달러 환율"""
    try:
        url = "https://m.stock.naver.com/api/exchange/FX_USDKRW/basic"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        return {
            "rate": data.get("closePrice"),
            "change": data.get("compareToPreviousClosePrice")
        }
    except:
        return {"rate": "조회실패"}

# 지수
def get_kospi():
    """코스피 지수"""
    try:
        url = "https://m.stock.naver.com/api/index/KOSPI/basic"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        return {
            "index": data.get("closePrice"),
            "change_pct": data.get("fluctuationsRatio")
        }
    except:
        return {"index": "조회실패"}

# 날씨
def get_weather(city="Seoul"):
    """날씨 조회"""
    try:
        url = f"https://wttr.in/{city}?format=%c+%t+%h"
        resp = requests.get(url, timeout=10)
        return resp.text.strip()
    except:
        return "조회실패"

# 시스템 상태
def get_system_status():
    """시스템 상태"""
    import subprocess
    try:
        # 디스크
        disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        disk_info = disk.stdout.strip().split("\n")[-1].split()

        # 메모리
        mem = subprocess.run(["free", "-h"], capture_output=True, text=True)
        mem_info = mem.stdout.strip().split("\n")[1].split()

        return {
            "disk_used": disk_info[4] if len(disk_info) > 4 else "?",
            "mem_used": mem_info[2] if len(mem_info) > 2 else "?",
            "mem_total": mem_info[1] if len(mem_info) > 1 else "?"
        }
    except:
        return {"error": "조회실패"}

# 종합 리포트
def daily_report():
    """일일 종합 리포트"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = [f"📊 일일 리포트 ({now})", "="*40]

    # 시장
    kospi = get_kospi()
    report.append(f"코스피: {kospi.get('index', '?')} ({kospi.get('change_pct', '?')}%)")

    # 환율
    fx = get_exchange_rate()
    report.append(f"원/달러: {fx.get('rate', '?')}원")

    # 관심종목
    report.append("\n📈 관심종목:")
    report.append(get_watchlist_prices())

    # 날씨
    report.append(f"\n🌤 서울: {get_weather('Seoul')}")

    # 시스템
    sys = get_system_status()
    report.append(f"\n💻 시스템: 디스크 {sys.get('disk_used', '?')}, 메모리 {sys.get('mem_used', '?')}/{sys.get('mem_total', '?')}")

    return "\n".join(report)


if __name__ == "__main__":
    print(daily_report())
