import { test, expect, type Page } from "@playwright/test";

const baseUrl = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000";

async function login(page: Page, creds?: { username: string; password: string }) {
  const resp = await page.goto(`${baseUrl}/login/`, { waitUntil: "domcontentloaded" });
  if (!resp || !resp.ok()) {
    throw new Error(
      `Backend not reachable at ${baseUrl}. Start Django server before running Playwright.`
    );
  }
  await expect(page.getByTestId("login-username")).toBeVisible({ timeout: 20000 });
  await page.getByTestId("login-username").fill(creds?.username ?? "mahasiswa_test");
  await page.getByTestId("login-password").fill(creds?.password ?? "password123");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(`${baseUrl}/`, { timeout: 20000 });
}

test.use({ viewport: { width: 1280, height: 720 } });

test("XSS in chat response is sanitized", async ({ page }) => {
  test.setTimeout(120000);

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
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });
  await page.route("**/api/chat/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        answer:
          "Halo\n\n<script>window.__xss = true</script>\n\n" +
          "<img src=x onerror=\"window.__xss = true\" />\n\n" +
          "**OK**",
        sources: [],
      }),
    });
  });

  await login(page);

  await page.getByTestId("chat-input").fill("test xss");
  await page.getByTestId("chat-send").click();

  const thread = page.getByTestId("chat-thread");
  await expect(thread).toContainText("OK", { timeout: 20000 });

  const hasScript = await page.evaluate(() => {
    return !!document.querySelector("[data-testid='chat-thread'] script");
  });
  const xssFlag = await page.evaluate(() => (window as any).__xss === true);
  expect(hasScript).toBeFalsy();
  expect(xssFlag).toBeFalsy();
});

test("Upload oversized shows error toast", async ({ page }) => {
  test.setTimeout(120000);

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
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });
  await page.route("**/api/upload/", async (route) => {
    await route.fulfill({
      status: 413,
      contentType: "application/json",
      body: JSON.stringify({ status: "error", msg: "File terlalu besar." }),
    });
  });

  await login(page);

  const uploadBtn = page.getByTestId("chat-upload");
  await uploadBtn.click();
  const uploadInput = page.getByTestId("upload-input");
  await uploadInput.setInputFiles("e2e/fixtures/KURIKULUM.pdf");

  await expect(page.getByText("File terlalu besar.")).toBeVisible({ timeout: 20000 });
});

test("Upload input accepts only allowed extensions", async ({ page }) => {
  await login(page);
  const uploadInput = page.getByTestId("upload-input");
  await expect(uploadInput).toHaveAttribute("accept", ".pdf,.xlsx,.xls,.csv,.md,.txt");
});

test("Empty chat input does not send", async ({ page }) => {
  await page.route("**/api/chat/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ answer: "should-not-send" }),
    });
  });
  await login(page);

  const sendBtn = page.getByTestId("chat-send");
  await expect(sendBtn).toHaveClass(/pointer-events-none/);
});

test("Chat API 500 shows error toast and UI stays responsive", async ({ page }) => {
  test.setTimeout(120000);

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
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });
  await page.route("**/api/chat/", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "Terjadi kesalahan pada server AI." }),
    });
  });

  await login(page);

  await page.getByTestId("chat-input").fill("test error");
  await page.getByTestId("chat-send").click();

  await expect(page.getByTestId("toast-message")).toHaveText("Terjadi kesalahan pada server AI.", { timeout: 20000 });
  await expect(page.getByTestId("chat-input")).toBeEnabled();
});

test("Upload failure (file type reject) shows error toast", async ({ page }) => {
  test.setTimeout(120000);

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
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });
  await page.route("**/api/upload/", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ status: "error", msg: "Tipe file tidak didukung" }),
    });
  });

  await login(page);
  await page.getByTestId("chat-upload").click();
  const uploadInput = page.getByTestId("upload-input");
  await uploadInput.setInputFiles("e2e/fixtures/KURIKULUM.pdf");

  await expect(page.getByText("Tipe file tidak didukung")).toBeVisible({ timeout: 20000 });
});

