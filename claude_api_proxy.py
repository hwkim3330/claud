#!/usr/bin/env python3
"""
Claude CLI API 프록시 + Haiku 컨트롤러
Haiku가 메인 컨트롤러로 다른 모델들을 판단해서 호출

모델 계층:
- Haiku: 빠른 판단, 간단한 작업
- Sonnet: 일반 분석, 대화
- Opus: 복잡한 추론
- Codex: 코드 실행
- Gemini: 추가 옵션
"""

from flask import Flask, request, jsonify
import subprocess
import os
import json
import time
import re
from datetime import datetime

app = Flask(__name__)

# 설정
HOST = "127.0.0.1"
PORT = 8180
HAIKU_CONTROLLER = True  # Haiku가 모델 선택


def call_claude_cli(prompt: str, system: str = "", model: str = "haiku") -> str:
    """Claude CLI 호출"""
    try:
        cmd = ["claude", "-p", prompt]
        if system:
            cmd.extend(["--system-prompt", system])
        if "opus" in model.lower():
            cmd.extend(["--model", "opus"])
        elif "sonnet" in model.lower():
            cmd.extend(["--model", "sonnet"])
        # else: haiku (기본)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return f"Error: {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (180s)"
    except Exception as e:
        return f"Error: {e}"


def call_codex_cli(prompt: str) -> str:
    """Codex CLI 호출"""
    try:
        result = subprocess.run(
            ["codex", "exec", prompt],
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        return result.stdout.strip() if result.returncode == 0 else f"Codex error: {result.stderr[:300]}"
    except Exception as e:
        return f"Error: {e}"


def call_gemini_cli(prompt: str) -> str:
    """Gemini CLI 호출 (없으면 Sonnet fallback)"""
    try:
        # gemini CLI 확인
        result = subprocess.run(
            ["which", "gemini"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            # Gemini 없으면 Sonnet으로 fallback
            return call_claude_cli(prompt, "", "sonnet")

        result = subprocess.run(
            ["gemini", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        return result.stdout.strip() if result.returncode == 0 else call_claude_cli(prompt, "", "sonnet")
    except Exception as e:
        return call_claude_cli(prompt, "", "sonnet")  # fallback


def haiku_decide_model(prompt: str) -> str:
    """Haiku가 적절한 모델 선택"""
    decision_prompt = f"""다음 작업에 가장 적합한 모델을 선택해. 한 단어로만 답해:
- haiku: 간단한 질문, 빠른 응답, 인사, 날씨, 시간
- sonnet: 일반 분석, 요약, 설명, 번역
- opus: 복잡한 추론, 깊은 분석, 어려운 문제, 전략
- codex: 코드 작성, 프로그래밍, 스크립트, 디버깅
- gemini: Google 관련, 검색 필요, 대안 의견

작업: {prompt[:500]}

선택 (haiku/sonnet/opus/codex/gemini):"""

    try:
        result = subprocess.run(
            ["claude", "-p", decision_prompt, "--model", "haiku"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        decision = result.stdout.strip().lower()

        # 모델 이름 추출
        for model in ["opus", "sonnet", "codex", "gemini", "haiku"]:
            if model in decision:
                return model
        return "haiku"  # 기본
    except:
        return "haiku"


def smart_route(prompt: str, system: str = "") -> str:
    """Haiku 컨트롤러가 모델 선택 후 실행"""
    if not HAIKU_CONTROLLER:
        return call_claude_cli(prompt, system, "sonnet")

    model = haiku_decide_model(prompt)
    print(f"[Router] 선택된 모델: {model}")

    if model == "codex":
        return f"[Codex]\n{call_codex_cli(prompt)}"
    elif model == "gemini":
        return f"[Gemini]\n{call_gemini_cli(prompt)}"
    elif model == "opus":
        return f"[Opus]\n{call_claude_cli(prompt, system, 'opus')}"
    elif model == "sonnet":
        return f"[Sonnet]\n{call_claude_cli(prompt, system, 'sonnet')}"
    else:
        return call_claude_cli(prompt, system, "haiku")


@app.route("/v1/messages", methods=["POST"])
def anthropic_messages():
    """Anthropic Messages API 호환 엔드포인트 - Haiku 컨트롤러"""
    data = request.json or {}

    model = data.get("model", "claude-3-sonnet")
    messages = data.get("messages", [])
    system = data.get("system", "")

    # 메시지 조합
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if c.get("type") == "text"])
        prompt_parts.append(f"{role}: {content}")

    prompt = "\n".join(prompt_parts)

    # Haiku 컨트롤러가 모델 선택 (또는 명시된 모델 사용)
    if "haiku" in model.lower() or "sonnet" in model.lower() or "opus" in model.lower():
        # 명시적 모델 지정시 해당 모델 사용
        response_text = call_claude_cli(prompt, system, model)
    else:
        # 자동 라우팅
        response_text = smart_route(prompt, system)

    # Anthropic API 형식으로 응답
    return jsonify({
        "id": f"msg_{int(time.time()*1000)}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [
            {
                "type": "text",
                "text": response_text
            }
        ],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": len(prompt) // 4,
            "output_tokens": len(response_text) // 4
        }
    })


@app.route("/v1/chat/completions", methods=["POST"])
def openai_chat():
    """OpenAI Chat API 호환 엔드포인트"""
    data = request.json or {}

    model = data.get("model", "gpt-4")
    messages = data.get("messages", [])

    # 시스템 메시지 추출
    system = ""
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system = content
        else:
            prompt_parts.append(content)

    prompt = "\n".join(prompt_parts)

    # Codex 모델이면 Codex CLI, 아니면 Claude CLI
    if "codex" in model.lower():
        response_text = call_codex_cli(prompt)
    else:
        response_text = call_claude_cli(prompt, system, model)

    # OpenAI API 형식으로 응답
    return jsonify({
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(prompt) // 4,
            "completion_tokens": len(response_text) // 4,
            "total_tokens": (len(prompt) + len(response_text)) // 4
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


@app.route("/", methods=["GET"])
def index():
    return """
    <h1>🤖 Claude CLI API Proxy</h1>
    <p>Anthropic/OpenAI API 형식으로 요청하면 Claude CLI로 처리합니다.</p>
    <h3>엔드포인트:</h3>
    <ul>
        <li>POST /v1/messages - Anthropic Messages API</li>
        <li>POST /v1/chat/completions - OpenAI Chat API</li>
        <li>GET /health - 헬스체크</li>
    </ul>
    <h3>사용법:</h3>
    <pre>
# MoltBot 설정
ANTHROPIC_API_KEY=dummy
ANTHROPIC_BASE_URL=http://127.0.0.1:8080
    </pre>
    """


if __name__ == "__main__":
    print("=" * 50)
    print("🤖 Claude CLI API Proxy")
    print(f"주소: http://{HOST}:{PORT}")
    print("=" * 50)
    app.run(host=HOST, port=PORT, threaded=True)
