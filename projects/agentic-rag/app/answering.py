from __future__ import annotations

import re
from typing import Protocol

import httpx

from app.domain import AnswerResult, SearchHit
from app.embeddings import tokenize


class Answerer(Protocol):
    name: str

    async def answer(self, question: str, hits: list[SearchHit]) -> AnswerResult: ...


class ExtractiveAnswerer:
    """Offline answerer: extracts relevant evidence instead of inventing prose."""

    name = "demo-extractive"

    async def answer(self, question: str, hits: list[SearchHit]) -> AnswerResult:
        question_tokens = set(tokenize(question))
        candidates: list[tuple[float, str, str]] = []
        for source_number, hit in enumerate(hits, start=1):
            heading_tokens = set(tokenize(hit.chunk.heading or ""))
            for raw_line in hit.chunk.content.splitlines():
                line = raw_line.strip().strip("|").strip()
                if not _is_evidence_line(line, heading=hit.chunk.heading):
                    continue
                line_tokens = set(tokenize(line))
                overlap = len(question_tokens & line_tokens)
                heading_overlap = len(question_tokens & heading_tokens)
                score = overlap + heading_overlap * 0.35 + hit.score * 0.1
                candidates.append((score, line, f"S{source_number}"))

        selected: list[tuple[str, str]] = []
        seen_lines: set[str] = set()
        for score, line, source_id in sorted(candidates, reverse=True):
            if score <= 0 or line in seen_lines:
                continue
            selected.append((line, source_id))
            seen_lines.add(line)
            # Demo mode proves retrieval and citation wiring. Returning only the
            # strongest line avoids pretending this extractor can synthesize
            # multi-fact answers like a real LLM.
            if len(selected) == 1:
                break

        if not selected:
            return AnswerResult(
                answer="当前知识库没有找到足够证据，暂时无法回答这个问题。",
                cited_chunk_ids=(),
            )

        answer = "根据当前知识库找到的原文：\n" + "\n".join(
            f"- {line} [{source_id}]" for line, source_id in selected
        )
        cited_numbers = {source_id for _, source_id in selected}
        cited_chunk_ids = tuple(
            hit.chunk.id
            for index, hit in enumerate(hits, start=1)
            if f"S{index}" in cited_numbers
        )
        return AnswerResult(answer=answer, cited_chunk_ids=cited_chunk_ids)


class OpenAICompatibleAnswerer:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    async def answer(self, question: str, hits: list[SearchHit]) -> AnswerResult:
        context = "\n\n".join(
            f"[S{index}] 文件：{hit.chunk.filename}\n"
            f"章节：{hit.chunk.heading or '未命名章节'}\n"
            f"{hit.chunk.content}"
            for index, hit in enumerate(hits, start=1)
        )
        prompt = (
            "只根据下面的资料回答问题。每个事实后使用 [S1] 这样的编号标注来源。"
            "资料不足时明确说无法回答，不要使用外部常识补充。\n\n"
            f"资料：\n{context}\n\n问题：{question}"
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是企业知识库助手，答案必须基于给定资料。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
        cited_numbers = {
            int(value)
            for value in re.findall(r"\[S(\d+)]", answer)
            if 1 <= int(value) <= len(hits)
        }
        return AnswerResult(
            answer=answer,
            cited_chunk_ids=tuple(
                hit.chunk.id
                for index, hit in enumerate(hits, start=1)
                if index in cited_numbers
            ),
        )


def _is_evidence_line(line: str, heading: str | None) -> bool:
    if len(line) < 3 or line.startswith("#"):
        return False
    if heading and line == heading:
        return False
    if "|" in line and not re.search(r"\d", line):
        return False
    compact = re.sub(r"[\s|:-]", "", line)
    return bool(compact) and not set(compact) <= {"-"}
