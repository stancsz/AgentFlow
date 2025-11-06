from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agentflow.adapters import CodexCLIAdapter, CodexCLIError


def perform_self_evaluation(
    adapter: CodexCLIAdapter,
    prompt: str,
    response: str,
) -> Optional[Dict[str, Any]]:
    """Ask the adapter to score how well the response satisfied the prompt."""
    evaluation_prompt = (
        "You are an impartial self-evaluation judge. Score how well the assistant's reply satisfies the "
        "original prompt. The score must be a float between 0.0 and 1.0 inclusive, where 1.0 represents a perfect answer.\n"
        "Respond STRICTLY with a single-line JSON object of the form "
        '{"score": <float>, "justification": "<concise reasoning>"}.\n'
        "Do not emit any extra text, markdown, or code fences. If you cannot evaluate, still return JSON with score 0.0.\n"
        "Conversation to evaluate:\n"
        "User:\n<<<\n"
        f"{prompt}\n"
        ">>>\n"
        "Assistant:\n<<<\n"
        f"{response}\n"
        ">>>\n"
    )

    try:
        evaluation_result = adapter.run(evaluation_prompt)
    except CodexCLIError as exc:
        return {"error": f"Self-evaluation failed: {exc}"}

    parsed = parse_evaluation_payload(evaluation_result.message)
    payload: Dict[str, Any] = {
        "raw_message": evaluation_result.message,
        "events": evaluation_result.events,
        "usage": evaluation_result.usage or {},
    }
    if parsed:
        payload.update(parsed)
    else:
        payload["error"] = "Self-evaluation response was not valid JSON."
    return payload


def parse_evaluation_payload(message: str) -> Optional[Dict[str, Any]]:
    """Read self-evaluation JSON from the adapter's response."""
    candidate = message.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if "\n" in candidate:
            candidate = candidate.split("\n", 1)[-1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return parse_plaintext_evaluation(message)

    score = payload.get("score")
    try:
        if score is not None:
            score = float(score)
    except (TypeError, ValueError):
        score = None

    justification = payload.get("justification") or payload.get("reasoning")
    if justification is not None:
        justification = str(justification).strip()

    return {"score": score, "justification": justification}


def build_evaluation_outputs(evaluation_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Transform evaluation payload fields into plan outputs."""
    outputs: Dict[str, Any] = {}
    if evaluation_payload.get("score") is not None:
        outputs["score"] = evaluation_payload["score"]
    if evaluation_payload.get("justification"):
        outputs["justification"] = evaluation_payload["justification"]
    if evaluation_payload.get("error"):
        outputs["error"] = evaluation_payload["error"]
    outputs["raw_message"] = evaluation_payload.get("raw_message", "")
    outputs["events"] = evaluation_payload.get("events", [])
    outputs["usage"] = evaluation_payload.get("usage", {})
    return outputs


def parse_plaintext_evaluation(message: str) -> Optional[Dict[str, Any]]:
    """
    Fall back to heuristic parsing when the adapter emits human readable text instead of JSON.
    """
    score: Optional[float] = None
    justification_parts: List[str] = []
    lines = message.splitlines()

    for index, raw_line in enumerate(lines):
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue

        normalized = stripped_line.lstrip("-*").strip()
        lower = normalized.lower()

        if lower.startswith("score"):
            numeric_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", normalized)
            if numeric_match:
                try:
                    score = float(numeric_match.group(1))
                except ValueError:
                    score = None
            continue

        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", normalized):
            try:
                score = float(normalized)
            except ValueError:
                score = None
            continue

        if lower.startswith(("reason", "justification", "rationale")):
            text = normalized.split(":", 1)[1].strip() if ":" in normalized else normalized
            if text:
                justification_parts.append(text)

            for follow in lines[index + 1 :]:
                follow_stripped = follow.strip()
                if not follow_stripped:
                    continue
                follow_normalized = follow_stripped.lstrip("-*").strip()
                follow_lower = follow_normalized.lower()
                if follow_lower.startswith(("score", "reason", "justification", "rationale")):
                    break
                justification_parts.append(follow_normalized)
            break

    if score is None:
        return None

    justification = " ".join(justification_parts).strip() or None
    return {"score": score, "justification": justification}

