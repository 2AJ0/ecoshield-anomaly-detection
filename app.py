import json
from typing import Any

import requests
import streamlit as st


BACKEND_URL = "http://localhost:8000/analyze-underwriting"


def _first_non_null(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _status_from_result(veracity_score: int | None, anomalies: Any) -> bool:
    if isinstance(anomalies, list) and anomalies:
        return True
    if isinstance(anomalies, str) and anomalies.strip():
        return True
    if isinstance(veracity_score, (int, float)) and veracity_score < 70:
        return True
    return False


st.set_page_config(
    page_title="EcoShield: Agentic Underwriting Intelligence",
    page_icon="🌱",
    layout="wide",
)

with st.sidebar:
    st.title("EcoShield: Agentic Underwriting Intelligence")
    st.caption("Upload or paste underwriting context and run anomaly analysis.")

st.header("Underwriting Anomaly Analyzer")
st.write("Paste JSON and/or upload a mock document to run analysis against your backend.")

json_input = st.text_area(
    "Paste underwriting JSON",
    height=220,
    placeholder='{\n  "application_id": "APP-001",\n  "land_deed": {...},\n  "financials": {...}\n}',
)
uploaded_file = st.file_uploader("Upload mock document (.txt or .json)", type=["txt", "json"])

if st.button("Analyze for Anomalies", type="primary", use_container_width=True):
    request_payload: dict[str, Any] = {}
    parsed_json: dict[str, Any] | None = None
    uploaded_text: str | None = None

    if json_input.strip():
        try:
            parsed_json = json.loads(json_input)
            request_payload["json_data"] = parsed_json
        except json.JSONDecodeError as exc:
            st.error(f"Invalid JSON provided: {exc}")
            st.stop()

    if uploaded_file is not None:
        uploaded_text = uploaded_file.getvalue().decode("utf-8", errors="replace")
        request_payload["document_text"] = uploaded_text
        request_payload["document_name"] = uploaded_file.name

    if not request_payload:
        st.warning("Please paste JSON or upload a mock document before analyzing.")
        st.stop()

    with st.spinner("Analyzing underwriting payload for anomalies..."):
        try:
            response = requests.post(BACKEND_URL, json=request_payload, timeout=45)
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            st.error(f"Failed to reach backend at {BACKEND_URL}: {exc}")
            st.stop()
        except ValueError:
            st.error("Backend returned a non-JSON response.")
            st.stop()

    veracity_score = _first_non_null(result, ["veracity_score", "Veracity Score", "score"])
    if isinstance(veracity_score, str) and veracity_score.isdigit():
        veracity_score = int(veracity_score)
    if not isinstance(veracity_score, (int, float)):
        veracity_score = None

    anomalies = _first_non_null(result, ["anomalies", "anomaly_findings", "flags", "issues"])
    risk_summary = _first_non_null(result, ["risk_summary", "summary", "decision"]) or "No summary provided."
    has_anomalies = _status_from_result(veracity_score, anomalies)

    col1, col2 = st.columns([1, 2])
    with col1:
        metric_value = f"{int(veracity_score)}/100" if isinstance(veracity_score, (int, float)) else "N/A"
        st.metric("Veracity Score", metric_value)
    with col2:
        if has_anomalies:
            st.error("🚨 Potential anomalies detected in the underwriting submission.")
        else:
            st.success("✅ Submission looks safe based on current checks.")

    with st.expander("Risk Summary", expanded=True):
        st.write(risk_summary)

    with st.expander("Anomaly Findings", expanded=True):
        if isinstance(anomalies, list):
            if anomalies:
                for item in anomalies:
                    st.markdown(f"- {item}")
            else:
                st.write("No anomalies reported.")
        elif isinstance(anomalies, str) and anomalies.strip():
            st.write(anomalies)
        else:
            st.write("No anomaly details returned.")

    with st.expander("Raw Backend Response"):
        st.json(result)
