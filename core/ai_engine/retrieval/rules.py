import re
from typing import Optional, Dict, Any

_SEMESTER_RE = re.compile(r"\bsemester\s*(\d+)\b", re.IGNORECASE)
_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
_WEIGHT_RE = re.compile(r"(?:bobot|weight)\s*[:=]?\s*(\d{1,3})", re.IGNORECASE)
_TARGET_NUM_RE = re.compile(r"(?:target|nilai akhir|final)\s*[:=]?\s*(\d{2,3})", re.IGNORECASE)
_TARGET_LETTER_RE = re.compile(r"(?:target|supaya|agar)\s*(?:nilai\s*)?([abcde])\b", re.IGNORECASE)

_GRADE_KEYWORDS = [
    "hitung nilai",
    "berapa nilai",
    "nilai uas",
    "nilai akhir",
    "target nilai",
    "grade rescue",
    "naik ke b",
    "naik ke a",
]

_LETTER_TO_SCORE = {
    "a": 80.0,
    "b": 70.0,
    "c": 56.0,
    "d": 45.0,
    "e": 0.0,
}


def infer_doc_type(q: str) -> Optional[str]:
    ql = (q or "").lower()
    if any(k in ql for k in ["jadwal", "jam", "hari", "ruang", "kelas"]):
        return "schedule"
    if any(k in ql for k in ["transkrip", "nilai", "grade", "bobot", "ipk", "ips"]):
        return "transcript"
    if "krs" in ql:
        return "schedule"
    return None


def is_grade_rescue_query(q: str) -> bool:
    ql = (q or "").lower()
    if any(k in ql for k in _GRADE_KEYWORDS):
        return True

    # Heuristik tambahan agar frasa seperti
    # "UTS 60 bobot 40 target B" tetap terbaca intent grade.
    has_assessment = any(k in ql for k in ["uts", "uas", "quiz", "tugas", "nilai"])
    has_weight = bool(_WEIGHT_RE.search(ql)) or ("bobot" in ql) or ("weight" in ql)
    has_target = bool(_TARGET_NUM_RE.search(ql) or _TARGET_LETTER_RE.search(ql)) or ("target" in ql)
    return (has_assessment and has_target) or (has_weight and has_target)


def extract_grade_calc_input(q: str) -> Optional[Dict[str, Any]]:
    """
    Parse ringan dari kalimat user untuk kebutuhan grade calculator.
    Contoh yang didukung:
    - \"UTS 55 bobot 40 target B\"
    - \"nilai sekarang 60, bobot 30, target 75\"
    """
    text = (q or "").strip()
    if not text:
        return None

    nums = []
    for m in _NUM_RE.findall(text):
        try:
            nums.append(float(m.replace(",", ".")))
        except Exception:
            pass

    if not nums:
        return None

    # current score default: angka pertama
    current_score = float(nums[0])
    current_weight = 40.0
    target_score = 70.0

    m_weight = _WEIGHT_RE.search(text)
    if m_weight:
        try:
            current_weight = float(m_weight.group(1))
        except Exception:
            current_weight = 40.0
    elif len(nums) >= 2 and 0 <= nums[1] <= 100:
        # fallback heuristik (angka kedua sering bobot)
        current_weight = float(nums[1])

    m_target_num = _TARGET_NUM_RE.search(text)
    if m_target_num:
        try:
            target_score = float(m_target_num.group(1))
        except Exception:
            target_score = 70.0
    else:
        m_target_letter = _TARGET_LETTER_RE.search(text)
        if m_target_letter:
            target_score = _LETTER_TO_SCORE.get(m_target_letter.group(1).lower(), 70.0)
        elif len(nums) >= 3 and 0 <= nums[2] <= 100:
            target_score = float(nums[2])

    current_weight = max(0.0, min(100.0, current_weight))
    remaining_weight = max(0.0, 100.0 - current_weight)

    return {
        "achieved_components": [
            {"name": "Nilai Saat Ini", "weight": current_weight, "score": current_score}
        ],
        "target_final_score": target_score,
        "remaining_weight": remaining_weight,
        "current_score": current_score,
        "current_weight": current_weight,
        "target_score": target_score,
    }
