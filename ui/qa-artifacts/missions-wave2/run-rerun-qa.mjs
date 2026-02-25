import { chromium } from "playwright-core";
import fs from "node:fs/promises";
import path from "node:path";

const baseUrl = "http://127.0.0.1:4173";
const apiBaseUrl = "http://127.0.0.1:8000";
const outDir = path.resolve("qa-artifacts", "missions-wave2");
const chromePath = "C:/Program Files/Google/Chrome/Application/chrome.exe";

/** @type {Array<{id:string,status:string,check:string,notes:string,evidence:string}>} */
const checks = [];

const addCheck = (id, status, check, notes = "", evidence = "") => {
  checks.push({ id, status, check, notes, evidence });
};

const waitForWorkspace = async (page, timeout = 60000) => {
  await page.goto(`${baseUrl}/missions`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".missions-workspace .registry-shell", { timeout });
  await page.waitForTimeout(600);
};

await fs.mkdir(outDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: chromePath,
  args: ["--disable-gpu", "--no-sandbox"]
});

const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const consoleErrors = [];
const pageErrors = [];

page.on("console", (msg) => {
  if (msg.type() === "error") {
    consoleErrors.push(msg.text());
  }
});
page.on("pageerror", (error) => {
  pageErrors.push(String(error?.message ?? error));
});

