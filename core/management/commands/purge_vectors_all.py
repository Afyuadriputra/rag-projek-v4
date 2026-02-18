from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from core.ai_engine.vector_ops import purge_vectors_for_user


class Command(BaseCommand):
    help = "Hapus SEMUA embedding (vector) untuk SEMUA user"

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Konfirmasi eksekusi. Wajib diisi agar command benar-benar jalan.",
        )

    def handle(self, *args, **options):
        if not options.get("yes"):
            self.stderr.write(
                self.style.ERROR(
                    "❌ Dibutuhkan konfirmasi. Jalankan ulang dengan: "
                    "`python manage.py purge_vectors_all --yes`"
                )
            )
            return

        user_ids = list(User.objects.values_list("id", flat=True))
        if not user_ids:
            self.stdout.write(self.style.WARNING("ℹ️ Tidak ada user. Tidak ada vector yang dihapus."))
            return

        total_deleted = 0
        processed = 0
        for uid in user_ids:
            deleted = purge_vectors_for_user(uid)
            total_deleted += int(deleted or 0)
            processed += 1
            self.stdout.write(f"- user_id={uid} deleted≈{deleted}")

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Selesai reset vector untuk semua user ({processed} user, total≈{total_deleted} vectors)."
            )
        )
