# core/service.py
import time
import logging
from typing import Any, Dict, List, Tuple

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile

from .models import AcademicDocument, ChatHistory, ChatSession, UserQuota
from .ai_engine.ingest import process_document
from .ai_engine.retrieval import ask_bot
from .ai_engine.vector_ops import delete_vectors_for_doc, delete_vectors_for_doc_strict
from .ai_engine.config import get_vectorstore
from .ai_engine.retrieval.llm import (
    build_llm,
    get_backup_models,
    get_runtime_openrouter_config,
    invoke_text,
)
from .ai_engine.retrieval.prompt import PLANNER_OUTPUT_TEMPLATE
from .ai_engine.retrieval.rules import extract_grade_calc_input, is_grade_rescue_query
from .academic import planner as planner_engine
from .academic.grade_calculator import (
    analyze_transcript_risks,
    calculate_required_score,
)


logger = logging.getLogger(__name__)



# =========================
# Helpers (logic layer)
# =========================
def bytes_to_human(n: int) -> str:
    """
    [HELPER] Konversi ukuran byte -> teks ramah manusia (KB/MB/GB).
    Dipakai untuk menampilkan storage usage di UI dashboard/documents.
    """
    try:
        n = int(n)
    except Exception:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.2f} {u}" if u != "B" else f"{int(size)} {u}"
        size /= 1024
    return f"{int(n)} B"


def serialize_documents_for_user(user: User, limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
    """
    [HELPER] Ambil daftar dokumen milik user dari DB + hitung total ukuran file.
    Output:
      - documents: list dict (untuk ditampilkan di frontend)
      - total_bytes: total ukuran semua file (buat progress quota)
    """
    docs_qs = AcademicDocument.objects.filter(user=user).order_by("-uploaded_at")[:limit]
    documents: List[Dict[str, Any]] = []
    total_bytes = 0

    for d in docs_qs:
        size = 0
        try:
            if d.file and hasattr(d.file, "size"):
                size = d.file.size or 0
        except Exception:
            size = 0

        total_bytes += size
        documents.append({
            "id": d.id,
            "title": d.title,
            "is_embedded": d.is_embedded,
            "uploaded_at": d.uploaded_at.strftime("%Y-%m-%d %H:%M"),
            "size_bytes": size,
        })

    return documents, total_bytes


def serialize_sessions_for_user(user: User, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    qs = ChatSession.objects.filter(user=user).order_by("-updated_at")
    sessions = qs[offset:offset + limit]
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M"),
        }
        for s in sessions
    ]


def _get_or_create_default_session(user: User) -> ChatSession:
    session = ChatSession.objects.filter(user=user).order_by("-updated_at").first()
    if session:
        return session
    return ChatSession.objects.create(user=user, title="Chat Baru")


def _attach_legacy_history_to_session(user: User, session: ChatSession) -> None:
    """
    Migrasi ringan: history lama tanpa session diarahkan ke session default.
    """
    ChatHistory.objects.filter(user=user, session__isnull=True).update(session=session)


def build_storage_payload(total_bytes: int, quota_bytes: int) -> Dict[str, Any]:
    """
    [HELPER] Bentuk payload storage (used/quota/persen) untuk UI.
    Dipakai di dashboard & endpoint documents.
    """
    quota_bytes = max(int(quota_bytes), 1)
    used_pct = int(min(100, (total_bytes / quota_bytes) * 100))
    return {
        "used_bytes": int(total_bytes),
        "quota_bytes": int(quota_bytes),
        "used_pct": used_pct,
        "used_human": bytes_to_human(total_bytes),
        "quota_human": bytes_to_human(quota_bytes),
    }


