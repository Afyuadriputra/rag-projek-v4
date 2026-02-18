import { expect, test, type Page } from "@playwright/test";

const baseUrl = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000";

async function login(page: Page) {
  const resp = await page.goto(`${baseUrl}/login/`, { waitUntil: "domcontentloaded" });
  if (!resp || !resp.ok()) {
    throw new Error(`Backend not reachable at ${baseUrl}. Start Django server before running Playwright.`);
  }
  // Jika sudah auto-login/redirect ke home, lanjutkan.
  if (page.url() === `${baseUrl}/`) return;

  const usernameInput = page
    .locator('[data-testid="login-username"], input[name="username"]')
    .first();
  const passwordInput = page
    .locator('[data-testid="login-password"], input[name="password"]')
    .first();
  const submitButton = page
    .locator('[data-testid="login-submit"], button[type="submit"]')
    .first();

  const hasUiLogin = await usernameInput.isVisible({ timeout: 3000 }).catch(() => false);
  if (hasUiLogin) {
    await usernameInput.fill("mahasiswa_test");
    await passwordInput.fill("password123");
    await submitButton.click();
    await expect(page).toHaveURL(`${baseUrl}/`, { timeout: 20000 });
    return;
  }

  // Fallback: login programatik jika markup login tidak sesuai ekspektasi test.
  const csrfCookie = (await page.context().cookies(baseUrl)).find((c) => c.name === "csrftoken");
  const csrf = csrfCookie?.value || "";
  const loginResp = await page.request.post(`${baseUrl}/login/`, {
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRFToken": csrf } : {}),
    },
    data: {
      username: "mahasiswa_test",
      password: "password123",
    },
  });

  if (![200, 302, 303].includes(loginResp.status())) {
    throw new Error(`Programmatic login failed with status=${loginResp.status()}`);
  }

  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(`${baseUrl}/`, { timeout: 20000 });
}

test.use({ viewport: { width: 1280, height: 720 } });

test("Phase 4 flow: Chat -> Plan -> pilih opsi -> kembali Chat", async ({ page }) => {
  const chatPayloads: Array<Record<string, unknown>> = [];

  await page.route("**/api/chat/", async (route) => {
    const reqBody = route.request().postDataJSON() as Record<string, unknown>;
    chatPayloads.push(reqBody);

    if (reqBody.mode === "planner" && (reqBody.message ?? "") === "" && reqBody.option_id == null) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          type: "planner_step",
          answer: "Pilih strategi data.",
          options: [
            { id: 1, label: "📎 Ya, saya mau upload file", value: "upload" },
            { id: 2, label: "✍️ Tidak, saya isi manual", value: "manual" },
          ],
          allow_custom: false,
          planner_step: "data",
          session_state: { current_step: "data", collected_data: {}, data_level: { level: 0 } },
        }),
      });
      return;
    }

    if (reqBody.mode === "planner" && reqBody.option_id === 1) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          type: "planner_step",
          answer: "Masuk ke langkah jurusan.",
          options: [{ id: 1, label: "Teknik Informatika", value: "Teknik Informatika" }],
          allow_custom: true,
          planner_step: "profile_jurusan",
          session_state: { current_step: "profile_jurusan", collected_data: {} },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        type: "chat",
        answer: "Balik ke mode chat.",
        sources: [],
        session_id: 1,
      }),
    });
  });

  await page.route("**/api/sessions/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [], pagination: { page: 1, page_size: 20, total: 0, has_next: false } }),
    });
  });
  await page.route("**/api/documents/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 1024, used_pct: 0 } }),
    });
  });

  await login(page);

  await page.getByTestId("mode-planner").click();
  await expect(page.getByTestId("chat-thread")).toContainText("Pilih strategi data.");

  await page.getByTestId("planner-option-1").click();
  await expect(page.getByTestId("chat-thread")).toContainText("Masuk ke langkah jurusan.");

  await page.getByTestId("mode-chat").click();
  await page.getByTestId("chat-input").fill("Halo mode chat");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-thread")).toContainText("Balik ke mode chat.");

  expect(chatPayloads.some((p) => p.mode === "planner" && p.option_id === 1)).toBeTruthy();
  expect(chatPayloads.some((p) => p.mode === "chat")).toBeTruthy();
});

test("Phase 4 upload: inline + drag-drop", async ({ page }) => {
  let uploadCount = 0;

  await page.route("**/api/chat/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ type: "chat", answer: "ok", sources: [], session_id: 1 }),
    });
  });

  await page.route("**/api/sessions/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [], pagination: { page: 1, page_size: 20, total: 0, has_next: false } }),
    });
  });

  await page.route("**/api/documents/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        documents: uploadCount
          ? [{ id: 1, title: "KURIKULUM.pdf", is_embedded: true, uploaded_at: "2026-02-18 18:00", size_bytes: 10 }]
          : [],
        storage: { used_bytes: 0, quota_bytes: 1024, used_pct: 0 },
      }),
    });
  });

  await page.route("**/api/upload/", async (route) => {
    uploadCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "success", msg: "Upload OK" }),
    });
  });

  await login(page);

  await page.getByTestId("chat-upload").click();
  await page.getByTestId("upload-input").setInputFiles("e2e/fixtures/KURIKULUM.pdf");
  await expect(page.getByText("Upload OK")).toBeVisible({ timeout: 20000 });

  const dataTransfer = await page.evaluateHandle(() => {
    const dt = new DataTransfer();
    const file = new File(["dummy-pdf-content"], "KURIKULUM.pdf", { type: "application/pdf" });
    dt.items.add(file);
    return dt;
  });
  await page.getByTestId("chat-drop-target").dispatchEvent("dragover", { dataTransfer });
  await page.getByTestId("chat-drop-target").dispatchEvent("drop", { dataTransfer });

  await expect(page.getByText("Upload OK")).toBeVisible({ timeout: 20000 });
  expect(uploadCount).toBeGreaterThanOrEqual(2);
});
