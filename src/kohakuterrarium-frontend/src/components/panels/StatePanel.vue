<template>
  <div class="h-full flex bg-warm-50 dark:bg-warm-900 overflow-hidden">
    <!-- Vertical tab rail on the left -->
    <div
      class="flex flex-col gap-1 py-2 px-1 border-r border-warm-200 dark:border-warm-700 shrink-0"
    >
      <button
        v-for="t in tabs"
        :key="t.id"
        class="w-8 h-8 flex items-center justify-center rounded text-warm-400 hover:text-warm-600 dark:hover:text-warm-300 transition-colors"
        :class="activeTab === t.id ? 'bg-iolite/10 text-iolite' : ''"
        :title="t.label"
        @click="activeTab = t.id"
      >
        <div :class="t.icon" class="text-sm" />
      </button>
    </div>

    <!-- Tab body -->
    <div class="flex-1 min-w-0 flex flex-col overflow-hidden">
      <div
        class="flex items-center gap-2 px-3 py-2 border-b border-warm-200 dark:border-warm-700 shrink-0"
      >
        <span class="text-xs font-medium text-warm-500 dark:text-warm-400 flex-1">
          {{ activeLabel }}
        </span>
        <button
          v-if="activeTab === 'scratchpad'"
          class="w-6 h-6 flex items-center justify-center rounded text-warm-400 hover:text-warm-600 dark:hover:text-warm-300 transition-colors"
          title="Refresh"
          @click="refreshScratchpad"
        >
          <div class="i-carbon-renew text-sm" />
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-3 py-2 text-xs">
        <!-- Scratchpad tab -->
        <template v-if="activeTab === 'scratchpad'">
          <div
            v-if="loading && !entries.length"
            class="text-warm-400 py-6 text-center"
          >
            Loading...
          </div>
          <div
            v-else-if="errorMsg"
            class="text-coral py-4 text-[11px]"
          >
            {{ errorMsg }}
          </div>
          <div
            v-else-if="entries.length === 0"
            class="text-warm-400 py-6 text-center"
          >
            Scratchpad is empty
          </div>
          <div v-else class="flex flex-col gap-2">
            <div
              v-for="[key, value] in entries"
              :key="key"
              class="flex flex-col gap-0.5 rounded border border-warm-200 dark:border-warm-700 px-2 py-1.5"
            >
              <div class="flex items-center gap-2">
                <span class="text-iolite font-mono text-[10px]">{{ key }}</span>
                <span class="flex-1" />
                <button
                  class="text-warm-400 hover:text-coral transition-colors"
                  title="Delete"
                  @click="deleteKey(key)"
                >
                  <div class="i-carbon-close text-[10px]" />
                </button>
              </div>
              <div class="text-warm-600 dark:text-warm-400 font-mono text-[11px] break-all">
                {{ value }}
              </div>
            </div>
          </div>
        </template>

        <!-- Memory tab — placeholder until Phase 6 -->
        <template v-else-if="activeTab === 'memory'">
          <div class="text-warm-400 py-6 text-center text-[11px]">
            Memory search lands in Phase 6.
          </div>
        </template>

        <!-- Plan tab — placeholder -->
        <template v-else-if="activeTab === 'plan'">
          <div class="text-warm-400 py-6 text-center text-[11px]">
            Plan view is not yet implemented.
          </div>
        </template>

        <!-- Compaction tab — placeholder -->
        <template v-else-if="activeTab === 'compact'">
          <div class="text-warm-400 py-6 text-center text-[11px]">
            Compaction history lands in Phase 6.
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { useScratchpadStore } from "@/stores/scratchpad";

const props = defineProps({
  instance: { type: Object, default: null },
});

const scratchpad = useScratchpadStore();

const tabs = [
  { id: "scratchpad", label: "Scratchpad", icon: "i-carbon-notebook" },
  { id: "memory", label: "Memory", icon: "i-carbon-data-base" },
  { id: "plan", label: "Plan", icon: "i-carbon-list-checked" },
  { id: "compact", label: "Compaction", icon: "i-carbon-compare" },
];
const activeTab = ref("scratchpad");

const activeLabel = computed(
  () => tabs.find((t) => t.id === activeTab.value)?.label || "",
);

const agentId = computed(() => props.instance?.id || null);

const entries = computed(() => {
  const id = agentId.value;
  if (!id) return [];
  return Object.entries(scratchpad.getFor(id));
});

const loading = computed(() => {
  const id = agentId.value;
  return id ? !!scratchpad.loading[id] : false;
});

const errorMsg = computed(() => {
  const id = agentId.value;
  return id ? scratchpad.error[id] || "" : "";
});

function refreshScratchpad() {
  if (agentId.value) scratchpad.fetch(agentId.value);
}

async function deleteKey(key) {
  if (!agentId.value) return;
  await scratchpad.patch(agentId.value, { [key]: null });
}

watch(
  agentId,
  (id, prev) => {
    if (prev) scratchpad.stopPolling(prev);
    if (id) scratchpad.startPolling(id);
  },
  { immediate: true },
);

onMounted(() => {
  if (agentId.value) scratchpad.startPolling(agentId.value);
});

onUnmounted(() => {
  if (agentId.value) scratchpad.stopPolling(agentId.value);
});
</script>
