"""Diary-aware LifeHub recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from lifehub.scoring import ReadinessScore


@dataclass(frozen=True)
class RecommendationEvent:
    recommendation_type: str
    activity: str
    location_id: str
    score: int
    decision: str
    reasons: str
    generated_at: str


def build_recommendations(
    scores: list[ReadinessScore],
    week_summary: dict | None = None,
    feedback_profile: dict[str, dict] | None = None,
    preferences: dict | None = None,
    recovery_summary: dict | None = None,
) -> list[RecommendationEvent]:
    if not scores:
        return []
    summary = week_summary or {}
    best_by_activity: dict[str, ReadinessScore] = {}
    for score in scores:
        current = best_by_activity.get(score.activity)
        if current is None or score.score > current.score:
            best_by_activity[score.activity] = score

    fatigue = float(summary.get("avg_fatigue") or 0)
    mood = float(summary.get("avg_mood") or 0)
    pain_sessions = int(summary.get("pain_sessions") or 0)
    sessions = int(summary.get("sessions") or 0)
    feedback = feedback_profile or {}
    prefs = preferences or {}
    weekly_counts = weekly_activity_counts(summary)
    weekly_goals = {str(key): int(value) for key, value in (prefs.get("weekly_goals") or {}).items()}
    priorities = {str(key): int(value) for key, value in (prefs.get("priority_activities") or {}).items()}
    policy = prefs.get("recommendation_policy") or {}
    recovery = recovery_summary or {}
    recovery_score = float(recovery.get("latest_recovery_score") or recovery.get("avg_recovery_score") or 0)
    sleep_minutes = float(recovery.get("latest_duration_minutes") or recovery.get("avg_duration_minutes") or 0)
    under_target_boost = int(policy.get("under_target_boost") or 7)
    high_priority_boost = int(policy.get("high_priority_boost") or 3)
    max_goal_boost = int(policy.get("max_goal_boost") or 10)
    generated_at = datetime.now(timezone.utc).isoformat()

    recommendations = []
    for score in best_by_activity.values():
        adjusted_score = score.score
        reasons = [score.explanation]
        decision = score.decision

        if fatigue >= 7:
            adjusted_score -= 20
            reasons.append("recent fatigue is high")
        if pain_sessions > 0:
            adjusted_score -= 15
            reasons.append("pain was logged this week")
        if mood and mood <= 4:
            adjusted_score -= 10
            reasons.append("recent mood is low")
        if sessions == 0 and score.activity in {"walk", "volleyball"}:
            adjusted_score += 5
            reasons.append("no sessions logged this week")
        if sessions >= 5 and score.activity in {"skate", "snowboard", "moto_lesson"}:
            adjusted_score -= 10
            reasons.append("weekly load is already high")
        if recovery_score and recovery_score < 65 and score.activity in {"skate", "snowboard", "moto_lesson", "volleyball"}:
            adjusted_score -= 15
            reasons.append(f"sleep recovery is low ({recovery_score:.0f}/100)")
        if sleep_minutes and sleep_minutes < 390 and score.activity in {"skate", "snowboard", "moto_lesson"}:
            adjusted_score -= 10
            reasons.append("sleep duration was short")
        if recovery_score >= 75 and score.activity in {"walk", "gym"}:
            adjusted_score += 3
            reasons.append("recovery is stable")

        goal = weekly_goals.get(score.activity, 0)
        done = weekly_counts.get(score.activity, 0)
        if goal > 0 and done < goal:
            gap = goal - done
            boost = min(max_goal_boost, under_target_boost + max(0, gap - 1) * 2)
            adjusted_score += boost
            reasons.append(f"weekly goal gap {done}/{goal}")
        if priorities.get(score.activity, 0) >= 8 and score.activity in weekly_goals:
            adjusted_score += high_priority_boost
            reasons.append("high priority activity")

        profile = feedback.get(score.activity, {})
        feedback_events = int(profile.get("feedback_events") or 0)
        follow_rate = float(profile.get("follow_rate") or 0)
        good_results = int(profile.get("good_results") or 0)
        bad_results = int(profile.get("bad_results") or 0)
        skipped_events = int(profile.get("skipped_events") or 0)
        if feedback_events >= 2 and follow_rate >= 0.7:
            adjusted_score += 8
            reasons.append("recent feedback says this is usually followed")
        if good_results >= 2 and good_results > bad_results:
            adjusted_score += 5
            reasons.append("recent outcomes were good")
        if feedback_events >= 2 and follow_rate <= 0.35:
            adjusted_score -= 8
            reasons.append("recent feedback says this is often skipped")
        if bad_results >= 1 and bad_results >= good_results:
            adjusted_score -= 7
            reasons.append("recent outcomes were weak")
        if skipped_events >= 2 and score.decision == "go":
            adjusted_score -= 5
            reasons.append("go recommendation was often ignored")

        bounded = max(0, min(100, adjusted_score))
        if pain_sessions > 0 or fatigue >= 8 or (recovery_score and recovery_score < 55):
            decision = "recover" if bounded < 75 else "caution"
        elif recovery_score and recovery_score < 65 and score.activity in {"skate", "snowboard", "moto_lesson", "volleyball"}:
            decision = "caution" if bounded >= 50 else "recover"
        elif bounded >= 75:
            decision = "go"
        elif bounded >= 50:
            decision = "caution"
        else:
            decision = "recover"

        recommendations.append(
            RecommendationEvent(
                recommendation_type="daily",
                activity=score.activity,
                location_id=score.location_id,
                score=bounded,
                decision=decision,
                reasons=", ".join(dict.fromkeys(reason for reason in reasons if reason)),
                generated_at=generated_at,
            )
        )
    return sorted(recommendations, key=lambda item: item.score, reverse=True)


def weekly_activity_counts(week_summary: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in week_summary.get("by_activity") or []:
        activity = row.get("activity_type") or row.get("activity")
        if activity:
            counts[str(activity)] = int(row.get("sessions") or 0)
    return counts


def goal_progress_rows(week_summary: dict, preferences: dict | None = None) -> list[dict[str, int | str | float]]:
    prefs = preferences or {}
    weekly_goals = {str(key): int(value) for key, value in (prefs.get("weekly_goals") or {}).items()}
    weekly_counts = weekly_activity_counts(week_summary)
    rows = []
    for activity, target in weekly_goals.items():
        done = weekly_counts.get(activity, 0)
        rows.append(
            {
                "activity": activity,
                "done": done,
                "target": target,
                "progress": min(1.0, done / target) if target else 0.0,
            }
        )
    return rows


def render_goal_summary(week_summary: dict, preferences: dict | None = None) -> str:
    rows = goal_progress_rows(week_summary, preferences)
    if not rows:
        return "LifeHub goals: no weekly goals configured."
    lines = ["LifeHub goals this week:"]
    for row in rows:
        done = int(row["done"])
        target = int(row["target"])
        status = "covered" if done >= target else "open"
        lines.append(f"- {row['activity']}: {done}/{target} ({status})")
    gaps = [row for row in rows if int(row["done"]) < int(row["target"])]
    if gaps:
        lines.append("Next: pick one open goal when readiness and recovery allow it.")
    else:
        lines.append("Next: weekly targets are covered; protect recovery.")
    return "\n".join(lines)


def render_personal_digest(recommendations: list[RecommendationEvent]) -> str:
    if not recommendations:
        return "LifeHub today: no recommendation data available yet."
    best = recommendations[0]
    lines = [
        f"LifeHub today: {best.activity} ({best.score}/100, {best.decision}).",
        "",
        "Why:",
        f"- {best.reasons}",
        "",
        "Options:",
    ]
    for item in recommendations[:5]:
        lines.append(f"- {item.activity}: {item.score}/100, {item.decision} — {item.reasons}")
    lines.append("")
    lines.append("Log after session: /log activity intensity mood fatigue result notes")
    return "\n".join(lines)


def render_coach_summary(
    week_summary: dict,
    recommendations: list[RecommendationEvent],
    preferences: dict | None = None,
) -> str:
    sessions = int(week_summary.get("sessions") or 0)
    if sessions == 0:
        return "LifeHub coach: no sessions logged this week. Start with one easy /log after activity."

    fatigue = float(week_summary.get("avg_fatigue") or 0)
    mood = float(week_summary.get("avg_mood") or 0)
    pain_sessions = int(week_summary.get("pain_sessions") or 0)
    best = recommendations[0] if recommendations else None
    prefs = preferences or {}

    lines = [
        f"LifeHub coach: {sessions} sessions this week.",
        f"Load signal: fatigue {fatigue}/10, mood {mood}/10, pain sessions {pain_sessions}.",
    ]
    if pain_sessions:
        lines.append("Focus: recovery or low-impact movement until pain clears.")
    elif fatigue >= 7:
        lines.append("Focus: reduce intensity today; keep consistency without chasing max effort.")
    elif sessions < 3:
        lines.append("Focus: add one light session or walk to keep the week alive.")
    else:
        lines.append("Focus: maintain rhythm; avoid stacking hard sessions back-to-back.")
    if best:
        lines.append(f"Today: {best.activity} is the best fit ({best.score}/100, {best.decision}).")
    progress_rows = goal_progress_rows(week_summary, prefs)
    if progress_rows:
        gaps = [f"{row['activity']} {row['done']}/{row['target']}" for row in progress_rows if int(row["done"]) < int(row["target"])]
        if gaps:
            lines.append(f"Goal gaps: {', '.join(gaps[:5])}.")
        else:
            lines.append("Goal gaps: weekly targets are covered.")
    return "\n".join(lines)


def render_weekly_intelligence_report(
    week_summary: dict,
    recommendations: list[RecommendationEvent],
    feedback_profile: dict[str, dict] | None = None,
    preferences: dict | None = None,
    signals: list | None = None,
) -> str:
    sessions = int(week_summary.get("sessions") or 0)
    fatigue = float(week_summary.get("avg_fatigue") or 0)
    mood = float(week_summary.get("avg_mood") or 0)
    pain_sessions = int(week_summary.get("pain_sessions") or 0)
    progress_rows = goal_progress_rows(week_summary, preferences)
    feedback = feedback_profile or {}
    context_signals = signals or []

    lines = [
        "LifeHub weekly review",
        f"Sessions: {sessions}; mood {mood}/10; fatigue {fatigue}/10; pain sessions {pain_sessions}.",
    ]

    if week_summary.get("by_activity"):
        activity_line = ", ".join(
            f"{row['activity_type']} {row['sessions']}" for row in week_summary["by_activity"][:6]
        )
        lines.append(f"Activity mix: {activity_line}.")
    else:
        lines.append("Activity mix: no logged sessions yet.")

    if week_summary.get("by_result"):
        result_line = ", ".join(f"{row['result']} {row['sessions']}" for row in week_summary["by_result"][:4])
        lines.append(f"Outcomes: {result_line}.")

    if progress_rows:
        open_goals = [row for row in progress_rows if int(row["done"]) < int(row["target"])]
        covered_goals = [row for row in progress_rows if int(row["done"]) >= int(row["target"])]
        if open_goals:
            lines.append(
                "Open goals: "
                + ", ".join(f"{row['activity']} {row['done']}/{row['target']}" for row in open_goals[:5])
                + "."
            )
        if covered_goals:
            lines.append(
                "Covered goals: "
                + ", ".join(f"{row['activity']} {row['done']}/{row['target']}" for row in covered_goals[:5])
                + "."
            )

    if feedback:
        learned = sorted(
            feedback.items(),
            key=lambda item: (
                float(item[1].get("follow_rate") or 0),
                int(item[1].get("good_results") or 0),
                int(item[1].get("feedback_events") or 0),
            ),
            reverse=True,
        )
        top_activity, top_profile = learned[0]
        lines.append(
            "Learning: "
            f"{top_activity} has follow rate {float(top_profile.get('follow_rate') or 0):.2f} "
            f"across {int(top_profile.get('feedback_events') or 0)} feedback events."
        )
    else:
        lines.append("Learning: no recommendation feedback yet; use Done/Skip after /today.")

    high_urgency = [
        signal
        for signal in context_signals
        if int(getattr(signal, "urgency", 0) or 0) >= 7
    ]
    if high_urgency:
        titles = ", ".join(getattr(signal, "title", "context signal") for signal in high_urgency[:3])
        lines.append(f"Context watch: {titles}.")

    best = recommendations[0] if recommendations else None
    if pain_sessions:
        next_focus = "Next week: keep sport, but bias toward recovery until pain clears."
    elif fatigue >= 7:
        next_focus = "Next week: reduce intensity and protect sleep/recovery before adding load."
    elif progress_rows and any(int(row["done"]) < int(row["target"]) for row in progress_rows):
        next_focus = "Next week: choose the highest-readiness open goal first."
    elif sessions == 0:
        next_focus = "Next week: start with one easy logged session to create a baseline."
    else:
        next_focus = "Next week: maintain rhythm and use feedback to refine recommendations."
    lines.append(next_focus)
    if best:
        lines.append(f"Best next action now: {best.activity} ({best.score}/100, {best.decision}).")
    return "\n".join(lines)


def render_progress_scorecard(
    week_summary: dict,
    decision_metrics: dict | None = None,
    feedback_profile: dict[str, dict] | None = None,
    preferences: dict | None = None,
) -> str:
    sessions = int(week_summary.get("sessions") or 0)
    metrics = decision_metrics or {}
    useful_days = int(metrics.get("useful_decision_days") or 0)
    followed_events = int(metrics.get("followed_events") or 0)
    skipped_events = int(metrics.get("skipped_events") or 0)
    total_feedback = followed_events + skipped_events
    follow_rate = float(metrics.get("follow_rate") or (followed_events / total_feedback if total_feedback else 0))
    goal_rows = goal_progress_rows(week_summary, preferences)
    covered_goals = sum(1 for row in goal_rows if int(row["done"]) >= int(row["target"]))
    open_goals = [row for row in goal_rows if int(row["done"]) < int(row["target"])]
    feedback = feedback_profile or {}

    if useful_days >= 4 and follow_rate >= 0.6:
        status = "compounding"
    elif useful_days >= 2 or sessions >= 3:
        status = "building"
    else:
        status = "thin data"

    lines = [
        f"LifeHub metrics: {status}.",
        f"North Star: useful decision days {useful_days}/7.",
        f"Logged sessions: {sessions}/week.",
        f"Feedback: {followed_events} followed, {skipped_events} skipped, follow rate {follow_rate:.0%}.",
        f"Weekly goals covered: {covered_goals}/{len(goal_rows)}.",
    ]
    if open_goals:
        lines.append(
            "Open goal gaps: "
            + ", ".join(f"{row['activity']} {row['done']}/{row['target']}" for row in open_goals[:5])
            + "."
        )
    if feedback:
        best_activity, best_profile = sorted(
            feedback.items(),
            key=lambda item: (
                float(item[1].get("follow_rate") or 0),
                int(item[1].get("feedback_events") or 0),
            ),
            reverse=True,
        )[0]
        lines.append(
            f"Best learned activity: {best_activity} "
            f"({float(best_profile.get('follow_rate') or 0):.0%} follow rate)."
        )
    if useful_days == 0:
        lines.append("Next metric move: use /today once and tap Done/Skip after the decision.")
    elif open_goals:
        lines.append("Next metric move: close one open goal with the highest-readiness activity.")
    else:
        lines.append("Next metric move: keep feedback density high and protect recovery.")
    return "\n".join(lines)
