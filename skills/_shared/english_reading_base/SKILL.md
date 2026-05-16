---
id: english.reading.shared.english_reading_base
version: 0.1.0
subject: english
stage: senior_high
domain: reading
question_format: shared
task: base_prompt_fragments
required_tools: []
includes: []
input_schema: input.schema.json
output_schema: output.schema.json
---

## 适用场景

该技能包用于复用高中英语阅读理解的通用命题与证据原则，不作为独立运行技能。

## 输入要求

通常不直接使用；由其它阅读题型技能通过 `includes` 引用指定章节。

## 命题原则

- 题干必须可在原文中找到明确依据，避免“想当然”。  
- 干扰项要有 plausible wrong reasoning，但不能基于原文未出现的信息捏造事实。  
- 语言表达应贴近真实考试用语，避免歧义与双重否定陷阱。  
- 难度应与原题同一量级：词汇、句法复杂度与推理跨度不要显著跃迁。

## 原题分析规则

（本基础包不强制输出原题分析；由具体题型技能定义）

## 平行题生成规则

（由具体题型技能定义）

## 证据定位要求

- `evidence_text` 必须是原文连续片段的忠实摘录（允许最小改写以匹配标点或大小写，但不得改变事实）。  
- 证据必须直接支撑正确答案，而不是“相关但不充分”。  
- 若证据跨句，选择最能一句话锁定的最短连续片段。

## 干扰项设计要求

- 每个错误选项都要说明“为什么错”，并指出可能的迷思/典型错因。  
- 不要出现多个看似正确的答案；如出现，主动提高干清晰度或改写选项。

## 中文解析要求

- 先用 1-2 句说明正确思路，再指出证据如何锁定答案。  
- 解释要站在教师讲题视角：学生易错点、关键句、排除法步骤可写清楚。

## 质量评价 Rubric

从清晰度、难度匹配、答案唯一性三方面自评，并给出 0-100 分数与文字说明。

## 输出格式约束

（由具体题型的 JSON schema 定义）

## 示例

（由具体题型给出）
