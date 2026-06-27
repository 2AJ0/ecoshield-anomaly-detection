
from __future__ import annotations

import re
from typing import Any, Dict, List, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agents import MOCK_LLM_CONFIG, run_ecoshield_analysis

try:
    from pydantic import RootModel

    class UnderwritingRequest(RootModel[Dict[str, Any]]):
        """Raw underwriting payload body."""

    def _request_payload(request: UnderwritingRequest) -> Dict[str, Any]:
        return request.root

except ImportError:

    class UnderwritingRequest(BaseModel):
        """Raw underwriting payload body."""

        __root__: Dict[str, Any]

    def _request_payload(request: UnderwritingRequest) -> Dict[str, Any]:
        return request.__root__


class UnderwritingResponse(BaseModel):
    veracity_score: int = Field(ge=0, le=100)
    status: Literal["Approved", "Flagged", "Rejected"]
    detected_anomalies: List[str]


app = FastAPI(title="EcoShield Underwriting Backend")


def _determine_status(veracity_score: int) -> Literal["Approved", "Flagged", "Rejected"]:
    if veracity_score >= 80:
        return "Approved"
    if veracity_score >= 50:
        return "Flagged"
    return "Rejected"


def _extract_anomalies(*findings: str) -> List[str]:
    anomalies: List[str] = []
    for text in findings:
        for part in re.split(r"[.;\n]", text):
            cleaned = part.strip()
            if cleaned and cleaned.lower() not in {"no major concerns found", "none"}:
                anomalies.append(cleaned)
    return list(dict.fromkeys(anomalies))


@app.post("/analyze-underwriting", response_model=UnderwritingResponse)
def analyze_underwriting(request: UnderwritingRequest) -> UnderwritingResponse:
    payload = _request_payload(request)
    if not payload:
        raise HTTPException(status_code=400, detail="Request payload cannot be empty.")

    analysis = run_ecoshield_analysis(payload, MOCK_LLM_CONFIG)
    veracity_score = max(0, min(100, int(analysis.veracity_score)))

    return UnderwritingResponse(
        veracity_score=veracity_score,
        status=_determine_status(veracity_score),
        detected_anomalies=_extract_anomalies(
            analysis.regulatory_findings, analysis.anomaly_findings
        ),
    )
