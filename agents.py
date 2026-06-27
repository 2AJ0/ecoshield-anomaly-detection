"""EcoShield CrewAI prototype for underwriting veracity checks.

This script defines:
1) Regulatory Auditor Agent
2) Anomaly Detection Agent

The crew evaluates a sample land/financial application JSON and returns a
final Veracity Score and Risk Summary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from crewai import Agent, Crew, Process, Task


# Mock LLM settings so local setup is simple. Update values as needed.
MOCK_LLM_CONFIG = {
    "model": "gpt-4o-mini",
    "api_key": "sk-mock-local-key",
    "base_url": "https://api.openai.com/v1",
}


@dataclass
class AnalysisResult:
    """Normalized final output from EcoShield checks."""

    veracity_score: int
    risk_summary: str
    regulatory_findings: str
    anomaly_findings: str


def get_sample_application() -> Dict[str, Any]:
    """Return a mock underwriting payload (land + financial)."""
    return {
        "application_id": "APP-2026-0042",
        "applicant": {
            "name": "GreenField Agro Pvt Ltd",
            "tax_id": "TAX-998712",
            "declared_annual_income": 185000,
        },
        "land_deed": {
            "parcel_id": "PCL-77A",
            "owner_name": "GreenField Agro Pvt Ltd",
            "registry_owner_name": "GreenField Agriculture Private Limited",
            "zoning": "agricultural",
            "requested_use": "commercial warehousing",
            "deed_document_hash": "hash_abc123",
            "registry_document_hash": "hash_abc123",
        },
        "financials": {
            "declared_assets": 450000,
            "declared_liabilities": 390000,
            "bank_statement_total": 51000,
            "loan_requested": 300000,
        },
        "documents": [
            {"type": "deed", "verified": True},
            {"type": "tax_certificate", "verified": False},
        ],
    }


def build_agents(llm_config: Dict[str, str]) -> tuple[Agent, Agent]:
    """Create CrewAI agents for compliance and fraud checks."""
    llm = {
        "model": llm_config["model"],
        "api_key": llm_config["api_key"],
        "base_url": llm_config["base_url"],
    }

    regulatory_auditor = Agent(
        role="Regulatory Auditor Agent",
        goal="Check land and financial applications for compliance violations.",
        backstory=(
            "You are a strict underwriting compliance specialist focused on "
            "zoning, ownership consistency, and financial eligibility rules."
        ),
        llm=llm,
        verbose=True,
    )

    anomaly_detector = Agent(
        role="Anomaly Detection Agent",
        goal="Detect structural fraud signals and suspicious inconsistencies.",
        backstory=(
            "You are an investigator that detects fabricated documents, "
            "identity inconsistencies, and risk amplification patterns."
        ),
        llm=llm,
        verbose=True,
    )

    return regulatory_auditor, anomaly_detector


def build_tasks(
    payload: Dict[str, Any], regulatory_agent: Agent, anomaly_agent: Agent
) -> tuple[Task, Task, Task]:
    """Create modular tasks for each agent and a synthesis step."""
    payload_json = json.dumps(payload, indent=2)

    compliance_task = Task(
        description=(
            "Review this underwriting JSON for compliance with land-use and "
            "financial rules. Flag violations and severity.\n\n"
            f"INPUT:\n{payload_json}\n\n"
            "Respond as JSON with keys: regulatory_findings, compliance_risk_score"
            " (0-100, where 100 is highest risk)."
        ),
        expected_output=(
            "JSON object containing regulatory_findings and compliance_risk_score."
        ),
        agent=regulatory_agent,
    )

    anomaly_task = Task(
        description=(
            "Analyze the same underwriting JSON for structural fraud patterns "
            "(ownership mismatch, fake docs, unrealistic financials).\n\n"
            f"INPUT:\n{payload_json}\n\n"
            "Respond as JSON with keys: anomaly_findings, anomaly_risk_score"
            " (0-100, where 100 is highest risk)."
        ),
        expected_output="JSON object containing anomaly_findings and anomaly_risk_score.",
        agent=anomaly_agent,
    )

    summary_task = Task(
        description=(
            "Combine prior task results into a final decision."
            " Return JSON with keys:\n"
            "- veracity_score (0-100, where 100 means highly trustworthy)\n"
            "- risk_summary (short paragraph)"
        ),
        expected_output="JSON with veracity_score and risk_summary.",
        agent=regulatory_agent,
        context=[compliance_task, anomaly_task],
    )

    return compliance_task, anomaly_task, summary_task


def run_local_fallback(payload: Dict[str, Any]) -> AnalysisResult:
    """Deterministic fallback so script still runs without remote LLM access."""
    risks = []
    risk_points = 0

    deed = payload["land_deed"]
    if deed["owner_name"].lower() != deed["registry_owner_name"].lower():
        risks.append("Ownership name mismatch between deed and registry.")
        risk_points += 30

    if deed["requested_use"].lower() != deed["zoning"].lower():
        risks.append("Requested use does not match zoning classification.")
        risk_points += 20

    if any(not doc["verified"] for doc in payload["documents"]):
        risks.append("One or more supporting documents are unverified.")
        risk_points += 25

    financials = payload["financials"]
    if financials["loan_requested"] > (financials["declared_assets"] - financials["declared_liabilities"]):
        risks.append("Requested loan exceeds declared net asset position.")
        risk_points += 15

    risk_points = min(risk_points, 100)
    veracity_score = max(0, 100 - risk_points)

    findings = " ".join(risks) if risks else "No major concerns found."
    summary = (
        f"Overall risk is {'high' if risk_points >= 60 else 'moderate' if risk_points >= 30 else 'low'}; "
        f"Veracity Score: {veracity_score}/100."
    )

    return AnalysisResult(
        veracity_score=veracity_score,
        risk_summary=summary,
        regulatory_findings=findings,
        anomaly_findings=findings,
    )


def run_ecoshield_analysis(payload: Dict[str, Any], llm_config: Dict[str, str]) -> AnalysisResult:
    """Run CrewAI workflow and return normalized result."""
    regulatory_agent, anomaly_agent = build_agents(llm_config)
    compliance_task, anomaly_task, summary_task = build_tasks(
        payload, regulatory_agent, anomaly_agent
    )

    crew = Crew(
        agents=[regulatory_agent, anomaly_agent],
        tasks=[compliance_task, anomaly_task, summary_task],
        process=Process.sequential,
        verbose=True,
    )

    try:
        result_text = str(crew.kickoff())
        parsed = json.loads(result_text)

        return AnalysisResult(
            veracity_score=int(parsed.get("veracity_score", 50)),
            risk_summary=str(parsed.get("risk_summary", "Risk summary unavailable.")),
            regulatory_findings="See compliance task output in crew logs.",
            anomaly_findings="See anomaly task output in crew logs.",
        )
    except Exception:
        # Fallback allows easy local execution even without real model credentials.
        return run_local_fallback(payload)


def main() -> None:
    sample_payload = get_sample_application()
    result = run_ecoshield_analysis(sample_payload, MOCK_LLM_CONFIG)

    print("\n=== EcoShield Underwriting Assessment ===")
    print(f"Application ID: {sample_payload['application_id']}")
    print(f"Veracity Score: {result.veracity_score}/100")
    print(f"Risk Summary: {result.risk_summary}")
    print(f"Regulatory Findings: {result.regulatory_findings}")
    print(f"Anomaly Findings: {result.anomaly_findings}")


if __name__ == "__main__":
    main()
