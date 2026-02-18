from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.ai_engine.vector_ops import purge_vectors_for_user

class Command(BaseCommand):
    help = "Hapus SEMUA embedding (vector) milik user tertentu"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            required=True,
            help="User ID yang embedding-nya ingin dihapus total",
        )

    def handle(self, *args, **options):
        user_id = options["user"]

        if not User.objects.filter(id=user_id).exists():
            self.stderr.write(self.style.ERROR(f"❌ User ID {user_id} tidak ditemukan"))
            return

        deleted = purge_vectors_for_user(user_id)

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Reset vector selesai untuk user={user_id} (≈{deleted} vectors dihapus)"
            )
        )
