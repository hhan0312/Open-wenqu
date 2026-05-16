import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  cancelRun,
  createRun,
  getOrCreateClientId,
  getRun,
  loadDraft,
  openEventsSource,
  patchArtifact,
  saveDraft,
  listSkills,
  type WorkbenchForm
} from "./workbenchModel";
import { apiDownload } from "./api";

const SKILL_ID = "english.reading.mcq.parallel_generation";

const defaultForm: WorkbenchForm = {
  passage: "",
  stem: "",
  optA: "",
  optB: "",
  optC: "",
  optD: "",
  correct: "A",
  notes: "",
  curriculum: "",
  totalQuestions: 3,
  detailQuestions: 2,
  inferenceQuestions: 1,
  exportTitle: "高中英语阅读平行题",
  bypassCache: false
};

export default function App() {
  const clientId = useMemo(() => getOrCreateClientId(), []);
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<Array<{ seq: number; type: string; node?: string | null }>>([]);
  const [lastSeq, setLastSeq] = useState(0);
  const [sseError, setSseError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const { data: skills } = useQuery({
    queryKey: ["skills"],
    queryFn: listSkills
  });

  const form = useForm<WorkbenchForm>({
    defaultValues: loadDraft() ?? defaultForm
  });

  useEffect(() => {
    const t = window.setInterval(() => {
      saveDraft(form.getValues());
    }, 2000);
    return () => window.clearInterval(t);
  }, [form]);

  const runDetailQ = useQuery({
    queryKey: ["run", runId, clientId],
    enabled: Boolean(runId),
    queryFn: async () => getRun(runId!, clientId),
    refetchInterval: (q) => {
      const st = String((q.state.data as Record<string, unknown> | undefined)?.status ?? "");
      if (st === "running") return 1500;
      return false;
    }
  });

  const createMut = useMutation({
    mutationFn: async (v: WorkbenchForm) => {
      return createRun({
        client_id: clientId,
        skill_id: SKILL_ID,
        passage: v.passage,
        source_question: {
          stem: v.stem,
          options: [
            { key: "A", text: v.optA },
            { key: "B", text: v.optB },
            { key: "C", text: v.optC },
            { key: "D", text: v.optD }
          ],
          correct_answer: v.correct,
          notes: v.notes.trim() ? v.notes : null
        },
        curriculum_text: v.curriculum.trim() ? v.curriculum : null,
        generation: {
          total_questions: v.totalQuestions,
          detail_questions: v.detailQuestions,
          inference_questions: v.inferenceQuestions
        },
        bypass_cache: v.bypassCache,
        export_title: v.exportTitle
      });
    },
    onSuccess: (res) => {
      setRunId(res.run_id);
      setEvents([]);
      setLastSeq(0);
      setSseError(null);
    }
  });

  useEffect(() => {
    if (!runId) return;
    if (esRef.current) esRef.current.close();

    const es = openEventsSource(runId, clientId, lastSeq);
    esRef.current = es;

    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as { seq: number; type: string; node?: string | null };
        setEvents((prev) => {
          if (prev.some((p) => p.seq === msg.seq)) return prev;
          return [...prev, msg].sort((a, b) => a.seq - b.seq);
        });
        setLastSeq((s) => Math.max(s, msg.seq));
      } catch {
        // ignore
      }
    };
    es.onerror = () => {
      setSseError("SSE 连接中断，正在由轮询补偿…");
    };

    return () => es.close();
  }, [runId, clientId]);

  const finalArtifactId = String((runDetailQ.data as any)?.final_artifact_id ?? "");
  const status = String((runDetailQ.data as any)?.status ?? "");

  const [editedJson, setEditedJson] = useState<string>("");

  useEffect(() => {
    const data = runDetailQ.data as Record<string, unknown> | undefined;
    const arts = data?.artifacts as Array<{ id: string; payload: unknown }> | undefined;
    const fid = data?.final_artifact_id as string | undefined;
    if (!arts?.length) return;
    const art = fid ? arts.find((a) => a.id === fid) ?? arts[arts.length - 1] : arts[arts.length - 1];
    setEditedJson(JSON.stringify(art.payload, null, 2));
  }, [runDetailQ.data]);

  const saveEditMut = useMutation({
    mutationFn: async () => {
      if (!runId || !finalArtifactId) throw new Error("missing artifact");
      const payload = JSON.parse(editedJson);
      return patchArtifact(runId, finalArtifactId, clientId, payload);
    },
    onSuccess: async () => {
      await runDetailQ.refetch();
    }
  });

  const exportMut = useMutation({
    mutationFn: async () => {
      if (!runId || !finalArtifactId) throw new Error("missing artifact");
      const v = form.getValues();
      const blob = await apiDownload(`/api/runs/${encodeURIComponent(runId)}/export/docx`, {
        client_id: clientId,
        artifact_id: finalArtifactId,
        title: v.exportTitle
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `open-wenqu-${runId}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    }
  });

  return (
    <div style={{ fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, PingFang SC, Microsoft Yahei, Arial", maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <header style={{ marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Open Wenqu 问渠 · 教师工作台（V1）</h1>
        <p style={{ marginTop: 8, color: "#444" }}>client_id：{clientId}</p>
      </header>

      <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <h2>阅读材料</h2>
          <textarea {...form.register("passage")} rows={14} style={{ width: "100%" }} placeholder="粘贴阅读原文（建议 600-1000 词）" />

          <h2>原题（结构化）</h2>
          <label style={{ display: "block", marginTop: 8 }}>题干</label>
          <textarea {...form.register("stem")} rows={3} style={{ width: "100%" }} />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
            <label>
              A
              <input {...form.register("optA")} style={{ width: "100%" }} />
            </label>
            <label>
              B
              <input {...form.register("optB")} style={{ width: "100%" }} />
            </label>
            <label>
              C
              <input {...form.register("optC")} style={{ width: "100%" }} />
            </label>
            <label>
              D
              <input {...form.register("optD")} style={{ width: "100%" }} />
            </label>
          </div>

          <label style={{ display: "block", marginTop: 8 }}>
            正确答案
            <select {...form.register("correct")} style={{ marginLeft: 8 }}>
              {(["A", "B", "C", "D"] as const).map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>

          <label style={{ display: "block", marginTop: 8 }}>备注/原解析</label>
          <textarea {...form.register("notes")} rows={3} style={{ width: "100%" }} />

          <h2>课标 / 能力目标</h2>
          <textarea {...form.register("curriculum")} rows={5} style={{ width: "100%" }} placeholder="可选" />

          <h2>生成设置</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            <label>
              总题数
              <input type="number" {...form.register("totalQuestions", { valueAsNumber: true })} />
            </label>
            <label>
              细节题
              <input type="number" {...form.register("detailQuestions", { valueAsNumber: true })} />
            </label>
            <label>
              推理题
              <input type="number" {...form.register("inferenceQuestions", { valueAsNumber: true })} />
            </label>
          </div>

          <label style={{ display: "block", marginTop: 8 }}>
            <input type="checkbox" {...form.register("bypassCache")} /> 绕过缓存重新生成
          </label>

          <label style={{ display: "block", marginTop: 8 }}>
            导出标题
            <input {...form.register("exportTitle")} style={{ width: "100%" }} />
          </label>

          <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" onClick={form.handleSubmit((v) => createMut.mutate(v))} disabled={createMut.isPending}>
              生成
            </button>
            <button
              type="button"
              disabled={!runId}
              onClick={() => runId && cancelRun(runId, clientId)}
            >
              取消运行
            </button>
            <button type="button" disabled={!finalArtifactId} onClick={() => exportMut.mutate()}>
              导出 DOCX
            </button>
          </div>

          <div style={{ marginTop: 12, padding: 12, border: "1px dashed #bbb", color: "#666" }}>
            <strong>上传扫描件 / 拍照</strong>：V1 仅占位。后续接入 OCR/VLM 后，将统一转换为 Document，不再改动命题链路。
          </div>
        </div>

        <div>
          <h2>可用技能（后端注册）</h2>
          <pre style={{ background: "#f6f6f6", padding: 12, overflow: "auto", maxHeight: 160 }}>{JSON.stringify(skills, null, 2)}</pre>

          <h2>Agent 进度（SSE）</h2>
          {sseError && <p style={{ color: "#a60" }}>{sseError}</p>}
          <pre style={{ background: "#f6f6f6", padding: 12, overflow: "auto", maxHeight: 220 }}>{JSON.stringify(events, null, 2)}</pre>

          <h2>运行状态</h2>
          <p>
            <strong>run_id</strong>：{runId ?? "（未创建）"}
          </p>
          <p>
            <strong>status</strong>：{status || "—"}
          </p>

          <h2>结果编辑（JSON 整体替换）</h2>
          <textarea value={editedJson} onChange={(e) => setEditedJson(e.target.value)} rows={16} style={{ width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas" }} />
          <button type="button" style={{ marginTop: 8 }} disabled={!finalArtifactId || saveEditMut.isPending} onClick={() => saveEditMut.mutate()}>
            保存教师编辑（新 artifact 版本）
          </button>
          {saveEditMut.error && <p style={{ color: "#b00" }}>{String((saveEditMut.error as any)?.message ?? saveEditMut.error)}</p>}
          {createMut.error && <p style={{ color: "#b00" }}>{String((createMut.error as any)?.message ?? createMut.error)}</p>}
        </div>
      </section>
    </div>
  );
}
