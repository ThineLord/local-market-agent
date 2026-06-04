from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, TypeVar

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
    current_prompt = prompt
    for _attempt in range(max_retries + 1):
        raw = provider.complete_json(current_prompt)
        try:
            payload = json.loads(raw)
            return schema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(str(exc))
            current_prompt = (
                f"{prompt}\n\nPrevious output was invalid. Return strict JSON only. "
                f"Validation error: {exc}"
            )
    raise StructuredOutputError("; ".join(errors))


class MockLLMProvider:
    """Deterministic offline provider for tests and local demos."""

    def complete_json(self, prompt: str) -> str:
        payload = json.loads(prompt)
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
    timeout_seconds: float = 30.0

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
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


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
