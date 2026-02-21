from __future__ import annotations

from typing import Any, Dict, List, Tuple

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile

from core.academic.profile_extractor import extract_profile_hints
from core.ai_engine.config import get_vectorstore
from core.ai_engine.ingest import process_document
from core.ai_engine.retrieval import ask_bot
from core.ai_engine.retrieval.llm import build_llm, get_backup_models, get_runtime_openrouter_config, invoke_text
from core.ai_engine.retrieval.prompt import PLANNER_OUTPUT_TEMPLATE
from core.ai_engine.vector_ops import delete_vectors_for_doc, delete_vectors_for_doc_strict
from core.models import AcademicDocument, ChatSession, PlannerRun
from core.services.chat import serializers as _chat_serializers
from core.services.chat import service as _chat_service
from core.services.documents import service as _documents_service
from core.services.planner import service as _planner_service
from core.services.shared import utils as _shared_utils


# shared
bytes_to_human = _shared_utils.bytes_to_human

# documents (direct delegates where patch compatibility is not required)
serialize_documents_for_user = _documents_service.serialize_documents_for_user
get_user_quota_bytes = _documents_service.get_user_quota_bytes
build_storage_payload = _documents_service.build_storage_payload
get_documents_payload = _documents_service.get_documents_payload

# chat/session/timeline
serialize_sessions_for_user = _chat_serializers.serialize_sessions_for_user
_get_or_create_default_session = _chat_service._get_or_create_default_session
get_or_create_chat_session = _chat_service.get_or_create_chat_session
_attach_legacy_history_to_session = _chat_service._attach_legacy_history_to_session
_maybe_update_session_title = _chat_service._maybe_update_session_title
get_dashboard_props = _chat_service.get_dashboard_props
list_sessions = _chat_service.list_sessions
create_session = _chat_service.create_session
rename_session = _chat_service.rename_session
delete_session = _chat_service.delete_session
get_session_history = _chat_service.get_session_history
get_session_timeline = _chat_service.get_session_timeline


def chat_and_save(user: User, message: str, request_id: str = "-", session_id: int | None = None) -> Dict[str, Any]:
    return _chat_service.chat_and_save(
        user=user,
        message=message,
        request_id=request_id,
        session_id=session_id,
        ask_bot_fn=ask_bot,
    )


def upload_files_batch(user: User, files: List[UploadedFile], quota_bytes: int) -> Dict[str, Any]:
    # shim for compatibility with patches on core.service.process_document
    success_count = 0
    error_count = 0
    errors: List[str] = []
    _, total_bytes = serialize_documents_for_user(user=user, limit=100000)
    remaining_bytes = max(0, int(quota_bytes) - int(total_bytes))
    for file_obj in files:
        file_size = getattr(file_obj, "size", 0) or 0
        if (total_bytes + file_size) > quota_bytes:
            error_count += 1
            errors.append(
                f"{file_obj.name} (Melebihi kuota. Sisa {bytes_to_human(remaining_bytes)}, file {bytes_to_human(file_size)})"
            )
            continue
        try:
            doc = AcademicDocument.objects.create(user=user, file=file_obj)
            total_bytes += file_size
            remaining_bytes = max(0, int(quota_bytes) - int(total_bytes))
            ok = process_document(doc)
            if ok:
                doc.is_embedded = True
                doc.save(update_fields=["is_embedded"])
                success_count += 1
            else:
                doc.delete()
                error_count += 1
                errors.append(f"{file_obj.name} (Gagal Parsing)")
        except Exception:
            error_count += 1
            errors.append(f"{file_obj.name} (System Error)")
    if success_count > 0:
        msg = f"Berhasil memproses {success_count} file."
        if error_count > 0:
            msg += f" (Gagal: {error_count})"
        return {"status": "success", "msg": msg}
    return {"status": "error", "msg": f"Gagal semua. Detail: {', '.join(errors)}"}


def reingest_documents_for_user(user: User, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    qs = AcademicDocument.objects.filter(user=user).order_by("-uploaded_at")
    if doc_ids:
        qs = qs.filter(id__in=doc_ids)
    total = qs.count()
    if total == 0:
        return {"status": "error", "msg": "Tidak ada dokumen untuk di-reingest."}
    ok_count = 0
    fail_count = 0
    fails: List[str] = []
    for doc in qs:
        try:
            delete_vectors_for_doc(user_id=str(user.id), doc_id=str(doc.id), source=getattr(doc, "title", None))
            ok = process_document(doc)
            if ok:
                doc.is_embedded = True
                doc.save(update_fields=["is_embedded"])
                ok_count += 1
            else:
                fail_count += 1
                fails.append(f"{doc.title} (Gagal Parsing)")
        except Exception:
            fail_count += 1
            fails.append(f"{doc.title} (System Error)")
    if ok_count > 0:
        msg = f"Re-ingest berhasil: {ok_count}/{total} dokumen."
        if fail_count > 0:
            msg += f" Gagal: {fail_count} ({', '.join(fails[:5])}{'...' if len(fails) > 5 else ''})"
        return {"status": "success", "msg": msg}
    return {"status": "error", "msg": f"Gagal re-ingest semua dokumen. Detail: {', '.join(fails)}"}


def delete_document_for_user(user: User, doc_id: int) -> bool:
    doc = AcademicDocument.objects.filter(user=user, id=doc_id).first()
    if not doc:
        return False
    ok, _remaining = delete_vectors_for_doc_strict(
        user_id=str(user.id),
        doc_id=str(doc.id),
        source=getattr(doc, "title", None),
    )
    if not ok:
        return False
    try:
        if doc.file:
            doc.file.delete(save=False)
    except Exception:
        pass
    doc.delete()
    return True


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
        context="",
        grade_rescue_data=grade_rescue_data,
    )
    backups = get_backup_models(str(runtime_cfg.get("model") or ""), runtime_cfg.get("backup_models"))
    for model_name in backups:
        try:
            llm = build_llm(model_name, runtime_cfg)
            answer = invoke_text(llm, prompt).strip()
            if answer:
                return answer
        except Exception:
            continue
    return ""


