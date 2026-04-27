# 🧪 SQA_GenAI

> QA 工程師貼入任何形式的需求，AI 自動產出對應格式的測試案例，節省撰寫時間。

串接 Anthropic Claude API 與本機 Ollama，將自然語言需求一鍵轉換為結構化測試文件，支援多模型切換、測試類型選擇、專案記憶與 Skills 指令。

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
| 🤖 多模型切換 | Claude Sonnet / Opus / Haiku，或本機 Ollama（deepseek-r1） |
| 🎯 測試類型選擇 | Functional / Regression / Smoke / Unit / Integration / API / Negative / UAT，或 AI 自動決定 |
| 🔢 案例數量設定 | 每次生成可指定產出數量（1–50，預設 2）|
| 🧠 Memory | 儲存專案背景知識，生成時自動帶入 AI 上下文 |
| 📄 CLAUDE.md Import | 直接上傳 `.md`/`.txt` 檔案，內容存入記憶 |
| ⚡ Skills 快捷 | Security / Mobile / Performance / A11y / i18n / Data 一鍵加入 |
| 📂 匯入 Excel / CSV | 拖曳或點擊上傳需求檔案 |
| ☑ 勾選轉換 | 勾選 Test Case 後直接轉為 Gherkin 或 API Test |
| 🔑 多 API Key | 右上角 ⚙️ 個人設定，不同使用者各自管理 |
| ⬇ 匯出 CSV | 含 BOM，Excel 可直接開啟 |
| 🔒 封閉模式 | 支援本機 Ollama，資料不離開內網 |

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

## 🔒 Ollama 本機封閉模式

不想讓測試資料傳到外部網路？可以改用本機 Ollama：

```bash
# 安裝 Ollama：https://ollama.com
ollama pull deepseek-r1:1.5b
# 啟動後在前端右上角 ⚙️ 選擇 deepseek-chat 模型即可
```

> Ollama 服務若未啟動，系統會在第一次呼叫時自動執行 `ollama serve`。

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
| `deepseek-chat` 🔒 | 本機 Ollama，封閉系統不連外網 |

### 🎯 測試類型

未勾選任何類型時，預設由 AI 自動分析需求並決定最適合的測試類型組合。

| 類型 | 說明 |
|------|------|
| 🎯 Functional | 驗證每個功能按需求規格正確運作 |
| 🔁 Regression | 確保既有功能在新版本後未遭破壞 |
| 💨 Smoke | 部署後快速驗證核心路徑可用 |
| 🔬 Unit | 針對單一函式或模組的隔離驗證 |
| 🔗 Integration | 驗證多個模組或服務串接後的資料流 |
| 🌐 API | 針對端點的請求/回應/狀態碼驗證 |
| ⚠️ Negative | 以非預期輸入探測系統弱點與錯誤處理 |
| 👤 UAT | 從終端使用者角度驗證業務流程 |

### 🧠 Memory & Skills

1. 點右上角 **⚙️** 開啟設定
2. 在 **Memory** 區塊貼入專案背景（技術棧、規格、測試方針）
3. 或點 **📄 匯入 CLAUDE.md** 直接載入專案文件
4. 選擇 **Skills 快捷**（如 🔒 Security）自動附加專業測試指令
5. 按「💾 儲存記憶」—之後每次生成都會自動帶入

---

## 技術規格

- **後端**：Python FastAPI + Anthropic SDK + OpenAI SDK（Ollama 相容）
- **前端**：單一 HTML（原生 CSS + JavaScript，無框架依賴）
- **預設模型**：`claude-sonnet-4-6`
- **支援匯入格式**：`.xlsx`、`.xls`、`.csv`、`.md`（Memory）
- **Python**：3.10+
