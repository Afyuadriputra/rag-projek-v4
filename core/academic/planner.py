from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import AcademicDocument

PLANNER_STEPS = [
    "data",
    "profile_jurusan",
    "profile_semester",
    "goals",
    "career",
    "preferences_time",
    "preferences_free_day",
    "preferences_balance",
    "review",
    "generate",
    "iterate",
]


STEP_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "data": {
        "question": "Apakah kamu punya dokumen akademik?",
        "options": [
            {"id": 1, "label": "📎 Ya, saya mau upload file", "value": "upload"},
            {"id": 2, "label": "✍️ Tidak, saya isi manual", "value": "manual"},
            {"id": 3, "label": "🤷 Bantu tanpa data lengkap", "value": "no_data"},
        ],
        "allow_custom": False,
    },
    "profile_jurusan": {
        "question": "Jurusan kamu apa?",
        "options": [
            {"id": 1, "label": "Teknik Informatika", "value": "Teknik Informatika"},
            {"id": 2, "label": "Sistem Informasi", "value": "Sistem Informasi"},
            {"id": 3, "label": "Manajemen", "value": "Manajemen"},
            {"id": 4, "label": "Akuntansi", "value": "Akuntansi"},
            {"id": 5, "label": "Lainnya (ketik sendiri)", "value": "custom"},
        ],
        "allow_custom": True,
    },
    "profile_semester": {
        "question": "Saat ini kamu semester berapa?",
        "options": [
            {"id": 1, "label": "Semester 1", "value": 1},
            {"id": 2, "label": "Semester 3", "value": 3},
            {"id": 3, "label": "Semester 5", "value": 5},
            {"id": 4, "label": "Semester 7", "value": 7},
            {"id": 5, "label": "Ketik sendiri", "value": "custom"},
        ],
        "allow_custom": True,
    },
    "goals": {
        "question": "Apa tujuan utama semester ini?",
        "options": [
            {"id": 1, "label": "Lulus lebih cepat", "value": "fast_graduate"},
            {"id": 2, "label": "IPK setinggi mungkin", "value": "max_gpa"},
            {"id": 3, "label": "Seimbang", "value": "balanced"},
            {"id": 4, "label": "Fokus karir tertentu", "value": "career"},
        ],
        "allow_custom": False,
    },
    "career": {
        "question": "Target karir kamu apa?",
        "options": [
            {"id": 1, "label": "Data Scientist", "value": "Data Scientist"},
            {"id": 2, "label": "Software Engineer", "value": "Software Engineer"},
            {"id": 3, "label": "UI/UX Designer", "value": "UI/UX Designer"},
            {"id": 4, "label": "Cybersecurity", "value": "Cybersecurity"},
            {"id": 5, "label": "Ketik sendiri", "value": "custom"},
        ],
        "allow_custom": True,
    },
    "preferences_time": {
        "question": "Preferensi waktu kuliah?",
        "options": [
            {"id": 1, "label": "Pagi", "value": "morning"},
            {"id": 2, "label": "Siang-Sore", "value": "afternoon"},
            {"id": 3, "label": "Fleksibel", "value": "flexible"},
        ],
        "allow_custom": False,
    },
    "preferences_free_day": {
        "question": "Hari yang ingin dikosongkan?",
        "options": [
            {"id": 1, "label": "Jumat", "value": "friday"},
            {"id": 2, "label": "Sabtu", "value": "saturday"},
            {"id": 3, "label": "Tidak ada", "value": "none"},
        ],
        "allow_custom": False,
    },
    "preferences_balance": {
        "question": "Sebar mata kuliah berat merata?",
        "options": [
            {"id": 1, "label": "Ya", "value": "yes"},
            {"id": 2, "label": "Terserah AI", "value": "auto"},
        ],
        "allow_custom": False,
    },
    "review": {
        "question": "Cek data kamu dulu. Jika sudah benar, kita generate rencana.",
        "options": [
            {"id": 1, "label": "✅ Benar, susun rencana", "value": "confirm"},
            {"id": 2, "label": "✏️ Ubah data", "value": "edit"},
        ],
        "allow_custom": False,
    },
    "iterate": {
        "question": "Mau lanjut apa selanjutnya?",
        "options": [
            {"id": 1, "label": "🔄 Buat opsi Padat", "value": "dense"},
            {"id": 2, "label": "🔄 Buat opsi Santai", "value": "relaxed"},
            {"id": 3, "label": "✏️ Ubah sesuatu", "value": "edit"},
            {"id": 4, "label": "✅ Simpan rencana ini", "value": "save"},
        ],
        "allow_custom": False,
    },
}


def detect_data_level(user) -> Dict[str, Any]:
    docs = AcademicDocument.objects.filter(user=user, is_embedded=True).order_by("-uploaded_at")

    titles = [str(d.title or "").lower() for d in docs]
    has_transcript = any(("transkrip" in t) or ("khs" in t) or ("nilai" in t) for t in titles)
    has_schedule = any(("jadwal" in t) or ("krs" in t) for t in titles)
    has_curriculum = any(("kurikulum" in t) or ("curriculum" in t) for t in titles)

    level = 0
    if has_transcript or has_schedule:
        level = 2
    if has_transcript and has_schedule:
        level = 3

    return {
        "level": level,
        "has_transcript": has_transcript,
        "has_schedule": has_schedule,
        "has_curriculum": has_curriculum,
        "documents": [d.title for d in docs],
    }


