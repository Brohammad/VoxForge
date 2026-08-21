from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.core.domain.alerts import AlertItem, AlertSummary, AlertThresholds
from voxforge.infrastructure.db.dashboard_repository import DashboardRepository
from voxforge.infrastructure.db.models import SupportTemplateModel
from voxforge.infrastructure.observability.metrics import regression_alerts_total


class AlertService:
    def __init__(self, db: AsyncSession, repository: DashboardRepository) -> None:
        self._db = db
        self._repository = repository

    async def get_alerts(self, org_id: UUID, *, days: int = 7) -> AlertSummary:
        thresholds = await self._resolve_thresholds(org_id)
        outcomes = await self._repository.get_outcome_summary(org_id, days=days)
        evals = await self._repository.get_evaluation_summary(org_id)
        latency = await self._repository.get_latency_stats(org_id)

        alerts: list[AlertItem] = []
        alerts.extend(self._outcome_alerts(outcomes, thresholds))
        alerts.extend(self._evaluation_alerts(evals, thresholds))
        alerts.extend(self._latency_alerts(latency, thresholds))

        for alert in alerts:
            regression_alerts_total.labels(code=alert.code, severity=alert.severity).inc()

        return AlertSummary(
            active_count=len(alerts),
            critical_count=sum(1 for alert in alerts if alert.severity == "critical"),
            warning_count=sum(1 for alert in alerts if alert.severity == "warning"),
            thresholds=thresholds,
            alerts=alerts,
        )

    def _outcome_alerts(self, outcomes, thresholds: AlertThresholds) -> list[AlertItem]:
        if outcomes.total_sessions <= 0:
            return []
        alerts: list[AlertItem] = []
        if outcomes.task_success_rate < thresholds.task_success_min:
            severe = outcomes.task_success_rate < thresholds.task_success_min * 0.85
            alerts.append(
                self._alert(
                    code="task_success_regression",
                    severity="critical" if severe else "warning",
                    metric="task_success_rate",
                    observed=outcomes.task_success_rate,
                    threshold=thresholds.task_success_min,
                    message=(
                        "Task success rate fell below template threshold "
                        f"({outcomes.task_success_rate:.0%} < "
                        f"{thresholds.task_success_min:.0%})."
                    ),
                )
            )
        if outcomes.escalation_rate > thresholds.escalation_max:
            alerts.append(
                self._alert(
                    code="escalation_spike",
                    severity="warning",
                    metric="escalation_rate",
                    observed=outcomes.escalation_rate,
                    threshold=thresholds.escalation_max,
                    message=(
                        "Escalation rate exceeded threshold "
                        f"({outcomes.escalation_rate:.0%} > "
                        f"{thresholds.escalation_max:.0%})."
                    ),
                )
            )
        return alerts

    def _evaluation_alerts(self, evals, thresholds: AlertThresholds) -> list[AlertItem]:
        if evals.total_runs <= 0:
            return []
        alerts: list[AlertItem] = []
        avg_score = float(evals.avg_score or 0.0)
        if avg_score < thresholds.quality_min:
            severe = avg_score < thresholds.quality_min * 0.85
            alerts.append(
                self._alert(
                    code="quality_regression",
                    severity="critical" if severe else "warning",
                    metric="avg_evaluation_score",
                    observed=avg_score,
                    threshold=thresholds.quality_min,
                    message=(
                        "Average evaluation score dropped below quality floor "
                        f"({avg_score:.2f} < {thresholds.quality_min:.2f})."
                    ),
                )
            )
        failed_rate = evals.failed / evals.total_runs
        if failed_rate > thresholds.failed_evaluation_max_rate:
            alerts.append(
                self._alert(
                    code="failed_evaluation_rate",
                    severity="warning",
                    metric="failed_evaluation_rate",
                    observed=failed_rate,
                    threshold=thresholds.failed_evaluation_max_rate,
                    message=(
                        "Failed evaluation rate is elevated "
                        f"({failed_rate:.0%} > "
                        f"{thresholds.failed_evaluation_max_rate:.0%})."
                    ),
                )
            )
        return alerts

    def _latency_alerts(self, latency, thresholds: AlertThresholds) -> list[AlertItem]:
        e2e = next((bucket for bucket in latency if bucket.metric_name == "e2e_ms"), None)
        if e2e is None or e2e.avg_ms <= thresholds.e2e_latency_max_ms:
            return []
        severe = e2e.avg_ms > thresholds.e2e_latency_max_ms * 1.5
        return [
            self._alert(
                code="latency_regression",
                severity="critical" if severe else "warning",
                metric="avg_e2e_latency_ms",
                observed=e2e.avg_ms,
                threshold=thresholds.e2e_latency_max_ms,
                message=(
                    "Average E2E latency exceeds target "
                    f"({e2e.avg_ms:.0f}ms > {thresholds.e2e_latency_max_ms:.0f}ms)."
                ),
            )
        ]

    async def _resolve_thresholds(self, org_id: UUID) -> AlertThresholds:
        from voxforge.infrastructure.db.agent_config_repository import AgentConfigRepository

        active = await AgentConfigRepository(self._db).get_active(org_id)
        if active is not None and active.eval_thresholds:
            raw = active.eval_thresholds
        else:
            result = await self._db.execute(
                select(SupportTemplateModel)
                .where(SupportTemplateModel.is_default.is_(True))
                .order_by(SupportTemplateModel.created_at.asc())
                .limit(1)
            )
            template = result.scalar_one_or_none()
            raw = (template.eval_thresholds if template is not None else {}) or {}
        return AlertThresholds(
            task_success_min=float(raw.get("task_success_min", 0.8)),
            escalation_max=float(raw.get("escalation_max", 0.35)),
            quality_min=float(raw.get("quality_min", 0.75)),
            e2e_latency_max_ms=float(raw.get("e2e_latency_max_ms", 2000.0)),
            failed_evaluation_max_rate=float(raw.get("failed_evaluation_max_rate", 0.2)),
        )

    @staticmethod
    def _alert(
        *,
        code: str,
        severity: str,
        metric: str,
        observed: float,
        threshold: float,
        message: str,
    ) -> AlertItem:
        return AlertItem(
            code=code,
            severity=severity,
            metric=metric,
            observed=round(observed, 4),
            threshold=round(threshold, 4),
            message=message,
        )
