# 🧪 SQA_GenAI

> QA 工程師貼入任何形式的需求，AI 自動產出對應格式的測試案例，節省撰寫時間。

串接 Anthropic Claude API，將自然語言需求一鍵轉換為結構化測試文件，支援多模型切換、專案記憶與 Skills 指令。

---

## 功能

| Tab | 輸入 | 輸出 |
|-----|------|------|
| 📋 Test Case | 需求描述 / Excel / CSV | 測試案例表格（可勾選 + 匯出 CSV）|
| 🥒 Gherkin | User Story | BDD Gherkin 格式 |
| 🔧 API Test | API 規格 / Swagger YAML | 完整 pytest 自動化程式碼 |

### 進階功能

| 功能 | 說明 |
|------|------|
| 🤖 多模型切換 | Sonnet 4.6（預設）/ Opus 4.7 / Haiku 4.5 / Sonnet 4.5 |
| 🔢 案例數量設定 | 每次生成可指定產出數量（1–50，預設 10）|
| 🧠 Memory | 儲存專案背景知識，生成時自動帶入 AI 上下文 |
| 📄 CLAUDE.md Import | 直接上傳 `.md`/`.txt` 檔案，內容存入記憶 |
| ⚡ Skills 快捷 | Security / Mobile / Performance / A11y / i18n / Data 一鍵加入 |
| 📂 匯入 Excel / CSV | 拖曳或點擊上傳需求檔案 |
| ☑ 勾選轉換 | 勾選 Test Case 後直接轉為 Gherkin 或 API Test |
| 🔑 多 API Key | 右上角 ⚙️ 個人設定，不同使用者各自管理 |
| ⬇ 匯出 CSV | 含 BOM，Excel 可直接開啟 |

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

## ⚙️ 設定說明

### API Key

| 方式 | 說明 |
|------|------|
| 伺服器端 `.env` | 填入 `ANTHROPIC_API_KEY`，適合共用伺服器 |
| 個人設定（⚙️）| 存於瀏覽器 `localStorage`，不同使用者互不影響 |

### AI 模型

| 模型 | 適用情境 |
|------|----------|
| `claude-sonnet-4-6` ⚡ | **預設**，速度與品質最佳平衡 |
| `claude-opus-4-7` 🧠 | 最強智能，複雜需求 / 多層業務邏輯 |
| `claude-haiku-4-5` 💨 | 最快最省成本，簡單需求快速驗證 |
| `claude-sonnet-4-5` 📦 | 舊版相容 |

### 🧠 Memory & Skills

1. 點右上角 **⚙️** 開啟設定
2. 在 **Memory** 區塊貼入專案背景（技術棧、規格、測試方針）
3. 或點 **📄 匯入 CLAUDE.md** 直接載入專案文件
4. 選擇 **Skills 快捷**（如 🔒 Security）自動附加專業測試指令
5. 按「💾 儲存記憶」—之後每次生成都會自動帶入

---

## 技術規格

- **後端**：Python FastAPI + Anthropic SDK
- **前端**：單一 HTML（原生 CSS + JavaScript，無框架依賴）
- **預設模型**：`claude-sonnet-4-6`
- **支援匯入格式**：`.xlsx`、`.xls`、`.csv`、`.md`（Memory）
- **Python**：3.10+
