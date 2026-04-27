import csv
import io
import json
import os
import re
import subprocess
import time
import urllib.request

import anthropic
import openai as _openai
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Generator, List, Optional

from prompts import (
    API_TEST_PROMPT,
    GHERKIN_PROMPT,
    OLLAMA_TEST_CASE_PROMPT,
    TEST_CASE_PROMPT,
    TEST_TYPE_HINTS,
    TESTCASE_TO_API_PROMPT,
    TESTCASE_TO_GHERKIN_PROMPT,
)

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

load_dotenv()

app = FastAPI(title="SQA_GenAI", description="自然語言轉測試案例的 AI 工具")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_MODEL = "claude-sonnet-4-6"

# Ollama 本地模型（封閉系統，不連接外部網路）
# 前端顯示名稱 → Ollama 實際 model tag 對照表
OLLAMA_MODEL_MAP: dict[str, str] = {
    "deepseek-chat": os.getenv("OLLAMA_DEEPSEEK_MODEL", "deepseek-r1:1.5b"),
}
OLLAMA_MODELS = set(OLLAMA_MODEL_MAP.keys())
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

ALLOWED_MODELS = {
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
} | OLLAMA_MODELS


def _is_ollama(model: str) -> bool:
    return model in OLLAMA_MODELS


def _ensure_ollama_running(timeout: int = 10) -> None:
    """確認 Ollama 服務正在運行；若未啟動則自動執行 `ollama serve`。"""
    health_url = OLLAMA_BASE_URL.replace("/v1", "").rstrip("/") + "/api/tags"

    def _is_alive() -> bool:
        try:
            with urllib.request.urlopen(health_url, timeout=2):
                return True
        except Exception:
            return False

    if _is_alive():
        return

    # 嘗試在背景啟動 Ollama
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="找不到 ollama 指令，請先安裝 Ollama（https://ollama.com）",
        )

    # 等待服務就緒
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        if _is_alive():
            return

    raise HTTPException(
        status_code=503,
        detail=f"無法連線至 Ollama（{OLLAMA_BASE_URL}），自動啟動逾時，請手動執行 `ollama serve`",
    )


def _get_ollama_client() -> _openai.OpenAI:
    """回傳只連本機 Ollama 的 OpenAI 相容客戶端（封閉系統）。"""
    return _openai.OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",  # Ollama 不驗證 key，填任意值即可
        timeout=_openai.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0),
    )


def get_client(api_key: Optional[str] = None) -> anthropic.Anthropic:
    key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(status_code=401, detail="未設定 API Key，請在右上角 ⚙️ 設定中輸入")
    return anthropic.Anthropic(api_key=key)


def get_model(x_model: Optional[str]) -> str:
    if x_model and x_model in ALLOWED_MODELS:
        return x_model
    return DEFAULT_MODEL


def _ollama_create_with_retry(
    ollama_model: str,
    system: str,
    user_msg: str,
    max_tokens: int,
    retries: int = 3,
) -> str:
    """呼叫 Ollama，失敗時最多重試 retries 次。"""
    cli = _get_ollama_client()
    last_err: Exception = RuntimeError("unknown")
    for attempt in range(retries):
        try:
            resp = cli.chat.completions.create(
                model=ollama_model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
            )
            text = resp.choices[0].message.content or ""
            # 驗證可解析再回傳，否則繼續重試
            cleaned = _strip_fences(text)
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            candidate = cleaned[start:end + 1] if start != -1 and end > start else cleaned
            json.loads(_repair_json(candidate))  # 驗證用，成功才往下
            return cleaned
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
        except Exception as e:
            raise e
    raise HTTPException(status_code=500, detail=f"Ollama 回傳格式錯誤（已重試 {retries} 次）：{last_err}")


