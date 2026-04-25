# 🧪 SQA_GenAI

> QA 工程師貼入任何形式的需求，AI 自動產出對應格式的測試案例，節省撰寫時間。

串接 Anthropic Claude API，將自然語言需求一鍵轉換為結構化測試文件。

---

## 功能

| Tab | 輸入 | 輸出 |
|-----|------|------|
| 📋 Test Case | 需求描述 / Excel / CSV | 測試案例表格（可勾選 + 匯出 CSV）|
| 🥒 Gherkin | User Story | BDD Gherkin 格式 |
| 🔧 API Test | API 規格 | 完整 pytest 自動化程式碼 |

### 進階功能

- **匯入 Excel / CSV**：拖曳或點擊上傳，自動填入需求欄位
- **勾選轉換**：勾選 Test Case 後直接轉為 Gherkin 或 API Test
- **多 API Key 支援**：右上角 ⚙️ 可設定個人 Key，不同使用者各自管理
- **匯出 CSV**：一鍵下載測試案例（含 BOM，Excel 可直接開啟）

---

## 快速啟動

```bash
git clone https://github.com/PorscheWen/SQA_GenAI.git
cd SQA_GenAI
pip install -r requirements.txt
cp .env.example .env        # 填入你的 ANTHROPIC_API_KEY
uvicorn main:app --reload
```

開啟瀏覽器：`http://localhost:8000`

> **快捷鍵**：`Ctrl + Enter` 在當前 Tab 直接送出生成

---

## 設定 API Key

**方法一（伺服器端）**：在 `.env` 填入 `ANTHROPIC_API_KEY`，適合單人或共用伺服器。

**方法二（個人設定）**：點右上角 ⚙️，貼入 Key 並按「儲存」，存於瀏覽器 `localStorage`，不同使用者互不影響。

---

## 技術規格

- **後端**：Python FastAPI + Anthropic SDK
- **前端**：單一 HTML（原生 CSS + JavaScript，無框架依賴）
- **AI 模型**：`claude-sonnet-4-5`
- **支援匯入格式**：`.xlsx`、`.xls`、`.csv`
- **Python**：3.10+
