<template>
  <!-- Leaf node: render the panel -->
  <div v-if="node.type === 'leaf'" class="layout-leaf h-full w-full overflow-hidden">
    <component
      :is="panel?.component"
      v-if="panel?.component"
      v-bind="panelRuntimeProps"
    />
    <div
      v-else
      class="h-full w-full flex items-center justify-center text-[11px] text-warm-400"
    >
      {{ node.panelId ? `no such panel: ${node.panelId}` : 'empty' }}
    </div>
  </div>

  <!-- Split node: two children separated by a draggable handle -->
  <div
    v-else-if="node.type === 'split'"
    ref="containerEl"
    class="layout-split h-full w-full overflow-hidden"
    :class="node.direction === 'horizontal' ? 'flex flex-row' : 'flex flex-col'"
  >
    <!-- First child -->
    <div
      class="overflow-hidden"
      :style="firstStyle"
    >
      <LayoutNode
        :node="node.children[0]"
        :instance-id="instanceId"
        :panel-props-map="panelPropsMap"
      />
    </div>

    <!-- Drag handle -->
    <div
      class="layout-split__handle shrink-0"
      :class="node.direction === 'horizontal'
        ? 'w-[3px] cursor-col-resize hover:bg-iolite/30 active:bg-iolite/50'
        : 'h-[3px] cursor-row-resize hover:bg-iolite/30 active:bg-iolite/50'"
      :style="{ background: dragging ? 'var(--color-iolite, #6366f1)' : '' }"
      @pointerdown.prevent="onPointerDown"
    />

    <!-- Second child -->
    <div
      class="overflow-hidden"
      :style="secondStyle"
    >
      <LayoutNode
        :node="node.children[1]"
        :instance-id="instanceId"
        :panel-props-map="panelPropsMap"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref } from "vue";

import { useLayoutStore } from "@/stores/layout";

const props = defineProps({
  node: { type: Object, required: true },
  instanceId: { type: String, default: null },
  panelPropsMap: { type: Object, default: null },
});

const layout = useLayoutStore();

// For leaf nodes: resolve the panel component and runtime props.
const panel = computed(() => {
  if (props.node.type !== "leaf") return null;
  return layout.getPanel(props.node.panelId);
});

// panelPropsMap can come via prop (from parent LayoutNode) or via
// inject (from the route page's provide("panelProps", ...)).
const injectedProps = inject("panelProps", null);

const panelRuntimeProps = computed(() => {
  if (props.node.type !== "leaf") return {};
  const panelId = props.node.panelId;
  // Try prop first, then inject.
  const map = props.panelPropsMap || (injectedProps && typeof injectedProps === "object" && "value" in injectedProps ? injectedProps.value : injectedProps) || {};
  return map[panelId] || {};
});

// For split nodes: compute child sizes from the ratio.
const ratio = computed(() => props.node.ratio ?? 50);

const firstStyle = computed(() => {
  if (props.node.direction === "horizontal") {
    return { width: ratio.value + "%", height: "100%" };
  }
  return { height: ratio.value + "%", width: "100%" };
});

const secondStyle = computed(() => {
  if (props.node.direction === "horizontal") {
    return { width: (100 - ratio.value) + "%", height: "100%" };
  }
  return { height: (100 - ratio.value) + "%", width: "100%" };
});

// Drag handle logic.
const containerEl = ref(null);
const dragging = ref(false);

function onPointerDown(e) {
  dragging.value = true;
  e.target.setPointerCapture(e.pointerId);

  const onMove = (ev) => {
    if (!dragging.value || !containerEl.value) return;
    const rect = containerEl.value.getBoundingClientRect();
    let pct;
    if (props.node.direction === "horizontal") {
      pct = ((ev.clientX - rect.left) / rect.width) * 100;
    } else {
      pct = ((ev.clientY - rect.top) / rect.height) * 100;
    }
    // Clamp between 10% and 90%.
    props.node.ratio = Math.max(10, Math.min(90, pct));
  };

  const onUp = (ev) => {
    dragging.value = false;
    ev.target.releasePointerCapture(ev.pointerId);
    ev.target.removeEventListener("pointermove", onMove);
    ev.target.removeEventListener("pointerup", onUp);
    ev.target.removeEventListener("pointercancel", onUp);
  };

  e.target.addEventListener("pointermove", onMove);
  e.target.addEventListener("pointerup", onUp);
  e.target.addEventListener("pointercancel", onUp);
}
</script>

<style scoped>
.layout-split__handle {
  transition: background 0.15s ease;
  touch-action: none;
  z-index: 1;
}
</style>