def _chat_create(
    model: str,
    system: str,
    user_msg: str,
    max_tokens: int,
    api_key: Optional[str] = None,
) -> str:
    """統一 AI 呼叫介面，自動路由至 Anthropic 或本機 Ollama。"""
    if _is_ollama(model):
        _ensure_ollama_running()
        ollama_model = OLLAMA_MODEL_MAP.get(model, model)
        return _ollama_create_with_retry(ollama_model, system, user_msg, max_tokens)
    else:
        client = get_client(api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return msg.content[0].text


def _chat_stream(
    model: str,
    system: str,
    user_msg: str,
    max_tokens: int,
    api_key: Optional[str] = None,
) -> Generator[str, None, None]:
    """統一串流介面，yield 文字片段。"""
    if _is_ollama(model):
        _ensure_ollama_running()
        cli = _get_ollama_client()
        ollama_model = OLLAMA_MODEL_MAP.get(model, model)
        ollama_system = (
            "你是 JSON 輸出機器。規則："
            "1. 只輸出純 JSON，從 [ 開始，以 ] 結尾。"
            "2. 絕對不要有任何說明文字、markdown、code block。"
            "3. id 欄位必須是字串如 \"TC-001\"。\n\n"
        ) + system
        with cli.chat.completions.create(
            model=ollama_model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": ollama_system},
                {"role": "user", "content": user_msg},
            ],
            stream=True,
        ) as stream:
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
    else:
        client = get_client(api_key)
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for text in stream.text_stream:
                yield text


class TestCaseRequest(BaseModel):
    input_text: str
    language: Optional[str] = "zh"
    max_cases: Optional[int] = 10
    context: Optional[str] = None
    test_types: Optional[List[dict]] = None  # [{"type": "Functional", "count": 5}, ...]


class GherkinRequest(BaseModel):
    input_text: str
    context: Optional[str] = None


class ApiTestRequest(BaseModel):
    input_text: str
    context: Optional[str] = None


class ConvertRequest(BaseModel):
    test_cases: List[dict]
    context: Optional[str] = None


