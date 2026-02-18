import { devices, expect, test, type Page } from "@playwright/test";

const baseUrl = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000";

async function login(page: Page) {
  const resp = await page.goto(`${baseUrl}/login/`, { waitUntil: "domcontentloaded" });
  if (!resp || !resp.ok()) {
    throw new Error(`Backend not reachable at ${baseUrl}. Start Django server before running Playwright.`);
  }
  if (page.url() === `${baseUrl}/`) return;

  const usernameInput = page.locator('[data-testid="login-username"], input[name="username"]').first();
  const passwordInput = page.locator('[data-testid="login-password"], input[name="password"]').first();
  const submitButton = page.locator('[data-testid="login-submit"], button[type="submit"]').first();

  const hasUiLogin = await usernameInput.isVisible({ timeout: 3000 }).catch(() => false);
  if (hasUiLogin) {
    await usernameInput.fill("mahasiswa_test");
    await passwordInput.fill("password123");
    await submitButton.click();
    await expect(page).toHaveURL(`${baseUrl}/`, { timeout: 20000 });
    return;
  }

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

test.use({ ...devices["iPhone 13"] });

test.describe("Phase 5 mobile responsiveness", () => {
  test("mobile chat-planner controls and flow stay usable", async ({ page }) => {
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
            answer: "Planner mobile start.",
            options: [{ id: 1, label: "Manual", value: "manual" }],
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
            answer: "Planner mobile next step.",
            options: [{ id: 1, label: "TI", value: "Teknik Informatika" }],
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
          answer: "Mobile chat response.",
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

    await expect(page.getByTestId("mode-chat-mobile")).toBeVisible();
    await expect(page.getByTestId("mode-planner-mobile")).toBeVisible();
    await expect(page.getByTestId("chat-input")).toBeVisible();
    await expect(page.getByTestId("chat-send")).toBeVisible();
    await expect(page.getByTestId("chat-upload")).toBeVisible();

    await page.getByTestId("mode-planner-mobile").click();
    await expect(page.getByTestId("chat-thread")).toContainText("Planner mobile start.");

    await page.getByTestId("planner-option-1").click();
    await expect(page.getByTestId("chat-thread")).toContainText("Planner mobile next step.");

    await page.getByTestId("mode-chat-mobile").click();
    await page.getByTestId("chat-input").fill("tes mobile chat");
    await page.getByTestId("chat-send").click();
    await expect(page.getByTestId("chat-thread")).toContainText("Mobile chat response.");

    expect(chatPayloads.some((p) => p.mode === "planner" && p.option_id === 1)).toBeTruthy();
    expect(chatPayloads.some((p) => p.mode === "chat")).toBeTruthy();
  });
});
