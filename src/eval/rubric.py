"""
Evaluation Rubric - Scoring dimensions for incident analysis quality.

Based on AWS DevOps Agent methodology:
- Correct root cause identification
- Valid reasoning with right evidence
- Actionable recommendations
- Failure severity when wrong
"""

from dataclasses import dataclass
from enum import Enum


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FailureSeverity(Enum):
    """How dangerous is a wrong answer?"""

    NONE = "none"  # Correct answer
    MINOR = "minor"  # Wrong but harmless misdirection
    MODERATE = "moderate"  # Wrong, wastes significant time
    MAJOR = "major"  # Wrong, could cause damage (bad rollback)
    CRITICAL = "critical"  # Wrong and confidently so


@dataclass
class RubricScore:
    """Score for a single evaluation dimension."""

    dimension: str
    score: float  # 0.0 to 1.0
    weight: float  # Weight in final score
    reasoning: str  # Why this score
    evidence: list[str]  # Supporting evidence


@dataclass
class RubricResult:
    """Complete rubric evaluation result."""

    incident_id: str

    # Individual dimension scores
    root_cause_score: RubricScore
    reasoning_score: RubricScore
    actionability_score: RubricScore
    failure_severity: FailureSeverity

    # Aggregate
    weighted_score: float
    pass_threshold: float = 0.6

    @property
    def passed(self) -> bool:
        return self.weighted_score >= self.pass_threshold

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "weighted_score": round(self.weighted_score, 3),
            "passed": self.passed,
            "failure_severity": self.failure_severity.value,
            "dimensions": {
                "root_cause": {
                    "score": self.root_cause_score.score,
                    "reasoning": self.root_cause_score.reasoning,
                },
                "reasoning": {
                    "score": self.reasoning_score.score,
                    "reasoning": self.reasoning_score.reasoning,
                },
                "actionability": {
                    "score": self.actionability_score.score,
                    "reasoning": self.actionability_score.reasoning,
                },
            },
        }