def _strip_fences(text: str) -> str:
    """移除 markdown 圍欄（支援首尾及內嵌）並移除 DeepSeek <think> 推理區塊。"""
    # 移除 DeepSeek R1 的 <think>...</think> 推理區塊
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    # 優先取 ```json ... ``` 或 ``` ... ``` 圍欄內的第一段內容
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    # 無圍欄時，移除首尾的 ``` 行
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _repair_json(text: str) -> str:
    """修復常見的 AI 輸出 JSON 問題。"""
    # 修復 "id": 0001 → "id": "TC-001" 型前導零數字（JSON 不允許）
    text = re.sub(r'"id"\s*:\s*(0\d+)', lambda m: f'"id": "{m.group(1)}"', text)
    # 把全形逗號、全形引號換成半形
    text = text.replace('，', ',').replace('\u201c', '"').replace('\u201d', '"')
    # 移除尾端多餘逗號（},] 或 ,]）
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _parse_json_array(text: str):
    """嘗試從 AI 回傳文字中解析 JSON 陣列，支援有多餘說明文字的情況。"""
    text = text.strip()
    # 先取出 [ ... ] 範圍，排除說明文字
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 嘗試修復後再解析
    repaired = _repair_json(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    # 找第一個 [ 到最後一個 ] 之間的內容（貪婪匹配完整陣列）
    start = repaired.find("[")
    end = repaired.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = repaired[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    raise HTTPException(status_code=500, detail="無法解析 AI 回傳的 JSON 格式，請重試")


def _inject_context(base: str, context: Optional[str]) -> str:
    if context and context.strip():
        return f"【專案背景知識 / Memory】\n{context.strip()}\n\n{base}"
    return base


def _build_type_instruction(test_types: List[dict]) -> str:
    lines = []
    total = 0
    for tt in test_types:
        t = tt.get("type", "")
        c = max(1, min(int(tt.get("count", 5)), 50))
        hint = TEST_TYPE_HINTS.get(t, "")
        lines.append(f"  - {t}（{hint}）：{c} 個")
        total += c
    total = min(total, 50)
    return (
        "請依照以下測試類型分別產生測試案例，每個案例需加入 test_type 欄位標示所屬類型：\n"
        + "\n".join(lines)
        + f"\n總計不超過 {total} 個。"
    )


# ── Static ─────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse("index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "default_model": DEFAULT_MODEL}


# ── 測試 API Key ───────────────────────────────────────
@app.post("/test-key")
async def test_key(
    x_api_key: Optional[str] = Header(default=None),
    x_model: Optional[str] = Header(default=None),
):
    model = get_model(x_model)
    try:
        if _is_ollama(model):
            cli = _get_ollama_client()
            ollama_model = OLLAMA_MODEL_MAP.get(model, model)
            cli.chat.completions.create(
                model=ollama_model, max_tokens=5,
                messages=[{"role": "user", "content": "hi"}],
            )
            return {"status": "ok", "message": f"✅ Ollama 本機連線正常（{model}）"}
        else:
            client = get_client(x_api_key)
            client.messages.create(
                model=model, max_tokens=10,
                messages=[{"role": "user", "content": "hi"}]
            )
            return {"status": "ok", "message": f"✅ API Key 有效（{model}）"}
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效，請確認後重試")
    except _openai.APIConnectionError:
        raise HTTPException(status_code=503, detail=f"無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 匯入 Excel / CSV ──────────────────────────────────
@app.post("/upload/file")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    name = (file.filename or "").lower()

    if name.endswith(".csv"):
        try:
            text_raw = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text_raw = content.decode("big5", errors="replace")
        reader = csv.reader(io.StringIO(text_raw))
        lines = [
            " ".join(c.strip() for c in row if c.strip())
            for row in reader if any(c.strip() for c in row)
        ]
        return {"text": "\n".join(lines), "rows": len(lines)}

    elif name.endswith((".xlsx", ".xls")):
        if not HAS_OPENPYXL:
            raise HTTPException(status_code=400, detail="請先執行 pip install openpyxl")
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        lines = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                line = " ".join(str(v).strip() for v in row if v is not None and str(v).strip())
                if line:
                    lines.append(line)
        wb.close()
        return {"text": "\n".join(lines), "rows": len(lines)}

    raise HTTPException(status_code=400, detail="只支援 .csv 或 .xlsx 檔案")


# ── 生成 Test Case ─────────────────────────────────────
@app.post("/generate/testcase")
async def generate_testcase(
    request: TestCaseRequest,
    x_api_key: Optional[str] = Header(default=None),
    x_model: Optional[str] = Header(default=None),
):
    model = get_model(x_model)
    max_cases = max(1, min(request.max_cases or 10, 50))
    test_types = request.test_types or []
    ai_decide = any(tt.get("type") == "AI" for tt in test_types)
    try:
        if ai_decide:
            qty_instruction = (
                f"請根據需求內容自行分析，決定最適合的測試類型組合，"
                f"每個案例加入 test_type 欄位（可用類型：Functional / Regression / Smoke / Unit / Integration / API / Negative / UAT），"
                f"依需求的複雜度與風險自動分配各類型數量，總計最多 {max_cases} 個測試案例。"
            )
        elif test_types:
            qty_instruction = _build_type_instruction(test_types)
        else:
            qty_instruction = f"請產生最多 {max_cases} 個測試案例。"
        user_content = _inject_context(
            f"語言設定：{request.language}\n"
            f"{qty_instruction}\n\n"
            f"需求描述：\n{request.input_text}",
            request.context,
        )
        text = _chat_create(model, TEST_CASE_PROMPT, user_content, 8192, x_api_key)
        return _parse_json_array(_strip_fences(text))
    except HTTPException:
        raise
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="API 請求頻率超限，請稍後再試")
    except _openai.APIConnectionError:
        raise HTTPException(status_code=503, detail=f"無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── 串流生成 Test Case ──────────────────────────────────
@app.post("/generate/testcase/stream")
async def generate_testcase_stream(
    request: TestCaseRequest,
    x_api_key: Optional[str] = Header(default=None),
    x_model: Optional[str] = Header(default=None),
):
    model = get_model(x_model)
    max_cases = max(1, min(request.max_cases or 10, 50))
    test_types = request.test_types or []
    ai_decide = any(tt.get("type") == "AI" for tt in test_types)

    if ai_decide:
        qty_instruction = (
            f"請根據需求內容自行分析，決定最適合的測試類型組合，"
            f"每個案例加入 test_type 欄位（可用類型：Functional / Regression / Smoke / Unit / Integration / API / Negative / UAT），"
            f"依需求的複雜度與風險自動分配各類型數量，總計最多 {max_cases} 個測試案例。"
        )
    elif test_types:
        qty_instruction = _build_type_instruction(test_types)
    else:
        qty_instruction = f"請產生最多 {max_cases} 個測試案例。"

    user_content = _inject_context(
        f"語言設定：{request.language}\n{qty_instruction}\n\n需求描述：\n{request.input_text}",
        request.context,
    )

    # Ollama 小模型：走非串流 + retry，再用 SSE 回傳結果（避免串流解析問題）
    if _is_ollama(model):
        def ollama_stream_gen():
            try:
                _ensure_ollama_running()
                ollama_model = OLLAMA_MODEL_MAP.get(model, model)
                ollama_user = _inject_context(
                    f"Generate exactly {max_cases} test cases. Feature: {request.input_text}",
                    request.context,
                )
                clean = _ollama_create_with_retry(
                    ollama_model, OLLAMA_TEST_CASE_PROMPT, ollama_user, 8192
                )
                yield f"data: {json.dumps({'result': clean})}\n\n"
                yield "data: [DONE]\n\n"
            except HTTPException as e:
                yield f"data: {json.dumps({'error': e.detail})}\n\n"
            except _openai.APIConnectionError:
                yield f"data: {json.dumps({'error': f'無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            ollama_stream_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def stream_gen():
        try:
            collected: list[str] = []
            for text in _chat_stream(model, TEST_CASE_PROMPT, user_content, 8192, x_api_key):
                collected.append(text)
                yield f"data: {json.dumps({'d': text})}\n\n"
            # 收集完整輸出後清理，送出乾淨 JSON 供前端可靠解析
            clean = _strip_fences("".join(collected))
            yield f"data: {json.dumps({'result': clean})}\n\n"
            yield "data: [DONE]\n\n"
        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'error': 'API Key 無效'})}\n\n"
        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'error': 'API 請求頻率超限，請稍後再試'})}\n\n"
        except _openai.APIConnectionError:
            yield f"data: {json.dumps({'error': f'無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 生成 Gherkin ───────────────────────────────────────
