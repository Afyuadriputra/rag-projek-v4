from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from django.core.management.base import BaseCommand, CommandError


@dataclass
class BenchmarkStats:
    runs: int = 0
    errors: int = 0
    p50_total_ms: int = 0
    p95_total_ms: int = 0
    p50_retrieval_ms: int = 0
    p95_retrieval_ms: int = 0
    p50_llm_ms: int = 0
    p95_llm_ms: int = 0


def _ask(user_id: int, query: str, request_id: str) -> Dict[str, Any]:
    from core.ai_engine.retrieval.application.chat_service import ask_bot

    return ask_bot(user_id=user_id, query=query, request_id=request_id)


def _percentile(values: List[int], pct: float) -> int:
    if not values:
        return 0
    sorted_vals = sorted(int(v or 0) for v in values)
    idx = min(int(len(sorted_vals) * pct), len(sorted_vals) - 1)
    return int(sorted_vals[idx])


def _build_stats(total: List[int], retrieval: List[int], llm: List[int], errors: int) -> BenchmarkStats:
    return BenchmarkStats(
        runs=len(total),
        errors=max(int(errors), 0),
        p50_total_ms=_percentile(total, 0.50),
        p95_total_ms=_percentile(total, 0.95),
        p50_retrieval_ms=_percentile(retrieval, 0.50),
        p95_retrieval_ms=_percentile(retrieval, 0.95),
        p50_llm_ms=_percentile(llm, 0.50),
        p95_llm_ms=_percentile(llm, 0.95),
    )


@contextmanager
def _temp_env(name: str, value: str):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


