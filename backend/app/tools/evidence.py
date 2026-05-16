from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models.domain import Block, Document, SourceSpan


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


@dataclass
class EvidenceLocateResult:
    ok: bool
    span: SourceSpan | None = None
    confidence: float = 0.0
    reason: str | None = None


def locate_evidence(*, document: Document, evidence_text: str) -> EvidenceLocateResult:
    needle = (evidence_text or "").strip()
    if not needle:
        return EvidenceLocateResult(ok=False, reason="empty_evidence")

    doc_id = document.id
    best: tuple[float, Block | None, int, int] = (-1.0, None, -1, -1)

    for block in document.blocks:
        hay = block.text
        idx = hay.find(needle)
        if idx >= 0:
            span = SourceSpan(
                document_id=doc_id,
                block_id=block.id,
                start_offset=idx,
                end_offset=idx + len(needle),
                confidence=1.0,
            )
            return EvidenceLocateResult(ok=True, span=span, confidence=1.0)

        n_norm = _normalize(needle)
        h_norm = _normalize(hay)
        pos = h_norm.find(n_norm)
        if pos >= 0:
            approx_start = max(0, min(len(hay), hay.lower().find(needle[:12].lower())))
            span = SourceSpan(
                document_id=doc_id,
                block_id=block.id,
                start_offset=approx_start,
                end_offset=min(len(hay), approx_start + len(needle)),
                confidence=0.92,
            )
            return EvidenceLocateResult(ok=True, span=span, confidence=0.92)

        ratio = SequenceMatcher(None, n_norm, h_norm).ratio()
        if ratio > best[0]:
            best = (ratio, block, 0, len(hay))

    if best[0] >= 0.72 and best[1] is not None:
        block = best[1]
        span = SourceSpan(
            document_id=doc_id,
            block_id=block.id,
            start_offset=0,
            end_offset=min(len(needle), len(block.text)),
            confidence=float(best[0]),
        )
        return EvidenceLocateResult(
            ok=True,
            span=span,
            confidence=float(best[0]),
            reason="fuzzy_matched_weak",
        )

    return EvidenceLocateResult(ok=False, reason="not_found_in_document")
