from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import yaml


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "core" / "test" / "fixtures" / "uploaded_docs_complex"
DATA_DIR = ROOT / "core" / "test" / "data"

GRADE_POINTS = {
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.5,
    "B": 3.0,
    "C+": 2.5,
    "C": 2.0,
    "D": 1.0,
    "E": 0.0,
}


@dataclass
class MajorSpec:
    key: str
    label: str
    code_prefix: str
    file_name: str
    header_lines: list[str]


MAJORS = [
    MajorSpec(
        key="ti",
        label="Teknik Informatika",
        code_prefix="IF",
        file_name="khs_ti_mahasiswa_c_200x8.pdf",
        header_lines=[
            "Header A: No | Kode | Mata Kuliah | SKS | Nilai | Bobot | Semester",
            "Header B: MK | Course | Credits | Grade | Point | Term",
        ],
    ),
    MajorSpec(
        key="hukum",
        label="Ilmu Hukum",
        code_prefix="HK",
        file_name="khs_hukum_mahasiswa_d_200x8.pdf",
        header_lines=[
            "Header A: Semester | Kode MK | Nama MK | Nilai | SKS | Mutu",
            "Header B: Term | Subject Code | Subject | Grade | Credit | Point",
        ],
    ),
    MajorSpec(
        key="ekonomi",
        label="Ekonomi",
        code_prefix="EK",
        file_name="khs_ekonomi_mahasiswa_e_200x8.pdf",
        header_lines=[
            "Header A: No | MK | SKS | Grade | Semester | Catatan",
            "Header B: Course | Credit | Letter | Term | Remarks",
        ],
    ),
    MajorSpec(
        key="kedokteran",
        label="Kedokteran",
        code_prefix="KD",
        file_name="khs_kedokteran_mahasiswa_f_200x8.pdf",
        header_lines=[
            "Header A: Blok | Kode | Mata Ajar | SKS | Nilai | Semester",
            "Header B: Block | Code | Subject | Credit | Grade | Term",
        ],
    ),
    MajorSpec(
        key="sastra",
        label="Sastra",
        code_prefix="SS",
        file_name="khs_sastra_mahasiswa_g_200x8.pdf",
        header_lines=[
            "Header A: No | Course | Term | SKS | Grade | Bobot",
            "Header B: MK | Semester | Credit | Letter | Point",
        ],
    ),
]


def _escape_pdf_text(s: str) -> str:
    return s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')


