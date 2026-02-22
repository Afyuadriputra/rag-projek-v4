from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ExtractPagePayload:
    page: int
    raw_text: str = ""
    rough_table_text: str = ""


@dataclass
class ExtractResult:
    text_content: str
    detected_columns: List[str] = field(default_factory=list)
    schedule_rows: List[Dict[str, Any]] = field(default_factory=list)
    page_payloads: List[ExtractPagePayload] = field(default_factory=list)


@dataclass
class ParseResult:
    doc_type: str
    transcript_rows: List[Dict[str, Any]] = field(default_factory=list)
    schedule_rows: List[Dict[str, Any]] = field(default_factory=list)
    row_chunks: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ChunkPayload:
    text: str
    chunk_kind: str = "text"
    page: Optional[int] = None
    section: Optional[str] = None


@dataclass
class BuildChunksResult:
    chunks: List[str] = field(default_factory=list)
    metadatas: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineOps:
    pdfplumber: Any
    get_vectorstore: Callable[[], Any]
    UniversalTranscriptParser: Any
    UniversalScheduleParser: Any
    extract_semester_from_text: Callable[[str], Optional[int]]
    extract_pdf_tables: Callable[[Any], Any]
    extract_pdf_page_raw_payload: Callable[..., List[Dict[str, Any]]]
    is_schedule_candidate: Callable[..., bool]
    is_transcript_candidate: Callable[..., bool]
    canonical_schedule_to_legacy_rows: Callable[..., List[Dict[str, Any]]]
    repair_rows_with_llm: Callable[..., Any]
    schedule_rows_to_row_chunks: Callable[..., List[str]]
    schedule_rows_to_csv_text: Callable[..., Any]
    transcript_rows_to_row_chunks: Callable[..., List[str]]
    transcript_rows_to_csv_text: Callable[..., Any]
    csv_preview: Callable[..., str]
    norm: Callable[[Any], str]
    extract_transcript_rows_deterministic: Callable[..., Dict[str, Any]]
    detect_doc_type: Callable[..., str]
    build_chunk_payloads: Callable[..., List[Dict[str, Any]]]

    @classmethod
    def from_mapping(cls, deps: Dict[str, Any]) -> "PipelineOps":
        return cls(
            pdfplumber=deps["pdfplumber"],
            get_vectorstore=deps["get_vectorstore"],
            UniversalTranscriptParser=deps["UniversalTranscriptParser"],
            UniversalScheduleParser=deps["UniversalScheduleParser"],
            extract_semester_from_text=deps["_extract_semester_from_text"],
            extract_pdf_tables=deps["_extract_pdf_tables"],
            extract_pdf_page_raw_payload=deps["_extract_pdf_page_raw_payload"],
            is_schedule_candidate=deps["_is_schedule_candidate"],
            is_transcript_candidate=deps["_is_transcript_candidate"],
            canonical_schedule_to_legacy_rows=deps["_canonical_schedule_to_legacy_rows"],
            repair_rows_with_llm=deps["_repair_rows_with_llm"],
            schedule_rows_to_row_chunks=deps["_schedule_rows_to_row_chunks"],
            schedule_rows_to_csv_text=deps["_schedule_rows_to_csv_text"],
            transcript_rows_to_row_chunks=deps["_transcript_rows_to_row_chunks"],
            transcript_rows_to_csv_text=deps["_transcript_rows_to_csv_text"],
            csv_preview=deps["_csv_preview"],
            norm=deps["_norm"],
            extract_transcript_rows_deterministic=deps["_extract_transcript_rows_deterministic"],
            detect_doc_type=deps["_detect_doc_type"],
            build_chunk_payloads=deps["_build_chunk_payloads"],
        )

    def as_legacy_mapping(self) -> Dict[str, Any]:
        return {
            "pdfplumber": self.pdfplumber,
            "get_vectorstore": self.get_vectorstore,
            "UniversalTranscriptParser": self.UniversalTranscriptParser,
            "UniversalScheduleParser": self.UniversalScheduleParser,
            "_extract_semester_from_text": self.extract_semester_from_text,
            "_extract_pdf_tables": self.extract_pdf_tables,
            "_extract_pdf_page_raw_payload": self.extract_pdf_page_raw_payload,
            "_is_schedule_candidate": self.is_schedule_candidate,
            "_is_transcript_candidate": self.is_transcript_candidate,
            "_canonical_schedule_to_legacy_rows": self.canonical_schedule_to_legacy_rows,
            "_repair_rows_with_llm": self.repair_rows_with_llm,
            "_schedule_rows_to_row_chunks": self.schedule_rows_to_row_chunks,
            "_schedule_rows_to_csv_text": self.schedule_rows_to_csv_text,
            "_transcript_rows_to_row_chunks": self.transcript_rows_to_row_chunks,
            "_transcript_rows_to_csv_text": self.transcript_rows_to_csv_text,
            "_csv_preview": self.csv_preview,
            "_norm": self.norm,
            "_extract_transcript_rows_deterministic": self.extract_transcript_rows_deterministic,
            "_detect_doc_type": self.detect_doc_type,
            "_build_chunk_payloads": self.build_chunk_payloads,
        }