try {
  await waitForWorkspace(page);

  const seedResult = await page.evaluate(async (apiRoot) => {
    const normalize = (payload) => {
      if (Array.isArray(payload)) return payload;
      if (payload && Array.isArray(payload.missions)) return payload.missions;
      return [];
    };

    const listResponse = await fetch(`${apiRoot}/api/r3akt/missions`);
    if (!listResponse.ok) {
      const text = await listResponse.text();
      return { ok: false, error: `list failed: ${listResponse.status} ${text.slice(0, 200)}` };
    }

    let missions = normalize(await listResponse.json());
    const beforeCount = missions.length;
    let createdUid = "";

    if (missions.length < 2) {
      const stamp = new Date().toISOString().replace(/[.:]/g, "-");
      const createPayload = {
        mission_name: `QA Wave2 ReRun ${stamp}`,
        mission_status: "MISSION_ACTIVE",
        description: "QA seed mission for Missions Wave 2 rerun"
      };

      const createResponse = await fetch(`${apiRoot}/api/r3akt/missions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(createPayload)
      });

      if (!createResponse.ok) {
        const text = await createResponse.text();
        return {
          ok: false,
          error: `create failed: ${createResponse.status} ${text.slice(0, 200)}`,
          beforeCount
        };
      }

      const created = await createResponse.json();
      createdUid = String(created?.uid ?? "").trim();

      const refreshResponse = await fetch(`${apiRoot}/api/r3akt/missions`);
      if (!refreshResponse.ok) {
        const text = await refreshResponse.text();
        return {
          ok: false,
          error: `refresh failed: ${refreshResponse.status} ${text.slice(0, 200)}`,
          beforeCount,
          createdUid
        };
      }

      missions = normalize(await refreshResponse.json());
    }

    return {
      ok: true,
      beforeCount,
      afterCount: missions.length,
      createdUid,
      missionNames: missions.map((mission) => String(mission?.mission_name ?? "").trim()).filter(Boolean)
    };
  }, apiBaseUrl);

  if (seedResult.ok) {
    addCheck(
      "seed-rerun",
      "PASS",
      "Mission data seed for workspace checks",
      `before=${seedResult.beforeCount}, after=${seedResult.afterCount}, createdUid=${seedResult.createdUid || "none"}`
    );
  } else {
    addCheck("seed-rerun", "FAIL", "Mission data seed for workspace checks", seedResult.error || "Unknown seed error");
  }

  await waitForWorkspace(page);

  const topStatusPresent = await page.locator(".registry-top .registry-title").count();
  addCheck(
    "3.1-rerun",
    topStatusPresent > 0 ? "PASS" : "FAIL",
    "Top status area rendered with shared cosmic primitives",
    topStatusPresent > 0 ? "registry-top detected" : "registry-top missing"
  );

  const tokenizedCounts = await page.evaluate(() => {
    const buttons = document.querySelectorAll(".cui-btn, .panel-tab, .screen-actions button").length;
    const chips = document.querySelectorAll(".panel-chip, .cui-status-pill, .checklist-chip").length;
    return { buttons, chips };
  });
  addCheck(
    "3.2-rerun",
    tokenizedCounts.buttons > 0 && tokenizedCounts.chips > 0 ? "PASS" : "FAIL",
    "Tokenized controls present",
    `buttons=${tokenizedCounts.buttons}, chips=${tokenizedCounts.chips}`
  );

  await page.keyboard.press("Tab");
  const focusProbe = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active) return null;
    const style = getComputedStyle(active);
    return {
      tag: active.tagName,
      className: active.className,
      outlineWidth: style.outlineWidth,
      outlineStyle: style.outlineStyle,
      boxShadow: style.boxShadow
    };
  });
  const hasFocusIndicator = Boolean(
    focusProbe &&
      ((focusProbe.outlineWidth && focusProbe.outlineWidth !== "0px" && focusProbe.outlineStyle !== "none") ||
        (focusProbe.boxShadow && focusProbe.boxShadow !== "none"))
  );
  addCheck(
    "3.3-rerun",
    hasFocusIndicator ? "PASS" : "FAIL",
    "Keyboard focus indicator visible after tab navigation",
    focusProbe ? JSON.stringify(focusProbe) : "No active element"
  );

  await page.emulateMedia({ reducedMotion: "reduce" });
  const reducedMotionProbe = await page.evaluate(() => {
    const target = document.querySelector(".mission-directory-create-button") || document.querySelector("button");
    if (!target) {
      return { reducedMatch: window.matchMedia("(prefers-reduced-motion: reduce)").matches, animationName: "", transitionDuration: "" };
    }
    const style = getComputedStyle(target);
    return {
      reducedMatch: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      animationName: style.animationName,
      transitionDuration: style.transitionDuration
    };
  });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const reducedMotionPass = reducedMotionProbe.reducedMatch && (reducedMotionProbe.transitionDuration === "0s" || reducedMotionProbe.animationName === "none");
  addCheck(
    "3.4-rerun",
    reducedMotionPass ? "PASS" : "FAIL",
    "Reduced-motion mode disables non-essential animation",
    JSON.stringify(reducedMotionProbe)
  );

  await page.locator(".mission-directory-create-button").first().click();
  await page.waitForTimeout(400);

  const formAnatomy = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll(".stage-card"));
    const createCard = cards.find((card) => {
      const title = card.querySelector("h4")?.textContent?.trim().toLowerCase();
      return title === "mission create";
    });
    if (!createCard) return { cardFound: false, labels: 0, controls: 0 };
    const labels = createCard.querySelectorAll("label.field-control").length;
    const controls = createCard.querySelectorAll("input,select,textarea").length;
    const readonly = createCard.querySelector("input[readonly]") !== null;
    const requiredMarker = createCard.querySelector(".required-marker") !== null;
    const requiredInput = createCard.querySelector('input[placeholder="Mission Name"]');
    const requiredAttr = requiredInput?.hasAttribute("required") ?? false;
    const ariaRequired = requiredInput?.getAttribute("aria-required") === "true";
    const details = createCard.querySelector("details.mission-advanced-properties");
    return {
      cardFound: true,
      labels,
      controls,
      readonly,
      requiredMarker,
      requiredAttr,
      ariaRequired,
      detailsInitialOpen: details ? details.open : null
    };
  });

  addCheck(
    "4.1-rerun",
    formAnatomy.cardFound && formAnatomy.labels > 0 && formAnatomy.controls > 0 ? "PASS" : "FAIL",
    "Form anatomy visible in Mission Create screen",
    `cardFound=${formAnatomy.cardFound}, labels=${formAnatomy.labels}, controls=${formAnatomy.controls}`
  );

  addCheck(
    "4.3-rerun",
    formAnatomy.readonly ? "PASS" : "FAIL",
    "Readonly control semantics present (Mission UID)",
    `readonly=${formAnatomy.readonly}`
  );

  const requiredPass = formAnatomy.requiredMarker && formAnatomy.requiredAttr && formAnatomy.ariaRequired;
  addCheck(
    "4.4-rerun",
    requiredPass ? "PASS" : "FAIL",
    "Required indicators appear consistently where required",
    JSON.stringify({
      requiredMarker: formAnatomy.requiredMarker,
      requiredAttr: formAnatomy.requiredAttr,
      ariaRequired: formAnatomy.ariaRequired
    })
  );

  const advancedToggle = await page.evaluate(() => {
    const details = document.querySelector("details.mission-advanced-properties");
    const summary = details?.querySelector("summary");
    if (!details || !summary) return { found: false };
    const before = details.open;
    summary.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const afterOpen = details.open;
    summary.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const afterClose = details.open;
    return { found: true, before, afterOpen, afterClose };
  });

  addCheck(
    "4.5-rerun",
    advancedToggle.found && advancedToggle.afterOpen !== advancedToggle.before && advancedToggle.afterClose === advancedToggle.before
      ? "PASS"
      : "FAIL",
    "Advanced/collapsible section expands and collapses",
    JSON.stringify(advancedToggle)
  );

  await page.locator(".tree-list .tree-item").first().click();
  await page.waitForTimeout(500);

  const broadcastBtn = page.locator(".screen-actions button", { hasText: /^Broadcast$/i }).first();
  if ((await broadcastBtn.count()) > 0) {
    await broadcastBtn.click();
    await page.waitForTimeout(700);
    addCheck("5.2-prep-rerun", "PASS", "Prepare mission audit sample data", "Broadcast action executed");
  } else {
    addCheck("5.2-prep-rerun", "FAIL", "Prepare mission audit sample data", "Broadcast button not found");
  }

  const auditShellProbe = await page.evaluate(() => {
    const shell = document.querySelector(".mission-audit-table-shell");
    if (!shell) return { found: false, overflowY: "" };
    return { found: true, overflowY: getComputedStyle(shell).overflowY };
  });
  addCheck(
    "5.2-rerun",
    auditShellProbe.found && auditShellProbe.overflowY === "auto" ? "PASS" : "FAIL",
    "Mission audit table variant renders with scroll container",
    JSON.stringify(auditShellProbe)
  );

  const detailsButtons = page.locator(".mission-audit-toggle:not([disabled])");
  const detailsCount = await detailsButtons.count();
  if (detailsCount > 0) {
    await detailsButtons.first().click();
    await page.waitForTimeout(300);
    const detailsVisible = (await page.locator(".mission-audit-details-row").count()) > 0;
    addCheck(
      "5.4-rerun",
      detailsVisible ? "PASS" : "FAIL",
      "Audit row action is keyboard/click accessible and reveals details",
      `enabled detail buttons: ${detailsCount}, detailsVisible=${detailsVisible}`
    );
  } else {
    addCheck("5.4-rerun", "FAIL", "Audit row action is keyboard/click accessible and reveals details", "No enabled detail buttons");
  }

  const assetsBtn = page.locator(".screen-actions button", { hasText: /^Assets$/i }).first();
  if ((await assetsBtn.count()) > 0) {
    await assetsBtn.click();
    await page.waitForSelector("h4:has-text('Asset Registry')", { timeout: 10000 });
    const assetProbe = await page.evaluate(() => {
      const listShell = document.querySelector(".mission-asset-list-shell");
      const actionRow = document.querySelector(".mission-asset-registry-actions");
      if (!listShell || !actionRow) {
        return { found: false, overflowY: "", actionRowBelow: false };
      }
      const listRect = listShell.getBoundingClientRect();
      const actionRect = actionRow.getBoundingClientRect();
      return {
        found: true,
        overflowY: getComputedStyle(listShell).overflowY,
        actionRowBelow: actionRect.top >= listRect.bottom - 2
      };
    });
    addCheck(
      "5.3-rerun",
      assetProbe.found && assetProbe.overflowY === "auto" && assetProbe.actionRowBelow ? "PASS" : "FAIL",
      "Asset registry list is scrollable and actions are below list",
      JSON.stringify(assetProbe)
    );
  } else {
    addCheck("5.3-rerun", "FAIL", "Asset registry list is scrollable and actions are below list", "Assets button not found");
  }

  await page.goto(`${baseUrl}/checklists`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".checklists-workspace", { timeout: 20000 });
  await page.waitForTimeout(500);

  let templatesTab = page.locator(".checklist-overview-tab", { hasText: /Templates/i }).first();
  if ((await templatesTab.count()) === 0) {
    const backButton = page.locator("button", { hasText: /^Back$/i }).first();
    if ((await backButton.count()) > 0) {
      await backButton.click();
      await page.waitForTimeout(350);
    }
    templatesTab = page.locator(".checklist-overview-tab", { hasText: /Templates/i }).first();
  }

  if ((await templatesTab.count()) > 0) {
    await templatesTab.click();
    await page.waitForTimeout(300);
    const templatesActive = await templatesTab.evaluate((node) => node.classList.contains("active"));
    addCheck(
      "6.3-rerun",
      templatesActive ? "PASS" : "FAIL",
      "Checklist tabs update selected state and content",
      `templatesActive=${templatesActive}`
    );
  } else {
    addCheck("6.3-rerun", "FAIL", "Checklist tabs update selected state and content", "Templates tab not found");
  }

  const newButton = page.locator("button", { hasText: /^New$/i }).first();
  if ((await newButton.count()) > 0) {
    await newButton.click();
    await page.waitForSelector(".cui-modal[role='dialog']", { timeout: 10000 });

    const focusTrapResult = await page.evaluate(() => {
      const modal = document.querySelector(".cui-modal[role='dialog']");
      if (!modal) return { found: false, forwardLooped: false, backwardLooped: false };

      const focusables = Array.from(
        modal.querySelectorAll("a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex='-1'])")
      ).filter((node) => !node.hasAttribute("disabled"));

      if (focusables.length < 2) {
        return { found: true, focusableCount: focusables.length, forwardLooped: false, backwardLooped: false };
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      last.focus();
      return {
        found: true,
        focusableCount: focusables.length,
        firstTag: first.tagName,
        lastTag: last.tagName
      };
    });

    let forwardLooped = false;
    let backwardLooped = false;

    if (focusTrapResult.found && (focusTrapResult.focusableCount ?? 0) >= 2) {
      await page.keyboard.press("Tab");
      forwardLooped = await page.evaluate(() => {
        const modal = document.querySelector(".cui-modal[role='dialog']");
        if (!modal) return false;
        const focusables = Array.from(
          modal.querySelectorAll("a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex='-1'])")
        ).filter((node) => !node.hasAttribute("disabled"));
        return document.activeElement === focusables[0];
      });

      await page.evaluate(() => {
        const modal = document.querySelector(".cui-modal[role='dialog']");
        if (!modal) return;
        const focusables = Array.from(
          modal.querySelectorAll("a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex='-1'])")
        ).filter((node) => !node.hasAttribute("disabled"));
        if (focusables.length > 0) {
          focusables[0].focus();
        }
      });
      await page.keyboard.down("Shift");
      await page.keyboard.press("Tab");
      await page.keyboard.up("Shift");
      backwardLooped = await page.evaluate(() => {
        const modal = document.querySelector(".cui-modal[role='dialog']");
        if (!modal) return false;
        const focusables = Array.from(
          modal.querySelectorAll("a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex='-1'])")
        ).filter((node) => !node.hasAttribute("disabled"));
        return document.activeElement === focusables[focusables.length - 1];
      });
    }

    addCheck(
      "6.1-focus-trap-rerun",
      forwardLooped && backwardLooped ? "PASS" : "FAIL",
      "Modal focus trap wraps from last to first focusable element",
      JSON.stringify({
        found: focusTrapResult.found,
        focusableCount: focusTrapResult.focusableCount,
        forwardLooped,
        backwardLooped
      })
    );

    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    const modalStillOpen = (await page.locator(".cui-modal[role='dialog']").count()) > 0;
    addCheck(
      "6.1-escape-rerun",
      modalStillOpen ? "FAIL" : "PASS",
      "Modal closes on Escape",
      `modalStillOpen=${modalStillOpen}`
    );
  } else {
    addCheck("6.1-focus-trap-rerun", "BLOCKED", "Modal focus trap wraps from last to first focusable element", "New button not found");
    addCheck("6.1-escape-rerun", "BLOCKED", "Modal closes on Escape", "New button not found");
  }

  await waitForWorkspace(page);
  const treeItems = page.locator(".tree-list .tree-item");
  const treeCount = await treeItems.count();
  if (treeCount >= 2) {
    const secondLabel = await treeItems.nth(1).locator(".tree-label").innerText();
    await treeItems.nth(1).click();
    await page.waitForTimeout(250);

    await page.goto(`${baseUrl}/checklists`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".checklists-workspace", { timeout: 15000 });
    await page.goto(`${baseUrl}/missions`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".missions-workspace .registry-shell", { timeout: 30000 });

    const activeLabel = await page.evaluate(() => {
      const active = document.querySelector(".tree-list .tree-item.active .tree-label");
      return active?.textContent?.trim() ?? "";
    });

    const expectedLabel = secondLabel.trim();
    const matches = expectedLabel.localeCompare(activeLabel, undefined, { sensitivity: "accent" }) === 0;
    addCheck(
      "6.4-rerun",
      matches ? "PASS" : "FAIL",
      "Tree selection updates and remains stable during in-page navigation",
      `expected='${expectedLabel}', actual='${activeLabel}'`
    );
  } else {
    addCheck(
      "6.4-rerun",
      "BLOCKED",
      "Tree selection updates and remains stable during in-page navigation",
      `Need >=2 missions in directory; found ${treeCount}`
    );
  }

  const responsiveProfiles = [
    { id: "7.1-rerun", width: 1440, height: 900, file: "missions-desktop-1440-rerun.png", label: "Responsive stability check at 1440x900" },
    { id: "7.2-rerun", width: 1280, height: 800, file: "missions-laptop-1280-rerun.png", label: "Responsive stability check at 1280x800" },
    { id: "7.3-rerun", width: 900, height: 1280, file: "missions-tablet-900-rerun.png", label: "Responsive stability check at 900x1280" },
    { id: "7.4-rerun", width: 390, height: 844, file: "missions-mobile-390-rerun.png", label: "Responsive stability check at 390x844" },
    { id: "7.5-rerun", width: 360, height: 800, file: "missions-mobile-360-rerun.png", label: "Responsive stability check at 360x800" }
  ];

  for (const profile of responsiveProfiles) {
    await page.setViewportSize({ width: profile.width, height: profile.height });
    await waitForWorkspace(page);
    const metrics = await page.evaluate(() => {
      const overflowPx = Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const createBtn = document.querySelector(".mission-directory-create-button");
      const refreshBtn = Array.from(document.querySelectorAll(".screen-actions button")).find(
        (node) => node.textContent?.trim().toLowerCase() === "refresh"
      );
      const isVisible = (node) => {
        if (!node) return false;
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      };
      return {
        overflowPx,
        missionCreateVisible: isVisible(createBtn),
        screenActionVisible: isVisible(refreshBtn)
      };
    });

    const screenshotPath = path.join(outDir, profile.file);
    await page.screenshot({ path: screenshotPath, fullPage: true });

    addCheck(
      profile.id,
      metrics.overflowPx === 0 ? "PASS" : "FAIL",
      profile.label,
      `overflowPx=${metrics.overflowPx}, missionCreateVisible=${metrics.missionCreateVisible}, screenActionVisible=${metrics.screenActionVisible}`,
      profile.file
    );
  }

  const hasRuntimeErrors = consoleErrors.length === 0 && pageErrors.length === 0;
  addCheck(
    "3.5-rerun",
    hasRuntimeErrors ? "PASS" : "FAIL",
    "No console errors or page errors during interactions",
    hasRuntimeErrors
      ? "No console/page errors detected"
      : `consoleErrors=${consoleErrors.slice(0, 5).join(" | ")}; pageErrors=${pageErrors.slice(0, 5).join(" | ")}`
  );

  const resultPath = path.join(outDir, "manual-qa-results-rerun.json");
  await fs.writeFile(
    resultPath,
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        baseUrl,
        checks
      },
      null,
      2
    ),
    "utf8"
  );

  console.log(`Wrote QA rerun results: ${resultPath}`);
  console.log(`Checks recorded: ${checks.length}`);
} catch (error) {
  console.error("QA rerun script failed:", error);
  process.exitCode = 1;
} finally {
  await browser.close();
}