class Rubric:
    """
    Evaluation rubric for incident analysis quality.

    Dimensions:
    1. Root Cause (40%): Did it identify the correct root cause?
    2. Reasoning (25%): Did it use correct evidence and logic?
    3. Actionability (20%): Are the recommendations useful?
    4. Failure Severity (15%): If wrong, how dangerous?
    """

    WEIGHTS = {
        "root_cause": 0.40,
        "reasoning": 0.25,
        "actionability": 0.20,
        "failure_severity": 0.15,
    }

    def __init__(self, llm_judge=None):
        """
        Initialize rubric.

        Args:
            llm_judge: Optional LLM client for automated scoring
        """
        self.llm_judge = llm_judge

    def score_root_cause(
        self,
        predicted: str,
        actual: str,
        partial_credit: bool = True,
    ) -> RubricScore:
        """
        Score root cause identification.

        Args:
            predicted: The copilot's root cause hypothesis
            actual: The ground truth root cause
            partial_credit: Allow partial scores for close answers
        """
        # Normalize for comparison
        predicted_lower = predicted.lower().strip()
        actual_lower = actual.lower().strip()

        # Exact match
        if actual_lower in predicted_lower or predicted_lower in actual_lower:
            return RubricScore(
                dimension="root_cause",
                score=1.0,
                weight=self.WEIGHTS["root_cause"],
                reasoning="Root cause correctly identified",
                evidence=[predicted],
            )

        # Keyword overlap for partial credit
        if partial_credit:
            actual_words = set(actual_lower.split())
            predicted_words = set(predicted_lower.split())
            overlap = len(actual_words & predicted_words)

            if overlap >= 2:
                score = min(0.7, overlap * 0.2)
                return RubricScore(
                    dimension="root_cause",
                    score=score,
                    weight=self.WEIGHTS["root_cause"],
                    reasoning=f"Partial match: {overlap} keywords overlap",
                    evidence=[predicted],
                )

        return RubricScore(
            dimension="root_cause",
            score=0.0,
            weight=self.WEIGHTS["root_cause"],
            reasoning="Root cause not identified correctly",
            evidence=[predicted],
        )

    def score_reasoning(
        self,
        analysis: str,
        expected_evidence: list[str],
    ) -> RubricScore:
        """
        Score reasoning quality - did it use correct evidence?

        Args:
            analysis: The copilot's full analysis
            expected_evidence: Evidence that should be referenced
        """
        analysis_lower = analysis.lower()
        found_evidence = []

        for evidence in expected_evidence:
            if evidence.lower() in analysis_lower:
                found_evidence.append(evidence)

        if not expected_evidence:
            return RubricScore(
                dimension="reasoning",
                score=0.5,
                weight=self.WEIGHTS["reasoning"],
                reasoning="No expected evidence to check",
                evidence=[],
            )

        score = len(found_evidence) / len(expected_evidence)

        return RubricScore(
            dimension="reasoning",
            score=score,
            weight=self.WEIGHTS["reasoning"],
            reasoning=f"Referenced {len(found_evidence)}/{len(expected_evidence)} expected evidence",
            evidence=found_evidence,
        )

    def score_actionability(
        self,
        recommendations: list[str],
        valid_actions: list[str],
    ) -> RubricScore:
        """
        Score actionability of recommendations.

        Args:
            recommendations: The copilot's recommended actions
            valid_actions: Actions that would actually help
        """
        if not recommendations:
            return RubricScore(
                dimension="actionability",
                score=0.0,
                weight=self.WEIGHTS["actionability"],
                reasoning="No recommendations provided",
                evidence=[],
            )

        # Check if recommendations include valid actions
        matched = []
        recommendations_text = " ".join(recommendations).lower()

        for action in valid_actions:
            if action.lower() in recommendations_text:
                matched.append(action)

        if not valid_actions:
            # No ground truth, give benefit of doubt if recommendations exist
            return RubricScore(
                dimension="actionability",
                score=0.5,
                weight=self.WEIGHTS["actionability"],
                reasoning="Recommendations provided, no ground truth to validate",
                evidence=recommendations,
            )

        score = len(matched) / len(valid_actions)

        return RubricScore(
            dimension="actionability",
            score=score,
            weight=self.WEIGHTS["actionability"],
            reasoning=f"Matched {len(matched)}/{len(valid_actions)} valid actions",
            evidence=matched,
        )

    def assess_failure_severity(
        self,
        predicted_root_cause: str,
        actual_root_cause: str,
        recommendations: list[str],
        confidence: ConfidenceLevel,
    ) -> FailureSeverity:
        """
        Assess how dangerous a wrong answer is.

        High confidence + wrong + dangerous action = CRITICAL
        Low confidence + wrong = MINOR
        """
        # If correct, no failure (check both directions for substring match)
        predicted_lower = predicted_root_cause.lower()
        actual_lower = actual_root_cause.lower()
        if actual_lower in predicted_lower or predicted_lower in actual_lower:
            return FailureSeverity.NONE

        # Check for dangerous recommendations
        dangerous_keywords = [
            "rollback",
            "restart",
            "delete",
            "scale down",
            "terminate",
        ]
        has_dangerous_action = any(
            kw in " ".join(recommendations).lower() for kw in dangerous_keywords
        )

        if confidence == ConfidenceLevel.HIGH and has_dangerous_action:
            return FailureSeverity.CRITICAL
        elif confidence == ConfidenceLevel.HIGH:
            return FailureSeverity.MAJOR
        elif has_dangerous_action:
            return FailureSeverity.MODERATE
        else:
            return FailureSeverity.MINOR

    def evaluate(
        self,
        incident_id: str,
        predicted_root_cause: str,
        actual_root_cause: str,
        analysis: str,
        recommendations: list[str],
        expected_evidence: list[str],
        valid_actions: list[str],
        confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    ) -> RubricResult:
        """
        Run full rubric evaluation.

        Returns RubricResult with all dimension scores.
        """
        root_cause_score = self.score_root_cause(
            predicted_root_cause, actual_root_cause
        )
        reasoning_score = self.score_reasoning(analysis, expected_evidence)
        actionability_score = self.score_actionability(recommendations, valid_actions)
        failure_severity = self.assess_failure_severity(
            predicted_root_cause, actual_root_cause, recommendations, confidence
        )

        # Calculate weighted score
        # Failure severity reduces score if wrong
        severity_penalty = {
            FailureSeverity.NONE: 0.0,
            FailureSeverity.MINOR: 0.05,
            FailureSeverity.MODERATE: 0.10,
            FailureSeverity.MAJOR: 0.20,
            FailureSeverity.CRITICAL: 0.35,
        }

        weighted_score = (
            root_cause_score.score * root_cause_score.weight
            + reasoning_score.score * reasoning_score.weight
            + actionability_score.score * actionability_score.weight
        )
        weighted_score -= severity_penalty[failure_severity]
        weighted_score = max(0.0, min(1.0, weighted_score))

        return RubricResult(
            incident_id=incident_id,
            root_cause_score=root_cause_score,
            reasoning_score=reasoning_score,
            actionability_score=actionability_score,
            failure_severity=failure_severity,
            weighted_score=weighted_score,
        )
