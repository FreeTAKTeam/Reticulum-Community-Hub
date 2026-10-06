import { expect, test } from "@playwright/test";

test("protected mission route requires login and retains the destination on reload", async ({ page }) => {
  await page.goto("/missions");
  await expect(page).toHaveURL(/\/connect\?redirect=\/missions$/);
  await expect(page.getByRole("button", { name: "Log in", exact: true })).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/connect\?redirect=\/missions$/);
});

test("missing credentials cannot establish a remote session", async ({ page }) => {
  await page.goto("/connect");
  await page.getByLabel("Base URL", { exact: true }).fill("https://hub.example.invalid");
  await page.getByLabel("WebSocket Base URL", { exact: true }).fill("wss://hub.example.invalid");
  await page.getByLabel("API Key", { exact: true }).fill("");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByText("API key is required for remote backend authentication.", { exact: true }).first()).toBeVisible();
  await page.goto("/missions");
  await expect(page).toHaveURL(/\/connect\?redirect=\/missions$/);
});

test("remote credentials are refused over an insecure connection", async ({ page }) => {
  await page.goto("/connect");
  await page.getByLabel("Base URL", { exact: true }).fill("http://hub.example.invalid");
  await page.getByLabel("WebSocket Base URL", { exact: true }).fill("ws://hub.example.invalid");
  await page.getByLabel("API Key", { exact: true }).fill("browser-test-only");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL(/\/connect$/);
  await expect(page.getByText("Use HTTPS for a remote backend.", { exact: true }).first()).toBeVisible();
});
