import { test, expect, type Page } from "@playwright/test";

// Mock drafts data
const MOCK_DRAFTS = [
  {
    id: "draft-001",
    source_id: "src-001",
    target_platform: "wechat",
    title: "AI 技术最新突破：大模型推理能力显著提升",
    body: "近日，多家科技公司发布了新一代大语言模型...\n\n主要进展包括：\n1. 推理速度提升3倍\n2. 多模态理解能力增强\n3. 长文本支持达到100万tokens",
    summary: "多家公司发布新一代大语言模型，推理能力显著提升",
    hashtags: ["AI", "大模型", "科技"],
    media_urls: [],
    video_url: "",
    video_provider: "",
    status: "summarized",
    quality_score: 0.85,
    quality_details: {},
    created_at: "2026-02-20T10:00:00Z",
    updated_at: null,
  },
  {
    id: "draft-002",
    source_id: "src-002",
    target_platform: "douyin",
    title: "短视频趋势：AI生成内容爆发增长",
    body: "短视频平台上AI生成的内容正在快速增长...",
    summary: "AI生成内容在短视频平台快速增长",
    hashtags: ["短视频", "AIGC"],
    media_urls: [],
    video_url: "https://example.com/video.mp4",
    video_provider: "keling",
    status: "quality_checked",
    quality_score: 0.92,
    quality_details: {},
    created_at: "2026-02-20T11:00:00Z",
    updated_at: null,
  },
];

const MOCK_SOURCES = [
  {
    id: "src-001",
    source_platform: "twitter",
    source_id: "tweet-123",
    source_url: "https://twitter.com/example/status/123",
    title: "Breaking: AI advances",
    description: "Latest AI developments",
    author: "tech_news",
    language: "en",
    engagement_score: 5000,
    normalized_heat_score: 0.85,
    hashtags: ["AI"],
    media_urls: [],
    parse_status: "completed",
    scraped_at: "2026-02-20T09:00:00Z",
  },
];

/**
 * Helper: mock auth + APIs and navigate to a page
 */
async function mockAuthAndNavigate(page: Page, path: string) {
  await page.goto("/login");
  await page.evaluate(() => {
    localStorage.setItem("token", "fake-test-token");
  });

  await page.route("**/api/v1/dashboard/stats", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total_sources: 128,
        total_drafts: 45,
        total_published: 12,
        total_pipeline_runs: 8,
      }),
    })
  );

  await page.route("**/api/v1/pipeline/runs*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  );

  await page.route("**/api/v1/content?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_DRAFTS),
    })
  );

  await page.route("**/api/v1/content/draft-001", (route) => {
    if (route.request().method() === "PUT") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, draft_id: "draft-001" }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_DRAFTS[0]),
    });
  });

  await page.route("**/api/v1/publish", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        message: "Publishing initiated",
        draft_ids: ["draft-001"],
        platforms: ["wechat"],
      }),
    })
  );

  await page.route("**/api/v1/sources?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SOURCES),
    })
  );

  await page.route("**/api/v1/pipeline/run", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        pipeline_run_id: "test-run-12345678",
      }),
    })
  );

  await page.goto(path);
}

// ─── Login Flow ─────────────────────────────────────────────

test.describe("Login page", () => {
  test("should show login form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("username-input")).toBeVisible();
    await expect(page.getByTestId("password-input")).toBeVisible();
    await expect(page.getByTestId("submit-button")).toBeVisible();
  });

  test("should redirect to login when not authenticated", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("should login and redirect to dashboard", async ({ page }) => {
    await page.route("**/api/v1/auth/login", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-jwt-token",
          username: "testuser",
          tenant_id: "default",
          role: "user",
        }),
      })
    );
    await page.route("**/api/v1/dashboard/stats", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_sources: 0,
          total_drafts: 0,
          total_published: 0,
          total_pipeline_runs: 0,
        }),
      })
    );
    await page.route("**/api/v1/pipeline/runs*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
    );

    await page.goto("/login");
    await page.getByTestId("username-input").fill("testuser");
    await page.getByTestId("password-input").fill("password123");
    await page.getByTestId("submit-button").click();
    await expect(page).toHaveURL("/");
  });
});

// ─── Content Management ─────────────────────────────────────