test("Session pagination loads more sessions", async ({ page }) => {
  test.setTimeout(120000);

  const firstPage = {
    sessions: [
      { id: 1, title: "Chat 1", updated_at: "2026-02-05 10:00" },
      { id: 2, title: "Chat 2", updated_at: "2026-02-05 10:01" },
    ],
    pagination: { page: 1, page_size: 2, total: 4, has_next: true },
  };
  const secondPage = {
    sessions: [
      { id: 3, title: "Chat 3", updated_at: "2026-02-05 10:02" },
      { id: 4, title: "Chat 4", updated_at: "2026-02-05 10:03" },
    ],
    pagination: { page: 2, page_size: 2, total: 4, has_next: false },
  };

  await page.route("**/api/sessions/**", async (route) => {
    const url = route.request().url();
    if (url.includes("page=2")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(secondPage),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(firstPage),
      });
    }
  });
  await page.route("**/api/documents/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });

  await login(page);

  await expect(page.getByRole("button", { name: "Chat 1" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Chat 2" }).first()).toBeVisible();

  const loadMore = page.getByTestId("sessions-load-more").first();
  await expect(loadMore).toBeVisible();
  await loadMore.click();

  await expect(page.getByRole("button", { name: "Chat 3" }).first()).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("button", { name: "Chat 4" }).first()).toBeVisible({ timeout: 20000 });
});

test("Login success redirects to home", async ({ page }) => {
  await login(page);
  await expect(page).toHaveURL(`${baseUrl}/`);
});

test("Login fail shows error box", async ({ page }) => {
  await page.goto(`${baseUrl}/login/`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("login-username").fill("mahasiswa_test");
  await page.getByTestId("login-password").fill("wrong-password");
  await page.getByTestId("login-submit").click();
  await expect(page.getByText("Username atau password salah.")).toBeVisible({ timeout: 20000 });
});

test("Login rate limit shows locked message", async ({ page }) => {
  await page.route("**/login/", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 403,
      headers: {
        "Content-Type": "application/json",
        "X-Inertia": "true",
      },
      body: JSON.stringify({
        component: "Auth/Login",
        props: { errors: { auth: "Terlalu banyak percobaan. Coba lagi nanti." } },
        url: "/login/",
        version: null,
      }),
    });
  });

  await page.goto(`${baseUrl}/login/`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("login-username").fill("ratelimit_user");
  await page.getByTestId("login-password").fill("wrong-password");
  await page.getByTestId("login-submit").click();
  await expect(page.getByText("Terlalu banyak percobaan. Coba lagi nanti.")).toBeVisible({ timeout: 20000 });
});

test("Logout redirects to /login/", async ({ page }) => {
  await login(page);
  await page.getByTestId("user-menu-button").click();
  await page.getByTestId("logout-link").click();
  await expect(page).toHaveURL(`${baseUrl}/login/`, { timeout: 20000 });
});

test("Chat invalid session_id shows error toast", async ({ page }) => {
  test.setTimeout(120000);

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
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });
  await page.route("**/api/chat/", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "session_id tidak valid" }),
    });
  });

  await login(page);
  await page.getByTestId("chat-input").fill("test invalid session");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("toast-message")).toHaveText("session_id tidak valid", { timeout: 20000 });
});

