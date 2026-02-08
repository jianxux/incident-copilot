"""
Evaluation Harness - Run evaluations and track results.

Usage:
    harness = EvalHarness(copilot)
    results = await harness.run_eval(incidents)
    print(harness.summary())
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog

from .rubric import ConfidenceLevel, Rubric, RubricResult
from .synthetic import SyntheticIncident, SyntheticIncidentGenerator

logger = structlog.get_logger()


@dataclass
class EvalResult:
    """Result from evaluating a single incident."""

    incident_id: str
    scenario_type: str
    difficulty: str

    # What the copilot produced
    predicted_root_cause: str
    analysis: str
    recommendations: list[str]
    confidence: ConfidenceLevel

    # Timing
    latency_ms: int
    tokens_used: int

    # Rubric score
    rubric: RubricResult

    # Raw outputs for debugging
    raw_output: str | None = None

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "scenario_type": self.scenario_type,
            "difficulty": self.difficulty,
            "predicted_root_cause": self.predicted_root_cause,
            "recommendations": self.recommendations,
            "confidence": self.confidence.value,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "rubric": self.rubric.to_dict(),
        }


@dataclass
class EvalSummary:
    """Summary of evaluation run."""

    total_incidents: int
    passed: int
    failed: int

    avg_score: float
    avg_latency_ms: float
    avg_tokens: float

    by_scenario: dict[str, dict]
    by_difficulty: dict[str, dict]

    failure_severities: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "total": self.total_incidents,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": f"{self.passed / self.total_incidents * 100:.1f}%",
            "avg_score": round(self.avg_score, 3),
            "avg_latency_ms": round(self.avg_latency_ms),
            "avg_tokens": round(self.avg_tokens),
            "by_scenario": self.by_scenario,
            "by_difficulty": self.by_difficulty,
            "failure_severities": self.failure_severities,
        }


class EvalHarness:
    """
    Evaluation harness for testing incident copilot quality.

    Runs synthetic incidents through the copilot and scores results.
    """

    def __init__(
        self,
        copilot=None,
        rubric: Rubric | None = None,
        output_dir: str = "eval_results",
    ):
        """
        Initialize harness.

        Args:
            copilot: The incident copilot to evaluate
            rubric: Evaluation rubric (default if None)
            output_dir: Directory to save results
        """
        self.copilot = copilot
        self.rubric = rubric or Rubric()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.results: list[EvalResult] = []

    async def run_eval(
        self,
        incidents: list[SyntheticIncident],
        parallel: int = 1,
    ) -> list[EvalResult]:
        """
        Run evaluation on a list of incidents.

        Args:
            incidents: Synthetic incidents to evaluate
            parallel: Number of parallel evaluations
        """
        self.results = []

        if parallel > 1:
            # Run in parallel batches
            for i in range(0, len(incidents), parallel):
                batch = incidents[i : i + parallel]
                batch_results = await asyncio.gather(
                    *[self._evaluate_incident(inc) for inc in batch]
                )
                self.results.extend(batch_results)
        else:
            # Run sequentially
            for incident in incidents:
                result = await self._evaluate_incident(incident)
                self.results.append(result)

        # Save results
        self._save_results()

        return self.results

    async def _evaluate_incident(self, incident: SyntheticIncident) -> EvalResult:
        """Evaluate a single incident."""
        import time

        start = time.time()

        logger.info(
            "evaluating_incident",
            incident_id=incident.incident_id,
            scenario=incident.scenario_type,
        )

        try:
            if self.copilot:
                # Run actual copilot
                output = await self._run_copilot(incident)
            else:
                # Mock output for testing harness itself
                output = self._mock_copilot_output(incident)

            latency_ms = int((time.time() - start) * 1000)

            # Parse copilot output
            predicted_root_cause = output.get("root_cause", "")
            analysis = output.get("analysis", "")
            recommendations = output.get("recommendations", [])
            confidence = self._parse_confidence(output.get("confidence", "medium"))
            tokens_used = output.get("tokens_used", 0)

            # Score with rubric
            rubric_result = self.rubric.evaluate(
                incident_id=incident.incident_id,
                predicted_root_cause=predicted_root_cause,
                actual_root_cause=incident.actual_root_cause,
                analysis=analysis,
                recommendations=recommendations,
                expected_evidence=incident.expected_evidence,
                valid_actions=incident.valid_actions,
                confidence=confidence,
            )

            return EvalResult(
                incident_id=incident.incident_id,
                scenario_type=incident.scenario_type,
                difficulty=incident.difficulty,
                predicted_root_cause=predicted_root_cause,
                analysis=analysis,
                recommendations=recommendations,
                confidence=confidence,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                rubric=rubric_result,
                raw_output=json.dumps(output),
            )

        except Exception as e:
            logger.error(
                "evaluation_failed",
                incident_id=incident.incident_id,
                error=str(e),
            )

            # Return failed result
            return EvalResult(
                incident_id=incident.incident_id,
                scenario_type=incident.scenario_type,
                difficulty=incident.difficulty,
                predicted_root_cause="",
                analysis=f"Evaluation failed: {e}",
                recommendations=[],
                confidence=ConfidenceLevel.LOW,
                latency_ms=int((time.time() - start) * 1000),
                tokens_used=0,
                rubric=self.rubric.evaluate(
                    incident_id=incident.incident_id,
                    predicted_root_cause="",
                    actual_root_cause=incident.actual_root_cause,
                    analysis="",
                    recommendations=[],
                    expected_evidence=incident.expected_evidence,
                    valid_actions=incident.valid_actions,
                ),
            )

    async def _run_copilot(self, incident: SyntheticIncident) -> dict:
        """Run the actual copilot on an incident."""
        # This would integrate with the real copilot
        # For now, return mock
        return self._mock_copilot_output(incident)

    def _mock_copilot_output(self, incident: SyntheticIncident) -> dict:
        """Generate mock copilot output for testing harness."""
        # Simulate a reasonably good copilot
        import random

        # Sometimes get the right answer
        if random.random() > 0.3:
            root_cause = incident.actual_root_cause
            recommendations = incident.valid_actions[:3]
            confidence = "high"
        else:
            root_cause = "Unknown issue requiring investigation"
            recommendations = ["Check logs", "Review metrics", "Escalate if needed"]
            confidence = "low"

        # Include some evidence
        evidence_found = random.sample(
            incident.expected_evidence,
            min(len(incident.expected_evidence), random.randint(1, 3)),
        )

        analysis = f"""
        Analyzed {len(incident.logs)} log lines and metrics.

        Found evidence of: {', '.join(evidence_found)}

        Root cause hypothesis: {root_cause}
        """

        return {
            "root_cause": root_cause,
            "analysis": analysis,
            "recommendations": recommendations,
            "confidence": confidence,
            "tokens_used": random.randint(1000, 3000),
        }

    def _parse_confidence(self, confidence_str: str) -> ConfidenceLevel:
        """Parse confidence string to enum."""
        confidence_str = confidence_str.lower()
        if "high" in confidence_str:
            return ConfidenceLevel.HIGH
        elif "low" in confidence_str:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.MEDIUM

    def summary(self) -> EvalSummary:
        """Generate summary of evaluation results."""
        if not self.results:
            return EvalSummary(
                total_incidents=0,
                passed=0,
                failed=0,
                avg_score=0,
                avg_latency_ms=0,
                avg_tokens=0,
                by_scenario={},
                by_difficulty={},
                failure_severities={},
            )

        passed = sum(1 for r in self.results if r.rubric.passed)
        failed = len(self.results) - passed

        avg_score = sum(r.rubric.weighted_score for r in self.results) / len(
            self.results
        )
        avg_latency = sum(r.latency_ms for r in self.results) / len(self.results)
        avg_tokens = sum(r.tokens_used for r in self.results) / len(self.results)

        # By scenario
        by_scenario = {}
        for r in self.results:
            if r.scenario_type not in by_scenario:
                by_scenario[r.scenario_type] = {
                    "count": 0,
                    "passed": 0,
                    "total_score": 0,
                }
            by_scenario[r.scenario_type]["count"] += 1
            by_scenario[r.scenario_type]["passed"] += 1 if r.rubric.passed else 0
            by_scenario[r.scenario_type]["total_score"] += r.rubric.weighted_score

        for scenario in by_scenario:
            by_scenario[scenario]["avg_score"] = (
                by_scenario[scenario]["total_score"] / by_scenario[scenario]["count"]
            )

        # By difficulty
        by_difficulty = {}
        for r in self.results:
            if r.difficulty not in by_difficulty:
                by_difficulty[r.difficulty] = {"count": 0, "passed": 0}
            by_difficulty[r.difficulty]["count"] += 1
            by_difficulty[r.difficulty]["passed"] += 1 if r.rubric.passed else 0

        # Failure severities
        from collections import Counter

        failure_severities = Counter(
            r.rubric.failure_severity.value for r in self.results
        )

        return EvalSummary(
            total_incidents=len(self.results),
            passed=passed,
            failed=failed,
            avg_score=avg_score,
            avg_latency_ms=avg_latency,
            avg_tokens=avg_tokens,
            by_scenario=by_scenario,
            by_difficulty=by_difficulty,
            failure_severities=dict(failure_severities),
        )

    def _save_results(self):
        """Save results to output directory."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Save individual results
        results_file = self.output_dir / f"results_{timestamp}.json"
        with open(results_file, "w") as f:
            json.dump([r.to_dict() for r in self.results], f, indent=2)

        # Save summary
        summary_file = self.output_dir / f"summary_{timestamp}.json"
        with open(summary_file, "w") as f:
            json.dump(self.summary().to_dict(), f, indent=2)

        logger.info(
            "eval_results_saved",
            results_file=str(results_file),
            summary_file=str(summary_file),
        )


async def run_quick_eval(copilot=None, count: int = 10):
    """Quick evaluation with synthetic incidents."""
    generator = SyntheticIncidentGenerator(seed=42)
    incidents = generator.generate_batch(count)

    harness = EvalHarness(copilot)
    await harness.run_eval(incidents)

    summary = harness.summary()

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total: {summary.total_incidents}")
    print(
        f"Passed: {summary.passed} ({summary.passed / summary.total_incidents * 100:.1f}%)"
    )
    print(f"Failed: {summary.failed}")
    print(f"Avg Score: {summary.avg_score:.3f}")
    print(f"Avg Latency: {summary.avg_latency_ms:.0f}ms")
    print(f"Avg Tokens: {summary.avg_tokens:.0f}")
    print("\nBy Scenario:")
    for scenario, data in summary.by_scenario.items():
        print(
            f"  {scenario}: {data['passed']}/{data['count']} passed, avg={data['avg_score']:.2f}"
        )
    print("\nFailure Severities:")
    for severity, count in summary.failure_severities.items():
        print(f"  {severity}: {count}")

    return summary


if __name__ == "__main__":
    asyncio.run(run_quick_eval())
