#!/usr/bin/env python3
"""
Haiku 컨트롤러 - 재귀적 모델 관리
- Haiku가 메인 컨트롤러
- 필요에 따라 Sonnet/Opus/Codex/Gemini 호출
- 무한 메모리 연동
"""

import subprocess
import json
import re
import os
from datetime import datetime
from pathlib import Path

# 무한 메모리
try:
    from infinite_memory import InfiniteMemory
    memory = InfiniteMemory()
except:
    memory = None


class HaikuController:
    """Haiku가 다른 모델들을 부하로 관리"""

    def __init__(self):
        self.models = {
            "haiku": {"cmd": ["claude", "-p", "{prompt}", "--model", "haiku"], "desc": "빠른 응답, 간단한 질문"},
            "sonnet": {"cmd": ["claude", "-p", "{prompt}", "--model", "sonnet"], "desc": "일반 분석, 요약"},
            "opus": {"cmd": ["claude", "-p", "{prompt}", "--model", "opus"], "desc": "복잡한 추론, 창작"},
            "codex": {"cmd": ["codex", "exec", "{prompt}"], "desc": "코드 작성, 실행"},
            "gemini": {"cmd": ["gemini", "-p", "{prompt}"], "desc": "Google 관련, 멀티모달"}
        }
        self.call_history = []

    def route_query(self, user_query: str) -> str:
        """Haiku가 적절한 모델 선택"""
        routing_prompt = f"""당신은 AI 모델 라우터입니다. 다음 사용자 질문에 가장 적합한 모델을 선택하세요.

사용 가능한 모델:
- haiku: 간단한 질문, 빠른 응답, 일상 대화, 번역
- sonnet: 일반 분석, 요약, 설명, 중간 복잡도
- opus: 복잡한 추론, 창작, 논문 분석, 심층 분석
- codex: 코드 작성, 프로그래밍, 디버깅, 스크립트
- gemini: Google 서비스 연동, 이미지 분석

사용자 질문: {user_query}

반드시 다음 형식으로만 답변:
모델: [모델이름]
이유: [한 줄 이유]"""

        try:
            result = subprocess.run(
                ["claude", "-p", routing_prompt, "--model", "haiku"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "LANG": "ko_KR.UTF-8"}
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                # 모델 추출
                match = re.search(r'모델:\s*(\w+)', output)
                if match:
                    model = match.group(1).lower()
                    if model in self.models:
                        return model

        except Exception as e:
            print(f"[라우터] 오류: {e}")

        return "haiku"  # 기본값

    def call_model(self, model: str, prompt: str, timeout: int = 60) -> dict:
        """특정 모델 호출"""
        if model not in self.models:
            return {"error": f"Unknown model: {model}", "output": ""}

        start_time = datetime.now()

        try:
            if model == "codex":
                # Codex는 다른 형식
                result = subprocess.run(
                    ["codex", "exec", prompt],
                    capture_output=True, text=True, timeout=timeout,
                    env={**os.environ, "LANG": "ko_KR.UTF-8"}
                )
            elif model == "gemini":
                result = subprocess.run(
                    ["gemini", "-p", prompt],
                    capture_output=True, text=True, timeout=timeout,
                    env={**os.environ, "LANG": "ko_KR.UTF-8"}
                )
            else:
                result = subprocess.run(
                    ["claude", "-p", prompt, "--model", model],
                    capture_output=True, text=True, timeout=timeout,
                    env={**os.environ, "LANG": "ko_KR.UTF-8"}
                )

            elapsed = (datetime.now() - start_time).total_seconds()

            call_record = {
                "model": model,
                "prompt_preview": prompt[:100],
                "elapsed": elapsed,
                "success": result.returncode == 0,
                "timestamp": datetime.now().isoformat()
            }
            self.call_history.append(call_record)

            if result.returncode == 0:
                return {"output": result.stdout.strip(), "model": model, "elapsed": elapsed}
            else:
                return {"error": result.stderr.strip(), "output": "", "model": model}

        except subprocess.TimeoutExpired:
            return {"error": "Timeout", "output": "", "model": model}
        except FileNotFoundError:
            return {"error": f"{model} CLI not found", "output": "", "model": model}
        except Exception as e:
            return {"error": str(e), "output": "", "model": model}

    def process(self, user_query: str, user_id: str = "default", force_model: str = None) -> dict:
        """사용자 질문 처리 (자동 라우팅)"""

        # 메모리에 저장
        if memory:
            memory.save_conversation(user_id, "user", user_query)

        # 모델 선택
        if force_model and force_model in self.models:
            selected_model = force_model
            routing_reason = "강제 지정"
        else:
            selected_model = self.route_query(user_query)
            routing_reason = "Haiku 자동 선택"

        print(f"[컨트롤러] {routing_reason} → {selected_model}")

        # 모델 호출
        result = self.call_model(selected_model, user_query)

        # 응답 저장
        if memory and result.get("output"):
            memory.save_conversation(user_id, "assistant", result["output"],
                                    {"model": selected_model, "elapsed": result.get("elapsed", 0)})

        result["routing"] = {
            "selected": selected_model,
            "reason": routing_reason,
            "available": list(self.models.keys())
        }

        return result

    def delegate_task(self, main_task: str, subtasks: list) -> list:
        """복잡한 작업을 여러 모델에 분배"""
        results = []

        for subtask in subtasks:
            model = self.route_query(subtask["query"])
            result = self.call_model(model, subtask["query"], timeout=subtask.get("timeout", 60))
            results.append({
                "task": subtask.get("name", "unnamed"),
                "model": model,
                "result": result
            })

        return results

    def get_stats(self) -> dict:
        """호출 통계"""
        if not self.call_history:
            return {"total_calls": 0}

        model_counts = {}
        total_time = 0
        success_count = 0

        for call in self.call_history:
            model = call["model"]
            model_counts[model] = model_counts.get(model, 0) + 1
            total_time += call.get("elapsed", 0)
            if call.get("success"):
                success_count += 1

        return {
            "total_calls": len(self.call_history),
            "by_model": model_counts,
            "avg_time": total_time / len(self.call_history),
            "success_rate": success_count / len(self.call_history)
        }


# API 서버 역할
def run_api_server(host="127.0.0.1", port=8180):
    """Flask 기반 API 서버"""
    from flask import Flask, request, jsonify

    app = Flask(__name__)
    controller = HaikuController()

    @app.route("/v1/messages", methods=["POST"])
    def messages():
        """Anthropic Messages API 호환 (스트리밍 지원)"""
        from flask import Response
        import uuid

        data = request.json or {}
        messages_data = data.get("messages", [])
        model = data.get("model", "auto")
        stream = data.get("stream", False)

        if not messages_data:
            return jsonify({"error": "No messages"}), 400

        # 텍스트 추출
        user_msg = messages_data[-1].get("content", "")
        if isinstance(user_msg, list):
            user_msg = " ".join([c.get("text", "") for c in user_msg if c.get("type") == "text"])

        if model == "auto":
            result = controller.process(user_msg)
        else:
            result = controller.process(user_msg, force_model=model)

        output_text = result.get("output", result.get("error", ""))
        message_id = f"msg_{uuid.uuid4().hex[:24]}"

        if stream:
            # SSE 스트리밍 응답
            def generate():
                # message_start
                yield f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": {"id": message_id, "type": "message", "role": "assistant", "content": [], "model": model, "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 0}}})}\n\n'

                # content_block_start
                yield f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})}\n\n'

                # content_block_delta with full text
                yield f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": output_text}})}\n\n'

                # content_block_stop
                yield f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": 0})}\n\n'

                # message_delta
                yield f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": len(output_text.split())}})}\n\n'

                # message_stop
                yield f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n'

            return Response(generate(), mimetype='text/event-stream', headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            })
        else:
            # 일반 JSON 응답
            return jsonify({
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": output_text}],
                "model": model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": len(output_text.split())},
                "routing": result.get("routing", {}),
                "actual_model": result.get("model", model)
            })

    @app.route("/v1/stats", methods=["GET"])
    def stats():
        return jsonify(controller.get_stats())

    @app.route("/health", methods=["GET"])
    def health():
        return "OK"

    print(f"Haiku Controller API: http://{host}:{port}")
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        run_api_server()
    else:
        # 테스트
        controller = HaikuController()

        test_queries = [
            "안녕하세요",
            "Python으로 피보나치 함수 작성해줘",
            "양자역학의 이중슬릿 실험에 대해 심층 분석해줘",
            "이 글을 요약해줘: AI의 발전이 빠르게 진행되고 있다."
        ]

        print("=" * 60)
        print("🎯 Haiku 컨트롤러 테스트")
        print("=" * 60)

        for q in test_queries:
            print(f"\n[질문] {q[:40]}...")
            result = controller.process(q)
            print(f"[모델] {result['routing']['selected']}")
            print(f"[응답] {result.get('output', result.get('error', ''))[:100]}...")
