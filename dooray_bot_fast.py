#!/usr/bin/env python3
"""
두레이 Claude 봇 - Haiku 컨트롤러 + 주식 + 이미지
/s [질문] - Haiku가 적절한 모델 선택
/s 시세 - 주식 현황
/s 이미지 [설명] - 이미지 생성
"""

from flask import Flask, request, jsonify
import subprocess
import threading
import urllib.parse
import requests
import os
import re
import json
from pathlib import Path

app = Flask(__name__)

# 키움 트레이더 연동
KIWOOM_STATE = Path("/home/kim/dooray-claude-bot/kiwoom_state.json")

class ClaudeWorker:
    def __init__(self):
        self.lock = threading.Lock()

    def ask(self, question, use_router=True):
        """Claude에게 질문 (Haiku 컨트롤러 사용)"""
        with self.lock:
            try:
                if use_router:
                    # 프록시를 통해 Haiku 컨트롤러 사용
                    resp = requests.post(
                        "http://127.0.0.1:8180/v1/messages",
                        json={"model": "auto", "messages": [{"role": "user", "content": question}]},
                        timeout=120
                    )
                    if resp.status_code == 200:
                        answer = resp.json().get("content", [{}])[0].get("text", "응답 없음")
                        if len(answer) > 3000:
                            answer = answer[:3000] + "\n...(생략)"
                        return answer

                # fallback: 직접 Claude CLI
                result = subprocess.run(
                    ["claude", "-p", question, "--model", "haiku"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "LANG": "ko_KR.UTF-8"}
                )
                if result.returncode == 0:
                    answer = result.stdout.strip()
                    if len(answer) > 3000:
                        answer = answer[:3000] + "\n...(생략)"
                    return answer
                return f"오류: {result.stderr.strip()[:200]}"
            except subprocess.TimeoutExpired:
                return "⏱️ 시간 초과"
            except Exception as e:
                return f"오류: {str(e)}"

    def translate_to_english(self, korean_text):
        """한글을 영어로 번역 (이미지 생성용)"""
        with self.lock:
            try:
                result = subprocess.run(
                    ["claude", "-p", f"Translate this to English for image generation. Only output the translation, nothing else: {korean_text}", "--model", "haiku"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env={**os.environ, "LANG": "ko_KR.UTF-8"}
                )
                if result.returncode == 0:
                    return result.stdout.strip()
                return korean_text
            except:
                return korean_text

# 워커 인스턴스
claude = ClaudeWorker()


def get_stock_status():
    """주식 현황 조회"""
    try:
        if KIWOOM_STATE.exists():
            state = json.loads(KIWOOM_STATE.read_text())
            watchlist = state.get("watchlist", ["005930", "000660", "035720"])
        else:
            watchlist = ["005930", "000660", "035720"]

        status = []
        for code in watchlist:
            try:
                url = f"https://m.stock.naver.com/api/stock/{code}/basic"
                resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    name = data.get("stockName", code)
                    price = data.get("closePrice", "N/A")
                    change = float(data.get("fluctuationsRatio", "0"))
                    emoji = "🔴" if change < 0 else "🟢" if change > 0 else "⚪"
                    status.append(f"{emoji} **{name}**: {price}원 ({change:+.2f}%)")
            except:
                pass

        return "\n".join(status) if status else "시세 조회 실패"
    except Exception as e:
        return f"오류: {e}"


def is_stock_request(text):
    """주식 관련 요청인지 확인"""
    keywords = ["시세", "주식", "stock", "주가", "코스피", "코스닥", "삼성", "하이닉스", "카카오"]
    return any(kw in text.lower() for kw in keywords)

def generate_image_url(prompt, model="zimage"):
    """Pollinations.ai로 이미지 생성 URL 만들기"""
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model={model}&nologo=true"

def is_image_request(text):
    """이미지 생성 요청인지 확인"""
    patterns = [
        r'^이미지\s+',
        r'^그려\s*줘?\s+',
        r'^그림\s+',
        r'^생성\s+',
        r'^만들어\s*줘?\s+',
        r'^image\s+',
        r'^draw\s+',
        r'^generate\s+',
    ]
    for pattern in patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    return False

def extract_image_prompt(text):
    """이미지 프롬프트 추출"""
    patterns = [
        r'^이미지\s+(.+)',
        r'^그려\s*줘?\s+(.+)',
        r'^그림\s+(.+)',
        r'^생성\s+(.+)',
        r'^만들어\s*줘?\s+(.+)',
        r'^image\s+(.+)',
        r'^draw\s+(.+)',
        r'^generate\s+(.+)',
    ]
    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return text

@app.route("/slash", methods=["POST"])
def slash():
    """두레이 슬래시 커맨드 - Haiku 컨트롤러"""
    data = request.json or {}

    user = data.get("userName", "사용자")
    text = data.get("text", "").strip()
    cmd = data.get("command", "/s")

    print(f"[요청] {user}: {text}")

    if not text:
        return jsonify({
            "text": "💡 **사용법:**\n• `/s [질문]` - Haiku가 적절한 모델 선택\n• `/s 시세` - 주식 현황\n• `/s 이미지 [설명]` - 이미지 생성",
            "responseType": "ephemeral"
        })

    # 주식 시세 요청
    if text in ["시세", "주식", "stock"]:
        status = get_stock_status()
        return jsonify({
            "text": f"📊 **주식 현황**\n\n{status}",
            "responseType": "inChannel"
        })

    # 이미지 생성 요청 확인
    if is_image_request(text):
        prompt = extract_image_prompt(text)
        print(f"[이미지] 프롬프트: {prompt}")

        # 한글이면 영어로 번역
        if any('\uac00' <= c <= '\ud7a3' for c in prompt):
            english_prompt = claude.translate_to_english(prompt)
            print(f"[번역] {prompt} -> {english_prompt}")
        else:
            english_prompt = prompt

        image_url = generate_image_url(english_prompt)
        print(f"[이미지] URL: {image_url}")

        return jsonify({
            "text": f"**🎨 {user}:** {prompt}",
            "responseType": "inChannel",
            "attachments": [{
                "title": "생성된 이미지",
                "text": f"프롬프트: {english_prompt}",
                "imageUrl": image_url,
                "color": "green"
            }]
        })

    # Haiku 컨트롤러로 라우팅 (자동 모델 선택)
    answer = claude.ask(text, use_router=True)
    print(f"[응답] {answer[:50]}...")

    return jsonify({
        "text": f"**🙋 {user}:** {text}\n\n**🤖 Claude:**\n{answer}",
        "responseType": "inChannel"
    })

@app.route("/image", methods=["POST"])
def image():
    """이미지 생성 전용 엔드포인트"""
    data = request.json or {}

    user = data.get("userName", "사용자")
    text = data.get("text", "").strip()

    if not text:
        return jsonify({
            "text": "💡 사용법: `/이미지 [설명]`\n예: `/이미지 우주에서 본 지구`",
            "responseType": "ephemeral"
        })

    # 한글이면 영어로 번역
    if any('\uac00' <= c <= '\ud7a3' for c in text):
        english_prompt = claude.translate_to_english(text)
    else:
        english_prompt = text

    image_url = generate_image_url(english_prompt)

    return jsonify({
        "text": f"**🎨 {user}:** {text}",
        "responseType": "inChannel",
        "attachments": [{
            "title": "생성된 이미지",
            "text": f"프롬프트: {english_prompt}",
            "imageUrl": image_url,
            "color": "green"
        }]
    })

@app.route("/health", methods=["GET"])
def health():
    return "OK"

@app.route("/", methods=["GET"])
def home():
    return "Dooray Claude Bot (Image Support)"

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 두레이 Claude 봇 (이미지 생성 지원)")
    print("   /s [질문] - Claude 채팅")
    print("   /s 이미지 [설명] - 이미지 생성")
    print("   /image [설명] - 이미지 전용")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, threaded=True)
