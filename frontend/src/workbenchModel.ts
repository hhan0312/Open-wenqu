import { apiGet, apiPost } from "./api";

const STORAGE_KEY = "open_wenqu_client_id_v1";
const DRAFT_KEY = "open_wenqu_workbench_draft_v1";

export type SourceOption = { key: "A" | "B" | "C" | "D"; text: string };

export type WorkbenchForm = {
  passage: string;
  stem: string;
  optA: string;
  optB: string;
  optC: string;
  optD: string;
  correct: "A" | "B" | "C" | "D";
  notes: string;
  curriculum: string;
  totalQuestions: number;
  detailQuestions: number;
  inferenceQuestions: number;
  exportTitle: string;
  bypassCache: boolean;
};

export function getOrCreateClientId(): string {
  const existing = localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;
  const id = crypto.randomUUID();
  localStorage.setItem(STORAGE_KEY, id);
  return id;
}

export function loadDraft(): WorkbenchForm | null {
  const raw = localStorage.getItem(DRAFT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as WorkbenchForm;
  } catch {
    return null;
  }
}

export function saveDraft(form: WorkbenchForm) {
  localStorage.setItem(DRAFT_KEY, JSON.stringify(form));
}

export async function listSkills() {
  return apiGet<Array<Record<string, unknown>>>("/api/skills");
}

export async function createRun(payload: {
  client_id: string;
  skill_id: string;
  passage: string;
  source_question: {
    stem: string;
    options: SourceOption[];
    correct_answer: "A" | "B" | "C" | "D";
    notes: string | null;
  };
  curriculum_text: string | null;
  generation: {
    total_questions: number;
    detail_questions: number;
    inference_questions: number;
  };
  bypass_cache: boolean;
  export_title: string | null;
}) {
  return apiPost<{ run_id: string; status: string }>("/api/runs", payload);
}

export async function getRun(runId: string, clientId: string) {
  return apiGet<Record<string, unknown>>(`/api/runs/${encodeURIComponent(runId)}?client_id=${encodeURIComponent(clientId)}`);
}

export async function cancelRun(runId: string, clientId: string) {
  return apiPost<Record<string, unknown>>(
    `/api/runs/${encodeURIComponent(runId)}/cancel?client_id=${encodeURIComponent(clientId)}`,
    {}
  );
}

export async function patchArtifact(runId: string, artifactId: string, clientId: string, payload: unknown) {
  return apiPatch<{ artifact_id: string; version: number }>(
    `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`,
    { client_id: clientId, payload }
  );
}

export function openEventsSource(runId: string, clientId: string, afterSeq: number): EventSource {
  return new EventSource(
    `/api/runs/${encodeURIComponent(runId)}/events?client_id=${encodeURIComponent(clientId)}&after_seq=${afterSeq}`
  );
}

async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return (await r.json()) as T;
}
