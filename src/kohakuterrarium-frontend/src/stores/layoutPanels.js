/**
 * Panel registration glue — maps existing single-responsibility components
 * into the layout store as panels. Called once from main.js so every page
 * can reference them via the layout store instead of direct imports.
 *
 * Phase 2 registers only the panels used by the two legacy routes. Phase 3
 * will rehome more panels (Sessions, Registry, Settings, etc.) here.
 */

import ChatPanel from "@/components/chat/ChatPanel.vue";
import StatusBar from "@/components/chrome/StatusBar.vue";
import EditorMain from "@/components/editor/EditorMain.vue";
import EditorStatus from "@/components/editor/EditorStatus.vue";
import FileTree from "@/components/editor/FileTree.vue";
import ActivityPanel from "@/components/panels/ActivityPanel.vue";
import CreaturesPanel from "@/components/panels/CreaturesPanel.vue";
import FilesPanel from "@/components/panels/FilesPanel.vue";
import StatePanel from "@/components/panels/StatePanel.vue";
import StatusDashboard from "@/components/status/StatusDashboard.vue";

import { useLayoutStore } from "@/stores/layout";

/** Legacy preset: matches the old /instances/:id layout exactly. */
const LEGACY_INSTANCE_PRESET = {
  id: "legacy-instance",
  label: "Legacy Instance",
  shortcut: "",
  zones: {
    "left-sidebar": { visible: false },
    "left-aux": { visible: false },
    main: { visible: true, size: 65 },
    "right-aux": { visible: false },
    "right-sidebar": { visible: true, size: 35 },
    drawer: { visible: false },
    "status-bar": { visible: false },
  },
  slots: [
    { zoneId: "main", panelId: "chat" },
    { zoneId: "right-sidebar", panelId: "status-dashboard" },
  ],
};

/** Legacy preset: matches the old /editor/:id layout exactly. */
const LEGACY_EDITOR_PRESET = {
  id: "legacy-editor",
  label: "Legacy Editor",
  shortcut: "",
  zones: {
    "left-sidebar": { visible: true, size: 20 },
    "left-aux": { visible: false },
    main: { visible: true, size: 48 },
    "right-aux": { visible: true, size: 32 },
    "right-sidebar": { visible: false },
    drawer: { visible: false },
    "status-bar": { visible: false },
  },
  slots: [
    { zoneId: "left-sidebar", panelId: "file-tree" },
    { zoneId: "main", panelId: "monaco-editor" },
    { zoneId: "right-aux", panelId: "chat", size: 70 },
    { zoneId: "right-aux", panelId: "editor-status", size: 30 },
  ],
};

export function registerBuiltinPanels() {
  const layout = useLayoutStore();

  layout.registerPanel({
    id: "chat",
    label: "Chat",
    component: ChatPanel,
    preferredZones: ["main", "right-sidebar", "right-aux"],
    orientation: "any",
    supportsDetach: true,
  });

  layout.registerPanel({
    id: "status-dashboard",
    label: "Status",
    component: StatusDashboard,
    preferredZones: ["right-sidebar", "right-aux", "main"],
    orientation: "tall-narrow",
    supportsDetach: true,
  });

  layout.registerPanel({
    id: "file-tree",
    label: "Files",
    component: FileTree,
    preferredZones: ["left-sidebar"],
    orientation: "tall-narrow",
    supportsDetach: true,
  });

  layout.registerPanel({
    id: "monaco-editor",
    label: "Editor",
    component: EditorMain,
    preferredZones: ["main"],
    orientation: "any",
    supportsDetach: true,
  });

  layout.registerPanel({
    id: "editor-status",
    label: "Editor Status",
    component: EditorStatus,
    preferredZones: ["right-aux", "drawer"],
    orientation: "short-wide",
    supportsDetach: false,
  });

  // ── Phase 3 rehomed panels ────────────────────────────────────

  layout.registerPanel({
    id: "files",
    label: "Files",
    component: FilesPanel,
    preferredZones: ["left-sidebar"],
    orientation: "tall-narrow",
    supportsDetach: true,
  });

  layout.registerPanel({
    id: "activity",
    label: "Activity",
    component: ActivityPanel,
    preferredZones: ["right-sidebar", "right-aux"],
    orientation: "tall-narrow",
    supportsDetach: true,
  });

  layout.registerPanel({
    id: "state",
    label: "State",
    component: StatePanel,
    preferredZones: ["right-sidebar", "right-aux"],
    orientation: "tall-narrow",
    supportsDetach: true,
  });

  layout.registerPanel({
    id: "creatures",
    label: "Creatures",
    component: CreaturesPanel,
    preferredZones: ["left-sidebar", "right-sidebar"],
    orientation: "tall-narrow",
    supportsDetach: true,
  });

  // ── Chrome ────────────────────────────────────────────────────
  // StatusBar is used via the layout store, but it's a chrome strip
  // that doesn't support detach (always visible at workspace bottom).
  layout.registerPanel({
    id: "status-bar",
    label: "Status Bar",
    component: StatusBar,
    preferredZones: ["status-bar"],
    orientation: "thin-strip",
    supportsDetach: false,
  });

  // Register builtin presets.
  layout.registerBuiltinPreset(LEGACY_INSTANCE_PRESET);
  layout.registerBuiltinPreset(LEGACY_EDITOR_PRESET);
}
