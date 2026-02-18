from __future__ import annotations

from typing import List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from core.models import AcademicDocument
from core.ai_engine.ingest import process_document
from core.ai_engine.vector_ops import delete_vectors_for_doc


User = get_user_model()


class Command(BaseCommand):
    help = "Re-ingest dokumen (rebuild embeddings) untuk user tertentu. Contoh: python manage.py reingest_docs --user 1 --all"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            required=True,
            help="User ID yang dokumennya akan di-reingest",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Re-ingest semua dokumen milik user tersebut",
        )
        parser.add_argument(
            "--doc-ids",
            type=str,
            default="",
            help="(Opsional) daftar doc id dipisah koma, contoh: --doc-ids 12,15,18",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="(Opsional) batasi jumlah dokumen yang diproses (0 = tanpa batas)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="(Opsional) hanya tampilkan dokumen yang akan diproses, tanpa delete/ingest",
        )

    def handle(self, *args, **options):
        user_id: int = options["user"]
        do_all: bool = bool(options["all"])
        doc_ids_raw: str = (options.get("doc_ids") or "").strip()
        limit: int = int(options.get("limit") or 0)
        dry_run: bool = bool(options.get("dry_run"))

        # validate user
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User id={user_id} tidak ditemukan.")

        # parse doc ids
        doc_ids: List[int] = []
        if doc_ids_raw:
            for part in doc_ids_raw.split(","):
                part = part.strip()
                if not part:
                    continue
                if not part.isdigit():
                    raise CommandError(f"--doc-ids invalid: '{part}' (harus angka)")
                doc_ids.append(int(part))

        if not do_all and not doc_ids:
            raise CommandError("Wajib pilih salah satu: --all atau --doc-ids 1,2,3")

        qs = AcademicDocument.objects.filter(user=user).order_by("-uploaded_at")
        if doc_ids:
            qs = qs.filter(id__in=doc_ids)

        if limit and limit > 0:
            qs = qs[:limit]

        total = qs.count() if hasattr(qs, "count") else len(list(qs))
        if total == 0:
            self.stdout.write(self.style.WARNING("Tidak ada dokumen untuk diproses."))
            return

        self.stdout.write(self.style.SUCCESS(f"Re-ingest start: user={user.username} (id={user.id}), docs={total}, dry_run={dry_run}"))

        ok_count = 0
        fail_count = 0

        for idx, doc in enumerate(qs, start=1):
            title = getattr(doc, "title", None) or getattr(doc.file, "name", f"doc-{doc.id}")
            self.stdout.write(f"[{idx}/{total}] doc_id={doc.id} title='{title}' file='{getattr(doc.file, 'name', '-')}'")

            if dry_run:
                continue

            try:
                # 1) delete lama (aman: by doc_id; fallback: source)
                delete_vectors_for_doc(user_id=str(user.id), doc_id=str(doc.id), source=title)

                # 2) ingest ulang
                ok = process_document(doc)
                if ok:
                    doc.is_embedded = True
                    doc.save(update_fields=["is_embedded"])
                    ok_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✅ OK re-ingest doc_id={doc.id}"))
                else:
                    fail_count += 1
                    self.stdout.write(self.style.ERROR(f"  ❌ FAIL parsing/ingest doc_id={doc.id}"))

            except Exception as e:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f"  ❌ ERROR doc_id={doc.id}: {repr(e)}"))

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run selesai (tidak ada perubahan)."))
            return

        self.stdout.write(self.style.SUCCESS(f"Selesai. OK={ok_count} FAIL={fail_count} (total={total})"))
