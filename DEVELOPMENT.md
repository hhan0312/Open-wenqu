# Open Wenqu 本地开发说明

## 前置要求

- Python 3.11+
- Node.js 20+

## 后端

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：http://localhost:8000/docs

## 前端

```bash
cd frontend
npm install
npm run dev
```

默认开发代理将 `/api` 指到 `http://127.0.0.1:8000`（见 `vite.config.ts`）。

## 评测

```bash
cd backend
pytest
python ../evals/run_eval.py
```

## 目录结构

参见仓库根目录《执行计划.md》第 2 节总体架构。