test("Upload success shows document in sidebar", async ({ page }) => {
  test.setTimeout(120000);
  const uniqueTitle = `PLAYWRIGHT-${Date.now()}-KURIKULUM.pdf`;

  let docListCalls = 0;
  await page.route("**/api/documents/**", async (route) => {
    docListCalls += 1;
    const body =
      docListCalls >= 1
        ? { documents: [{ id: 999, title: uniqueTitle, status: "analyzed" }], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }
        : { documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/sessions/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [], pagination: { page: 1, page_size: 20, total: 0, has_next: false } }),
    });
  });
  await page.route("**/api/upload/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "success", msg: "Berhasil memproses 1 file." }),
    });
  });

  await login(page);
  await page.getByTestId("chat-upload").click();
  await page.getByTestId("upload-input").setInputFiles("e2e/fixtures/KURIKULUM.pdf");
  const docList = page.getByTestId("doc-list");
  await expect(docList.getByText(uniqueTitle).first()).toBeVisible({ timeout: 20000 });
});

test("Delete doc shows modal, spinner, and removes item", async ({ page }) => {
  test.setTimeout(120000);
  const uniqueTitle = `PLAYWRIGHT-${Date.now()}-KURIKULUM.pdf`;

  let docListCalls = 0;
  await page.route("**/api/documents/**", async (route) => {
    docListCalls += 1;
    const body =
      docListCalls === 1
        ? { documents: [{ id: 999, title: uniqueTitle, status: "analyzed" }], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }
        : { documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/sessions/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [], pagination: { page: 1, page_size: 20, total: 0, has_next: false } }),
    });
  });
  await page.route("**/api/documents/1/", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "success" }) });
  });

  await login(page);
  const docList = page.getByTestId("doc-list");
  const docItem = docList.locator("[data-testid^='doc-']").first();
  await expect(docItem).toBeVisible({ timeout: 20000 });

  const deleteBtn = docItem.locator("[data-testid$='-delete']");
  await deleteBtn.click();
  await expect(page.getByTestId("confirm-delete-doc")).toBeVisible();
  await page.getByTestId("confirm-delete-doc-btn").click();
  await expect(page.getByText("Dokumen berhasil dihapus.")).toBeVisible({ timeout: 20000 });
  await expect(docItem).not.toBeVisible();
});

test("Session create/rename/delete flow", async ({ page }) => {
  test.setTimeout(120000);

  await page.route("**/api/documents/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });

  await page.route("**/api/sessions/**", async (route) => {
    const url = route.request().url();
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session: { id: 1, title: "Chat Baru", created_at: "2026-02-05 10:00", updated_at: "2026-02-05 10:00" },
        }),
      });
      return;
    }
    if (route.request().method() === "PATCH") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session: { id: 1, title: "Judul Baru", created_at: "2026-02-05 10:00", updated_at: "2026-02-05 10:01" },
        }),
      });
      return;
    }
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "success" }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [], pagination: { page: 1, page_size: 20, total: 0, has_next: false } }),
    });
  });

  await login(page);

  await page.getByTestId("session-create").first().click();
  await expect(page.getByRole("button", { name: "Chat Baru" }).first()).toBeVisible({ timeout: 20000 });

  await page.getByTestId("session-rename-1").first().click();
  const input = page.getByPlaceholder("Judul chat");
  await input.fill("Judul Baru");
  await input.press("Enter");
  await expect(page.getByRole("button", { name: "Judul Baru" }).first()).toBeVisible({ timeout: 20000 });

  await page.getByTestId("session-delete-1").first().click();
  await expect(page.getByTestId("confirm-delete-session")).toBeVisible();
  await page.getByTestId("confirm-delete-session-btn").click();
  await expect(page.getByRole("button", { name: "Judul Baru" }).first()).not.toBeVisible();
});

test("API down shows error toast", async ({ page }) => {
  test.setTimeout(120000);

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
      body: JSON.stringify({ documents: [], storage: { used_bytes: 0, quota_bytes: 0, usage_percent: 0 } }),
    });
  });
  await page.route("**/api/chat/", async (route) => {
    await route.abort();
  });

  await login(page);
  await page.getByTestId("chat-input").fill("test network down");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("toast-message")).toContainText(/Gagal|Network Error/, {
    timeout: 20000,
  });
});
