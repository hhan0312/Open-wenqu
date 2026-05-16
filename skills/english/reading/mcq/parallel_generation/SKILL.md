---
id: english.reading.mcq.parallel_generation
version: 0.1.0
subject: english
stage: senior_high
domain: reading
question_format: mcq
task: parallel_generation
required_tools:
  - llm.generate_json
  - evidence.locate
  - docx.export
includes:
  - skill: english_reading_base
    sections:
      - 命题原则
      - 证据定位要求
      - 中文解析要求
input_schema: input.schema.json
output_schema: output.schema.json
---

## 适用场景

高中英语阅读理解单项选择题的“平行题”生成：在保持考查点相近的前提下，围绕同一篇材料生成新的题干与选项。

## 输入要求

用户会提供：阅读原文、`source_question` 原题（题干+四选项+正确答案+备注），以及生成数量与题型配比（细节/推理）。你必须严格服从 `normalized_input.generation` 的数量字段。

## 命题原则

（本节内容会由 includes 注入的更通用原则覆盖/补强；你仍需遵守本 SKILL 的题型特殊规则。）

## 原题分析规则

在输出 JSON 的 `plan_summary_zh` 与 `plan_focus_points` 中简要说明：

- 原题考查点（细节/推理/词汇/结构等）  
- 答案依据在原文中的大致位置与关键线索  
- 原题难度与陷阱类型（如有）

## 平行题生成规则

- 生成 `normalized_input.generation.total_questions` 道题。  
- 其中细节理解题数量必须等于 `detail_questions`，推理判断题数量必须等于 `inference_questions`。  
- 题干必须是英语；选项必须是英语（A-D 四选一）。  
- 每题必须明确 `question_type`：`detail` 或 `inference`。  
- 尽量避免与 `source_question` 在句子层面高度雷同；应改变设问角度与选项表述。

## 证据定位要求

（本节会由 includes 注入；输出时必须提供 `evidence_text`，并保证可回原文定位。）

## 干扰项设计要求

每道题必须对错误选项给出 `distractor_reviews`（逐项、含 `why_wrong_zh`）。

## 中文解析要求

（本节会由 includes 注入；输出字段 `explanation_zh` 为中文。）

## 质量评价 Rubric

每道题必须输出 `quality` 对象，包含 `score`（0-100）与三段文字：`clarity_zh`、`difficulty_match_zh`、`uniqueness_zh`，并给出 `issues_zh`（可为空数组）。

## 输出格式约束

你必须输出一个 JSON 对象，顶层字段包括：

- `plan_summary_zh`（字符串）  
- `plan_focus_points`（字符串数组）  
- `questions`（数组）

`questions` 每项字段必须包含：

- `id`（字符串）  
- `question_type`：`detail` 或 `inference`  
- `stem`（字符串）  
- `option_a`、`option_b`、`option_c`、`option_d`（字符串）  
- `correct_answer`：`A`/`B`/`C`/`D`  
- `explanation_zh`（字符串）  
- `evidence_text`（字符串）  
- `distractor_reviews`（数组；每项含 `option_key`、`why_wrong_zh`，可选 `confusion_risk_zh`）  
- `learning_objective_zh`（可选字符串）  
- `quality`（对象：`score`、`clarity_zh`、`difficulty_match_zh`、`uniqueness_zh`、`issues_zh`）

## 示例

见 `examples/` 目录（仅供风格参考；真实运行以用户输入为准）。