def write_text_pdf(path: Path, pages: list[list[str]]) -> None:
    """Write a simple multi-page extractable-text PDF using built-in Helvetica."""
    objs: list[bytes] = []

    def add_obj(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    catalog_id = add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    _ = catalog_id
    pages_id = 2

    page_obj_ids: list[int] = []
    content_obj_ids: list[int] = []

    # placeholder for pages tree object
    objs.append(b"")

    # Font object
    font_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for lines in pages:
        chunks = ["BT", "/F1 9 Tf", "45 805 Td"]
        first = True
        for ln in lines:
            ln = _escape_pdf_text(ln)
            if not first:
                chunks.append("0 -12 Td")
            chunks.append(f"({ln}) Tj")
            first = False
        chunks.append("ET")
        stream = "\n".join(chunks).encode("latin-1", errors="replace")
        content_id = add_obj(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        content_obj_ids.append(content_id)

        page_id = add_obj(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 "
            + str(font_id).encode()
            + b" 0 R >> >> /Contents "
            + str(content_id).encode()
            + b" 0 R >>"
        )
        page_obj_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objs[pages_id - 1] = f"<< /Type /Pages /Count {len(page_obj_ids)} /Kids [{kids}] >>".encode()

    out = bytearray()
    out.extend(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")

    xref_start = len(out)
    out.extend(f"xref\n0 {len(objs)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())

    out.extend(b"trailer\n")
    out.extend(f"<< /Size {len(objs)+1} /Root 1 0 R >>\n".encode())
    out.extend(b"startxref\n")
    out.extend(f"{xref_start}\n".encode())
    out.extend(b"%%EOF\n")

    path.write_bytes(out)


def make_rows(spec: MajorSpec, n_rows: int = 200) -> list[dict]:
    grade_cycle = ["A", "A-", "B+", "B", "C+", "C", "D", "E"]
    rows: list[dict] = []
    for i in range(1, n_rows + 1):
        semester = ((i - 1) % 7) + 1
        sks = 2 + (i % 3)  # 3,4,2 cycle
        grade = grade_cycle[(i + len(spec.key)) % len(grade_cycle)]
        point = GRADE_POINTS[grade]
        rows.append(
            {
                "no": i,
                "code": f"{spec.code_prefix}{1000 + i}",
                "course": f"{spec.label} Course {i:03d}",
                "sks": sks,
                "grade": grade,
                "point": point,
                "semester": semester,
            }
        )
    return rows


def build_pages(spec: MajorSpec, rows: list[dict]) -> list[list[str]]:
    pages: list[list[str]] = []
    rows_per_page = 25
    total_pages = 8
    for p in range(total_pages):
        start = p * rows_per_page
        end = start + rows_per_page
        chunk = rows[start:end]

        lines = [
            f"KHS KOMPLEKS {spec.label} - 200 rows - page {p+1}/8",
            "Layout Varian: split-header, shifted-columns, mixed labels",
            *spec.header_lines,
            "-- DATA ROWS --",
        ]

        for r in chunk:
            if spec.key in {"ti", "sastra"}:
                line = (
                    f"ROW {r['no']:03d} | Code={r['code']} | Course={r['course']} | "
                    f"SKS={r['sks']} | Grade={r['grade']} | Bobot={r['point']} | Semester={r['semester']}"
                )
            elif spec.key in {"hukum", "ekonomi"}:
                line = (
                    f"ROW {r['no']:03d} | Semester={r['semester']} | MK={r['course']} | "
                    f"Nilai={r['grade']} | SKS={r['sks']} | Point={r['point']} | Kode={r['code']}"
                )
            else:
                line = (
                    f"ROW {r['no']:03d} | Blok={r['semester']} | Subject={r['course']} | "
                    f"Credit={r['sks']} | Grade={r['grade']} | Code={r['code']} | Point={r['point']}"
                )
            lines.append(line)

        lines.append("-- END PAGE --")
        pages.append(lines)

    return pages


def summarize_major(rows: list[dict], source: str) -> dict:
    total_sks = sum(int(r["sks"]) for r in rows)
    total_matkul = len(rows)
    total_points = sum(float(r["point"]) * int(r["sks"]) for r in rows)
    ipk = round(total_points / total_sks, 2)

    count_d = sum(1 for r in rows if r["grade"] == "D")
    count_e = sum(1 for r in rows if r["grade"] == "E")
    count_tidak_lulus = count_d + count_e

    semester_stats = {}
    for sem in range(1, 8):
        sem_rows = [r for r in rows if r["semester"] == sem]
        semester_stats[f"semester_{sem}"] = {
            "sks": sum(int(r["sks"]) for r in sem_rows),
            "matkul": len(sem_rows),
        }

    ranked = sorted(rows, key=lambda x: (float(x["point"]), int(x["sks"]), -int(x["no"])), reverse=True)
    top_3 = [r["course"] for r in ranked[:3]]
    low_3 = [r["course"] for r in sorted(rows, key=lambda x: (float(x["point"]), int(x["sks"]), int(x["no"])))[:3]]

    return {
        "source": source,
        "total_sks": total_sks,
        "total_matkul": total_matkul,
        "ipk": ipk,
        "count_nilai_d": count_d,
        "count_nilai_e": count_e,
        "count_tidak_lulus": count_tidak_lulus,
        "semester_stats": semester_stats,
        "top_3_matkul_tertinggi": top_3,
        "top_3_matkul_terendah": low_3,
    }


def build_aggregate_pdf(major_facts: dict[str, dict]) -> list[list[str]]:
    ipk_rank = sorted(((k, v["ipk"]) for k, v in major_facts.items()), key=lambda x: x[1], reverse=True)
    sks_rank = sorted(((k, v["total_sks"]) for k, v in major_facts.items()), key=lambda x: x[1], reverse=True)
    heavy = max(
        ((k, max(v["semester_stats"].items(), key=lambda it: it[1]["sks"])) for k, v in major_facts.items()),
        key=lambda x: x[1][1]["sks"],
    )

    pages = []
    page1 = [
        "REKAP LINTAS JURUSAN KOMPLEKS 2026",
        "Layout campuran dan tabel agregat",
        "Columns: Jurusan | Total SKS | Total MK | IPK | D | E | Tidak Lulus",
    ]
    for key, fact in major_facts.items():
        page1.append(
            f"{key.upper()} | {fact['total_sks']} | {fact['total_matkul']} | {fact['ipk']} | "
            f"{fact['count_nilai_d']} | {fact['count_nilai_e']} | {fact['count_tidak_lulus']}"
        )
    pages.append(page1)

    page2 = ["RANKING IPK"] + [f"{i+1}. {k.upper()} : {v}" for i, (k, v) in enumerate(ipk_rank)]
    pages.append(page2)

    page3 = ["RANKING TOTAL SKS"] + [f"{i+1}. {k.upper()} : {v}" for i, (k, v) in enumerate(sks_rank)]
    pages.append(page3)

    hk, (sem_key, sem_stat) = heavy
    page4 = [
        "SEMESTER TERBERAT LINTAS JURUSAN",
        f"jurusan_terberat={hk.upper()}",
        f"semester_terberat={sem_key.replace('semester_', '')}",
        f"sks_semester_terberat={sem_stat['sks']}",
    ]
    pages.append(page4)

    while len(pages) < 8:
        idx = len(pages) + 1
        pages.append([
            f"APPENDIX PAGE {idx}",
            "Catatan: dokumen ini dibuat untuk regression test RAG kompleks.",
            "Termasuk variasi format jurusan dan tabel panjang.",
        ])

    return pages


def write_ground_truth(major_facts: dict[str, dict]) -> None:
    ipk_rank = [k for k, _ in sorted(((k, v["ipk"]) for k, v in major_facts.items()), key=lambda x: x[1], reverse=True)]
    sks_rank = [k for k, _ in sorted(((k, v["total_sks"]) for k, v in major_facts.items()), key=lambda x: x[1], reverse=True)]

    heavy_major = None
    heavy_sem = None
    heavy_sks = -1
    for k, v in major_facts.items():
        sem_key, sem_stat = max(v["semester_stats"].items(), key=lambda it: it[1]["sks"])
        if sem_stat["sks"] > heavy_sks:
            heavy_sks = sem_stat["sks"]
            heavy_major = k
            heavy_sem = int(sem_key.split("_")[1])

    gt = {
        "version": 1,
        "dataset_root": "core/test/fixtures/uploaded_docs_complex",
        "facts": {
            **{f"{k}_rekap": v for k, v in major_facts.items()},
            "lintas_jurusan_kompleks_2026": {
                "source": "rekap_lintas_jurusan_kompleks_2026.pdf",
                "ranking_ipk": ipk_rank,
                "ranking_total_sks": sks_rank,
                "jurusan_terberat": heavy_major,
                "semester_terberat": heavy_sem,
                "sks_semester_terberat": heavy_sks,
                "distribusi_grade": {
                    k: {
                        "d": v["count_nilai_d"],
                        "e": v["count_nilai_e"],
                        "tidak_lulus": v["count_tidak_lulus"],
                    }
                    for k, v in major_facts.items()
                },
            },
        },
    }
    (DATA_DIR / "rag_uploaded_docs_complex_ground_truth.yaml").write_text(
        yaml.safe_dump(gt, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def build_mapping(major_facts: dict[str, dict]) -> dict:
    groups = {f"{k}_docs": [v["source"]] for k, v in major_facts.items()}
    groups["lintas_jurusan"] = ["rekap_lintas_jurusan_kompleks_2026.pdf"]
    groups["all_uploaded_complex"] = [v["source"] for v in major_facts.values()] + ["rekap_lintas_jurusan_kompleks_2026.pdf"]

    queries = []
    qid = 1

    for k, v in major_facts.items():
        base = f"{k}_rekap"
        queries.extend([
            {
                "id": f"cxq{qid:03d}",
                "query": f"rekap hasil studi jurusan {k} semester 1 sampai 7",
                "pipeline_in": ["structured_analytics", "rag_semantic"],
                "intent_route_in": ["analytical_tabular", "default_rag"],
                "expected_validation_in": ["passed", "skipped_strict", "strict_no_fallback", "not_applicable"],
                "allowed_sources_group": f"{k}_docs",
                "source_match_mode": "any_of",
                "must_contain_any": ["hasil studi", "semester", k],
                "must_not_contain": ["resep"],
                "expected_numbers": [f"{base}.total_sks", f"{base}.total_matkul"],
            },
            {
                "id": f"cxq{qid+1:03d}",
                "query": f"berapa ipk jurusan {k}",
                "pipeline_in": ["structured_analytics", "rag_semantic"],
                "intent_route_in": ["analytical_tabular", "default_rag"],
                "expected_validation_in": ["passed", "skipped_strict", "strict_no_fallback", "not_applicable"],
                "allowed_sources_group": f"{k}_docs",
                "source_match_mode": "any_of",
                "must_contain_any": ["ipk", k],
                "must_not_contain": [],
                "expected_numbers": [f"{base}.ipk"],
            },
            {
                "id": f"cxq{qid+2:03d}",
                "query": f"jumlah nilai d dan e jurusan {k}",
                "pipeline_in": ["structured_analytics", "rag_semantic"],
                "intent_route_in": ["analytical_tabular", "default_rag"],
                "expected_validation_in": ["passed", "skipped_strict", "strict_no_fallback", "not_applicable"],
                "allowed_sources_group": f"{k}_docs",
                "source_match_mode": "any_of",
                "must_contain_any": ["nilai", "d", "e", k],
                "must_not_contain": [],
                "expected_numbers": [f"{base}.count_nilai_d", f"{base}.count_nilai_e", f"{base}.count_tidak_lulus"],
            },
            {
                "id": f"cxq{qid+3:03d}",
                "query": f"@{v['source']} total sks nya berapa",
                "pipeline_in": ["structured_analytics", "rag_semantic"],
                "intent_route_in": ["analytical_tabular", "default_rag"],
                "expected_validation_in": ["passed", "skipped_strict", "strict_no_fallback", "not_applicable"],
                "allowed_sources_group": f"{k}_docs",
                "source_match_mode": "any_of",
                "must_contain_any": ["sks", k],
                "must_not_contain": [],
                "expected_numbers": [f"{base}.total_sks"],
            },
            {
                "id": f"cxq{qid+4:03d}",
                "query": f"semester terberat jurusan {k} berapa sks",
                "pipeline_in": ["rag_semantic", "structured_analytics"],
                "intent_route_in": ["default_rag", "analytical_tabular"],
                "expected_validation_in": ["passed", "not_applicable", "skipped_strict"],
                "allowed_sources_group": "lintas_jurusan",
                "source_match_mode": "any_of",
                "must_contain_any": ["semester", "terberat", k],
                "must_not_contain": [],
                "expected_numbers": [f"{base}.semester_stats.semester_1.sks"],
            },
            {
                "id": f"cxq{qid+5:03d}",
                "query": f"top 3 mata kuliah nilai tertinggi jurusan {k}",
                "pipeline_in": ["rag_semantic", "structured_analytics"],
                "intent_route_in": ["default_rag", "analytical_tabular"],
                "expected_validation_in": ["passed", "not_applicable", "skipped_strict"],
                "allowed_sources_group": f"{k}_docs",
                "source_match_mode": "any_of",
                "must_contain_any": ["top", "mata kuliah", "nilai"],
                "must_not_contain": [],
            },
        ])
        qid += 6

    # cross-major + guards -> bring to 40
    extra = [
        {
            "id": f"cxq{qid:03d}",
            "query": "bandingkan ipk semua jurusan",
            "pipeline_in": ["rag_semantic"],
            "intent_route_in": ["default_rag"],
            "expected_validation_in": ["passed", "not_applicable"],
            "allowed_sources_group": "lintas_jurusan",
            "source_match_mode": "any_of",
            "must_contain_any": ["ipk", "jurusan"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+1:03d}",
            "query": "bandingkan total sks semua jurusan",
            "pipeline_in": ["rag_semantic"],
            "intent_route_in": ["default_rag"],
            "expected_validation_in": ["passed", "not_applicable"],
            "allowed_sources_group": "lintas_jurusan",
            "source_match_mode": "any_of",
            "must_contain_any": ["sks", "jurusan"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+2:03d}",
            "query": "berapa nomor ijazah saya",
            "pipeline_in": ["rag_semantic", "structured_analytics"],
            "intent_route_in": ["default_rag", "analytical_tabular"],
            "expected_validation_in": ["no_grounding_evidence"],
            "allowed_sources_group": "all_uploaded_complex",
            "source_match_mode": "any_of",
            "require_source_match": False,
            "must_contain_any": ["dokumen", "tidak", "cukup"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+3:03d}",
            "query": "resep ayam kecap",
            "pipeline_in": ["route_guard"],
            "intent_route_in": ["out_of_domain"],
            "expected_validation_in": ["not_applicable"],
            "allowed_sources_group": "all_uploaded_complex",
            "source_match_mode": "any_of",
            "require_source_match": False,
            "must_contain_any": ["asisten akademik"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+4:03d}",
            "query": "cara jadi dukun sakti",
            "pipeline_in": ["route_guard"],
            "intent_route_in": ["out_of_domain"],
            "expected_validation_in": ["not_applicable"],
            "allowed_sources_group": "all_uploaded_complex",
            "source_match_mode": "any_of",
            "require_source_match": False,
            "must_contain_any": ["asisten akademik"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+5:03d}",
            "query": "rekp nilia yg ga luls smua smstr semua jurusan",
            "pipeline_in": ["structured_analytics", "rag_semantic"],
            "intent_route_in": ["analytical_tabular", "default_rag"],
            "expected_validation_in": ["passed", "skipped_strict", "strict_no_fallback", "not_applicable", "no_grounding_evidence"],
            "allowed_sources_group": "lintas_jurusan",
            "source_match_mode": "any_of",
            "must_contain_any": ["nilai", "semester", "jurusan"],
            "must_not_contain": ["politik"],
        },
        {
            "id": f"cxq{qid+6:03d}",
            "query": "which major has the heaviest semester load",
            "pipeline_in": ["rag_semantic"],
            "intent_route_in": ["default_rag"],
            "expected_validation_in": ["passed", "not_applicable"],
            "allowed_sources_group": "lintas_jurusan",
            "source_match_mode": "any_of",
            "must_contain_any": ["heaviest", "semester", "jurusan"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+7:03d}",
            "query": "@rekap_lintas_jurusan_kompleks_2026.pdf ranking ipk",
            "pipeline_in": ["rag_semantic"],
            "intent_route_in": ["default_rag"],
            "expected_validation_in": ["passed", "not_applicable"],
            "allowed_sources_group": "lintas_jurusan",
            "source_match_mode": "any_of",
            "must_contain_any": ["ranking", "ipk"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+8:03d}",
            "query": "@rekap_lintas_jurusan_kompleks_2026.pdf ranking total sks",
            "pipeline_in": ["rag_semantic"],
            "intent_route_in": ["default_rag"],
            "expected_validation_in": ["passed", "not_applicable"],
            "allowed_sources_group": "lintas_jurusan",
            "source_match_mode": "any_of",
            "must_contain_any": ["ranking", "sks"],
            "must_not_contain": [],
        },
        {
            "id": f"cxq{qid+9:03d}",
            "query": "bandingkan performa semester 3 vs 6 semua jurusan",
            "pipeline_in": ["rag_semantic", "structured_analytics"],
            "intent_route_in": ["default_rag", "analytical_tabular"],
            "expected_validation_in": ["passed", "not_applicable", "skipped_strict"],
            "allowed_sources_group": "all_uploaded_complex",
            "source_match_mode": "any_of",
            "must_contain_any": ["semester 3", "semester 6", "jurusan"],
            "must_not_contain": [],
        },
    ]
    queries.extend(extra)
    assert len(queries) == 40

    return {
        "version": 1,
        "dataset_root": "core/test/fixtures/uploaded_docs_complex",
        "source_groups": groups,
        "queries": queries,
    }


def build_prompts(major_facts: dict[str, dict]) -> dict:
    groups = {f"{k}_docs": [v["source"]] for k, v in major_facts.items()}
    groups["lintas_jurusan"] = ["rekap_lintas_jurusan_kompleks_2026.pdf"]
    groups["all_uploaded_complex"] = [v["source"] for v in major_facts.values()] + ["rekap_lintas_jurusan_kompleks_2026.pdf"]

    prompts = []

    def add(pid: int, category: str, query: str, expected: dict):
        prompts.append({"id": f"cp{pid:03d}", "category": category, "query": query, "expected": expected})

    def e(*, pipelines, routes, vals, group=None, require=True, must=None, must_not=None, nums=None, expected_sem=None):
        data = {
            "pipeline_in": pipelines,
            "intent_route_in": routes,
            "validation_in": vals,
            "require_source_match": require,
            "source_match_mode": "any_of",
            "must_contain_any": must or [],
            "must_not_contain": must_not or [],
        }
        if group:
            data["allowed_sources_group"] = group
        if nums:
            data["expected_numbers"] = nums
        if expected_sem:
            data["expected_semesters"] = expected_sem
        return data

    pid = 1
    major_keys = list(major_facts.keys())

    # factual_transcript 25
    for i in range(25):
        mk = major_keys[i % len(major_keys)]
        base = f"{mk}_rekap"
        template_idx = i % 5
        if template_idx == 0:
            q = f"rekap hasil studi jurusan {mk}"
            ex = e(pipelines=["structured_analytics", "rag_semantic"], routes=["analytical_tabular", "default_rag"], vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable"], group=f"{mk}_docs", must=["hasil studi", mk], nums=[f"{base}.total_sks"]) 
        elif template_idx == 1:
            q = f"berapa ipk jurusan {mk} sekarang"
            ex = e(pipelines=["structured_analytics", "rag_semantic"], routes=["analytical_tabular", "default_rag"], vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable"], group=f"{mk}_docs", must=["ipk", mk], nums=[f"{base}.ipk"])
        elif template_idx == 2:
            q = f"nilai d dan e jurusan {mk} ada berapa"
            ex = e(pipelines=["structured_analytics", "rag_semantic"], routes=["analytical_tabular", "default_rag"], vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable"], group=f"{mk}_docs", must=["nilai", "d", "e"], nums=[f"{base}.count_nilai_d", f"{base}.count_nilai_e"])
        elif template_idx == 3:
            src = major_facts[mk]["source"]
            q = f"@{src} total mata kuliah berapa"
            ex = e(pipelines=["structured_analytics", "rag_semantic"], routes=["analytical_tabular", "default_rag"], vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable"], group=f"{mk}_docs", must=["mata kuliah", "jumlah"], nums=[f"{base}.total_matkul"])            
        else:
            q = f"buat ringkasan transcript {mk} dengan angka utama"
            ex = e(pipelines=["structured_analytics", "rag_semantic"], routes=["analytical_tabular", "default_rag"], vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable"], group=f"{mk}_docs", must=["studi", "nilai"], nums=[f"{base}.total_sks", f"{base}.ipk"])
        add(pid, "factual_transcript", q, ex)
        pid += 1

    # factual_schedule_or_semester 15
    for i in range(15):
        mk = major_keys[i % len(major_keys)]
        base = f"{mk}_rekap"
        sem = (i % 7) + 1
        q = f"jurusan {mk} semester {sem} sks dan jumlah matkul berapa"
        ex = e(
            pipelines=["structured_analytics", "rag_semantic"],
            routes=["analytical_tabular", "default_rag"],
            vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable"],
            group=f"{mk}_docs",
            must=["semester", str(sem), "sks"],
            expected_sem=[sem],
            nums=[f"{base}.semester_stats.semester_{sem}.sks", f"{base}.semester_stats.semester_{sem}.matkul"],
        )
        add(pid, "factual_schedule_or_semester", q, ex)
        pid += 1

    # cross_major_comparison 12
    for i in range(12):
        if i % 4 == 0:
            q = "bandingkan ipk antar 5 jurusan"
            ex = e(pipelines=["rag_semantic"], routes=["default_rag"], vals=["passed", "not_applicable"], group="lintas_jurusan", must=["ipk", "jurusan"]) 
        elif i % 4 == 1:
            q = "bandingkan total sks antar 5 jurusan"
            ex = e(pipelines=["rag_semantic"], routes=["default_rag"], vals=["passed", "not_applicable"], group="lintas_jurusan", must=["sks", "jurusan"]) 
        elif i % 4 == 2:
            q = "siapa jurusan dengan beban semester terberat"
            ex = e(pipelines=["rag_semantic"], routes=["default_rag"], vals=["passed", "not_applicable"], group="lintas_jurusan", must=["semester", "terberat", "jurusan"], nums=["lintas_jurusan_kompleks_2026.semester_terberat", "lintas_jurusan_kompleks_2026.sks_semester_terberat"]) 
        else:
            q = "@rekap_lintas_jurusan_kompleks_2026.pdf tampilkan ranking ipk"
            ex = e(pipelines=["rag_semantic"], routes=["default_rag"], vals=["passed", "not_applicable"], group="lintas_jurusan", must=["ranking", "ipk"]) 
        add(pid, "cross_major_comparison", q, ex)
        pid += 1

    # evaluative_grounded 10
    for i in range(10):
        mk = major_keys[i % len(major_keys)]
        q = f"menurut data dokumen, bagaimana performa akademik {mk}"
        ex = e(pipelines=["structured_analytics", "rag_semantic"], routes=["analytical_tabular", "default_rag"], vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable"], group=f"{mk}_docs", must=["berdasarkan", "dokumen", mk])
        add(pid, "evaluative_grounded", q, ex)
        pid += 1

    # typo_ambiguous_multilingual 8
    typo_queries = [
        "rekp nilia yg ga luls smua smstr jurusan ti",
        "ipk hkm skrg brp?",
        "pls summarize econ transcript and failed subjects",
        "smstr 3 med sks brp?",
        "@khs_sastra_mahasiswa_g_200x8.pdf top mk yg nilainya jelek",
        "bndingkn skl jurusan yg plng bnyk d/e",
        "which major has highest gpa from uploaded docs",
        "tolong recap lintas jurusan tp singkat",
    ]
    for q in typo_queries:
        ex = e(pipelines=["structured_analytics", "rag_semantic", "rag_semantic"], routes=["analytical_tabular", "default_rag"], vals=["passed", "skipped_strict", "strict_no_fallback", "not_applicable", "no_grounding_evidence"], group="all_uploaded_complex", must=["dokumen"], must_not=["politik"])
        add(pid, "typo_ambiguous_multilingual", q, ex)
        pid += 1

    # partial_evidence 4
    partial_q = [
        "apakah ada data kehadiran mahasiswa di dokumen ini",
        "siapa dosen wali saya dari dokumen upload",
        "apakah ada data nomor hp mahasiswa",
        "dokumen ini ada data alamat rumah?",
    ]
    for q in partial_q:
        ex = e(pipelines=["rag_semantic", "structured_analytics"], routes=["default_rag", "analytical_tabular"], vals=["no_grounding_evidence", "passed", "not_applicable"], group="all_uploaded_complex", require=False, must=["dokumen", "tidak", "tersedia"])
        add(pid, "partial_evidence", q, ex)
        pid += 1

    # no_evidence 3
    for q in ["berapa nomor ijazah saya", "berapa gaji pertama saya nanti", "siapa jodoh saya berdasarkan transkrip"]:
        ex = e(pipelines=["rag_semantic", "structured_analytics"], routes=["default_rag", "analytical_tabular"], vals=["no_grounding_evidence"], group="all_uploaded_complex", require=False, must=["dokumen", "tidak", "cukup"])
        add(pid, "no_evidence", q, ex)
        pid += 1

    # out_of_domain 3
    for q in ["resep ayam kecap pedas", "cara jadi dukun sakti", "prediksi skor bola malam ini"]:
        ex = e(pipelines=["route_guard"], routes=["out_of_domain"], vals=["not_applicable"], group="all_uploaded_complex", require=False, must=["asisten akademik"])
        add(pid, "out_of_domain", q, ex)
        pid += 1

    assert len(prompts) == 80, len(prompts)

    return {
        "version": 1,
        "dataset_root": "core/test/fixtures/uploaded_docs_complex",
        "source_groups": groups,
        "prompts": prompts,
    }


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    major_rows = {}
    major_facts = {}

    for spec in MAJORS:
        rows = make_rows(spec)
        major_rows[spec.key] = rows
        pages = build_pages(spec, rows)
        write_text_pdf(FIXTURE_DIR / spec.file_name, pages)
        major_facts[spec.key] = summarize_major(rows, spec.file_name)

    agg_pages = build_aggregate_pdf(major_facts)
    write_text_pdf(FIXTURE_DIR / "rekap_lintas_jurusan_kompleks_2026.pdf", agg_pages)

    write_ground_truth(major_facts)

    mapping = build_mapping(major_facts)
    (DATA_DIR / "rag_uploaded_docs_complex_mapping.yaml").write_text(
        yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    prompts = build_prompts(major_facts)
    (DATA_DIR / "rag_uploaded_docs_complex_prompts_80.yaml").write_text(
        yaml.safe_dump(prompts, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    print("Generated complex uploaded-docs fixtures and YAML contracts.")


if __name__ == "__main__":
    main()
