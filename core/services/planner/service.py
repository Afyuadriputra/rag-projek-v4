from __future__ import annotations

import logging
import os
import json
import re
import time
from datetime import timedelta
from typing import Any, Callable, Dict, List, Tuple

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from core.academic import planner as planner_engine
from core.academic.grade_calculator import analyze_transcript_risks, calculate_required_score
from core.ai_engine.retrieval.main import ask_bot
from core.ai_engine.config import get_vectorstore
from core.ai_engine.retrieval.llm import build_llm, get_backup_models, get_runtime_openrouter_config, invoke_text
from core.ai_engine.retrieval.prompt import PLANNER_OUTPUT_TEMPLATE
from core.ai_engine.retrieval.rules import extract_grade_calc_input, is_grade_rescue_query
from core.models import AcademicDocument, ChatHistory, ChatSession, PlannerHistory, PlannerRun
from core.services.chat.service import get_or_create_chat_session
from core.services.documents.service import get_user_quota_bytes, upload_files_batch
from core.services.planner import state_machine as sm
from core.services.planner import validators as vz

logger = logging.getLogger(__name__)


def _default_extract_profile_hints(user: User) -> Dict[str, Any]:
    from core.academic.profile_extractor import extract_profile_hints

    return extract_profile_hints(user)


def _planner_option_label_from_payload(payload: Dict[str, Any], option_id: int | None) -> str:
    if option_id is None:
        return ""
    for opt in payload.get("options", []) or []:
        try:
            if int(opt.get("id")) == int(option_id):
                return str(opt.get("label") or "").strip()
        except Exception:
            continue
    return ""


def _trim_text(value: str, max_len: int = 300) -> str:
    txt = (value or "").strip()
    if len(txt) <= max_len:
        return txt
    return txt[:max_len].rstrip() + "..."


def record_planner_history(
    *,
    user: User,
    session: ChatSession,
    event_type: str,
    planner_step: str,
    text: str,
    option_id: int | None = None,
    option_label: str = "",
    payload: Dict[str, Any] | None = None,
) -> None:
    PlannerHistory.objects.create(
        user=user,
        session=session,
        event_type=event_type,
        planner_step=(planner_step or "")[:64],
        text=_trim_text(text, max_len=1000),
        option_id=option_id,
        option_label=(option_label or "")[:255],
        payload=payload or {},
    )


def _build_grade_rescue_markdown(calc_input: Dict[str, Any] | None, calc_result: Dict[str, Any] | None) -> str:
    if not calc_input or not calc_result:
        return "- Tidak ada data grade rescue spesifik dari input user."
    required = calc_result.get("required")
    required_text = "-" if required is None else f"{float(required):.2f}"
    possible_text = "Ya" if calc_result.get("possible") else "Tidak"
    return (
        f"- Nilai saat ini: {float(calc_input.get('current_score', 0) or 0):.2f}\n"
        f"- Bobot saat ini: {float(calc_input.get('current_weight', 0) or 0):.0f}%\n"
        f"- Target akhir: {float(calc_input.get('target_score', 70) or 70):.2f}\n"
        f"- Bobot tersisa: {float(calc_input.get('remaining_weight', 0) or 0):.0f}%\n"
        f"- Minimal nilai komponen tersisa: {required_text}\n"
        f"- Target mungkin dicapai: {possible_text}"
    )


def _append_verified_grade_rescue(answer: str, calc_input: Dict[str, Any] | None, calc_result: Dict[str, Any] | None) -> str:
    if not calc_input or not calc_result:
        return answer
    required = calc_result.get("required")
    required_text = "-" if required is None else f"{float(required):.2f}"
    possible_text = "Ya" if calc_result.get("possible") else "Tidak"
    verified_block = (
        "\n\n## Grade Rescue (Kalkulasi Sistem)\n"
        f"- Nilai saat ini: **{float(calc_input.get('current_score', 0) or 0):.2f}** "
        f"(bobot **{float(calc_input.get('current_weight', 0) or 0):.0f}%**)\n"
        f"- Target akhir: **{float(calc_input.get('target_score', 70) or 70):.2f}**\n"
        f"- Bobot tersisa: **{float(calc_input.get('remaining_weight', 0) or 0):.0f}%**\n"
        f"- Nilai minimal komponen tersisa: **{required_text}**\n"
        f"- Target mungkin dicapai: **{possible_text}**"
    )
    if "Grade Rescue (Kalkulasi Sistem)" in (answer or ""):
        return answer
    return (answer or "").rstrip() + verified_block


def _build_planner_markdown(collected: Dict[str, Any], scenario: str | None = None, grade_rescue_md: str | None = None) -> str:
    jurusan = collected.get("jurusan") or "-"
    semester = collected.get("semester") or "-"
    goal = collected.get("goal") or "-"
    career = collected.get("career") or "-"
    time_pref = collected.get("time_pref") or "fleksibel"
    free_day = collected.get("free_day") or "tidak ada"
    scenario_text = "Mode normal"
    if scenario == "dense":
        scenario_text = "Mode skenario: **Padat / Lulus Cepat**"
    elif scenario == "relaxed":
        scenario_text = "Mode skenario: **Santai / Beban Ringan**"
    return (
        "## dY\". Jadwal\n"
        "| Hari | Mata Kuliah | Jam | SKS |\n"
        "|---|---|---|---|\n"
        "| Senin | Mata Kuliah Inti | 08:00-10:00 | 3 |\n"
        "| Selasa | Mata Kuliah Wajib | 10:00-12:00 | 3 |\n"
        "| Rabu | Mata Kuliah Pilihan | 13:00-15:00 | 3 |\n\n"
        "## dYZ_ Rekomendasi Mata Kuliah\n"
        f"- Prioritaskan mata kuliah inti untuk jurusan **{jurusan}** semester **{semester}**.\n"
        f"- Tujuan saat ini: **{goal}**.\n\n"
        "## dY'м Keselarasan Karir\n"
        f"- Target karir: **{career}**.\n"
        "- Fokuskan proyek/mata kuliah yang mendekatkan ke role tersebut.\n\n"
        "## Гs-Л,? Distribusi Beban\n"
        f"- Preferensi waktu: **{time_pref}**.\n"
        f"- Hari kosong: **{free_day}**.\n"
        f"- Skenario: {scenario_text}.\n\n"
        "## Гs Л,? Grade Rescue\n"
        f"{grade_rescue_md or '- Tidak ada input grade rescue khusus.'}\n\n"
        "## Selanjutnya\n"
        "1. dY\", Buat opsi Padat\n"
        "2. dY\", Buat opsi Santai\n"
        "3. ƒo?‹,? Ubah sesuatu\n"
        "4. ƒo. Simpan rencana ini\n"
    ).strip()


