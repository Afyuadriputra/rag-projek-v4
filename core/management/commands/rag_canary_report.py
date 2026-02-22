from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable, List

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import RagRequestMetric


@dataclass
class Stats:
    count: int = 0
    fallback_count: int = 0
    error_count: int = 0
    p50_retrieval_ms: int = 0
    p95_retrieval_ms: int = 0
    p50_rerank_ms: int = 0
    p95_rerank_ms: int = 0
    p50_llm_ms: int = 0
    p95_llm_ms: int = 0
    p50_total_ms: int = 0
    p95_total_ms: int = 0


def _percentile(values: List[int], pct: float) -> int:
    if not values:
        return 0
    sorted_vals = sorted(int(v or 0) for v in values)
    idx = min(int(len(sorted_vals) * pct), len(sorted_vals) - 1)
    return int(sorted_vals[idx])


def _rate(numer: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return (float(numer) / float(denom)) * 100.0


def _compute_stats(rows: Iterable[RagRequestMetric]) -> Stats:
    rows_list = list(rows)
    retrieval = [int(x.retrieval_ms or 0) for x in rows_list]
    rerank = [int(x.rerank_ms or 0) for x in rows_list]
    llm = [int(x.llm_time_ms or 0) for x in rows_list]
    total = [int(x.retrieval_ms or 0) + int(x.rerank_ms or 0) + int(x.llm_time_ms or 0) for x in rows_list]
    return Stats(
        count=len(rows_list),
        fallback_count=sum(1 for x in rows_list if bool(x.fallback_used)),
        error_count=sum(1 for x in rows_list if int(x.status_code or 0) >= 500),
        p50_retrieval_ms=_percentile(retrieval, 0.50),
        p95_retrieval_ms=_percentile(retrieval, 0.95),
        p50_rerank_ms=_percentile(rerank, 0.50),
        p95_rerank_ms=_percentile(rerank, 0.95),
        p50_llm_ms=_percentile(llm, 0.50),
        p95_llm_ms=_percentile(llm, 0.95),
        p50_total_ms=_percentile(total, 0.50),
        p95_total_ms=_percentile(total, 0.95),
    )


class Command(BaseCommand):
    help = "Generate canary report for RAG metrics (p50/p95, fallback/error, mode breakdown)."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=60, help="Window in minutes (default: 60)")
        parser.add_argument("--limit", type=int, default=5000, help="Max rows scanned in time window (default: 5000)")
        parser.add_argument("--top-slow", type=int, default=10, help="Show top N slow requests by total ms")
        parser.add_argument(
            "--request-prefix",
            type=str,
            default="",
            help="Optional request_id prefix filter (example: canary-10-)",
        )
        parser.add_argument(
            "--include-benchmark",
            action="store_true",
            help="Include benchmark rows (request_id starts with bench-)",
        )

    def handle(self, *args, **options):
        minutes = max(int(options.get("minutes") or 60), 1)
        limit = max(int(options.get("limit") or 5000), 1)
        top_slow = max(int(options.get("top_slow") or 10), 1)
        request_prefix = str(options.get("request_prefix") or "").strip()
        include_benchmark = bool(options.get("include_benchmark"))

        now = timezone.now()
        start = now - timedelta(minutes=minutes)

        qs = RagRequestMetric.objects.filter(created_at__gte=start)
        if not include_benchmark:
            qs = qs.exclude(request_id__startswith="bench-")
        if request_prefix:
            qs = qs.filter(request_id__startswith=request_prefix)
        qs = qs.order_by("-created_at")[:limit]
        rows = list(qs)

        if not rows:
            self.stdout.write(self.style.WARNING(f"No RAG metrics found for last {minutes} minutes."))
            return

        global_stats = _compute_stats(rows)
        self.stdout.write(self.style.SUCCESS("RAG Canary Report"))
        self.stdout.write(f"Window      : last {minutes} minutes")
        self.stdout.write(f"Rows        : {global_stats.count} (limit={limit})")
        self.stdout.write(f"Bench rows  : {'included' if include_benchmark else 'excluded'}")
        if request_prefix:
            self.stdout.write(f"Req prefix  : {request_prefix}")
        self.stdout.write(
            f"Fallback    : {global_stats.fallback_count} ({_rate(global_stats.fallback_count, global_stats.count):.2f}%)"
        )
        self.stdout.write(f"Errors (5xx): {global_stats.error_count} ({_rate(global_stats.error_count, global_stats.count):.2f}%)")
        self.stdout.write(
            "Latency p50/p95 (ms): "
            f"retrieval={global_stats.p50_retrieval_ms}/{global_stats.p95_retrieval_ms}, "
            f"rerank={global_stats.p50_rerank_ms}/{global_stats.p95_rerank_ms}, "
            f"llm={global_stats.p50_llm_ms}/{global_stats.p95_llm_ms}, "
            f"total={global_stats.p50_total_ms}/{global_stats.p95_total_ms}"
        )

        by_mode = defaultdict(list)
        for row in rows:
            by_mode[str(row.mode or "unknown")].append(row)

        self.stdout.write("\nBy mode:")
        for mode in sorted(by_mode.keys()):
            st = _compute_stats(by_mode[mode])
            self.stdout.write(
                f"- {mode}: n={st.count}, fallback={_rate(st.fallback_count, st.count):.2f}%, "
                f"errors={_rate(st.error_count, st.count):.2f}%, "
                f"total p95={st.p95_total_ms}ms"
            )

        def _print_distribution(title: str, accessor):
            bucket = defaultdict(int)
            for row in rows:
                key = str(accessor(row) or "unknown").strip() or "unknown"
                bucket[key] += 1
            self.stdout.write(f"\nBy {title}:")
            for key in sorted(bucket.keys()):
                self.stdout.write(f"- {key}: n={bucket[key]}")

        _print_distribution("pipeline", lambda x: x.pipeline)
        _print_distribution("validation", lambda x: x.validation)
        _print_distribution("intent_route", lambda x: x.intent_route)
        _print_distribution("answer_mode", lambda x: x.answer_mode)

        slow_sorted = sorted(
            rows,
            key=lambda x: int(x.retrieval_ms or 0) + int(x.rerank_ms or 0) + int(x.llm_time_ms or 0),
            reverse=True,
        )[:top_slow]

        self.stdout.write(f"\nTop {top_slow} slow requests:")
        for idx, row in enumerate(slow_sorted, start=1):
            total_ms = int(row.retrieval_ms or 0) + int(row.rerank_ms or 0) + int(row.llm_time_ms or 0)
            self.stdout.write(
                f"{idx}. request_id={row.request_id} mode={row.mode} status={row.status_code} "
                f"total={total_ms}ms (retrieval={row.retrieval_ms}, rerank={row.rerank_ms}, llm={row.llm_time_ms})"
            )