def build_initial_state(data_level: Dict[str, Any]) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "current_step": "data",
        "collected_data": {
            "has_transcript": bool(data_level.get("has_transcript")),
            "has_schedule": bool(data_level.get("has_schedule")),
            "has_curriculum": bool(data_level.get("has_curriculum")),
        },
        "data_level": data_level,
    }

    if int(data_level.get("level", 0)) >= 3:
        state["current_step"] = "goals"

    return state


def _resolve_option(step: str, option_id: Optional[int], message: str) -> Any:
    step_def = STEP_DEFINITIONS.get(step, {})
    options = step_def.get("options", [])
    by_id = {int(o.get("id")): o for o in options if str(o.get("id", "")).isdigit()}

    if option_id is not None and option_id in by_id:
        return by_id[option_id].get("value")

    raw = (message or "").strip()
    if raw.isdigit() and int(raw) in by_id:
        return by_id[int(raw)].get("value")

    # exact label match fallback
    for opt in options:
        if raw.lower() == str(opt.get("label", "")).strip().lower():
            return opt.get("value")

    return raw


def _next_step(current_step: str, collected: Dict[str, Any], selection: Any) -> str:
    if current_step == "data":
        return "profile_jurusan"
    if current_step == "profile_jurusan":
        return "profile_semester"
    if current_step == "profile_semester":
        return "goals"
    if current_step == "goals":
        return "career" if selection == "career" else "preferences_time"
    if current_step == "career":
        return "preferences_time"
    if current_step == "preferences_time":
        return "preferences_free_day"
    if current_step == "preferences_free_day":
        return "preferences_balance"
    if current_step == "preferences_balance":
        return "review"
    if current_step == "review":
        return "generate" if selection == "confirm" else "profile_jurusan"
    if current_step == "iterate":
        if selection in {"dense", "relaxed", "edit"}:
            return "generate" if selection in {"dense", "relaxed"} else "profile_jurusan"
        return "iterate"
    return current_step


def process_answer(state: Dict[str, Any], message: str = "", option_id: Optional[int] = None) -> Dict[str, Any]:
    current = str(state.get("current_step") or "data")
    collected = dict(state.get("collected_data") or {})

    if current == "generate":
        return {**state, "current_step": "iterate", "collected_data": collected}

    selection = _resolve_option(current, option_id=option_id, message=message)

    if current == "data":
        collected["data_strategy"] = selection
    elif current == "profile_jurusan":
        if selection and selection != "custom":
            collected["jurusan"] = selection
        elif message.strip():
            collected["jurusan"] = message.strip()
    elif current == "profile_semester":
        if isinstance(selection, int):
            collected["semester"] = selection
        elif isinstance(selection, str) and selection.isdigit():
            collected["semester"] = int(selection)
    elif current == "goals":
        collected["goal"] = selection
    elif current == "career":
        if selection and selection != "custom":
            collected["career"] = selection
        elif message.strip():
            collected["career"] = message.strip()
    elif current == "preferences_time":
        collected["time_pref"] = selection
    elif current == "preferences_free_day":
        collected["free_day"] = selection
    elif current == "preferences_balance":
        collected["balance_load"] = selection in {"yes", True}
    elif current == "review":
        collected["review_action"] = selection
    elif current == "iterate":
        collected["iterate_action"] = selection

    next_step = _next_step(current, collected=collected, selection=selection)
    return {**state, "current_step": next_step, "collected_data": collected}


def get_step_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    current = str(state.get("current_step") or "data")

    if current == "generate":
        return {
            "type": "planner_generate",
            "answer": "Saya sedang menyusun rencana berdasarkan data kamu...",
            "options": [],
            "allow_custom": False,
            "planner_meta": {"step": current},
        }

    if current == "review":
        c = dict(state.get("collected_data") or {})
        summary = (
            "Ringkasan data:\n"
            f"- Jurusan: {c.get('jurusan', '-')}\n"
            f"- Semester: {c.get('semester', '-')}\n"
            f"- Tujuan: {c.get('goal', '-')}\n"
            f"- Karir: {c.get('career', '-')}\n"
            f"- Preferensi waktu: {c.get('time_pref', '-')}\n"
            f"- Hari kosong: {c.get('free_day', '-')}\n"
            "Jika sudah sesuai, pilih konfirmasi untuk generate rencana."
        )
        step_def = STEP_DEFINITIONS[current]
        return {
            "type": "planner_step",
            "answer": summary,
            "options": step_def.get("options", []),
            "allow_custom": bool(step_def.get("allow_custom", False)),
            "planner_meta": {"step": current},
        }

    step_def = STEP_DEFINITIONS.get(current, STEP_DEFINITIONS["data"])
    return {
        "type": "planner_step",
        "answer": step_def.get("question", "Lanjutkan planner."),
        "options": step_def.get("options", []),
        "allow_custom": bool(step_def.get("allow_custom", False)),
        "planner_meta": {"step": current},
    }