def _ensure_planner_required_sections(answer: str, grade_rescue_md: str) -> str:
    text = (answer or "").strip()
    if not text:
        text = "## dY\". Jadwal\n- Belum ada output."
    checks = {
        "jadwal": "## dY\". Jadwal\n- Jadwal belum tersedia.",
        "rekomendasi mata kuliah": "## dYZ_ Rekomendasi Mata Kuliah\n- Rekomendasi belum tersedia.",
        "keselarasan karir": "## dY'м Keselarasan Karir\n- Keselarasan karir belum tersedia.",
        "distribusi beban": "## Гs-Л,? Distribusi Beban\n- Distribusi beban belum tersedia.",
        "grade rescue": f"## Гs Л,? Grade Rescue\n{grade_rescue_md}",
        "selanjutnya": "## Selanjutnya\n1. dY\", Buat opsi Padat\n2. dY\", Buat opsi Santai\n3. ƒo?‹,? Ubah sesuatu\n4. ƒo. Simpan rencana ini",
    }
    low = text.lower()
    for key, block in checks.items():
        if key not in low:
            text = f"{text}\n\n{block}"
            low = text.lower()
    return text


# NOTE: Compatibility override for required planner headings used by regression tests.
def _build_planner_markdown(collected: Dict[str, Any], scenario: str | None = None, grade_rescue_md: str | None = None) -> str:  # type: ignore[no-redef]
    jurusan = collected.get("jurusan") or "-"
    semester = collected.get("semester") or "-"
    goal = collected.get("goal") or "-"
    career = collected.get("career") or "-"
    time_pref = collected.get("time_pref") or "fleksibel"
    free_day = collected.get("free_day") or "tidak ada"
    scenario_text = "Mode normal"
    if scenario == "dense":
        scenario_text = "Mode skenario: **Padat / Lulus Cepat**"
    elif scenario == "relaxed":
        scenario_text = "Mode skenario: **Santai / Beban Ringan**"
    return (
        "## 📅 Jadwal\n"
        "| Hari | Mata Kuliah | Jam | SKS |\n"
        "|---|---|---|---|\n"
        "| Senin | Mata Kuliah Inti | 08:00-10:00 | 3 |\n"
        "| Selasa | Mata Kuliah Wajib | 10:00-12:00 | 3 |\n"
        "| Rabu | Mata Kuliah Pilihan | 13:00-15:00 | 3 |\n\n"
        "## 🎯 Rekomendasi Mata Kuliah\n"
        f"- Prioritaskan mata kuliah inti untuk jurusan **{jurusan}** semester **{semester}**.\n"
        f"- Tujuan saat ini: **{goal}**.\n\n"
        "## 💼 Keselarasan Karir\n"
        f"- Target karir: **{career}**.\n"
        "- Fokuskan proyek/mata kuliah yang mendekatkan ke role tersebut.\n\n"
        "## ⚖️ Distribusi Beban\n"
        f"- Preferensi waktu: **{time_pref}**.\n"
        f"- Hari kosong: **{free_day}**.\n"
        f"- Skenario: {scenario_text}.\n\n"
        "## ⚠️ Grade Rescue\n"
        f"{grade_rescue_md or '- Tidak ada input grade rescue khusus.'}\n\n"
        "## Selanjutnya\n"
        "1. Buat opsi Padat\n"
        "2. Buat opsi Santai\n"
        "3. Ubah sesuatu\n"
        "4. Simpan rencana ini\n"
    ).strip()


def _ensure_planner_required_sections(answer: str, grade_rescue_md: str) -> str:  # type: ignore[no-redef]
    text = (answer or "").strip()
    if not text:
        text = "## 📅 Jadwal\n- Belum ada output."
    checks = {
        "jadwal": "## 📅 Jadwal\n- Jadwal belum tersedia.",
        "rekomendasi mata kuliah": "## 🎯 Rekomendasi Mata Kuliah\n- Rekomendasi belum tersedia.",
        "keselarasan karir": "## 💼 Keselarasan Karir\n- Keselarasan karir belum tersedia.",
        "distribusi beban": "## ⚖️ Distribusi Beban\n- Distribusi beban belum tersedia.",
        "grade rescue": f"## ⚠️ Grade Rescue\n{grade_rescue_md}",
        "selanjutnya": "## Selanjutnya\n1. Buat opsi Padat\n2. Buat opsi Santai\n3. Ubah sesuatu\n4. Simpan rencana ini",
    }
    low = text.lower()
    for key, block in checks.items():
        if key not in low:
            text = f"{text}\n\n{block}"
            low = text.lower()
    return text


def _generate_planner_with_llm(
    user: User,
    collected: Dict[str, Any],
    grade_rescue_data: str,
    request_id: str = "-",
) -> str:
    runtime_cfg = get_runtime_openrouter_config()
    if not str(runtime_cfg.get("api_key") or "").strip():
        return ""
    prompt = PLANNER_OUTPUT_TEMPLATE.format(
        jurusan=collected.get("jurusan") or "-",
        semester=collected.get("semester") or "-",
        goal=collected.get("goal") or "-",
        career=collected.get("career") or "-",
        time_pref=collected.get("time_pref") or "-",
        free_day=collected.get("free_day") or "-",
        balance_pref="merata" if collected.get("balance_load") else "fleksibel",
        context=_planner_context_for_user(user, "rencana studi dan jadwal"),
        grade_rescue_data=grade_rescue_data,
    )
    backups = get_backup_models(str(runtime_cfg.get("model") or ""), runtime_cfg.get("backup_models"))
    last_err = ""
    for model_name in backups:
        try:
            llm = build_llm(model_name, runtime_cfg)
            answer = invoke_text(llm, prompt).strip()
            if answer:
                return answer
        except Exception as exc:
            last_err = str(exc)
            continue
    if last_err:
        logger.warning("planner_generate_llm_failed request_id=%s err=%s", request_id, last_err)
    return ""


def _planner_context_for_user(user: User, query: str) -> str:
    try:
        vectorstore = get_vectorstore()
        docs = vectorstore.similarity_search(query or "rencana studi", k=8, filter={"user_id": str(user.id)})
    except Exception:
        return ""
    if not docs:
        return ""
    parts: List[str] = []
    for i, d in enumerate(docs[:5], start=1):
        text = str(getattr(d, "page_content", "") or "").strip()
        if not text:
            continue
        parts.append(f"[Doc {i}] {text[:360]}")
    return "\n".join(parts)


def _safe_json_obj(text: str) -> Dict[str, Any]:
    txt = str(text or "").strip()
    if not txt:
        return {}
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _sanitize_intent_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for i, c in enumerate(candidates[:4], start=1):
        if not isinstance(c, dict):
            continue
        label = str(c.get("label") or "").strip()[:140]
        value = str(c.get("value") or "").strip()[:120]
        reason = str(c.get("reason") or "").strip()[:220]
        if not label:
            continue
        if not value:
            value = f"intent_{i}"
        low = value.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append({"id": i, "label": label, "value": value, "reason": reason})
    return out


def _build_default_intent_candidates(docs_summary: List[Dict[str, Any]], profile_hints: Dict[str, Any]) -> List[Dict[str, Any]]:
    _ = profile_hints
    docs_text = ", ".join([str(d.get("title") or "") for d in docs_summary[:3]])
    return [
        {"id": 1, "label": "Evaluasi IPK dan tren nilai per semester", "value": "ipk_trend", "reason": f"Dokumen terdeteksi: {docs_text}"},
        {"id": 2, "label": "Rekomendasi SKS dan prioritas mata kuliah berikutnya", "value": "sks_plan", "reason": "Cocok untuk perencanaan semester berikut."},
        {"id": 3, "label": "Strategi perbaikan nilai pada mata kuliah berisiko", "value": "grade_recovery", "reason": "Fokus untuk peningkatan performa akademik."},
    ]