def assess_documents_relevance(user: User, docs_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _planner_service.assess_documents_relevance(user=user, docs_summary=docs_summary)


def _extract_major_state(profile_hints: Dict[str, Any], user: User, docs_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _planner_service._extract_major_state(profile_hints=profile_hints, user=user, docs_summary=docs_summary)


def _generate_planner_blueprint_llm(
    *,
    user: User,
    docs_summary: List[Dict[str, Any]],
    data_level: Dict[str, Any],
    profile_hints: Dict[str, Any],
) -> Dict[str, Any]:
    return _planner_service._generate_planner_blueprint_llm(
        user=user,
        docs_summary=docs_summary,
        data_level=data_level,
        profile_hints=profile_hints,
    )


def _generate_next_step_llm(
    *,
    user: User,
    run: PlannerRun,
    latest_step_key: str,
    latest_answer: str,
) -> Dict[str, Any]:
    return _planner_service._generate_next_step_llm(
        user=user,
        run=run,
        latest_step_key=latest_step_key,
        latest_answer=latest_answer,
    )


def _planner_deps() -> Dict[str, Any]:
    return {
        "ask_bot": ask_bot,
        "extract_profile_hints": extract_profile_hints,
        "assess_documents_relevance": assess_documents_relevance,
        "_extract_major_state": _extract_major_state,
        "_generate_planner_blueprint_llm": _generate_planner_blueprint_llm,
        "_generate_next_step_llm": _generate_next_step_llm,
        "_generate_planner_with_llm": _generate_planner_with_llm,
        "upload_files_batch": upload_files_batch,
        "get_user_quota_bytes": get_user_quota_bytes,
    }


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
    return _planner_service.record_planner_history(
        user=user,
        session=session,
        event_type=event_type,
        planner_step=planner_step,
        text=text,
        option_id=option_id,
        option_label=option_label,
        payload=payload,
    )


def planner_start(user: User, session: ChatSession) -> tuple[Dict[str, Any], Dict[str, Any]]:
    return _planner_service.planner_start(user=user, session=session, deps=_planner_deps())


def planner_generate(user: User, state: Dict[str, Any], request_id: str = "-") -> Dict[str, Any]:
    return _planner_service.planner_generate(user=user, state=state, request_id=request_id, deps=_planner_deps())


def planner_continue(
    user: User,
    session: ChatSession,
    planner_state: Dict[str, Any],
    message: str = "",
    option_id: int | None = None,
    request_id: str = "-",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    return _planner_service.planner_continue(
        user=user,
        session=session,
        planner_state=planner_state,
        message=message,
        option_id=option_id,
        request_id=request_id,
        deps=_planner_deps(),
    )


def planner_start_v3(
    *,
    user: User,
    files: List[UploadedFile] | None = None,
    reuse_doc_ids: List[int] | None = None,
    session_id: int | None = None,
) -> Dict[str, Any]:
    return _planner_service.planner_start_v3(
        user=user,
        files=files,
        reuse_doc_ids=reuse_doc_ids,
        session_id=session_id,
        deps=_planner_deps(),
    )


def planner_next_step_v3(
    *,
    user: User,
    planner_run_id: str,
    step_key: str,
    answer_value: str,
    answer_mode: str,
    client_step_seq: int,
) -> Dict[str, Any]:
    return _planner_service.planner_next_step_v3(
        user=user,
        planner_run_id=planner_run_id,
        step_key=step_key,
        answer_value=answer_value,
        answer_mode=answer_mode,
        client_step_seq=client_step_seq,
        deps=_planner_deps(),
    )


def get_planner_run_for_user(user: User, run_id: str) -> PlannerRun | None:
    return _planner_service.get_planner_run_for_user(user=user, run_id=run_id)


def _validate_planner_answers(blueprint: Dict[str, Any], answers: Dict[str, Any]) -> str:
    return _planner_service._validate_planner_answers(blueprint=blueprint, answers=answers)


def planner_execute_v3(
    *,
    user: User,
    planner_run_id: str,
    answers: Dict[str, Any],
    path_taken: List[Dict[str, Any]] | None = None,
    session_id: int | None = None,
    client_summary: str = "",
    request_id: str = "-",
) -> Dict[str, Any]:
    return _planner_service.planner_execute_v3(
        user=user,
        planner_run_id=planner_run_id,
        answers=answers,
        path_taken=path_taken,
        session_id=session_id,
        client_summary=client_summary,
        request_id=request_id,
        deps=_planner_deps(),
    )


def planner_cancel_v3(*, user: User, planner_run_id: str) -> Dict[str, Any]:
    return _planner_service.planner_cancel_v3(user=user, planner_run_id=planner_run_id, deps=_planner_deps())
