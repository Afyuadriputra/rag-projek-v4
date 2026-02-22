from __future__ import annotations

import re
from typing import Any, Dict

from ..utils import polish_answer_text_light


def _contains_any_pattern(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            hits.append(p)
    return hits


def classify_safety(query: str) -> Dict[str, Any]:
    q = str(query or "").strip()
    ql = q.lower()
    if not q:
        return {"decision": "allow", "reason": "empty_query", "tags": []}

    crime_patterns = [
        r"\bjudi\b",
        r"\bjudi online\b",
        r"\bslot\b",
        r"\btaruhan\b",
        r"\bphishing\b",
        r"\bcarding\b",
        r"\bscam\b",
        r"\bpenipuan\b",
        r"\bhack(?:ing)?\b",
        r"\bmeretas?\b",
        r"\bbobol\b",
        r"\bbypass\b",
        r"\bexploit\b",
        r"\bnarkoba\b",
    ]
    political_persuasion_patterns = [
        r"\bkampanye\b",
        r"\bpropaganda\b",
        r"\bmanipulasi opini\b",
        r"\bblack campaign\b",
        r"\bmenangkan calon\b",
        r"\bserang lawan politik\b",
    ]

    crime_hits = _contains_any_pattern(ql, crime_patterns)
    if crime_hits:
        return {"decision": "refuse_crime", "reason": "crime_or_harmful_request", "tags": crime_hits}

    political_hits = _contains_any_pattern(ql, political_persuasion_patterns)
    if political_hits:
        return {"decision": "refuse_political", "reason": "political_persuasion_request", "tags": political_hits}

    weird_markers = [
        "ramalan hoki",
        "cara jadi dukun",
        "santet",
        "pesugihan",
        "cara hipnotis orang",
    ]
    if any(m in ql for m in weird_markers):
        return {"decision": "redirect_weird", "reason": "out_of_scope_weird_query", "tags": weird_markers}

    return {"decision": "allow", "reason": "safe", "tags": []}


def build_guard_response(*, decision: str, query: str, request_id: str = "-") -> Dict[str, Any]:
    if decision == "redirect_weird":
        answer = (
            "## Ringkasan\n"
            "Pertanyaan tadi agak di luar fokus akademik kampus. Biar tetap berguna, Aku bantu arahkan ke hal yang lebih relevan untuk kuliah dan karier Kamu.\n\n"
            "- Kita bisa ubah jadi pertanyaan yang hasilnya benar-benar kepakai.\n"
            "- Aku siap bantu dengan jawaban yang ringkas dan konkret.\n\n"
            "## Opsi Lanjut\n"
            "- Mau Aku bantu pilih jurusan sesuai minat dan target kerja?\n"
            "- Atau Aku buatin rencana belajar singkat biar IPK dan skill kamu naik?"
        )
    elif decision == "refuse_crime":
        answer = (
            "## Ringkasan\n"
            "Aku paham Kamu lagi cari arah, dan itu valid. Tapi Aku tidak bisa bantu hal yang melanggar hukum atau berpotensi membahayakan.\n\n"
            "- Aku bisa bantu Kamu cari jalur akademik yang legal dan tetap realistis buat masa depan.\n"
            "- Kita bisa ubah fokus ke skill yang benar-benar kepakai di dunia kerja.\n\n"
            "## Opsi Lanjut\n"
            "- Kalau goal Kamu di HR/Tech/Bisnis, Aku bisa rekomendasikan jurusan dan roadmap skill yang valid.\n"
            "- Aku juga bisa bantu rencana semester singkat 3-6 bulan biar progres kamu jelas.\n"
            "- Kalau mau, kirim target kariermu, nanti Aku bikinin langkah konkretnya."
        )
    else:
        answer = (
            "## Ringkasan\n"
            "Aku tidak bisa bantu strategi propaganda atau manipulasi politik praktis. Namun, Aku tetap bisa bantu dari sisi akademik yang netral dan edukatif.\n\n"
            "- Fokusku adalah membantu Kamu memahami topik secara objektif.\n"
            "- Kita tetap bisa bahas jalur studi dan prospek karier yang relevan.\n\n"
            "## Opsi Lanjut\n"
            "- Aku bisa jelaskan jurusan Ilmu Politik, Hukum, Administrasi Publik, dan prospek kariernya.\n"
            "- Aku juga bisa bantu ringkas konsep sistem politik secara objektif untuk belajar."
        )
    answer = polish_answer_text_light(answer)
    return {
        "answer": answer,
        "sources": [],
        "meta": {
            "mode": "guard",
            "pipeline": "route_guard",
            "intent_route": "default_rag",
            "validation": "not_applicable",
            "analytics_stats": {},
        },
    }


def build_out_of_domain_response(*, intent_route: str) -> Dict[str, Any]:
    answer = (
        "## Ringkasan\n"
        "Maaf, saya hanya asisten akademik kampus.\n\n"
        "## Opsi Lanjut\n"
        "- Saya bisa bantu jadwal kuliah, rekap nilai, KRS/KHS, dan strategi studi.\n"
        "- Coba tulis ulang pertanyaan dalam konteks akademik."
    )
    answer = polish_answer_text_light(answer)
    return {
        "answer": answer,
        "sources": [],
        "meta": {
            "mode": "guard",
            "pipeline": "route_guard",
            "intent_route": intent_route,
            "validation": "not_applicable",
            "analytics_stats": {},
        },
    }