def _build_intent_step(intent_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    options = [{"id": int(x.get("id") or i + 1), "label": str(x.get("label") or f"Opsi {i + 1}"), "value": str(x.get("value") or f"intent_{i+1}")} for i, x in enumerate(intent_candidates[:4])]
    return {
        "step_key": "intent",
        "title": "Pilih Fokus Pertanyaan",
        "question": "Berikut kemungkinan pertanyaan berdasarkan dokumenmu. Pilih salah satu atau tulis manual.",
        "options": options,
        "allow_manual": True,
        "required": True,
        "source_hint": "mixed",
        "reason": "Intent dibentuk dari deteksi dokumen dan profil.",
    }


def _generate_intent_candidates_llm(*, docs_summary: List[Dict[str, Any]], profile_hints: Dict[str, Any]) -> List[Dict[str, Any]]:
    runtime_cfg = get_runtime_openrouter_config()
    if not str(runtime_cfg.get("api_key") or "").strip():
        return []
    cfg = {**runtime_cfg, "timeout": max(4, int(os.environ.get("PLANNER_BLUEPRINT_TIMEOUT_SEC", "12"))), "max_retries": 0}
    docs_text = "\n".join([f"- {d.get('title')}" for d in docs_summary[:6]])
    prompt = (
        "Buat 3-4 intent pertanyaan awal paling relevan berdasarkan dokumen user.\n"
        "Output HARUS JSON valid berupa array object: "
        "[{\"label\":str,\"value\":str,\"reason\":str}]\n"
        "Aturan: fokus akademik, singkat, tidak duplikat.\n"
        f"Profile hints: confidence={profile_hints.get('confidence_summary')} major={(profile_hints.get('major_candidates') or [])[:2]}\n"
        f"Dokumen:\n{docs_text}\n"
    )
    backups = get_backup_models(str(cfg.get("model") or ""), cfg.get("backup_models"))
    max_models = max(1, int(os.environ.get("PLANNER_BLUEPRINT_MAX_MODELS", "1")))
    for model_name in backups[:max_models]:
        try:
            llm = build_llm(model_name, cfg)
            raw = invoke_text(llm, prompt).strip()
            parsed = json.loads(raw) if raw else []
            if not isinstance(parsed, list):
                continue
            cleaned = _sanitize_intent_candidates([x for x in parsed if isinstance(x, dict)])
            if cleaned:
                return cleaned
        except Exception:
            continue
    return []


def planner_generate(user: User, state: Dict[str, Any], request_id: str = "-", deps: Dict[str, Callable[..., Any]] | None = None) -> Dict[str, Any]:
    llm_generate_fn = (deps or {}).get("_generate_planner_with_llm", _generate_planner_with_llm)
    collected = dict(state.get("collected_data") or {})
    scenario = str(collected.get("iterate_action") or "").strip().lower()
    grade_calc_input = collected.get("grade_calc_input")
    grade_calc_result = collected.get("grade_calc_result")
    grade_rescue_md = _build_grade_rescue_markdown(grade_calc_input, grade_calc_result)
    answer = llm_generate_fn(user=user, collected=collected, grade_rescue_data=grade_rescue_md, request_id=request_id)
    if not answer:
        _ = analyze_transcript_risks([])
        answer = _build_planner_markdown(collected, scenario=scenario, grade_rescue_md=grade_rescue_md)
    answer = _ensure_planner_required_sections(answer, grade_rescue_md=grade_rescue_md)
    answer = _append_verified_grade_rescue(answer, grade_calc_input, grade_calc_result)
    return {
        "type": "planner_output",
        "answer": answer,
        "options": [
            {"id": 1, "label": "dY\", Buat opsi Padat", "value": "dense"},
            {"id": 2, "label": "dY\", Buat opsi Santai", "value": "relaxed"},
            {"id": 3, "label": "ƒo?‹,? Ubah sesuatu", "value": "edit"},
            {"id": 4, "label": "ƒo. Simpan rencana ini", "value": "save"},
        ],
        "allow_custom": False,
        "planner_meta": {"step": "iterate", "mode": "planner", "request_id": request_id},
    }


def planner_start(user: User, session: ChatSession, deps: Dict[str, Callable[..., Any]] | None = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    extract_profile_hints_fn = (deps or {}).get("extract_profile_hints", _default_extract_profile_hints)
    data_level = planner_engine.detect_data_level(user)
    profile_hints = extract_profile_hints_fn(user)
    state = planner_engine.build_initial_state(data_level=data_level)
    state["profile_hints"] = profile_hints
    state["planner_warning"] = profile_hints.get("warning")
    payload = planner_engine.get_step_payload(state)
    payload["planner_meta"] = {
        **(payload.get("planner_meta") or {}),
        "data_level": data_level,
        "mode": "planner",
        "origin": "start_auto",
        "event_type": PlannerHistory.EVENT_START_AUTO,
    }
    record_planner_history(
        user=user,
        session=session,
        event_type=PlannerHistory.EVENT_START_AUTO,
        planner_step=str((payload.get("planner_meta") or {}).get("step") or state.get("current_step") or "data"),
        text=str(payload.get("answer") or "Planner dimulai."),
        payload={"planner_warning": state.get("planner_warning"), "profile_hints": state.get("profile_hints", {}), "data_level": state.get("data_level", {})},
    )
    return payload, state


def planner_continue(
    user: User,
    session: ChatSession,
    planner_state: Dict[str, Any],
    message: str = "",
    option_id: int | None = None,
    request_id: str = "-",
    deps: Dict[str, Callable[..., Any]] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    extract_profile_hints_fn = (deps or {}).get("extract_profile_hints", _default_extract_profile_hints)
    working_state = dict(planner_state or {})
    fresh_data_level = planner_engine.detect_data_level(user)
    fresh_profile_hints = extract_profile_hints_fn(user)
    working_state["data_level"] = fresh_data_level
    working_state["profile_hints"] = fresh_profile_hints
    working_state["planner_warning"] = fresh_profile_hints.get("warning")
    collected_data = dict(working_state.get("collected_data") or {})
    collected_data["has_transcript"] = bool(fresh_data_level.get("has_transcript"))
    collected_data["has_schedule"] = bool(fresh_data_level.get("has_schedule"))
    collected_data["has_curriculum"] = bool(fresh_data_level.get("has_curriculum"))
    working_state["collected_data"] = collected_data
    if message and is_grade_rescue_query(message):
        parsed = extract_grade_calc_input(message)
        if parsed:
            calc = calculate_required_score(
                achieved_components=parsed.get("achieved_components") or [],
                target_final_score=float(parsed.get("target_final_score", 70) or 70),
                remaining_weight=float(parsed.get("remaining_weight", 0) or 0),
            )
            collected_data["grade_calc_input"] = parsed
            collected_data["grade_calc_result"] = calc
            working_state["collected_data"] = collected_data
    prev_step = str(working_state.get("current_step") or "")
    prev_collected = dict(working_state.get("collected_data") or {})
    state = planner_engine.process_answer(working_state, message=message, option_id=option_id)
    origin = "option_select" if option_id is not None else "user_input"
    event_type = PlannerHistory.EVENT_OPTION_SELECT if option_id is not None else PlannerHistory.EVENT_USER_INPUT
    if option_id is not None and str(state.get("collected_data", {}).get("iterate_action") or "") == "save":
        event_type = PlannerHistory.EVENT_SAVE
    if state.get("current_step") == "generate":
        payload = planner_generate(user=user, state=state, request_id=request_id, deps=deps)
        state["current_step"] = "iterate"
        event_type = PlannerHistory.EVENT_GENERATE
        payload["planner_meta"] = {**(payload.get("planner_meta") or {}), "data_level": state.get("data_level", {}), "origin": origin, "event_type": event_type}
    else:
        payload = planner_engine.get_step_payload(state)
        payload["planner_meta"] = {**(payload.get("planner_meta") or {}), "data_level": state.get("data_level", {}), "mode": "planner", "origin": origin, "event_type": event_type}
    should_log = True
    if event_type == PlannerHistory.EVENT_USER_INPUT:
        has_validation_error = bool(str(state.get("validation_error") or "").strip())
        message_clean = (message or "").strip()
        progressed = prev_step != str(state.get("current_step") or "")
        changed_collected = dict(state.get("collected_data") or {}) != prev_collected
        should_log = bool(message_clean and not has_validation_error and (progressed or changed_collected))
    if should_log:
        step_name = str((payload.get("planner_meta") or {}).get("step") or state.get("current_step") or prev_step)
        option_label = _planner_option_label_from_payload(payload, option_id)
        event_text = str(payload.get("answer") or "")
        if event_type in {PlannerHistory.EVENT_OPTION_SELECT, PlannerHistory.EVENT_SAVE} and option_id is not None:
            event_text = f"Pilih opsi {option_id}: {option_label or '-'}"
        elif event_type == PlannerHistory.EVENT_USER_INPUT:
            event_text = f"Input user: {(message or '').strip()}"
        record_planner_history(
            user=user,
            session=session,
            event_type=event_type,
            planner_step=step_name,
            text=event_text,
            option_id=option_id,
            option_label=option_label,
            payload={"planner_warning": state.get("planner_warning"), "profile_hints": state.get("profile_hints", {}), "data_level": state.get("data_level", {}), "origin": origin},
        )
    return payload, state


def _planner_v3_expiry_hours() -> int:
    try:
        return max(1, int(os.environ.get("PLANNER_V3_EXPIRE_HOURS", "24")))
    except Exception:
        return 24


def _planner_v3_progress_hints() -> List[str]:
    return ["Memvalidasi dokumen", "Mengekstrak teks", "Mengenali tipe dokumen", "Menyusun sesi planner"]


def _serialize_embedded_docs_for_user(user: User, only_ids: List[int] | None = None) -> List[Dict[str, Any]]:
    qs = AcademicDocument.objects.filter(user=user, is_embedded=True).order_by("-uploaded_at")
    if only_ids:
        qs = qs.filter(id__in=only_ids)
    return [{"id": d.id, "title": d.title, "uploaded_at": d.uploaded_at.isoformat()} for d in qs[:20]]


def _build_planner_v3_user_summary(answers: Dict[str, Any], docs: List[Dict[str, Any]]) -> str:
    focus = str(answers.get("focus") or answers.get("goal") or "analisis akademik").strip()
    docs_text = ", ".join([str(d.get("title") or "-") for d in docs[:3]]) or "dokumen akademik"
    return f"Tolong analisis {docs_text} dengan fokus {focus}."


def get_planner_run_for_user(user: User, run_id: str) -> PlannerRun | None:
    try:
        return PlannerRun.objects.filter(user=user, id=run_id).first()
    except Exception:
        return None


def _validate_planner_answers(blueprint: Dict[str, Any], answers: Dict[str, Any]) -> str:
    return vz.validate_execute_answers(blueprint, answers)


def _extract_major_state(profile_hints: Dict[str, Any], user: User, docs_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    _ = user, docs_summary
    candidates = profile_hints.get("major_candidates") or []
    top = candidates[0] if candidates else {}
    conf = float(top.get("confidence") or 0.0)
    lvl = "high" if conf >= 0.75 else "medium" if conf >= 0.5 else "low"
    return {
        "major_label": str(top.get("label") or ""),
        "major_confidence_score": round(conf, 4),
        "major_confidence_level": lvl,
        "source": "inferred",
        "evidence": list((top.get("evidence") or [])[:3]) if isinstance(top, dict) else [],
    }


def _estimate_dynamic_total(*, docs_summary: List[Dict[str, Any]], relevance_score: float, depth: int = 0) -> int:
    complexity = min(2, max(0, len(docs_summary) // 3))
    rel_penalty = 1 if relevance_score < 0.75 else 0
    est = 3 + complexity + rel_penalty
    est = max(est, depth + 1)
    return max(2, min(4, est))


def _extract_major_override_from_answer(answer: str) -> str:
    txt = (answer or "").strip().lower()
    if "teknik informatika" in txt:
        return "Teknik Informatika"
    if "sistem informasi" in txt:
        return "Sistem Informasi"
    return ""


def _sanitize_dynamic_step(step: Dict[str, Any], fallback_step_key: str) -> Dict[str, Any]:
    if not isinstance(step, dict):
        return {}
    options = step.get("options") if isinstance(step.get("options"), list) else []
    clean_opts = []
    for i, o in enumerate(options[:4], start=1):
        if not isinstance(o, dict):
            continue
        label = str(o.get("label") or "").strip()[:120]
        value = str(o.get("value") or "").strip()[:100]
        if not label:
            continue
        if not value:
            value = f"opt_{i}"
        clean_opts.append({"id": int(o.get("id") or i), "label": label, "value": value})
    allow_manual = bool(step.get("allow_manual", True))
    if (not allow_manual) and len(clean_opts) < 2:
        return {}
    step_key = str(step.get("step_key") or "").strip()[:40] or fallback_step_key
    return {
        "step_key": step_key,
        "title": str(step.get("title") or "Pertanyaan Lanjutan")[:120],
        "question": str(step.get("question") or "Lanjutkan analisis planner.")[:320],
        "options": clean_opts,
        "allow_manual": allow_manual,
        "required": bool(step.get("required", True)),
        "source_hint": str(step.get("source_hint") or "mixed")[:20],
        "reason": str(step.get("reason") or "Pertanyaan ini membantu mempertajam analisis.")[:240],
    }


def _fallback_options_from_context(*, latest_answer: str, question: str, step_key: str) -> List[Dict[str, Any]]:
    q = (question or "").lower()
    ans = (latest_answer or "").strip()
    sk = (step_key or "").lower()
    if "ipk" in q or "cumlaude" in q:
        labels = [
            ("Target Cumlaude (> 3.50)", "target_cumlaude"),
            ("Target Sangat Memuaskan (3.00 - 3.49)", "target_sangat_memuaskan"),
            ("Fokus lulus tepat waktu", "target_tepat_waktu"),
        ]
    elif any(k in q for k in ["skripsi", "topik", "minat", "spesialisasi", "fokus", "focus"]):
        labels = [
            ("Pengembangan Perangkat Lunak", "minat_software_engineering"),
            ("Kecerdasan Buatan", "minat_artificial_intelligence"),
            ("Keamanan Siber", "minat_cybersecurity"),
        ]
    elif any(k in q for k in ["krs", "sks", "beban", "jadwal"]):
        labels = [
            ("Ambil beban SKS normal", "load_normal"),
            ("Ambil beban SKS ringan", "load_light"),
            ("Ambil beban SKS agresif", "load_aggressive"),
        ]
    else:
        prefix = re.sub(r"[^a-z0-9_]+", "_", (ans or "pilihan").lower()).strip("_")[:32] or "pilihan"
        key_prefix = re.sub(r"[^a-z0-9_]+", "_", sk).strip("_")[:24] or "followup"
        labels = [
            (f"Fokus utama: {ans[:40] or 'Prioritas akademik'}", f"{key_prefix}_{prefix}_utama"),
            ("Butuh rekomendasi strategi", f"{key_prefix}_{prefix}_strategi"),
            ("Butuh analisis risiko & mitigasi", f"{key_prefix}_{prefix}_risiko"),
        ]
    return [{"id": i, "label": str(label)[:120], "value": str(value)[:100]} for i, (label, value) in enumerate(labels[:4], start=1)]


def _ensure_step_has_options(*, step: Dict[str, Any], latest_answer: str) -> Dict[str, Any]:
    if not isinstance(step, dict):
        return step
    opts = step.get("options") if isinstance(step.get("options"), list) else []
    if len(opts) >= 2:
        return step
    step["options"] = _fallback_options_from_context(
        latest_answer=latest_answer,
        question=str(step.get("question") or ""),
        step_key=str(step.get("step_key") or "followup"),
    )
    step["allow_manual"] = True
    return step


def _normalize_slug_text(text: str) -> str:
    txt = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _is_redundant_question(next_question: str, path_taken: List[Dict[str, Any]]) -> bool:
    nq = _normalize_slug_text(next_question)
    if not nq:
        return False
    nq_tokens = {t for t in nq.split(" ") if len(t) >= 4}
    if not nq_tokens:
        return False
    for p in path_taken[-3:]:
        prev_q = _normalize_slug_text(str(p.get("question") or ""))
        if not prev_q:
            continue
        prev_tokens = {t for t in prev_q.split(" ") if len(t) >= 4}
        if not prev_tokens:
            continue
        inter = len(nq_tokens.intersection(prev_tokens))
        union = len(nq_tokens.union(prev_tokens)) or 1
        if (inter / union) >= 0.55:
            return True
    return False


def _build_step_path_label(step: Dict[str, Any], latest_answer: str) -> str:
    title = str(step.get("title") or "").strip()
    if title:
        return title
    ans = str(latest_answer or "").strip()
    if ans:
        return f"Path: {ans[:40]}"
    return "Path Analisis"


def _planner_path_summary(path_taken: List[Dict[str, Any]]) -> str:
    if not path_taken:
        return "Belum ada jawaban."
    tails = path_taken[-3:]
    return " -> ".join([f"{x.get('step_key')}: {x.get('answer_value')}" for x in tails])


def assess_documents_relevance(user: User, docs_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    titles = [str(d.get("title") or "").lower() for d in docs_summary]
    strong_keywords = {
        "khs",
        "krs",
        "jadwal",
        "transkrip",
        "kurikulum",
        "mata kuliah",
        "nilai",
        "ipk",
        "ips",
        "sks",
        "semester",
        "rencana studi",
        "kartu rencana studi",
        "kartu hasil studi",
    }
    weak_keywords = {"dosen", "kelas", "ruang", "kuliah", "akademik", "prodi", "jurusan", "studi", "skripsi"}
    reasons: List[str] = []
    strong_hits = 0
    weak_hits = 0
    for t in titles:
        title_strong = [kw for kw in strong_keywords if kw in t]
        title_weak = [kw for kw in weak_keywords if kw in t]
        if title_strong:
            strong_hits += len(title_strong)
            reasons.append(f"Judul dokumen mengandung sinyal akademik kuat: {', '.join(title_strong[:3])}")
        if title_weak:
            weak_hits += len(title_weak)
    score = min(1.0, (strong_hits * 0.28) + (weak_hits * 0.06) + 0.12)
    if strong_hits >= 1:
        score = max(score, 0.67)
    is_relevant = score >= 0.55
    return {
        "is_relevant": is_relevant,
        "relevance_score": round(score, 3),
        "relevance_reasons": reasons[:3],
        "blocked_reason": "" if is_relevant else "Dokumen belum terdeteksi relevan untuk perencanaan akademik. Upload KHS/KRS/Jadwal/Transkrip.",
    }


def _generate_planner_blueprint_llm(*, user: User, docs_summary: List[Dict[str, Any]], data_level: Dict[str, Any], profile_hints: Dict[str, Any]) -> Dict[str, Any]:
    runtime_cfg = get_runtime_openrouter_config()
    if not str(runtime_cfg.get("api_key") or "").strip():
        return {}
    cfg = {**runtime_cfg, "timeout": max(4, int(os.environ.get("PLANNER_BLUEPRINT_TIMEOUT_SEC", "12"))), "max_retries": 0}
    docs_text = "\n".join([f"- {d.get('title')}" for d in docs_summary[:8]])
    prompt = (
        "Kamu adalah AI Academic Planner Indonesia. "
        "Keluarkan JSON blueprint planner v3. "
        "Schema: {\"version\":\"v3_dynamic\",\"steps\":[{step_key,title,question,options,allow_manual,required,source_hint,reason}],\"meta\":{doc_type_detected,major_inferred,major_confidence,generation_mode,requires_major_confirmation}}.\n"
        "Output hanya JSON valid.\n"
        f"Data level: {data_level}\n"
        f"Profile hints: {profile_hints.get('confidence_summary')} {profile_hints.get('major_candidates')}\n"
        f"Dokumen:\n{docs_text}\n"
    )
    backups = get_backup_models(str(cfg.get("model") or ""), cfg.get("backup_models"))
    max_models = max(1, int(os.environ.get("PLANNER_BLUEPRINT_MAX_MODELS", "1")))
    for model_name in backups[:max_models]:
        try:
            llm = build_llm(model_name, cfg)
            raw = invoke_text(llm, prompt).strip()
            obj = _safe_json_obj(raw)
            steps = obj.get("steps") if isinstance(obj.get("steps"), list) else []
            if not steps:
                continue
            return obj
        except Exception:
            continue
    return {}


def _generate_next_step_llm(*, user: User, run: PlannerRun, latest_step_key: str, latest_answer: str) -> Dict[str, Any]:
    runtime_cfg = get_runtime_openrouter_config()
    if not str(runtime_cfg.get("api_key") or "").strip():
        return {}
    cfg = {
        **runtime_cfg,
        "timeout": max(4, int(os.environ.get("PLANNER_NEXT_TIMEOUT_SEC", "8"))),
        "max_retries": max(0, int(os.environ.get("PLANNER_NEXT_MAX_RETRIES", "1"))),
    }
    major_state = run.major_state_snapshot if isinstance(run.major_state_snapshot, dict) else {}
    major_source = str(major_state.get("source") or "inferred")
    major_label = str(major_state.get("major_label") or "").strip()
    prompt = (
        "Kamu adalah AI Academic Planner Indonesia. "
        "Buat satu pertanyaan lanjutan paling informatif atau set ready_to_generate=true jika cukup.\n"
        "Output JSON object valid: {\"ready_to_generate\":bool,\"step\":{step_key,title,question,options,allow_manual,required,source_hint,reason}}.\n"
        "step boleh null jika ready_to_generate=true.\n"
        "Jangan ulangi pertanyaan semantik yang sama.\n"
        "Jika major_source=user_override, jangan minta konfirmasi jurusan lagi.\n"
        f"Depth saat ini: {run.current_depth}/{run.max_depth}\n"
        f"Major state: label={major_label} source={major_source}\n"
        f"Jawaban terbaru: {latest_step_key}={latest_answer}\n"
        f"Path taken: {run.path_taken}\n"
    )
    backups = get_backup_models(str(cfg.get("model") or ""), cfg.get("backup_models"))
    max_models = max(1, int(os.environ.get("PLANNER_BLUEPRINT_MAX_MODELS", "1")))
    for model_name in backups[:max_models]:
        try:
            llm = build_llm(model_name, cfg)
            raw = invoke_text(llm, prompt).strip()
            obj = _safe_json_obj(raw)
            if not obj:
                continue
            ready = bool(obj.get("ready_to_generate"))
            step = obj.get("step")
            clean_step = _sanitize_dynamic_step(step, fallback_step_key=f"followup_{run.current_depth + 1}") if isinstance(step, dict) else {}
            if ready and not clean_step:
                return {"ready_to_generate": True}
            if clean_step:
                return {"ready_to_generate": ready, "step": clean_step}
        except Exception:
            continue
    return {}


def _fallback_next_step(run: PlannerRun) -> Dict[str, Any]:
    depth = int(run.current_depth or 0)
    if depth >= int(run.max_depth or 4):
        return {"ready_to_generate": True}
    key = f"followup_{depth + 1}"
    return {
        "ready_to_generate": False,
        "step": {
            "step_key": key,
            "title": "Pendalaman Analisis",
            "question": "Agar hasil lebih tajam, aspek mana yang ingin diperdalam lagi?",
            "options": [
                {"id": 1, "label": "Prioritas mata kuliah", "value": "priority_subject"},
                {"id": 2, "label": "Manajemen beban SKS", "value": "credit_load"},
                {"id": 3, "label": "Strategi belajar", "value": "study_strategy"},
            ],
            "allow_manual": True,
            "required": True,
            "source_hint": "mixed",
            "reason": "Langkah fallback untuk mempertajam keputusan sebelum generate.",
        },
    }


def planner_start_v3(
    *,
    user: User,
    files: List[UploadedFile] | None = None,
    reuse_doc_ids: List[int] | None = None,
    session_id: int | None = None,
    deps: Dict[str, Callable[..., Any]] | None = None,
) -> Dict[str, Any]:
    t0 = time.time()
    d = deps or {}
    assess_relevance_fn = d.get("assess_documents_relevance", assess_documents_relevance)
    extract_profile_hints_fn = d.get("extract_profile_hints", _default_extract_profile_hints)
    extract_major_state_fn = d.get("_extract_major_state", _extract_major_state)
    generate_blueprint_fn = d.get("_generate_planner_blueprint_llm", _generate_planner_blueprint_llm)
    upload_batch_fn = d.get("upload_files_batch", upload_files_batch)
    get_quota_fn = d.get("get_user_quota_bytes", get_user_quota_bytes)
    planner_session = get_or_create_chat_session(user=user, session_id=session_id)
    reuse_doc_ids = reuse_doc_ids or []
    had_upload = bool(files)
    if files:
        quota_bytes = get_quota_fn(user=user, default_quota_bytes=10 * 1024 * 1024)
        upload_result = upload_batch_fn(user=user, files=files, quota_bytes=quota_bytes)
        if upload_result.get("status") != "success":
            return {"status": "error", "error_code": "UPLOAD_FAILED", "error": upload_result.get("msg") or "Upload gagal.", "hint": "Periksa format/ukuran file lalu coba lagi.", "required_upload": True}
    docs_summary = _serialize_embedded_docs_for_user(user=user, only_ids=reuse_doc_ids if reuse_doc_ids else None)
    if not docs_summary:
        return {"status": "error", "error_code": "NO_EMBEDDED_DOCS", "error": "Belum ada dokumen embedded yang valid. Upload atau pilih dokumen existing dulu.", "hint": "Gunakan KHS/KRS/Jadwal/Transkrip/Kurikulum.", "required_upload": True, "progress_hints": _planner_v3_progress_hints(), "recommended_docs": ["KHS", "KRS", "Jadwal", "Transkrip", "Kurikulum"]}
    relevance = assess_relevance_fn(user=user, docs_summary=docs_summary)
    relevance_score = float(relevance.get("relevance_score") or 0.0)
    relevance_warning = ""
    if (not relevance.get("is_relevant")) and (relevance_score >= 0.5):
        relevance_warning = (
            "Dokumen terdeteksi borderline relevan. Planner tetap dilanjutkan, "
            "namun akurasi bisa meningkat jika menambahkan KHS/KRS/Transkrip."
        )
    elif not relevance.get("is_relevant"):
        return {"status": "error", "error_code": "IRRELEVANT_DOCUMENTS", "error": relevance.get("blocked_reason") or "Dokumen tidak relevan.", "hint": "Upload dokumen akademik inti agar planner dapat menganalisis dengan benar.", "required_upload": True, "doc_relevance": {"is_relevant": False, "score": relevance_score, "reasons": relevance.get("relevance_reasons") or []}, "reasons": relevance.get("relevance_reasons") or []}
    data_level = planner_engine.detect_data_level(user)
    profile_hints = extract_profile_hints_fn(user)
    major_state = extract_major_state_fn(profile_hints, user=user, docs_summary=docs_summary)
    if (not str(major_state.get("major_label") or "").strip()) and str(major_state.get("source") or "").strip().lower() == "unknown":
        major_state["major_label"] = "Belum terdeteksi"
        relevance_warning = (
            f"{relevance_warning} " if relevance_warning else ""
        ) + "Jurusan belum dapat dipastikan dari dokumen saat ini."
    estimated_total = _estimate_dynamic_total(docs_summary=docs_summary, relevance_score=relevance_score, depth=1)
    generated_blueprint = generate_blueprint_fn(user=user, docs_summary=docs_summary, data_level=data_level, profile_hints=profile_hints) or {}
    generation_mode = "llm" if generated_blueprint else "fallback_rule"
    wizard_blueprint = generated_blueprint or {"version": "v3_dynamic", "steps": [], "meta": {}}
    intent_candidates = _generate_intent_candidates_llm(docs_summary=docs_summary, profile_hints=profile_hints)
    if not intent_candidates:
        intent_candidates = _build_default_intent_candidates(docs_summary=docs_summary, profile_hints=profile_hints)
    run = PlannerRun.objects.create(
        user=user,
        session=planner_session,
        status=PlannerRun.STATUS_READY,
        wizard_blueprint=wizard_blueprint,
        documents_snapshot=docs_summary,
        intent_candidates_snapshot=intent_candidates,
        decision_tree_state={"expected_step_key": "intent", "next_seq": 1, "can_generate_now": False, "current_step_question": "Berikut kemungkinan pertanyaan berdasarkan dokumenmu. Pilih salah satu atau tulis manual.", "current_path_label": "Intent Awal"},
        path_taken=[],
        current_depth=0,
        max_depth=4,
        grounding_policy="doc_first_fallback",
        profile_hints_snapshot=profile_hints,
        doc_relevance_snapshot={"is_relevant": True, "score": relevance_score, "reasons": relevance.get("relevance_reasons") or []},
        major_state_snapshot=major_state,
        estimated_total_snapshot=estimated_total,
        ui_state_snapshot={"show_major_header": True, "show_path_header": False},
        expires_at=timezone.now() + timedelta(hours=_planner_v3_expiry_hours()),
    )
    payload = {
        "status": "success",
        "planner_run_id": str(run.id),
        "session_id": planner_session.id,
        "wizard_blueprint": run.wizard_blueprint,
        "documents_summary": docs_summary,
        "required_upload": False,
        "progress_hints": _planner_v3_progress_hints(),
        "doc_relevance": {"is_relevant": True, "score": relevance_score, "reasons": relevance.get("relevance_reasons") or []},
        "warning": relevance_warning or None,
        "planner_header": {"major_label": major_state.get("major_label") or "Belum terdeteksi", "major_confidence_level": major_state.get("major_confidence_level") or "low", "major_confidence_score": major_state.get("major_confidence_score") or 0.0, "doc_context_label": str((docs_summary[0].get("title") if docs_summary else "") or "Dokumen Akademik")},
        "progress": {"current": 1, "estimated_total": int(estimated_total), "style": "dynamic_estimate"},
        "ui_hints": {"show_major_header": True, "show_path_header": False},
        "intent_candidates": intent_candidates,
        "manual_intent_enabled": True,
        "next_action": "choose_intent",
        "planner_meta": {"event_type": "start_v3", "had_upload": had_upload, "reuse_count": len(reuse_doc_ids), "generation_mode": generation_mode, "major_source": major_state.get("source") or "inferred"},
    }
    logger.info("planner_start_v3_ms=%s", int((time.time() - t0) * 1000))
    return payload


def planner_next_step_v3(
    *,
    user: User,
    planner_run_id: str,
    step_key: str,
    answer_value: str,
    answer_mode: str,
    client_step_seq: int,
    deps: Dict[str, Callable[..., Any]] | None = None,
) -> Dict[str, Any]:
    t0 = time.time()
    d = deps or {}
    gen_next_fn = d.get("_generate_next_step_llm", _generate_next_step_llm)
    run = get_planner_run_for_user(user=user, run_id=planner_run_id)
    state_err = vz.validate_run_state_for_next_step(run=run, now_ts=timezone.now())
    if state_err:
        if state_err.get("error_code") == "RUN_EXPIRED" and run:
            run.status = PlannerRun.STATUS_EXPIRED
            run.save(update_fields=["status", "updated_at"])
        return state_err
    assert run is not None
    tree = run.decision_tree_state if isinstance(run.decision_tree_state, dict) else {}
    expected_step = sm.get_expected_step(tree)
    next_seq = sm.get_next_seq(tree)
    seq_res = vz.validate_step_sequence(client_step_seq=client_step_seq, next_seq=next_seq, submitted_step=str(step_key or "").strip(), expected_step=expected_step, answered_keys=list((run.answers_snapshot or {}).keys()))
    if not seq_res.get("ok"):
        return seq_res["error"]
    submitted_step = str(seq_res.get("submitted_step") or expected_step)
    payload_err = vz.validate_answer_payload(answer_value=answer_value, answer_mode=answer_mode)
    if payload_err:
        return payload_err
    normalized_mode = str(answer_mode or "").strip().lower()
    answer_text = str(answer_value or "").strip()
    major_state = dict(run.major_state_snapshot or {})
    major_override = _extract_major_override_from_answer(answer_text)
    if major_override:
        major_state["major_label"] = major_override
        major_state["source"] = "user_override"
        major_state["major_confidence_level"] = "high"
        major_state["major_confidence_score"] = 0.99
    answers = dict(run.answers_snapshot or {})
    answers[submitted_step] = answer_text
    tree_question = str(tree.get("current_step_question") or "")
    path = list(run.path_taken or [])
    path.append({"seq": next_seq, "step_key": submitted_step, "question": tree_question, "answer_value": answer_text, "answer_mode": normalized_mode})
    run.current_depth = int(run.current_depth or 0) + 1
    reached_max = run.current_depth >= int(run.max_depth or 4)
    next_payload: Dict[str, Any] = {"ready_to_generate": reached_max}
    if not reached_max:
        next_payload = gen_next_fn(user=user, run=run, latest_step_key=submitted_step, latest_answer=answer_text) or {}
        if isinstance(next_payload.get("step"), dict):
            q = str((next_payload.get("step") or {}).get("question") or "")
            if _is_redundant_question(q, path):
                regen = gen_next_fn(
                    user=user,
                    run=run,
                    latest_step_key=submitted_step,
                    latest_answer=f"{answer_text} (hindari pertanyaan mirip)",
                ) or {}
                if isinstance(regen.get("step"), dict):
                    rq = str((regen.get("step") or {}).get("question") or "")
                    if not _is_redundant_question(rq, path):
                        next_payload = regen
        if not next_payload:
            next_payload = _fallback_next_step(run)
    ready_to_generate = bool(next_payload.get("ready_to_generate"))
    next_step = next_payload.get("step") if isinstance(next_payload.get("step"), dict) else None
    if next_step:
        next_step = _ensure_step_has_options(step=next_step, latest_answer=answer_text)
    path_label = f"{answer_text[:48]}" if submitted_step == "intent" else _build_step_path_label(next_step or {}, answer_text)
    tree = sm.advance_tree_for_next_step(
        tree,
        next_seq=next_seq + 1,
        can_generate=sm.can_generate_now(ready_to_generate, reached_max),
        path_label=path_label,
        next_step_key=str((next_step or {}).get("step_key") or (f"followup_{run.current_depth+1}" if next_step else "")),
        next_question=str((next_step or {}).get("question") or ""),
    )
    run.answers_snapshot = answers
    run.path_taken = path
    run.status = PlannerRun.STATUS_COLLECTING
    run.major_state_snapshot = major_state
    estimated_total = _estimate_dynamic_total(docs_summary=(run.documents_snapshot or []), relevance_score=float((run.doc_relevance_snapshot or {}).get("score") or 0.0), depth=int(run.current_depth))
    run.estimated_total_snapshot = estimated_total
    run.ui_state_snapshot = sm.compute_ui_hints(run.current_depth)
    run.decision_tree_state = tree
    run.save(update_fields=["answers_snapshot", "path_taken", "current_depth", "status", "major_state_snapshot", "estimated_total_snapshot", "ui_state_snapshot", "decision_tree_state", "updated_at"])
    payload = {
        "status": "success",
        "step": next_step,
        "done_recommendation": "Data sudah cukup untuk generate." if not next_step else "",
        "step_header": {"path_label": str(tree.get("current_path_label") or "Path Analisis"), "reason": str((next_step or {}).get("reason") or "Pertanyaan dipilih untuk mempertajam analisis.")},
        "progress": sm.build_progress(run.current_depth, run.estimated_total_snapshot or 4, run.max_depth or 4),
        "can_generate_now": bool(tree.get("can_generate_now")),
        "path_summary": _planner_path_summary(path),
        "major_state": {"major_label": str(major_state.get("major_label") or "Belum terdeteksi"), "source": str(major_state.get("source") or "inferred"), "major_confidence_level": str(major_state.get("major_confidence_level") or "low"), "major_confidence_score": float(major_state.get("major_confidence_score") or 0.0)},
        "ui_hints": {"show_major_header": bool((run.ui_state_snapshot or {}).get("show_major_header")), "show_path_header": bool((run.ui_state_snapshot or {}).get("show_path_header"))},
        "path_taken": path,
    }
    logger.info("planner_next_step_v3_ms=%s", int((time.time() - t0) * 1000))
    return payload


def planner_execute_v3(
    *,
    user: User,
    planner_run_id: str,
    answers: Dict[str, Any],
    path_taken: List[Dict[str, Any]] | None = None,
    session_id: int | None = None,
    client_summary: str = "",
    request_id: str = "-",
    deps: Dict[str, Callable[..., Any]] | None = None,
) -> Dict[str, Any]:
    t0 = time.time()
    ask_bot_fn = (deps or {}).get("ask_bot", ask_bot)
    run = get_planner_run_for_user(user=user, run_id=planner_run_id)
    if not run:
        return {"status": "error", "error_code": "RUN_NOT_FOUND", "error": "planner_run_id tidak ditemukan."}
    if run.status in {PlannerRun.STATUS_CANCELLED, PlannerRun.STATUS_EXPIRED}:
        return {"status": "error", "error_code": "RUN_INVALID_STATUS", "error": f"Planner run sudah {run.status}."}
    if run.status not in {PlannerRun.STATUS_READY, PlannerRun.STATUS_STARTED, PlannerRun.STATUS_COLLECTING}:
        return {"status": "error", "error_code": "RUN_NOT_READY", "error": "Planner run tidak dalam status siap eksekusi."}
    if timezone.now() > run.expires_at:
        run.status = PlannerRun.STATUS_EXPIRED
        run.save(update_fields=["status", "updated_at"])
        return {"status": "error", "error_code": "RUN_EXPIRED", "error": "Planner run sudah kedaluwarsa."}
    if path_taken is not None:
        if not isinstance(path_taken, list):
            return {"status": "error", "error_code": "INVALID_PATH", "error": "path_taken harus array."}
        if path_taken != list(run.path_taken or []):
            return {"status": "error", "error_code": "PATH_MISMATCH", "error": "path_taken tidak konsisten dengan state server.", "hint": "Lakukan refresh dan lanjutkan dari state terbaru."}
    merged_answers = {**(run.answers_snapshot or {}), **(answers or {})}
    if not merged_answers:
        return {"status": "error", "error_code": "EMPTY_ANSWERS", "error": "Belum ada jawaban planner untuk dieksekusi."}
    valid_keys = {str(x.get("step_key")) for x in (run.path_taken or []) if isinstance(x, dict) and x.get("step_key")}
    if valid_keys:
        unknown = [k for k in merged_answers.keys() if k not in valid_keys]
        if unknown:
            return {"status": "error", "error_code": "UNKNOWN_STEP_KEY", "error": f"Jawaban memuat step tidak dikenal: {', '.join(sorted(unknown))}"}
    if not valid_keys:
        err = _validate_planner_answers(run.wizard_blueprint, merged_answers)
        if err:
            return {"status": "error", "error_code": "INVALID_ANSWERS", "error": err}
    run.status = PlannerRun.STATUS_EXECUTING
    run.answers_snapshot = merged_answers
    run.save(update_fields=["status", "answers_snapshot", "updated_at"])
    session = get_or_create_chat_session(user=user, session_id=session_id or run.session_id)
    summary = (client_summary or "").strip() or _build_planner_v3_user_summary(answers=merged_answers, docs=run.documents_snapshot)
    planner_prompt = (
        "Buat analisis akademik berbasis dokumen user dan jawaban wizard berikut.\n"
        "Aturan grounding: utamakan fakta dari dokumen. Jika data dokumen tidak cukup, beri disclaimer jelas "
        "('Data dokumen rujukan belum cukup ...') lalu lanjutkan panduan umum akademik.\n"
        f"Data: {{'planner_run_id': '{run.id}', 'documents': {run.documents_snapshot}, 'answers': {merged_answers}, 'path_taken': {run.path_taken}, 'grounding_policy': '{run.grounding_policy}'}}\n\n"
        f"Permintaan user: {summary}"
    )
    rag_result = ask_bot_fn(user.id, planner_prompt, request_id=request_id)
    answer = str((rag_result or {}).get("answer") or "Maaf, belum ada jawaban.")
    sources = list((rag_result or {}).get("sources") or [])
    ChatHistory.objects.create(user=user, session=session, question=summary, answer=answer)
    session.save(update_fields=["updated_at"])
    run.status = PlannerRun.STATUS_COMPLETED
    run.save(update_fields=["status", "updated_at"])
    fallback_used = (len(sources) == 0) or ("Data dokumen rujukan belum cukup" in answer)
    major_state = run.major_state_snapshot if isinstance(run.major_state_snapshot, dict) else {}
    payload = {
        "status": "success",
        "answer": answer,
        "sources": sources,
        "session_id": session.id,
        "planner_meta": {
            "event_type": "generate",
            "planner_run_id": str(run.id),
            "grounding_mode": "doc_first_fallback",
            "fallback_used": bool(fallback_used),
            "path_depth": len(run.path_taken or []),
            "estimated_total_at_execute": int(run.estimated_total_snapshot or run.max_depth or 4),
            "major_source": str(major_state.get("source") or "inferred"),
        },
    }
    logger.info("planner_execute_v3_ms=%s", int((time.time() - t0) * 1000))
    return payload


def planner_cancel_v3(*, user: User, planner_run_id: str, deps: Dict[str, Callable[..., Any]] | None = None) -> Dict[str, Any]:
    _ = deps
    run = get_planner_run_for_user(user=user, run_id=planner_run_id)
    if not run:
        return {"status": "error", "error": "planner_run_id tidak ditemukan."}
    if run.status in {PlannerRun.STATUS_COMPLETED, PlannerRun.STATUS_CANCELLED}:
        return {"status": "success", "status_detail": run.status}
    run.status = PlannerRun.STATUS_CANCELLED
    run.save(update_fields=["status", "updated_at"])
    return {"status": "success", "status_detail": "cancelled"}
