import { beforeEach } from "vitest";
import { describe } from "vitest";
import { expect } from "vitest";
import { it } from "vitest";
import { createPinia } from "pinia";
import { setActivePinia } from "pinia";
import { useNavStore } from "../src/stores/nav";

describe("nav store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("normalizes pinned state to expanded", () => {
    localStorage.setItem("rth-ui-nav", JSON.stringify({ collapsed: true, pinned: true }));
    setActivePinia(createPinia());
    const store = useNavStore();
    expect(store.isPinned).toBe(true);
    expect(store.isCollapsed).toBe(false);
  });

  it("collapsing unpins the nav", () => {
    const store = useNavStore();
    store.setPinned(true);
    store.setCollapsed(true);
    expect(store.isPinned).toBe(false);
    expect(store.isCollapsed).toBe(true);
  });

  it("pinning expands the nav", () => {
    const store = useNavStore();
    store.setCollapsed(true);
    store.setPinned(true);
    expect(store.isPinned).toBe(true);
    expect(store.isCollapsed).toBe(false);
  });

  it("collapseIfUnpinned collapses when not pinned", () => {
    const store = useNavStore();
    store.setPinned(false);
    store.setCollapsed(false);
    store.collapseIfUnpinned();
    expect(store.isCollapsed).toBe(true);
  });
});
