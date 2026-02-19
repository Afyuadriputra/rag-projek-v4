import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.admin import SystemSettingAdminForm, UserQuotaForm, _build_quick_admin_links
from core.models import (
    LLMConfiguration,
    RagRequestMetric,
    SystemHealthSnapshot,
    SystemSetting,
    UserLoginPresence,
    UserQuota,
)


class AdminFeatureTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp_base = tempfile.mkdtemp(prefix="admin-tests-")
        cls._override = override_settings(BASE_DIR=cls._tmp_base)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._tmp_base, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_HOST"] = "testserver"
        self.rf = RequestFactory()

        self.staff = User.objects.create_user(
            "staff", password="pass123", is_staff=True, is_superuser=True
        )
        self.user = User.objects.create_user("alice", password="pass123")

        SystemSetting.objects.update_or_create(
            pk=1,
            defaults={
                "registration_enabled": True,
                "maintenance_enabled": False,
                "admin_realtime_poll_seconds": 5,
                "admin_realtime_max_rows": 50,
            },
        )

        self.logs_dir = Path(self.settings.BASE_DIR) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "app.log").write_text(
            "INFO|app-line-1\nWARNING|app-line-2\n", encoding="utf-8"
        )
        (self.logs_dir / "audit.log").write_text(
            "INFO|audit-line-1\n", encoding="utf-8"
        )

    @property
    def settings(self):
        from django.conf import settings

        return settings

    def _staff_request(self, path="/admin/"):
        req = self.rf.get(path)
        req.user = self.staff
        return req

    def test_admin_index_staff_renders_dashboard_sections(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:index"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Academic RAG Admin Overview")
        self.assertContains(resp, "Quick Actions CRUD")
        self.assertContains(resp, "System Logs Preview")
        self.assertContains(resp, "Chart: Activity Throughput")
        self.assertContains(resp, "Chart: Online User Trend")
        self.assertContains(resp, "Chart: RAG Reliability Mix")
        self.assertIn("quick_admin_links", resp.context)
        self.assertIn("system_logs_url", resp.context)

    def test_admin_index_non_staff_is_denied(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("admin:index"))
        self.assertIn(resp.status_code, (302, 403))

    def test_admin_auth_user_change_page_smoke(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:auth_user_change", args=[self.user.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Change user")

    def test_base_site_shows_quick_nav_on_changelist(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:core_ragrequestmetric_changelist"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Quick Navigation")
        self.assertContains(resp, "Documents")
        self.assertContains(resp, "System Logs")

    def test_core_admin_changelists_are_accessible_for_staff(self):
        self.client.force_login(self.staff)
        names = [
            "admin:core_academicdocument_changelist",
            "admin:core_chathistory_changelist",
            "admin:core_chatsession_changelist",
            "admin:core_plannerhistory_changelist",
            "admin:core_userquota_changelist",
            "admin:core_userloginpresence_changelist",
            "admin:core_ragrequestmetric_changelist",
            "admin:core_systemhealthsnapshot_changelist",
            "admin:core_llmconfiguration_changelist",
            "admin:core_systemsetting_changelist",
        ]
        for name in names:
            with self.subTest(name=name):
                resp = self.client.get(reverse(name))
                self.assertEqual(resp.status_code, 200)

    def test_custom_admin_urls_require_staff(self):
        self.client.force_login(self.user)
        urls = [
            reverse("admin:system_logs"),
            reverse("admin:system_logs_tail"),
            reverse("admin:system_logs_detail", kwargs={"log_type": "app"}),
            reverse("admin:system_logs_detail_tail", kwargs={"log_type": "app"}),
            reverse("admin:realtime_users"),
            reverse("admin:realtime_overview"),
            reverse("admin:realtime_rag"),
            reverse("admin:realtime_infra"),
        ]
        for url in urls:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertIn(resp.status_code, (302, 403))

    def test_system_logs_page_and_detail_render(self):
        self.client.force_login(self.staff)

        page = self.client.get(reverse("admin:system_logs"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Open app.log")
        self.assertContains(page, "Open audit.log")

        detail = self.client.get(
            reverse("admin:system_logs_detail", kwargs={"log_type": "app"})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "app-line-1")
        self.assertContains(detail, "Reset Log")

    def test_system_logs_tail_endpoints_contract(self):
        self.client.force_login(self.staff)

        tail_all = self.client.get(reverse("admin:system_logs_tail"))
        self.assertEqual(tail_all.status_code, 200)
        payload_all = json.loads(tail_all.content.decode())
        self.assertIn("app_log_text", payload_all)
        self.assertIn("audit_log_text", payload_all)
        self.assertIn("app_log_size_kb", payload_all)

        tail_one = self.client.get(
            reverse("admin:system_logs_detail_tail", kwargs={"log_type": "audit"})
        )
        self.assertEqual(tail_one.status_code, 200)
        payload_one = json.loads(tail_one.content.decode())
        self.assertEqual(payload_one["log_type"], "audit")
        self.assertIn("log_text", payload_one)
        self.assertIn("audit-line-1", payload_one["log_text"])

    def test_system_logs_unknown_type_falls_back_to_app_log(self):
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("admin:system_logs_detail_tail", kwargs={"log_type": "unknown"})
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode())
        self.assertEqual(payload["log_type"], "app")

    def test_system_logs_backup_and_clear_actions(self):
        self.client.force_login(self.staff)
        backup_url = reverse("admin:system_logs_backup", kwargs={"log_type": "app"})
        clear_url = reverse("admin:system_logs_clear", kwargs={"log_type": "app"})

        resp_backup = self.client.post(backup_url)
        self.assertEqual(resp_backup.status_code, 302)

        backups_dir = self.logs_dir / "backups"
        backups = list(backups_dir.glob("app-*.log"))
        self.assertTrue(backups, "Backup file was not created")

        resp_clear = self.client.post(clear_url)
        self.assertEqual(resp_clear.status_code, 302)
        self.assertEqual((self.logs_dir / "app.log").read_text(encoding="utf-8"), "")

    def test_system_logs_backup_get_redirects(self):
        self.client.force_login(self.staff)
        backup_url = reverse("admin:system_logs_backup", kwargs={"log_type": "audit"})
        resp = self.client.get(backup_url)
        self.assertEqual(resp.status_code, 302)

    def test_realtime_endpoints_require_staff(self):
        self.client.force_login(self.user)
        for name in [
            "admin:realtime_users",
            "admin:realtime_overview",
            "admin:realtime_rag",
            "admin:realtime_infra",
        ]:
            resp = self.client.get(reverse(name))
            self.assertIn(resp.status_code, (302, 403), name)

    def test_realtime_endpoints_staff_contract(self):
        self.client.force_login(self.staff)

        UserLoginPresence.objects.create(user=self.user, session_key="presence-1", is_active=True)
        RagRequestMetric.objects.create(
            request_id="rid-1",
            user=self.user,
            mode="dense",
            retrieval_ms=123,
            llm_time_ms=456,
            fallback_used=False,
            status_code=200,
            source_count=1,
        )
        SystemHealthSnapshot.objects.create(
            cpu_percent=10.5,
            memory_percent=20.5,
            disk_percent=30.5,
            load_1m=0.2,
            active_sessions=1,
            online_users_non_staff=1,
        )
        cache.clear()

        users_resp = self.client.get(reverse("admin:realtime_users"))
        overview_resp = self.client.get(reverse("admin:realtime_overview"))
        rag_resp = self.client.get(reverse("admin:realtime_rag"))
        infra_resp = self.client.get(reverse("admin:realtime_infra"))

        self.assertEqual(users_resp.status_code, 200)
        self.assertEqual(overview_resp.status_code, 200)
        self.assertEqual(rag_resp.status_code, 200)
        self.assertEqual(infra_resp.status_code, 200)

        users_payload = json.loads(users_resp.content.decode())
        overview_payload = json.loads(overview_resp.content.decode())
        rag_payload = json.loads(rag_resp.content.decode())
        infra_payload = json.loads(infra_resp.content.decode())

        self.assertIn("summary", users_payload)
        self.assertIn("online_users", users_payload)
        self.assertIn("summary", overview_payload)
        self.assertIn("poll_seconds", overview_payload)
        self.assertIn("events", rag_payload)
        self.assertIn("p95_retrieval_ms", rag_payload)
        self.assertIn("snapshots", infra_payload)

    def test_realtime_rows_follow_admin_max_rows_limit(self):
        self.client.force_login(self.staff)
        SystemSetting.objects.update_or_create(
            pk=1,
            defaults={
                "registration_enabled": True,
                "maintenance_enabled": False,
                "admin_realtime_poll_seconds": 5,
                "admin_realtime_max_rows": 5,
            },
        )
        for i in range(12):
            RagRequestMetric.objects.create(
                request_id=f"rid-{i}",
                user=self.user,
                mode="dense",
                retrieval_ms=i,
                llm_time_ms=i,
                status_code=200,
            )
            SystemHealthSnapshot.objects.create(
                cpu_percent=1 + i,
                memory_percent=2 + i,
                disk_percent=3 + i,
                load_1m=0.1,
                active_sessions=1,
                online_users_non_staff=1,
            )
        cache.clear()

        rag_resp = self.client.get(reverse("admin:realtime_rag"))
        infra_resp = self.client.get(reverse("admin:realtime_infra"))

        rag_payload = json.loads(rag_resp.content.decode())
        infra_payload = json.loads(infra_resp.content.decode())
        # System setting clamps max_rows to minimum 10.
        self.assertLessEqual(len(rag_payload["events"]), 10)
        self.assertLessEqual(len(infra_payload["snapshots"]), 10)

    def test_quick_admin_links_builder_contract(self):
        links = _build_quick_admin_links()
        by_label = {item["label"]: item for item in links}

        self.assertIn("Documents", by_label)
        self.assertIn("LLM Config", by_label)
        self.assertIn("Presence", by_label)
        self.assertTrue(by_label["Documents"]["list_url"])
        self.assertTrue(by_label["Documents"]["add_url"])
        self.assertIsNone(by_label["Presence"]["add_url"])

    def test_each_context_includes_global_admin_shortcuts(self):
        req = self._staff_request()
        ctx = admin.site.each_context(req)

        self.assertIn("system_logs_url", ctx)
        self.assertIn("system_logs_button_label", ctx)
        self.assertIn("quick_admin_links", ctx)

    def test_user_quota_form_converts_mb_to_bytes(self):
        form = UserQuotaForm(data={"user": str(self.user.id), "quota_mb": 12})
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.quota_bytes, 12 * 1024 * 1024)

    def test_llm_configuration_admin_helpers(self):
        admin_obj = admin.site._registry[LLMConfiguration]

        obj = LLMConfiguration(
            name="Test",
            is_active=True,
            openrouter_api_key="abcd1234wxyz",
            openrouter_backup_models="m1\nm2, m3",
        )

        self.assertEqual(admin_obj.masked_api_key(obj), "abcd...wxyz")
        self.assertEqual(admin_obj.backup_count(obj), 3)

    def test_presence_admin_permissions_and_action(self):
        admin_obj = admin.site._registry[UserLoginPresence]
        req = self._staff_request()

        self.assertFalse(admin_obj.has_add_permission(req))
        self.assertFalse(admin_obj.has_change_permission(req))

        p1 = UserLoginPresence.objects.create(user=self.user, session_key="s1", is_active=True)
        UserLoginPresence.objects.create(user=self.user, session_key="s2", is_active=False)

        with patch.object(admin_obj, "message_user") as mocked_message:
            admin_obj.mark_selected_inactive(req, UserLoginPresence.objects.all())
            mocked_message.assert_called_once()

        p1.refresh_from_db()
        self.assertFalse(p1.is_active)
        self.assertIsNotNone(p1.logged_out_at)

    def test_metric_and_health_admin_permissions(self):
        req = self._staff_request()

        metric_admin = admin.site._registry[RagRequestMetric]
        health_admin = admin.site._registry[SystemHealthSnapshot]

        self.assertFalse(metric_admin.has_add_permission(req))
        self.assertFalse(metric_admin.has_change_permission(req))
        self.assertFalse(health_admin.has_add_permission(req))
        self.assertFalse(health_admin.has_change_permission(req))

    def test_system_setting_admin_add_delete_permissions(self):
        req = self._staff_request()
        setting_admin = admin.site._registry[SystemSetting]

        self.assertFalse(setting_admin.has_delete_permission(req))
        self.assertFalse(setting_admin.has_add_permission(req))

        SystemSetting.objects.all().delete()
        self.assertTrue(setting_admin.has_add_permission(req))

    def test_system_setting_admin_form_validation(self):
        base_data = {
            "registration_enabled": True,
            "maintenance_enabled": False,
            "allow_staff_bypass": True,
            "maintenance_message": "",
            "maintenance_start_at": "",
            "maintenance_estimated_end_at": "",
            "registration_limit_enabled": False,
            "max_registered_users": 100,
            "registration_limit_message": "",
            "concurrent_login_limit_enabled": False,
            "max_concurrent_logins": 100,
            "concurrent_limit_message": "",
            "staff_bypass_concurrent_limit": True,
            "admin_metrics_retention_days": 7,
            "admin_dashboard_locale": "id",
        }

        form_low_poll = SystemSettingAdminForm(
            data={
                **base_data,
                "admin_realtime_poll_seconds": 2,
                "admin_realtime_max_rows": 100,
            }
        )
        self.assertFalse(form_low_poll.is_valid())
        self.assertIn("admin_realtime_poll_seconds", form_low_poll.errors)

        form_bad_rows = SystemSettingAdminForm(
            data={
                **base_data,
                "admin_realtime_poll_seconds": 5,
                "admin_realtime_max_rows": 501,
            }
        )
        self.assertFalse(form_bad_rows.is_valid())
        self.assertIn("admin_realtime_max_rows", form_bad_rows.errors)

        form_ok = SystemSettingAdminForm(
            data={
                **base_data,
                "admin_realtime_poll_seconds": 5,
                "admin_realtime_max_rows": 120,
            }
        )
        self.assertTrue(form_ok.is_valid(), form_ok.errors)
