import { test, expect } from "@playwright/test";

/**
 * Integration tests that hit the real backend API through Vite proxy.
 * Requires backend running on port 8090.
 */

test.describe("Integration: Real backend", () => {
  test.beforeAll(async ({ request }) => {
    // Register a test user (ignore error if already exists)
    await request
      .post("/api/v1/auth/register", {
        data: { username: "playwright_user", password: "test123456" },
      })
      .catch(() => {});
  });

  test("should login and see dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("username-input").fill("playwright_user");
    await page.getByTestId("password-input").fill("test123456");
    await page.getByTestId("submit-button").click();

    await expect(page).toHaveURL("/", { timeout: 5000 });
    await expect(page.getByRole("main").getByText("数据源")).toBeVisible();
    await expect(page.getByText("内容稿件")).toBeVisible();
    await expect(page.getByText("已发布")).toBeVisible();
  });

  test("should navigate to content page", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("username-input").fill("playwright_user");
    await page.getByTestId("password-input").fill("test123456");
    await page.getByTestId("submit-button").click();
    await expect(page).toHaveURL("/", { timeout: 5000 });

    await page.getByText("内容管理").click();
    await expect(page).toHaveURL("/content");
    await expect(page.getByTestId("filter-platform")).toBeVisible();
    await expect(page.getByTestId("filter-status")).toBeVisible();
  });

  test("should navigate to sources page and trigger scrape", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByTestId("username-input").fill("playwright_user");
    await page.getByTestId("password-input").fill("test123456");
    await page.getByTestId("submit-button").click();
    await expect(page).toHaveURL("/", { timeout: 5000 });

    await page.getByRole("link", { name: "数据源" }).click();
    await expect(page).toHaveURL("/sources");
    await expect(page.getByTestId("trigger-scrape-btn")).toBeVisible();
  });

  test("should show error on invalid login", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("username-input").fill("nonexistent");
    await page.getByTestId("password-input").fill("wrongpassword");
    await page.getByTestId("submit-button").click();

    await expect(page.getByTestId("error-message")).toBeVisible({
      timeout: 3000,
    });
  });
});
