"""Discipline Score: a transparent weighted average of five behavior components, 0 to 100."""

from __future__ import annotations

from typing import Any, Final

FORMULA: Final = (
    "Discipline = 0.30 x plan adherence + 0.25 x risk consistency + 0.20 x post-loss behavior "
    "+ 0.15 x overtrading control + 0.10 x stop usage. Each component is 0 to 100. A component "
    "with no data is left out and the other weights are rescaled. The count of components "
    "used is reported with the score."
)
WEIGHTS: Final[dict[str, float]] = {
    "plan_adherence": 0.30,
    "risk_consistency": 0.25,
    "post_loss_behavior": 0.20,
    "overtrading_control": 0.15,
    "stop_usage": 0.10,
}


def discipline_score(
    behavior: dict[str, Any],
    risk_cv: float | None,
    stop_usage_rate: float | None,
) -> dict[str, Any]:
    """Combine the components. Missing data lowers the component count, not the score."""
    components: dict[str, float | None] = {
        "plan_adherence": None,
        "risk_consistency": None,
        "post_loss_behavior": None,
        "overtrading_control": None,
        "stop_usage": None,
    }
    plan = behavior.get("plan", {})
    if plan.get("adherence_rate") is not None:
        components["plan_adherence"] = 100.0 * float(plan["adherence_rate"])
    if risk_cv is not None:
        components["risk_consistency"] = 100.0 * max(0.0, 1.0 - min(risk_cv, 1.0))
    revenge = behavior.get("revenge", {})
    if revenge.get("rate_after_loss") is not None:
        components["post_loss_behavior"] = 100.0 * (1.0 - float(revenge["rate_after_loss"]))
    overtrading = behavior.get("overtrading", {})
    if overtrading.get("days"):
        share = overtrading["overtraded_days"] / overtrading["days"]
        components["overtrading_control"] = 100.0 * (1.0 - share)
    if stop_usage_rate is not None:
        components["stop_usage"] = 100.0 * stop_usage_rate

    available = {name: value for name, value in components.items() if value is not None}
    total_weight = sum(WEIGHTS[name] for name in available)
    score = (
        sum(WEIGHTS[name] * value for name, value in available.items()) / total_weight
        if total_weight > 0
        else None
    )
    return {
        "score": score,
        "components_used": len(available),
        "components_total": len(WEIGHTS),
        "components": components,
        "weights": dict(WEIGHTS),
        "formula": FORMULA,
    }