# =========================
# Use-cases (business logic)
# =========================
def get_dashboard_props(user: User, quota_bytes: int) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: DASHBOARD]
    Menyusun semua data awal untuk halaman utama chat (Inertia page):
      1) Profile user
      2) Riwayat chat user (initialHistory)
      3) Daftar dokumen user
      4) Informasi storage/quota
    """
    session = _get_or_create_default_session(user)
    _attach_legacy_history_to_session(user, session)

    histories = ChatHistory.objects.filter(user=user, session=session).order_by("timestamp")
    history_data = [
        {
            "question": h.question,
            "answer": h.answer,
            "time": h.timestamp.strftime("%H:%M"),
            "date": h.timestamp.strftime("%Y-%m-%d"),
        }
        for h in histories
    ]

    documents, total_bytes = serialize_documents_for_user(user, limit=50)
    storage = build_storage_payload(total_bytes, quota_bytes)
    sessions = serialize_sessions_for_user(user, limit=50)

    return {
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "activeSessionId": session.id,
        "sessions": sessions,
        "initialHistory": history_data,
        "documents": documents,
        "storage": storage,
    }


def get_user_quota_bytes(user: User, default_quota_bytes: int) -> int:
    try:
        quota = UserQuota.objects.filter(user=user).first()
        if quota and quota.quota_bytes and quota.quota_bytes > 0:
            return int(quota.quota_bytes)
    except Exception:
        pass
    return int(default_quota_bytes)


def get_documents_payload(user: User, quota_bytes: int) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: LIST DOKUMEN]
    Payload untuk endpoint GET /api/documents/:
      - daftar dokumen milik user
      - storage usage/quota
    """
    documents, total_bytes = serialize_documents_for_user(user, limit=50)
    storage = build_storage_payload(total_bytes, quota_bytes)
    return {"documents": documents, "storage": storage}


