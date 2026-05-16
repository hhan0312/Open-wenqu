# Evals（V1 最小评测）

本目录用于固定样本回归，避免 prompt / skill / LLM 合约改动引入隐性退化。

- `cases/`：JSON 样本（文章、原题、期望题量与最低质量分等）
- `run_eval.py`：最小运行入口（后续可接入 fake LLM 与统计报告）

修改 `skills/` 或 `backend/app/models/llm_contract.py` 后，请先跑：

```bash
cd backend
pytest
python ../evals/run_eval.py
```
