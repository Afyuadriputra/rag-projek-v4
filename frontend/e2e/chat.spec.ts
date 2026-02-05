import { test, expect, type Page } from "@playwright/test";

test.use({ viewport: { width: 1280, height: 720 } });

const baseUrl = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000";

async function login(page: Page) {
  const resp = await page.goto(`${baseUrl}/login/`, { waitUntil: "domcontentloaded" });
  if (!resp || !resp.ok()) {
    throw new Error(
      `Backend not reachable at ${baseUrl}. Start Django server before running Playwright.`
    );
  }
  await expect(page.getByTestId("login-username")).toBeVisible({ timeout: 20000 });
  await page.getByTestId("login-username").fill("mahasiswa_test");
  await page.getByTestId("login-password").fill("password123");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(`${baseUrl}/`, { timeout: 20000 });
}

test("E2E FULL: login → chat → lihat jawaban → upload → sidebar refresh", async ({ page }) => {
  test.setTimeout(120000);

  // ✅ STUB AI CHAT supaya tidak tergantung OpenRouter (stabil di headless)
  await page.route("**/api/chat/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ answer: "OK (stubbed AI answer)" }),
    });
  });

  await login(page);

  // Chat
  await expect(page.getByTestId("chat-input")).toBeVisible({ timeout: 20000 });
  await page.getByTestId("chat-input").fill("Halo, tes chat");
  await page.getByTestId("chat-send").click();

  // Pesan user tampil
  await expect(page.getByTestId("chat-thread")).toContainText("Halo, tes chat", { timeout: 20000 });
  // Jawaban AI stub tampil
  await expect(page.getByTestId("chat-thread")).toContainText("OK (stubbed AI answer)", { timeout: 20000 });

  // Setelah AI stub selesai, loading harus off -> upload enabled
  const uploadBtn = page.getByTestId("chat-upload");
  await expect(uploadBtn).toBeEnabled({ timeout: 20000 });

  // Upload
  const filePath = "e2e/fixtures/KURIKULUM.pdf";
  await uploadBtn.click();

  const uploadInput = page.getByTestId("upload-input");
  await uploadInput.setInputFiles(filePath);

  // Sidebar refresh (ambil salah satu karena ada 2 sidebar)
  const docList = page.getByTestId("doc-list").first();
  await expect(docList).toBeVisible({ timeout: 20000 });
  await expect(docList).toContainText("KURIKULUM.pdf", { timeout: 120000 });
});