def upload_files_batch(user: User, files: List[UploadedFile], quota_bytes: int) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: UPLOAD + INGEST]
    Dipanggil oleh endpoint POST /api/upload/
    Alur sistem:
      1) Simpan file ke AcademicDocument (DB + media/)
      2) Ingest ke vector DB (Chroma) via process_document()
      3) Jika sukses -> is_embedded=True
      4) Jika gagal parsing -> hapus record agar DB bersih
    """
    success_count = 0
    error_count = 0
    errors: List[str] = []

    # cek kuota (total file yang sudah ada)
    _, total_bytes = serialize_documents_for_user(user, limit=100000)
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
    else:
        return {"status": "error", "msg": f"Gagal semua. Detail: {', '.join(errors)}"}


def _maybe_update_session_title(session: ChatSession, message: str) -> None:
    if not session or not message:
        return
    if (session.title or "").strip().lower() == "chat baru":
        title = message.strip()
        if len(title) > 60:
            title = title[:60] + "..."
        session.title = title
        session.save(update_fields=["title", "updated_at"])


def _build_grade_rescue_response(parsed: Dict[str, Any], calc: Dict[str, Any]) -> str:
    current_score = float(parsed.get("current_score", 0) or 0)
    current_weight = float(parsed.get("current_weight", 0) or 0)
    target_score = float(parsed.get("target_score", 70) or 70)
    remaining_weight = float(parsed.get("remaining_weight", 0) or 0)

    required = calc.get("required")
    possible = bool(calc.get("possible"))
    required_text = "-"
    if required is not None:
        required_text = f"{float(required):.2f}"

    status_text = "Masih memungkinkan." if possible else "Target ini sulit/tidak memungkinkan pada bobot tersisa."

    return (
        "## Ringkasan Grade Rescue\n"
        f"- Nilai saat ini: **{current_score:.2f}** (bobot **{current_weight:.0f}%**)\n"
        f"- Target akhir: **{target_score:.2f}**\n"
        f"- Bobot tersisa: **{remaining_weight:.0f}%**\n"
        f"- Nilai minimal pada komponen tersisa: **{required_text}**\n\n"
        "## Insight\n"
        f"- Status: **{status_text}**\n"
        f"- Poin yang masih dibutuhkan: **{float(calc.get('needed_points', 0) or 0):.2f}**\n\n"
        "## Opsi Lanjut\n"
        "1. Kirim detail komponen nilai (tugas/UTS/UAS) agar simulasi lebih akurat.\n"
        "2. Saya bisa bantu strategi belajar 2-4 minggu untuk kejar target."
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


def _append_verified_grade_rescue(
    answer: str,
    calc_input: Dict[str, Any] | None,
    calc_result: Dict[str, Any] | None,
) -> str:
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

    # Hindari duplikasi jika block sudah ada.
    if "Grade Rescue (Kalkulasi Sistem)" in (answer or ""):
        return answer
    return (answer or "").rstrip() + verified_block


def _planner_context_for_user(user: User, query: str) -> str:
    try:
        vectorstore = get_vectorstore()
        docs = vectorstore.similarity_search(query or "rencana studi", k=8, filter={"user_id": str(user.id)})
    except Exception:
        return ""

    if not docs:
        return ""

    parts: List[str] = []
    for i, doc in enumerate(docs[:5], start=1):
        content = (getattr(doc, "page_content", "") or "").strip()
        if not content:
            continue
        content = content[:1200]
        parts.append(f"[Doc {i}]\n{content}")
    return "\n\n".join(parts)


def _generate_planner_with_llm(
    user: User,
    collected: Dict[str, Any],
    grade_rescue_data: str,
    request_id: str = "-",
) -> str:
    runtime_cfg = get_runtime_openrouter_config()
    api_key = (runtime_cfg.get("api_key") or "").strip()
    if not api_key:
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

    backup_models = get_backup_models(
        str(runtime_cfg.get("model") or ""),
        runtime_cfg.get("backup_models"),
    )
    last_error = ""
    for model_name in backup_models:
        try:
            llm = build_llm(model_name, runtime_cfg)
            answer = invoke_text(llm, prompt).strip()
            if answer:
                return answer
        except Exception as e:
            last_error = str(e)
            continue

    if last_error:
        logger.warning("planner llm failed request_id=%s err=%s", request_id, last_error)
    return ""


def chat_and_save(user: User, message: str, request_id: str = "-", session_id: int | None = None) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: CHAT RAG + SIMPAN HISTORY]
    Dipanggil oleh endpoint POST /api/chat/
    Alur sistem:
      1) Jalankan RAG (retrieval + LLM) via ask_bot()
      2) Simpan jawaban ke ChatHistory (DB)
      3) Kembalikan response ke frontend

     Pembaruan penting:
    - ask_bot() sekarang mengembalikan dict:
        {"answer": "...", "sources": [...]}
      agar frontend bisa menampilkan "rujukan/source trace".
    """
    session: ChatSession | None = None
    if session_id:
        session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        session = ChatSession.objects.create(user=user, title="Chat Baru")

    parsed_grade = extract_grade_calc_input(message) if is_grade_rescue_query(message) else None
    if parsed_grade:
        calc = calculate_required_score(
            achieved_components=parsed_grade.get("achieved_components") or [],
            target_final_score=float(parsed_grade.get("target_final_score", 70) or 70),
            remaining_weight=float(parsed_grade.get("remaining_weight", 0) or 0),
        )
        result: Dict[str, Any] = {"answer": _build_grade_rescue_response(parsed_grade, calc), "sources": []}
    else:
        result = ask_bot(user.id, message, request_id=request_id)

    # Normalisasi output (biar backward compatible kalau suatu saat ask_bot return string)
    if isinstance(result, dict):
        answer = result.get("answer", "")
        sources = result.get("sources", []) or []
    else:
        answer = str(result)
        sources = []

    ChatHistory.objects.create(user=user, session=session, question=message, answer=answer)
    _maybe_update_session_title(session, message)
    if session:
        session.save(update_fields=["updated_at"])

    # Return ke API: answer + sources (sources bisa ditampilkan di UI)
    return {"answer": answer, "sources": sources, "session_id": session.id}