@app.post("/generate/gherkin")
async def generate_gherkin(
    request: GherkinRequest,
    x_api_key: Optional[str] = Header(default=None),
    x_model: Optional[str] = Header(default=None),
):
    model = get_model(x_model)
    try:
        content = _inject_context(request.input_text, request.context)
        text = _chat_create(model, GHERKIN_PROMPT, content, 4096, x_api_key)
        return {"gherkin": text}
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效")
    except _openai.APIConnectionError:
        raise HTTPException(status_code=503, detail=f"無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── 生成 API Test ──────────────────────────────────────
@app.post("/generate/api-testcase")
async def generate_api_testcase(
    request: ApiTestRequest,
    x_api_key: Optional[str] = Header(default=None),
    x_model: Optional[str] = Header(default=None),
):
    model = get_model(x_model)
    try:
        content = _inject_context(request.input_text, request.context)
        text = _chat_create(model, API_TEST_PROMPT, content, 8192, x_api_key)
        return {"pytest_code": text}
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效")
    except _openai.APIConnectionError:
        raise HTTPException(status_code=503, detail=f"無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── Test Case → Gherkin ────────────────────────────────
@app.post("/convert/to-gherkin")
async def convert_to_gherkin(
    request: ConvertRequest,
    x_api_key: Optional[str] = Header(default=None),
    x_model: Optional[str] = Header(default=None),
):
    model = get_model(x_model)
    try:
        tc_text = json.dumps(request.test_cases, ensure_ascii=False, indent=2)
        content = _inject_context(
            f"請將以下測試案例轉換為 Gherkin 格式：\n\n{tc_text}",
            request.context,
        )
        text = _chat_create(model, TESTCASE_TO_GHERKIN_PROMPT, content, 4096, x_api_key)
        return {"gherkin": text}
    except _openai.APIConnectionError:
        raise HTTPException(status_code=503, detail=f"無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── Test Case → API Test ───────────────────────────────
@app.post("/convert/to-api-test")
async def convert_to_api_test(
    request: ConvertRequest,
    x_api_key: Optional[str] = Header(default=None),
    x_model: Optional[str] = Header(default=None),
):
    model = get_model(x_model)
    try:
        tc_text = json.dumps(request.test_cases, ensure_ascii=False, indent=2)
        content = _inject_context(
            f"請根據以下測試案例，生成對應的 pytest 程式碼：\n\n{tc_text}",
            request.context,
        )
        raw = _chat_create(model, TESTCASE_TO_API_PROMPT, content, 8192, x_api_key)
        code = re.sub(r"^```python\n?", "", raw.strip())
        code = re.sub(r"\n?```$", "", code).strip()
        return {"pytest_code": code}
    except _openai.APIConnectionError:
        raise HTTPException(status_code=503, detail=f"無法連線至 Ollama（{OLLAMA_BASE_URL}），請確認 Ollama 已啟動")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")
