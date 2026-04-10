<template>
  <div class="workspace-shell h-full w-full flex flex-col overflow-hidden">
    <!-- Preset dropdown (compact) -->
    <PresetStrip v-if="presetStrip && showPresetStrip" class="shrink-0" />

    <!-- Main content area: the split tree fills all remaining space -->
    <div class="flex-1 relative min-h-0">
      <div class="absolute inset-0">
        <LayoutNode
          v-if="treeRoot"
          :key="layout.activePresetId || 'none'"
          :node="treeRoot"
          :instance-id="instanceId"
        />
        <div
          v-else
          class="h-full w-full flex items-center justify-center text-warm-400 text-sm"
        >
          No layout preset active. Pick one from the dropdown above.
        </div>
      </div>
    </div>

    <!-- Status bar (always at bottom, outside the tree) -->
    <div class="shrink-0">
      <StatusBar />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from "vue";

import PresetStrip from "@/components/chrome/PresetStrip.vue";
import StatusBar from "@/components/chrome/StatusBar.vue";
import { useLayoutStore } from "@/stores/layout";
import LayoutNode from "./LayoutNode.vue";

const props = defineProps({
  instanceId: { type: String, default: null },
  presetStrip: { type: Boolean, default: true },
});

const layout = useLayoutStore();

const showPresetStrip = computed(() => {
  const id = layout.activePresetId || "";
  return !id.startsWith("legacy-");
});

// The tree root comes from the active preset.
const treeRoot = computed(() => {
  const p = layout.activePreset;
  if (!p) return null;
  return p.tree || null;
});
</script>
