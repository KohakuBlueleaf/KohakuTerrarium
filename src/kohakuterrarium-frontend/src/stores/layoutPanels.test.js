import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useLayoutStore } from "./layout.js";

// Stub every real component import used by layoutPanels.js so the test
// doesn't pull in Monaco, Element Plus, etc. The store only cares that
// the value is `markRaw`-able (any object works).
const stub = (name) => ({ name, render: () => null });

vi.mock("@/components/chat/ChatPanel.vue", () => ({
  default: stub("ChatPanel"),
}));
vi.mock("@/components/chrome/StatusBar.vue", () => ({
  default: stub("StatusBar"),
}));
vi.mock("@/components/editor/EditorMain.vue", () => ({
  default: stub("EditorMain"),
}));
vi.mock("@/components/editor/EditorStatus.vue", () => ({
  default: stub("EditorStatus"),
}));
vi.mock("@/components/editor/FileTree.vue", () => ({
  default: stub("FileTree"),
}));
vi.mock("@/components/panels/ActivityPanel.vue", () => ({
  default: stub("ActivityPanel"),
}));
vi.mock("@/components/panels/CreaturesPanel.vue", () => ({
  default: stub("CreaturesPanel"),
}));
vi.mock("@/components/panels/FilesPanel.vue", () => ({
  default: stub("FilesPanel"),
}));
vi.mock("@/components/panels/StatePanel.vue", () => ({
  default: stub("StatePanel"),
}));
vi.mock("@/components/status/StatusDashboard.vue", () => ({
  default: stub("StatusDashboard"),
}));

beforeEach(() => {
  setActivePinia(createPinia());
  if (typeof localStorage !== "undefined") localStorage.clear();
});

describe("layoutPanels — registerBuiltinPanels", () => {
  it("registers every canonical panel id", async () => {
    const { registerBuiltinPanels } = await import("./layoutPanels.js");
    registerBuiltinPanels();
    const store = useLayoutStore();
    const expected = [
      "chat",
      "status-dashboard",
      "file-tree",
      "monaco-editor",
      "editor-status",
      "files",
      "activity",
      "state",
      "creatures",
      "status-bar",
    ];
    for (const id of expected) {
      const p = store.getPanel(id);
      expect(p, `panel ${id} should be registered`).not.toBeNull();
      expect(p.component).toBeTruthy();
    }
    expect(store.panelList.length).toBeGreaterThanOrEqual(expected.length);
  });

  it("registers legacy-instance and legacy-editor builtin presets", async () => {
    const { registerBuiltinPanels } = await import("./layoutPanels.js");
    registerBuiltinPanels();
    const store = useLayoutStore();
    expect(store.allPresets["legacy-instance"]).toBeDefined();
    expect(store.allPresets["legacy-editor"]).toBeDefined();
    // legacy-instance: chat in main, status-dashboard in right-sidebar
    const inst = store.allPresets["legacy-instance"];
    const mainSlot = inst.slots.find((s) => s.zoneId === "main");
    expect(mainSlot.panelId).toBe("chat");
    const rightSlot = inst.slots.find((s) => s.zoneId === "right-sidebar");
    expect(rightSlot.panelId).toBe("status-dashboard");
    // legacy-editor: file-tree | monaco-editor | (chat + editor-status)
    const ed = store.allPresets["legacy-editor"];
    expect(ed.slots.find((s) => s.zoneId === "left-sidebar").panelId).toBe(
      "file-tree",
    );
    expect(ed.slots.find((s) => s.zoneId === "main").panelId).toBe(
      "monaco-editor",
    );
    const auxSlots = ed.slots.filter((s) => s.zoneId === "right-aux");
    expect(auxSlots.map((s) => s.panelId).sort()).toEqual(
      ["chat", "editor-status"].sort(),
    );
  });
});