def list_sessions(user: User, limit: int = 50, page: int = 1) -> Dict[str, Any]:
    page = max(int(page), 1)
    limit = max(int(limit), 1)
    offset = (page - 1) * limit
    total = ChatSession.objects.filter(user=user).count()
    sessions = serialize_sessions_for_user(user, limit=limit, offset=offset)
    has_next = (offset + limit) < total
    return {
        "sessions": sessions,
        "pagination": {
            "page": page,
            "page_size": limit,
            "total": total,
            "has_next": has_next,
        },
    }


def create_session(user: User, title: str | None = None) -> Dict[str, Any]:
    t = (title or "").strip() or "Chat Baru"
    session = ChatSession.objects.create(user=user, title=t)
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": session.updated_at.strftime("%Y-%m-%d %H:%M"),
    }


def rename_session(user: User, session_id: int, title: str | None = None) -> Dict[str, Any] | None:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return None
    t = (title or "").strip() or "Chat Baru"
    session.title = t
    session.save(update_fields=["title", "updated_at"])
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": session.updated_at.strftime("%Y-%m-%d %H:%M"),
    }


def delete_session(user: User, session_id: int) -> bool:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return False
    session.delete()
    return True


def get_session_history(user: User, session_id: int) -> List[Dict[str, Any]]:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return []
    histories = ChatHistory.objects.filter(user=user, session=session).order_by("timestamp")
    return [
        {
            "question": h.question,
            "answer": h.answer,
            "time": h.timestamp.strftime("%H:%M"),
            "date": h.timestamp.strftime("%Y-%m-%d"),
        }
        for h in histories
    ]

def reingest_documents_for_user(user: User, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    """
    Re-ingest dokumen milik user tanpa upload ulang.
    - Hapus embedding lama dulu (by doc_id)
    - Jalankan process_document lagi
    """
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
            #  delete embeddings lama
            delete_vectors_for_doc(user_id=str(user.id), doc_id=str(doc.id), source=getattr(doc, "title", None))

            #  ingest ulang
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
    # Strict delete: jika vector masih tersisa, batalkan delete dokumen.
    ok, remaining = delete_vectors_for_doc_strict(
        user_id=str(user.id),
        doc_id=str(doc.id),
        source=getattr(doc, "title", None),
    )
    if not ok:
        raise RuntimeError(
            f"Gagal menghapus vector dokumen secara tuntas (doc_id={doc.id}, remaining={remaining})"
        )
    # Hapus file dari storage
    try:
        if doc.file:
            doc.file.delete(save=False)
    except Exception:
        pass
    doc.delete()
    return True


def planner_start(user: User) -> tuple[Dict[str, Any], Dict[str, Any]]:
    data_level = planner_engine.detect_data_level(user)
    state = planner_engine.build_initial_state(data_level=data_level)
    payload = planner_engine.get_step_payload(state)
    payload["planner_meta"] = {
        **(payload.get("planner_meta") or {}),
        "data_level": data_level,
        "mode": "planner",
    }
    return payload, state


def _build_planner_markdown(
    collected: Dict[str, Any],
    scenario: str | None = None,
    grade_rescue_md: str | None = None,
) -> str:
    jurusan = collected.get("jurusan") or "-"
    semester = collected.get("semester") or "-"
    goal = collected.get("goal") or "-"
    career = collected.get("career") or "-"
    time_pref = collected.get("time_pref") or "fleksibel"
    free_day = collected.get("free_day") or "tidak ada"

    scenario_text = ""
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
        f"- Skenario: {scenario_text or 'Mode normal'}.\n\n"
        "## ⚠️ Grade Rescue\n"
        f"{grade_rescue_md or '- Tidak ada input grade rescue khusus.'}\n\n"
        "## Selanjutnya\n"
        "1. 🔄 Buat opsi Padat\n"
        "2. 🔄 Buat opsi Santai\n"
        "3. ✏️ Ubah sesuatu\n"
        "4. ✅ Simpan rencana ini\n"
    ).strip()


