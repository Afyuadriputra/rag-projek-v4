import re

DAY_WORDS = {
    "senin", "selasa", "rabu", "kamis", "jumat", "jum'at", "sabtu", "minggu",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}

TIME_RANGE_RE = re.compile(r"(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})")
TIME_SINGLE_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
SEMESTER_RE = re.compile(r"\bsemester\s*(\d+)\b", re.IGNORECASE)

HEADER_MAP = {
    "kode": "kode",
    "kode mk": "kode",
    "kode matakuliah": "kode",
    "kode matkul": "kode",
    "course code": "kode",
    "mk": "kode",
    "mata kuliah": "mata_kuliah",
    "matakuliah": "mata_kuliah",
    "nama mata kuliah": "mata_kuliah",
    "nama matakuliah": "mata_kuliah",
    "course name": "mata_kuliah",
    "nama": "mata_kuliah",
    "hari": "hari",
    "day": "hari",
    "jam": "jam",
    "sesi": "sesi",
    "session": "sesi",
    "waktu": "jam",
    "time": "jam",
    "sks": "sks",
    "credit": "sks",
    "credits": "sks",
    "dosen": "dosen",
    "pengampu": "dosen",
    "dosen pengampu": "dosen",
    "lecturer": "dosen",
    "kelas": "kelas",
    "class": "kelas",
    "ruang": "ruang",
    "room": "ruang",
    "lab": "ruang",
    "semester": "semester",
    "smt": "semester",
    "sm t": "semester",
    "s m t": "semester",
}

CANON_LABELS = {
    "kode": "Kode",
    "mata_kuliah": "Mata Kuliah",
    "hari": "Hari",
    "jam": "Jam",
    "sesi": "Sesi",
    "sks": "SKS",
    "dosen": "Dosen Pengampu",
    "kelas": "Kelas",
    "ruang": "Ruang",
    "semester": "Semester",
}

SCHEDULE_CANON_ORDER = [
    "hari",
    "sesi",
    "jam",
    "kode",
    "mata_kuliah",
    "sks",
    "kelas",
    "ruang",
    "dosen",
    "semester",
    "page",
]

MAX_SCHEDULE_ROWS = 2500
DAY_CANON = {
    "senin": "Senin",
    "selasa": "Selasa",
    "rabu": "Rabu",
    "kamis": "Kamis",
    "jumat": "Jumat",
    "sabtu": "Sabtu",
    "minggu": "Minggu",
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
}

TRANSCRIPT_TITLE_HINTS = (
    "khs", "transkrip", "hasil studi", "kartu hasil studi", "nilai", "huruf mutu", "ipk", "ips",
)
TRANSCRIPT_COL_HINTS = ("grade", "huruf mutu", "bobot", "kredit", "nilai", "ips", "ipk")
TRANSCRIPT_GRADE_WHITELIST = {
    "A", "B", "C", "D", "E", "AB", "BC", "CD", "A-", "B+", "B-", "C+", "C-", "D+", "D-",
}
TRANSCRIPT_ROW_RE = re.compile(r"^\s*(\d{1,3})\s+([A-Z0-9]{5,12})\s+(.+?)\s+(\d{1,2})\s+(.+?)\s*$", re.IGNORECASE)
TRANSCRIPT_PENDING_RE = re.compile(r"isi\s+kuisioner\s+terlebih\s+dahulu", re.IGNORECASE)
TRANSCRIPT_GRADE_PREFIX_RE = re.compile(r"^(A\-|AB|A|B\+|B\-|BC|B|C\+|C\-|CD|C|D\+|D\-|D|E)(?:\s|$)", re.IGNORECASE)

UNIVERSAL_TRANSCRIPT_SYSTEM_PROMPT = (
    "Kamu adalah Universal Data Extractor spesialis akademik Indonesia.\n"
    "Tugasmu adalah membaca teks berantakan dari PDF transkrip/KHS kampus dan mengubahnya menjadi array JSON yang seragam.\n"
    "Aturan terjemahan:\n"
    "- Jika kampus memakai kata 'Kredit' atau 'Bobot', petakan itu ke key 'sks'.\n"
    "- Jika kampus memakai kata 'Grade' atau 'Huruf Mutu', petakan itu ke 'nilai_huruf'.\n"
    "- Abaikan baris yang bukan mata kuliah (seperti kop surat, nama rektor, dll).\n\n"
    "Wajib kembalikan format JSON persis seperti schema ini:\n"
    "{\n"
    "  \"data_rows\": [\n"
    "    {\"semester\": 1, \"mata_kuliah\": \"Kalkulus\", \"sks\": 3, \"nilai_huruf\": \"A\"}\n"
    "  ]\n"
    "}\n"
)

SCHEDULE_TITLE_HINTS = ("jadwal", "krs", "rencana studi", "perkuliahan", "kuliah", "schedule", "timetable")
SCHEDULE_COL_HINTS = ("hari", "day", "jam", "waktu", "time", "mata kuliah", "matakuliah", "ruang", "room", "kelas", "krs")
UNIVERSAL_SCHEDULE_SYSTEM_PROMPT = (
    "Anda adalah Data Extractor akademik.\n"
    "Baca teks berantakan dari PDF kampus ini.\n"
    "Abaikan kop surat.\n"
    "Petakan istilah lokal (misal: 'Pukul' -> 'jam_mulai', 'Ruang/Lab/Room' -> 'ruangan').\n"
    "Kembalikan HANYA JSON object valid tanpa markdown.\n"
    "Jika baris bukan mata kuliah, abaikan.\n\n"
    "Schema wajib:\n"
    "{\n"
    "  \"data_rows\": [\n"
    "    {\"hari\":\"Senin\", \"jam_mulai\":\"07:00\", \"jam_selesai\":\"08:40\", \"mata_kuliah\":\"Kalkulus\", \"ruangan\":\"A1\"}\n"
    "  ]\n"
    "}\n"
)

