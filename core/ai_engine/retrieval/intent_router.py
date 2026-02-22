import re
from typing import Any, Dict


_ANALYTICAL_PATTERNS = [
    r"\brekap\b",
    r"\bringkas\b",
    r"\brangkum\b",
    r"\bhasil studi\b",
    r"\breview hasil studi\b",
    r"\bnilai rendah\b",
    r"\bmatakuliah.*rendah\b",
    r"\bjadwal hari\b",
    r"\bhari ini\b",
    r"\bkhs\b",
    r"\bkrs\b",
    r"\btranskrip\b",
    r"\bips\b",
    r"\bipk\b",
]

_SEMANTIC_POLICY_PATTERNS = [
    r"\baturan\b",
    r"\bsyarat lulus\b",
    r"\bcara cuti\b",
    r"\bpedoman\b",
    r"\bkebijakan\b",
    r"\bperaturan\b",
    r"\bskripsi\b.*\bsyarat\b",
    r"\bregistrasi\b.*\baturan\b",
]

_OUT_OF_DOMAIN_PATTERNS = [
    r"\bresep\b",
    r"\bcuaca\b",
    r"\bcrypto\b",
    r"\bsaham\b",
    r"\bprediksi skor\b",
    r"\bbola\b",
    r"\bgaming\b",
    r"\bfilm\b",
    r"\blagu\b",
    r"\bdrama korea\b",
]


def _hits(text: str, patterns: list[str]) -> list[str]:
    out: list[str] = []
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            out.append(p)
    return out


def route_intent(query: str) -> Dict[str, Any]:
    q = str(query or "").strip()
    ql = q.lower()
    if not q:
        return {"route": "default_rag", "reason": "empty_query", "matched": []}

    analytical_hits = _hits(ql, _ANALYTICAL_PATTERNS)
    if analytical_hits:
        return {
            "route": "analytical_tabular",
            "reason": "matched_analytical_keywords",
            "matched": analytical_hits,
        }

    semantic_hits = _hits(ql, _SEMANTIC_POLICY_PATTERNS)
    if semantic_hits:
        return {
            "route": "semantic_policy",
            "reason": "matched_semantic_policy_keywords",
            "matched": semantic_hits,
        }

    out_domain_hits = _hits(ql, _OUT_OF_DOMAIN_PATTERNS)
    if out_domain_hits:
        return {
            "route": "out_of_domain",
            "reason": "matched_out_of_domain_keywords",
            "matched": out_domain_hits,
        }

    return {"route": "default_rag", "reason": "no_route_match", "matched": []}
