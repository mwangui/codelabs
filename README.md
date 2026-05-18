# Google Codelabs PDF 匯出器

這個 repository 用來把 Google Codelabs 批次轉成 PDF，並把所有 PDF 存在本 repo 的 `PDF/` 資料夾裡。

這版只做本機匯出：

- 不上傳 Google Drive
- 不匯入 NotebookLM
- 不登入任何 Google 服務
- 不做排程
- 不做資料庫

## 最終目標

每一個 Codelab 產生一份獨立 PDF，檔名格式固定為：

```text
001__cloudnet-agent-gateway__Agent-Gateway-管理代理工作負載.pdf
```

格式說明：

```text
{三位數序號}__{slug}__{中文短標題}.pdf
```

這樣在 Finder 裡排序清楚，之後丟進 NotebookLM 或其他工具時也不會看不懂來源。

## 專案結構

```text
.
├── PDF/                  # 所有 PDF 都輸出到這裡
├── output/
│   ├── html/             # 每篇 Codelab 的除錯 HTML
│   ├── index.json        # 探索到的 Codelab 清單
│   ├── manifest.csv      # 成功/跳過紀錄
│   ├── errors.json       # 失敗紀錄
│   └── run.log           # 執行 log
├── src/
│   ├── discover.py       # 探索 Codelab URL
│   ├── manifest.py       # 寫入 manifest/errors
│   ├── normalize.py      # URL 與檔名正規化
│   └── render_pdf.py     # Playwright 產生 PDF
├── config.yaml
├── manual_urls.txt
├── requirements.txt
└── run.py
```

## 安裝

建議使用 Python 3.12 或更新版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## PDF 產生策略

工具不會直接列印 Google Codelabs 原始頁面。

原因是 Codelabs 原頁有 DevSite 外框、導覽列、scroll 容器和 web component；如果直接列印，可能只印出目前顯示的單一步驟。

目前採用的做法是：

1. 用 Playwright 打開真實 Codelab 頁面
2. 抽出全部 `google-codelab-step`
3. 重新組成乾淨 HTML
4. HTML 內容包含封面、來源 URL、目錄、所有步驟
5. 再用 Chromium 把乾淨 HTML 轉成 PDF

也就是說，一份 PDF 會包含該 Codelab 裡的全部步驟，不是只截目前頁面。

## 先測一份

先用單篇確認 PDF 版面、中文、圖片、程式碼區塊都正常：

```bash
python run.py render-one \
  --url "https://codelabs.developers.google.com/cloudnet-agent-gateway?hl=zh-tw"
```

成功後會在 `PDF/` 裡看到一份 PDF。

## 探索清單

```bash
python run.py discover
```

清單會輸出到：

```text
output/index.json
```

探索順序：

1. 先讀 Google Codelabs sitemap
2. sitemap 失敗時改讀首頁 HTML
3. 如果還是不完整，可以手動把 URL 放進 `manual_urls.txt`

## 預覽清單

只看會處理哪些 Codelab，不產 PDF：

```bash
python run.py dry-run
```

用關鍵字篩選：

```bash
python run.py dry-run --filter "gemini|agent|vertex|ai|llm|genai"
```

只預覽一小批：

```bash
python run.py dry-run --start-index 1 --end-index 50
python run.py dry-run --filter "gemini|agent|vertex|ai|llm|genai" --limit 20
```

## 批次產生全部 PDF

```bash
python run.py render-all
```

只產生 AI / Agent / Gemini 相關：

```bash
python run.py render-all --filter "gemini|agent|vertex|ai|llm|genai"
```

分批產生，避免一次跑太久：

```bash
python run.py render-all --start-index 1 --end-index 50
python run.py render-all --start-index 51 --end-index 100
```

先小批量驗收 10 筆：

```bash
python run.py render-all --limit 10
```

預設行為：

- PDF 已存在就跳過
- 單篇失敗不會中斷整批
- 失敗會寫進 `output/errors.json`
- 成功與跳過會寫進 `output/manifest.csv`
- 每產生一份 PDF 後會立刻驗證，結果寫進 `output/verification.csv`

## 重跑失敗項

```bash
python run.py retry-failed
```

如果要覆蓋既有 PDF：

```bash
python run.py render-all --force
```

## 驗證 PDF

每次 `render-one` 或 `render-all` 產生 PDF 後，工具會自動比對：

- manifest / render 結果的預期步驟數
- 乾淨 HTML 裡的 step 區塊數
- 乾淨 HTML 目錄裡的 step 連結數
- 最後一步是否存在
- PDF 是否存在
- PDF 大小是否合理
- PDF 是否超過一頁
- PDF 頁數是否少於步驟數

單獨驗證最新一份 PDF：

```bash
python run.py verify-one
```

驗證指定 PDF：

```bash
python run.py verify-one \
  --pdf "PDF/001__cloudnet-agent-gateway__透過-Gemini-Enterprise-Agent-Platform-的-Agent-Gateway-管理代理工作負載.pdf"
```

驗證所有 PDF：

```bash
python run.py verify-all
```

驗證結果會追加到：

```text
output/verification.csv
```

## 手動補 URL

如果你有特定 Codelab 想處理，可以把 URL 放進 `manual_urls.txt`，一行一筆。

範例：

```text
https://codelabs.developers.google.com/cloudnet-agent-gateway?hl=zh-tw
```

程式會自動：

- 去掉 `#0`、`#1`、`#2` 這些頁內錨點
- 補上 `hl=zh-tw`
- 去除重複 URL

## 驗收標準

完成後至少要確認：

1. `PDF/` 裡有產出的 PDF
2. PDF 檔名有序號、slug、中文短標題
3. PDF 內容包含完整步驟，不只目前顯示的單一步驟
4. 中文沒有亂碼
5. 程式碼區塊正常顯示
6. 圖片正常顯示
7. `output/manifest.csv` 可以追蹤每份 PDF 對應的來源 URL
8. `output/errors.json` 可以追蹤失敗項

## 目前不做的事

這個工具目前刻意不做：

- NotebookLM 自動匯入
- Google Drive 上傳
- Google API
- 瀏覽器登入
- Web UI
- 排程
- Docker

先把「Codelabs → PDF → repository/PDF」這條主線做穩。
