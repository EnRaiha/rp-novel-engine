#!/usr/bin/env python3
"""
Context Sentinel — inbound prompt-injection sanitization for the RAG pipeline.

Sits between data sources (PG, wiki .md files, vector store) and the LLM
context window. Scans retrieved/ingested text for instruction-override
patterns and redacts them BEFORE they reach the model.

Direction: INBOUND (Database/Files -> LLM Context).
"""
import re
from dataclasses import dataclass, field

# Injection patterns: regex -> redaction label
INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+(instructions|rules|prompts?|directives?)", re.I), "override_instructions"),
    (re.compile(r"reveal\s+(your\s+|the\s+)?system\s+prompt", re.I), "system_prompt_reveal"),
    (re.compile(r"print\s+(your\s+|the\s+)?system\s+prompt", re.I), "system_prompt_reveal"),
    (re.compile(r"you\s+are\s+now\s+(unrestricted|jailbroken|developer\s*mode|a\s*different\s*(model|ai)|in\s+dank?\s*mode)", re.I), "role_override"),
    (re.compile(r"\bsystem\s*:\s*(you\s+are|ignore|disregard|override)", re.I), "pseudo_system"),
    (re.compile(r"\b(user|assistant)\s*:\s*(ignore|override|disregard)", re.I), "pseudo_role"),
    (re.compile(r"\bdan\b|do\s+anything\s+now\b|jailbreak\b", re.I), "jailbreak_marker"),
    (re.compile(r"hidden\s+instruction|secret\s+instruction|undisclosed\s+directive", re.I), "hidden_instruction"),
    (re.compile(r"disregard\s+(the\s+)?(above|previous|earlier)", re.I), "override_instructions"),
    (re.compile(r"repeat\s+(your\s+|the\s+)?(system\s+)?prompt", re.I), "system_prompt_reveal"),
]


@dataclass
class ScanResult:
    is_clean: bool
    sanitized: str
    findings: list[dict] = field(default_factory=list)


def scan_text(text: str, source: str = "unknown") -> ScanResult:
    """
    Scan text for prompt-injection patterns.
    Returns sanitized text with matches redacted + findings list.
    """
    findings: list[dict] = []
    sanitized = text

    for pattern, label in INJECTION_PATTERNS:
        for m in pattern.finditer(sanitized):
            findings.append({
                "pattern": label,
                "match": m.group(0)[:80],
                "span": list(m.span()),
            })

    # Redact in one pass (descending spans to keep offsets valid)
    spans = [(m.start(), m.end()) for pattern, _ in INJECTION_PATTERNS
             for m in pattern.finditer(text)]
    if spans:
        spans.sort(key=lambda s: s[0], reverse=True)
        chars = list(text)
        for start, end in spans:
            for i in range(start, end):
                chars[i] = " "
        sanitized = "".join(chars)
        # Compact repeated whitespace introduced by redaction
        sanitized = re.sub(r" {2,}", " ", sanitized)

    if findings:
        from core.log import info
        info("sentinel", f"⚠️ Injection patterns in {source}: {[f['pattern'] for f in findings]}")

    return ScanResult(
        is_clean=len(findings) == 0,
        sanitized=sanitized,
        findings=findings,
    )


def gate_for_cli(text: str, source: str = "unknown") -> str:
    """Convenience wrapper — returns sanitized text only (fail-open)."""
    return scan_text(text, source).sanitized