class Command(BaseCommand):
    help = "Benchmark semantic optimized ON vs OFF and print p50/p95 comparison."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True, help="User id for benchmark requests")
        parser.add_argument("--iterations", type=int, default=3, help="Iterations per query per profile")
        parser.add_argument(
            "--warmup-runs",
            type=int,
            default=1,
            help="Warmup passes per profile (not counted in metrics)",
        )
        parser.add_argument(
            "--query",
            action="append",
            dest="queries",
            help="Benchmark query (repeat --query for multiple values)",
        )
        parser.add_argument("--max-on-p95-total-ms", type=int, default=2500, help="Gate: max ON total p95 in ms")
        parser.add_argument("--max-on-p95-retrieval-ms", type=int, default=1800, help="Gate: max ON retrieval p95 in ms")
        parser.add_argument("--max-on-p95-llm-ms", type=int, default=2000, help="Gate: max ON llm p95 in ms")
        parser.add_argument("--max-on-error-rate-pct", type=float, default=2.0, help="Gate: max ON error rate percentage")
        parser.add_argument("--max-delta-p95-total-ms", type=int, default=800, help="Gate: max (ON-OFF) total p95 in ms")
        parser.add_argument(
            "--max-delta-p95-retrieval-ms",
            type=int,
            default=600,
            help="Gate: max (ON-OFF) retrieval p95 in ms",
        )
        parser.add_argument("--max-delta-p95-llm-ms", type=int, default=800, help="Gate: max (ON-OFF) llm p95 in ms")
        parser.add_argument("--soft", action="store_true", help="Do not fail command on threshold breach")

    def handle(self, *args, **options):
        user_id = int(options["user_id"])
        iterations = max(int(options.get("iterations") or 3), 1)
        warmup_runs = max(int(options.get("warmup_runs") or 0), 0)
        queries = list(options.get("queries") or [])
        if not queries:
            queries = [
                "apa syarat lulus skripsi?",
                "apa itu sks?",
                "jelaskan aturan cuti kuliah",
            ]

        off_stats = self._run_profile(
            user_id=user_id,
            iterations=iterations,
            queries=queries,
            flag_enabled=False,
            warmup_runs=warmup_runs,
        )
        on_stats = self._run_profile(
            user_id=user_id,
            iterations=iterations,
            queries=queries,
            flag_enabled=True,
            warmup_runs=warmup_runs,
        )

        self.stdout.write(self.style.SUCCESS("RAG Semantic Benchmark"))
        self.stdout.write(f"Queries     : {len(queries)}")
        self.stdout.write(f"Iterations  : {iterations}")
        self.stdout.write(f"Total runs/profile: {len(queries) * iterations}")
        self.stdout.write("")
        self._print_stats("OFF  (RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=0)", off_stats)
        self._print_stats("ON   (RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=1)", on_stats)
        self.stdout.write("")
        self.stdout.write("Delta ON-OFF:")
        self.stdout.write(f"- total p95    : {on_stats.p95_total_ms - off_stats.p95_total_ms} ms")
        self.stdout.write(f"- retrieval p95: {on_stats.p95_retrieval_ms - off_stats.p95_retrieval_ms} ms")
        self.stdout.write(f"- llm p95      : {on_stats.p95_llm_ms - off_stats.p95_llm_ms} ms")
        self.stdout.write(f"- errors       : {on_stats.errors - off_stats.errors}")

        max_on_p95_total_ms = max(int(options.get("max_on_p95_total_ms") or 0), 1)
        max_on_p95_retrieval_ms = max(int(options.get("max_on_p95_retrieval_ms") or 0), 1)
        max_on_p95_llm_ms = max(int(options.get("max_on_p95_llm_ms") or 0), 1)
        max_on_error_rate_pct = max(float(options.get("max_on_error_rate_pct") or 0.0), 0.0)
        max_delta_p95_total_ms = max(int(options.get("max_delta_p95_total_ms") or 0), 0)
        max_delta_p95_retrieval_ms = max(int(options.get("max_delta_p95_retrieval_ms") or 0), 0)
        max_delta_p95_llm_ms = max(int(options.get("max_delta_p95_llm_ms") or 0), 0)
        soft = bool(options.get("soft"))

        on_error_rate_pct = (float(on_stats.errors) / float(max(on_stats.runs, 1))) * 100.0
        delta_total = on_stats.p95_total_ms - off_stats.p95_total_ms
        delta_retrieval = on_stats.p95_retrieval_ms - off_stats.p95_retrieval_ms
        delta_llm = on_stats.p95_llm_ms - off_stats.p95_llm_ms
        breaches: List[str] = []
        if on_stats.p95_total_ms > max_on_p95_total_ms:
            breaches.append(f"on_p95_total_ms={on_stats.p95_total_ms} > {max_on_p95_total_ms}")
        if on_stats.p95_retrieval_ms > max_on_p95_retrieval_ms:
            breaches.append(f"on_p95_retrieval_ms={on_stats.p95_retrieval_ms} > {max_on_p95_retrieval_ms}")
        if on_stats.p95_llm_ms > max_on_p95_llm_ms:
            breaches.append(f"on_p95_llm_ms={on_stats.p95_llm_ms} > {max_on_p95_llm_ms}")
        if on_error_rate_pct > max_on_error_rate_pct:
            breaches.append(f"on_error_rate_pct={on_error_rate_pct:.2f} > {max_on_error_rate_pct:.2f}")
        if delta_total > max_delta_p95_total_ms:
            breaches.append(f"delta_p95_total_ms={delta_total} > {max_delta_p95_total_ms}")
        if delta_retrieval > max_delta_p95_retrieval_ms:
            breaches.append(f"delta_p95_retrieval_ms={delta_retrieval} > {max_delta_p95_retrieval_ms}")
        if delta_llm > max_delta_p95_llm_ms:
            breaches.append(f"delta_p95_llm_ms={delta_llm} > {max_delta_p95_llm_ms}")

        if breaches:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Threshold Gate: FAILED"))
            for item in breaches:
                self.stdout.write(f"- {item}")
            if not soft:
                raise CommandError("Benchmark threshold gate failed")
        else:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Threshold Gate: PASSED"))

    def _run_profile(
        self,
        *,
        user_id: int,
        iterations: int,
        queries: Iterable[str],
        flag_enabled: bool,
        warmup_runs: int = 0,
    ) -> BenchmarkStats:
        totals: List[int] = []
        retrievals: List[int] = []
        llms: List[int] = []
        errors = 0

        flag_value = "1" if flag_enabled else "0"
        with _temp_env("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", flag_value):
            if warmup_runs > 0:
                for wi in range(warmup_runs):
                    for wj, q in enumerate(queries):
                        request_id = f"bench-warmup-{'on' if flag_enabled else 'off'}-{wi}-{wj}"
                        try:
                            _ask(user_id=user_id, query=str(q), request_id=request_id)
                        except Exception:
                            # Warmup is best effort; failures are measured in timed runs.
                            pass

            for i in range(iterations):
                for j, q in enumerate(queries):
                    request_id = f"bench-{'on' if flag_enabled else 'off'}-{i}-{j}"
                    t0 = time.perf_counter()
                    try:
                        out = _ask(user_id=user_id, query=str(q), request_id=request_id)
                        elapsed_ms = int(max((time.perf_counter() - t0) * 1000, 0))
                        meta = dict((out or {}).get("meta") or {})
                        stage = dict(meta.get("stage_timings_ms") or {})
                        retrieval_ms = int(stage.get("retrieval_ms") or meta.get("retrieval_ms") or 0)
                        llm_ms = int(stage.get("llm_ms") or meta.get("llm_time_ms") or 0)
                    except Exception:
                        elapsed_ms = int(max((time.perf_counter() - t0) * 1000, 0))
                        retrieval_ms = 0
                        llm_ms = 0
                        errors += 1
                    totals.append(elapsed_ms)
                    retrievals.append(retrieval_ms)
                    llms.append(llm_ms)

        return _build_stats(totals, retrievals, llms, errors)

    def _print_stats(self, title: str, stats: BenchmarkStats) -> None:
        self.stdout.write(title)
        self.stdout.write(f"- errors         : {stats.errors}/{stats.runs}")
        self.stdout.write(f"- total p50/p95  : {stats.p50_total_ms}/{stats.p95_total_ms} ms")
        self.stdout.write(f"- retr. p50/p95  : {stats.p50_retrieval_ms}/{stats.p95_retrieval_ms} ms")
        self.stdout.write(f"- llm p50/p95    : {stats.p50_llm_ms}/{stats.p95_llm_ms} ms")