test.describe("Content management page", () => {
  test("should display content cards with filters", async ({ page }) => {
    await mockAuthAndNavigate(page, "/content");

    // Filters should be visible
    await expect(page.getByTestId("filter-platform")).toBeVisible();
    await expect(page.getByTestId("filter-status")).toBeVisible();
    await expect(page.getByTestId("search-input")).toBeVisible();

    // Content grid should show cards
    await expect(page.getByTestId("content-grid")).toBeVisible();
    await expect(page.getByTestId("content-card-draft-001")).toBeVisible();
    await expect(page.getByTestId("content-card-draft-002")).toBeVisible();

    // Card should display title
    await expect(
      page.getByText("AI 技术最新突破：大模型推理能力显著提升")
    ).toBeVisible();
  });

  test("should open drawer on card click and show edit fields", async ({
    page,
  }) => {
    await mockAuthAndNavigate(page, "/content");

    // Click on a draft card
    await page.getByTestId("content-card-draft-001").click();

    // Drawer should open with editable fields
    await expect(page.getByTestId("content-drawer")).toBeVisible();
    await expect(page.getByTestId("edit-title")).toBeVisible();
    await expect(page.getByTestId("edit-body")).toBeVisible();
    await expect(page.getByTestId("edit-summary")).toBeVisible();
    await expect(page.getByTestId("edit-hashtags")).toBeVisible();

    // Title should be pre-filled
    await expect(page.getByTestId("edit-title")).toHaveValue(
      "AI 技术最新突破：大模型推理能力显著提升"
    );
  });

  test("should save edits successfully", async ({ page }) => {
    await mockAuthAndNavigate(page, "/content");

    await page.getByTestId("content-card-draft-001").click();
    await expect(page.getByTestId("content-drawer")).toBeVisible();

    // Edit title
    await page.getByTestId("edit-title").clear();
    await page.getByTestId("edit-title").fill("修改后的标题");

    // Save
    await page.getByTestId("save-draft").click();

    // Should show success state
    await expect(page.getByText("已保存")).toBeVisible();
  });

  test("should close drawer on backdrop click", async ({ page }) => {
    await mockAuthAndNavigate(page, "/content");
    await page.getByTestId("content-card-draft-001").click();
    await expect(page.getByTestId("content-drawer")).toBeVisible();

    await page.getByTestId("close-drawer").click();
    await expect(page.getByTestId("content-drawer")).not.toBeVisible();
  });
});

// ─── Publish from Drawer ────────────────────────────────────

test.describe("Publish from content drawer", () => {
  test("article draft: douyin disabled, wechat enabled", async ({ page }) => {
    await mockAuthAndNavigate(page, "/content");

    // Click article draft (no video_url)
    await page.getByTestId("content-card-draft-001").click();
    await expect(page.getByTestId("content-drawer")).toBeVisible();

    // Douyin should be disabled (article only)
    await expect(page.getByTestId("publish-channel-douyin")).toBeDisabled();

    // WeChat should be enabled
    await expect(page.getByTestId("publish-channel-wechat")).toBeEnabled();
    await expect(
      page.getByTestId("publish-channel-xiaohongshu")
    ).toBeEnabled();
    await expect(page.getByTestId("publish-channel-weibo")).toBeEnabled();
  });

  test("video draft: wechat disabled, douyin enabled", async ({ page }) => {
    await mockAuthAndNavigate(page, "/content");

    // Click video draft (has video_url)
    await page.getByTestId("content-card-draft-002").click();
    await expect(page.getByTestId("content-drawer")).toBeVisible();

    // WeChat should be disabled (video only)
    await expect(page.getByTestId("publish-channel-wechat")).toBeDisabled();

    // Douyin should be enabled
    await expect(page.getByTestId("publish-channel-douyin")).toBeEnabled();
    await expect(
      page.getByTestId("publish-channel-xiaohongshu")
    ).toBeEnabled();
    await expect(page.getByTestId("publish-channel-weibo")).toBeEnabled();
  });

  test("should publish article to selected channels", async ({ page }) => {
    await mockAuthAndNavigate(page, "/content");

    await page.getByTestId("content-card-draft-001").click();
    await expect(page.getByTestId("content-drawer")).toBeVisible();

    // Select wechat + xiaohongshu
    await page.getByTestId("publish-channel-wechat").click();
    await page.getByTestId("publish-channel-xiaohongshu").click();

    // Publish button should show channel count
    await expect(page.getByTestId("publish-button")).toContainText(
      "发布到 2 个渠道"
    );

    // Click publish
    await page.getByTestId("publish-button").click();

    // Should show success
    await expect(page.getByTestId("publish-success")).toBeVisible();
  });
});

// ─── Sources Page ───────────────────────────────────────────

test.describe("Sources page", () => {
  test("should display sources table", async ({ page }) => {
    await mockAuthAndNavigate(page, "/sources");

    await expect(page.getByTestId("sources-table")).toBeVisible();
    await expect(
      page.getByTestId("sources-table").getByText("twitter")
    ).toBeVisible();
  });

  test("should show trigger panel and submit scrape", async ({ page }) => {
    await mockAuthAndNavigate(page, "/sources");

    // Click trigger button
    await page.getByTestId("trigger-scrape-btn").click();
    await expect(page.getByTestId("trigger-panel")).toBeVisible();

    // Sources should be pre-selected
    await expect(page.getByTestId("trigger-source-twitter")).toBeVisible();

    // Submit scrape
    await page.getByTestId("trigger-submit").click();

    // Should show result message
    await expect(page.getByText("Pipeline 已启动")).toBeVisible({
      timeout: 3000,
    });
  });
});

// ─── Navigation ─────────────────────────────────────────────

test.describe("Navigation", () => {
  test("sidebar has correct nav items", async ({ page }) => {
    await mockAuthAndNavigate(page, "/");

    await expect(page.getByRole("link", { name: "仪表盘" })).toBeVisible();
    await expect(page.getByRole("link", { name: "内容管理" })).toBeVisible();
    await expect(page.getByRole("link", { name: "数据源" })).toBeVisible();
  });

  test("navigate between pages", async ({ page }) => {
    await mockAuthAndNavigate(page, "/");

    // Go to content
    await page.getByRole("link", { name: "内容管理" }).click();
    await expect(page).toHaveURL("/content");

    // Go to sources
    await page.getByRole("link", { name: "数据源" }).click();
    await expect(page).toHaveURL("/sources");

    // Go back to dashboard
    await page.getByRole("link", { name: "仪表盘" }).click();
    await expect(page).toHaveURL("/");
  });
});