def _ensure_planner_required_sections(answer: str, grade_rescue_md: str) -> str:
    text = (answer or "").strip()
    if not text:
        text = "## 📅 Jadwal\n- Belum ada output."

    checks = {
        "jadwal": "## 📅 Jadwal\n- Jadwal belum tersedia.",
        "rekomendasi mata kuliah": "## 🎯 Rekomendasi Mata Kuliah\n- Rekomendasi belum tersedia.",
        "keselarasan karir": "## 💼 Keselarasan Karir\n- Keselarasan karir belum tersedia.",
        "distribusi beban": "## ⚖️ Distribusi Beban\n- Distribusi beban belum tersedia.",
        "grade rescue": f"## ⚠️ Grade Rescue\n{grade_rescue_md}",
        "selanjutnya": (
            "## Selanjutnya\n"
            "1. 🔄 Buat opsi Padat\n"
            "2. 🔄 Buat opsi Santai\n"
            "3. ✏️ Ubah sesuatu\n"
            "4. ✅ Simpan rencana ini"
        ),
    }

    low = text.lower()
    for key, block in checks.items():
        if key not in low:
            text = f"{text}\n\n{block}"
            low = text.lower()
    return text


def planner_generate(user: User, state: Dict[str, Any], request_id: str = "-") -> Dict[str, Any]:
    collected = dict(state.get("collected_data") or {})
    scenario = str(collected.get("iterate_action") or "").strip().lower()
    grade_calc_input = collected.get("grade_calc_input")
    grade_calc_result = collected.get("grade_calc_result")
    grade_rescue_md = _build_grade_rescue_markdown(grade_calc_input, grade_calc_result)

    answer = _generate_planner_with_llm(
        user=user,
        collected=collected,
        grade_rescue_data=grade_rescue_md,
        request_id=request_id,
    )
    if not answer:
        # fallback deterministic agar planner tetap jalan tanpa LLM.
        _ = analyze_transcript_risks([])
        answer = _build_planner_markdown(collected, scenario=scenario, grade_rescue_md=grade_rescue_md)
    answer = _ensure_planner_required_sections(answer, grade_rescue_md=grade_rescue_md)
    answer = _append_verified_grade_rescue(answer, grade_calc_input, grade_calc_result)

    return {
        "type": "planner_output",
        "answer": answer,
        "options": [
            {"id": 1, "label": "🔄 Buat opsi Padat", "value": "dense"},
            {"id": 2, "label": "🔄 Buat opsi Santai", "value": "relaxed"},
            {"id": 3, "label": "✏️ Ubah sesuatu", "value": "edit"},
            {"id": 4, "label": "✅ Simpan rencana ini", "value": "save"},
        ],
        "allow_custom": False,
        "planner_meta": {"step": "iterate", "mode": "planner", "request_id": request_id},
    }


def planner_continue(
    user: User,
    planner_state: Dict[str, Any],
    message: str = "",
    option_id: int | None = None,
    request_id: str = "-",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    working_state = dict(planner_state or {})
    collected_data = dict(working_state.get("collected_data") or {})

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

    state = planner_engine.process_answer(working_state, message=message, option_id=option_id)

    if state.get("current_step") == "generate":
        payload = planner_generate(user=user, state=state, request_id=request_id)
        state["current_step"] = "iterate"
        payload["planner_meta"] = {
            **(payload.get("planner_meta") or {}),
            "data_level": state.get("data_level", {}),
        }
        return payload, state

    payload = planner_engine.get_step_payload(state)
    payload["planner_meta"] = {
        **(payload.get("planner_meta") or {}),
        "data_level": state.get("data_level", {}),
        "mode": "planner",
    }
    return payload, state
