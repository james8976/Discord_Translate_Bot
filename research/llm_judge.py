"""Optional, auditable LLM review for generated anchors and retrieval results.

No network request is made until a caller creates :class:`OpenAIJudge` with an
API key and explicitly enables a run.  LLM judgements are supplementary labels,
not ground truth; retain the original dictionaries and human-review samples.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


class OpenAIJudge:
    """Judge bilingual pairs with OpenAI Structured Outputs in bounded batches."""

    def __init__(self, model: str, api_key: str, batch_size: int = 20) -> None:
        if not model:
            raise ValueError("An LLM model name is required")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM judging is enabled")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the optional 'openai' package to enable LLM judging") from exc
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.batch_size = batch_size

    @staticmethod
    def _schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "score": {"type": "integer", "enum": [0, 1, 2]},
                            "label": {"type": "string", "enum": ["wrong", "partial", "equivalent"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["index", "score", "label", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["items"],
            "additionalProperties": False,
        }

    def judge(self, rows: Iterable[Dict[str, str]], task: str, max_items: int) -> List[Dict[str, Any]]:
        """Return scored rows with the original values preserved for audit."""
        selected = list(rows)[:max_items]
        judgements: List[Dict[str, Any]] = []
        instructions = (
            "You are a conservative bilingual lexicon evaluator. Return JSON only. "
            "Score 2 only for equivalent meanings and compatible usage, 1 for a related "
            "or partially acceptable answer, and 0 for wrong or unrelated. Do not infer "
            "facts absent from the supplied terms."
        )

        for start in range(0, len(selected), self.batch_size):
            batch = selected[start:start + self.batch_size]
            prompt = json.dumps({"task": task, "items": batch}, ensure_ascii=False)
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "bilingual_lexicon_review",
                        "schema": self._schema(),
                        "strict": True,
                    },
                },
                store=False,
            )
            decoded = json.loads(response.output_text)
            for item in decoded.get("items", []):
                local_index = item.get("index")
                if not isinstance(local_index, int) or not 0 <= local_index < len(batch):
                    continue
                source_row = dict(batch[local_index])
                source_row.update({"llm_score": item["score"], "llm_label": item["label"], "llm_reason": item["reason"]})
                judgements.append(source_row)
        return judgements
