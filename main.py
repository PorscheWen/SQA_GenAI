import csv
import io
import json
import os
import re

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from prompts import (
    API_TEST_PROMPT,
    GHERKIN_PROMPT,
    TEST_CASE_PROMPT,
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

MODEL = "claude-sonnet-4-5"


def get_client(api_key: Optional[str] = None) -> anthropic.Anthropic:
    key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(status_code=401, detail="未設定 API Key，請在右上角 ⚙️ 設定中輸入")
    return anthropic.Anthropic(api_key=key)


class TestCaseRequest(BaseModel):
    input_text: str
    language: Optional[str] = "zh"


class GherkinRequest(BaseModel):
    input_text: str


class ApiTestRequest(BaseModel):
    input_text: str


class ConvertRequest(BaseModel):
    test_cases: List[dict]


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\n?", "", text.strip())
    return re.sub(r"\n?```$", "", text).strip()


def _parse_json_array(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise HTTPException(status_code=500, detail="無法解析 AI 回傳的 JSON 格式，請重試")


# ── Static ─────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse("index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── 測試 API Key 是否有效 ──────────────────────────────
@app.post("/test-key")
async def test_key(x_api_key: Optional[str] = Header(default=None)):
    client = get_client(x_api_key)
    try:
        client.messages.create(
            model=MODEL, max_tokens=10,
            messages=[{"role": "user", "content": "hi"}]
        )
        return {"status": "ok", "message": "API Key 有效 ✅"}
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效，請確認後重試")
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
):
    client = get_client(x_api_key)
    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=8192, system=TEST_CASE_PROMPT,
            messages=[{"role": "user", "content": f"語言設定：{request.language}\n\n需求描述：\n{request.input_text}"}],
        )
        return _parse_json_array(_strip_fences(msg.content[0].text))
    except HTTPException:
        raise
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="API 請求頻率超限，請稍後再試")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── 生成 Gherkin ───────────────────────────────────────
@app.post("/generate/gherkin")
async def generate_gherkin(
    request: GherkinRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    client = get_client(x_api_key)
    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=4096, system=GHERKIN_PROMPT,
            messages=[{"role": "user", "content": request.input_text}],
        )
        return {"gherkin": msg.content[0].text}
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── 生成 API Test ──────────────────────────────────────
@app.post("/generate/api-testcase")
async def generate_api_testcase(
    request: ApiTestRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    client = get_client(x_api_key)
    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=8192, system=API_TEST_PROMPT,
            messages=[{"role": "user", "content": request.input_text}],
        )
        return {"pytest_code": msg.content[0].text}
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="API Key 無效")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── Test Case → Gherkin ────────────────────────────────
@app.post("/convert/to-gherkin")
async def convert_to_gherkin(
    request: ConvertRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    client = get_client(x_api_key)
    try:
        tc_text = json.dumps(request.test_cases, ensure_ascii=False, indent=2)
        msg = client.messages.create(
            model=MODEL, max_tokens=4096, system=TESTCASE_TO_GHERKIN_PROMPT,
            messages=[{"role": "user", "content": f"請將以下測試案例轉換為 Gherkin 格式：\n\n{tc_text}"}],
        )
        return {"gherkin": msg.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")


# ── Test Case → API Test ───────────────────────────────
@app.post("/convert/to-api-test")
async def convert_to_api_test(
    request: ConvertRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    client = get_client(x_api_key)
    try:
        tc_text = json.dumps(request.test_cases, ensure_ascii=False, indent=2)
        msg = client.messages.create(
            model=MODEL, max_tokens=8192, system=TESTCASE_TO_API_PROMPT,
            messages=[{"role": "user", "content": f"請根據以下測試案例，生成對應的 pytest 程式碼：\n\n{tc_text}"}],
        )
        code = re.sub(r"^```python\n?", "", msg.content[0].text.strip())
        code = re.sub(r"\n?```$", "", code).strip()
        return {"pytest_code": code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 錯誤：{str(e)}")
