#!/usr/bin/env python3
"""
Claude CLI API 프록시
Anthropic API 형식으로 요청받아서 Claude CLI로 처리

MoltBot이 이 프록시를 API 엔드포인트로 사용하면
API 키 없이 Claude CLI 인증으로 동작
"""

from flask import Flask, request, jsonify
import subprocess
import os
import json
import time
from datetime import datetime

app = Flask(__name__)

# 설정
HOST = "127.0.0.1"
PORT = 8180


def call_claude_cli(prompt: str, system: str = "", model: str = "sonnet") -> str:
    """Claude CLI 호출"""
    try:
        cmd = ["claude", "-p", prompt]
        if system:
            cmd.extend(["--system-prompt", system])
        if "opus" in model.lower():
            cmd.extend(["--model", "opus"])
        elif "haiku" in model.lower():
            cmd.extend(["--model", "haiku"])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return f"Error: {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except Exception as e:
        return f"Error: {e}"


def call_codex_cli(prompt: str) -> str:
    """Codex CLI 호출"""
    try:
        result = subprocess.run(
            ["codex", "-q", prompt],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.stdout.strip() if result.returncode == 0 else "Codex error"
    except Exception as e:
        return f"Error: {e}"


@app.route("/v1/messages", methods=["POST"])
def anthropic_messages():
    """Anthropic Messages API 호환 엔드포인트"""
    data = request.json or {}

    model = data.get("model", "claude-3-sonnet")
    messages = data.get("messages", [])
    system = data.get("system", "")
    max_tokens = data.get("max_tokens", 4096)

    # 메시지 조합
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if c.get("type") == "text"])
        prompt_parts.append(f"{role}: {content}")

    prompt = "\n".join(prompt_parts)

    # Claude CLI 호출
    response_text = call_claude_cli(prompt, system, model)

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
