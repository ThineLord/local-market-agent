from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError


class StructuredOutputError(RuntimeError):
    pass


class BaseLLMProvider(Protocol):
    def complete_json(self, prompt: str) -> str:
        """Return a JSON string for the requested structured task."""


T = TypeVar("T", bound=BaseModel)


def structured_completion(
    provider: BaseLLMProvider,
    prompt: str,
    schema: type[T],
    *,
    max_retries: int = 2,
) -> T:
    """Validate provider output as a Pydantic schema with bounded runtime retries."""

    errors: list[str] = []
    validation_error: str | None = None
    for _attempt in range(max_retries + 1):
        current_prompt = _structured_prompt(
            task_payload=prompt,
            schema=schema,
            validation_error=validation_error,
        )
        raw = provider.complete_json(current_prompt)
        try:
            payload = _parse_json_payload(raw)
            return schema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            validation_error = str(exc)
            errors.append(validation_error)
    raise StructuredOutputError("; ".join(errors))


class MockLLMProvider:
    """Deterministic offline provider for tests and local demos."""

    def complete_json(self, prompt: str) -> str:
        payload = _task_payload_from_prompt(prompt)
        snapshot = payload["snapshot"]
        market = snapshot["market"]
        all_evidence = payload.get("evidence", [])
        positive = [item for item in all_evidence if not item.get("metadata", {}).get("counter")]
        counter = [item for item in all_evidence if item.get("metadata", {}).get("counter")]

        evidence_quality = _evidence_quality(all_evidence)
        confidence = _confidence(evidence_quality, len(all_evidence))
        estimated_probability = _estimated_probability(
            all_evidence, snapshot.get("market_implied_probability")
        )
        market_probability = snapshot.get("market_implied_probability")
        spread = None
        if snapshot.get("best_bid") is not None and snapshot.get("best_ask") is not None:
            spread = snapshot["best_ask"] - snapshot["best_bid"]

        reasons: list[str] = ["Live trading is disabled; output is paper-only."]
        uncertainty_notes = [
            "Fixture evidence is limited and may not capture late-breaking developments."
        ]
        if not all_evidence:
            reasons.append("No evidence was available.")
            uncertainty_notes.append("No external corroboration was supplied.")
        if market_probability is None:
            reasons.append("Missing market price prevents a paper_buy_yes/no recommendation.")
            uncertainty_notes.append("Market-implied probability is unavailable.")
        if evidence_quality < 0.65:
            reasons.append("Evidence quality is below the strategy threshold.")
        if len(all_evidence) < 2:
            reasons.append("Sparse evidence lowers confidence.")

        action = "observe"
        if not all_evidence:
            action = "skip"
        elif market_probability is None:
            action = "observe"
        elif confidence >= 0.60 and evidence_quality >= 0.65 and estimated_probability is not None:
            threshold = max(0.08, 2 * (spread or 0.0))
            if estimated_probability - market_probability >= threshold:
                action = "paper_buy_yes"
            elif market_probability - estimated_probability >= threshold:
                action = "paper_buy_no"

        thesis = f"{market['title']}: {action.replace('_', ' ')}"
        rationale = (
            f"Estimated probability {estimated_probability}; market probability "
            f"{market_probability}; evidence quality {evidence_quality}."
        )
        return json.dumps(
            {
                "market_id": market["market_id"],
                "snapshot_id": snapshot["snapshot_id"],
                "thesis": thesis,
                "rationale": rationale,
                "evidence": positive,
                "counter_evidence": counter,
                "uncertainty_notes": uncertainty_notes,
                "confidence": confidence,
                "evidence_quality": evidence_quality,
                "estimated_probability": estimated_probability,
                "market_implied_probability": market_probability,
                "recommended_action": action,
                "must_not_trade_reasons": reasons,
            },
            sort_keys=True,
        )


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    base_url: str
    api_key: str | None
    model: str
    timeout_seconds: float = 600.0

    def complete_json(self, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        base = self.base_url.rstrip("/")
        url = f"{base}/chat/completions"
        response = httpx.post(
            url,
            headers=headers,
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return strict JSON that matches the requested schema.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "stream": False,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        return _message_content_as_text(message.get("content"))


def _structured_prompt(
    *,
    task_payload: str,
    schema: type[BaseModel],
    validation_error: str | None,
) -> str:
    try:
        parsed_input: Any = json.loads(task_payload)
    except json.JSONDecodeError:
        parsed_input = task_payload
    payload: dict[str, Any] = {
        "instructions": [
            "Return exactly one JSON object in the message content.",
            "The object must validate against json_schema.",
            "Use only the data in input.",
            "Do not include markdown, XML tags, reasoning, or prose outside JSON.",
            "For evidence arrays, copy full evidence objects from input evidence.",
            "Recommended action must be one of: observe, paper_buy_yes, paper_buy_no, "
            "paper_buy, paper_sell, skip.",
        ],
        "json_schema": schema.model_json_schema(),
        "input": parsed_input,
    }
    if validation_error is not None:
        payload["previous_validation_error"] = validation_error
    return json.dumps(payload, sort_keys=True)


def _task_payload_from_prompt(prompt: str) -> dict[str, Any]:
    payload = json.loads(prompt)
    if (
        isinstance(payload, dict)
        and isinstance(payload.get("json_schema"), dict)
        and isinstance(payload.get("input"), dict)
    ):
        return payload["input"]
    return payload


def _parse_json_payload(raw: str) -> Any:
    candidates = _json_candidates(raw)
    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return json.loads(raw)


def _json_candidates(raw: str) -> list[str]:
    text = str(raw).strip()
    without_think = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    candidates = [text, without_think.strip()]

    fenced = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        without_think,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        candidates.append(fenced.group(1).strip())

    extracted = _extract_json_object(without_think)
    if extracted is not None:
        candidates.append(extracted)

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1].strip()


def _message_content_as_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def _evidence_quality(evidence: list[dict[str, object]]) -> float:
    if not evidence:
        return 0.0
    scores = [
        float(item["relevance_score"]) * float(item["credibility_score"]) for item in evidence
    ]
    return round(sum(scores) / len(scores), 4)


def _confidence(evidence_quality: float, count: int) -> float:
    confidence = 0.35 + 0.60 * evidence_quality
    if count < 2:
        confidence -= 0.15
    return round(min(0.95, max(0.05, confidence)), 4)


def _estimated_probability(
    evidence: list[dict[str, object]], market_probability: float | None
) -> float | None:
    hints: list[tuple[float, float]] = []
    for item in evidence:
        metadata = item.get("metadata", {})
        if isinstance(metadata, dict) and "probability_hint" in metadata:
            weight = float(item["relevance_score"]) * float(item["credibility_score"])
            hints.append((float(metadata["probability_hint"]), weight))
    if not hints:
        return market_probability
    total_weight = sum(weight for _probability, weight in hints)
    if total_weight <= 0:
        return market_probability
    probability = sum(probability * weight for probability, weight in hints) / total_weight
    return round(min(0.99, max(0.01, probability)), 4)
