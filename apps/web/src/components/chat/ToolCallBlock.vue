<template>
  <div
    class="rounded-lg overflow-hidden"
    :class="
      tc.kind === 'subagent'
        ? 'border border-taaffeite/20 dark:border-taaffeite/25'
        : 'border border-warm-200/40 dark:border-warm-700/40'
    "
  >
    <!-- Header -->
    <div
      class="flex items-center gap-2 text-xs px-3 py-1.5 cursor-pointer select-none"
      :class="
        tc.kind === 'subagent'
          ? 'bg-taaffeite/6 dark:bg-taaffeite/10'
          : 'bg-warm-100/50 dark:bg-warm-800/30'
      "
      @click="$emit('toggle')"
    >
      <span :class="statusIcon.class">{{ statusIcon.icon }}</span>
      <span
        class="font-semibold font-mono"
        :class="
          tc.kind === 'subagent'
            ? 'text-taaffeite dark:text-taaffeite-light'
            : 'text-iolite dark:text-iolite-light'
        "
      >
        {{ tc.kind === "subagent" ? `[sub] ${tc.name}` : tc.name }}
      </span>
      <span
        class="text-warm-400 dark:text-warm-500 truncate flex-1 font-mono"
        >{{ formatArgs(tc.args) }}</span
      >
      <span
        v-if="elapsed"
        class="text-[10px] text-warm-400 font-mono shrink-0"
        >{{ elapsed }}</span
      >
      <span
        v-if="tc.result || tc.tools_used?.length"
        class="i-carbon-chevron-down text-warm-400 transition-transform text-[10px]"
        :class="{ 'rotate-180': expanded }"
      />
    </div>

    <!-- Expanded content -->
    <div
      v-if="expanded"
      class="border-t"
      :class="
        tc.kind === 'subagent'
          ? 'border-taaffeite/15 dark:border-taaffeite/20'
          : 'border-warm-200/30 dark:border-warm-700/30'
      "
    >
      <template v-if="tc.kind === 'subagent'">
        <!-- Sub-agent nested tool calls -->
        <div
          v-if="tc.children?.length"
          class="px-3 py-1.5 space-y-1 bg-taaffeite/3 dark:bg-taaffeite/5 border-b border-taaffeite/10 dark:border-taaffeite/15"
        >
          <div
            v-for="(child, i) in tc.children"
            :key="i"
            class="flex items-center gap-1.5 text-[11px] font-mono"
          >
            <span
              :class="
                child.status === 'error'
                  ? 'text-coral'
                  : 'text-sage dark:text-sage-light'
              "
            >
              {{ child.status === "error" ? "\u2717" : "\u2713" }}
            </span>
            <span class="text-iolite dark:text-iolite-light font-medium">{{
              child.name
            }}</span>
            <span
              v-if="child.args?.info"
              class="text-warm-400 dark:text-warm-500 truncate"
              >{{ child.args.info.slice(0, 60) }}</span
            >
          </div>
        </div>
        <!-- Sub-agent tools used (fallback when no children detail) -->
        <div
          v-else-if="tc.tools_used?.length"
          class="px-3 py-1.5 bg-taaffeite/4 dark:bg-taaffeite/6 border-b border-taaffeite/10 dark:border-taaffeite/15"
        >
          <span
            class="text-[10px] text-taaffeite-shadow dark:text-taaffeite-light/70 uppercase tracking-wider font-medium"
            >Tools:
          </span>
          <span
            v-for="(tool, i) in tc.tools_used"
            :key="i"
            class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium mr-1 bg-taaffeite/8 dark:bg-taaffeite/12 text-taaffeite-shadow dark:text-taaffeite-light"
            >{{ tool }}</span
          >
        </div>
        <!-- Sub-agent result as markdown, scrollable -->
        <div v-if="tc.result && tc.status !== 'interrupted'" class="relative">
          <div
            class="px-3 py-2 bg-taaffeite/3 dark:bg-taaffeite/5 text-xs max-h-48 overflow-y-auto scroll-smooth sa-result"
          >
            <MarkdownRenderer :content="tc.result" />
          </div>
        </div>
        <div
          v-else-if="tc.status === 'interrupted'"
          class="px-3 py-2 text-xs text-amber dark:text-amber-light"
        >
          (interrupted)
        </div>
        <div v-else class="px-3 py-2 text-xs text-warm-400">(running...)</div>
      </template>
      <template v-else>
        <!-- Tool raw output -->
        <div
          class="text-xs font-mono px-3 py-2 text-warm-500 dark:text-warm-400 whitespace-pre-wrap max-h-40 overflow-y-auto bg-warm-50 dark:bg-warm-900"
        >
          {{ tc.result || "(no output)" }}
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import MarkdownRenderer from "@/components/common/MarkdownRenderer.vue";

const props = defineProps({
  tc: { type: Object, required: true },
  expanded: { type: Boolean, default: false },
});

defineEmits(["toggle"]);

// Elapsed time for running tools
const elapsedSec = ref(0);
let _timer = null;

watchEffect(() => {
  if (props.tc.status === "running" && props.tc.startedAt) {
    if (!_timer) {
      _timer = setInterval(() => {
        elapsedSec.value = Math.floor((Date.now() - props.tc.startedAt) / 1000);
      }, 1000);
    }
  } else if (_timer) {
    clearInterval(_timer);
    _timer = null;
  }
});

onUnmounted(() => {
  if (_timer) clearInterval(_timer);
});

const elapsed = computed(() => {
  if (props.tc.status === "running" && elapsedSec.value > 0) {
    return `${elapsedSec.value}s`;
  }
  return "";
});

const statusIcon = computed(() => {
  if (props.tc.status === "running")
    return { icon: "\u2699", class: "text-amber kohaku-pulse" };
  if (props.tc.status === "error")
    return { icon: "\u2717", class: "text-coral" };
  if (props.tc.status === "interrupted")
    return { icon: "\u25cb", class: "text-amber" };
  return { icon: "\u2713", class: "text-sage" };
});

function formatArgs(args) {
  if (!args) return "";
  if (typeof args === "string") return args.slice(0, 80);
  return Object.entries(args)
    .filter(([k, v]) => k !== "info" || v)
    .map(([k, v]) => {
      const val =
        typeof v === "string" && v.length > 50 ? v.slice(0, 50) + "..." : v;
      return `${k}=${val}`;
    })
    .join(" ");
}
</script>

<style scoped>
/* Fade hint at bottom when content is scrollable */
.sa-result {
  mask-image: linear-gradient(
    to bottom,
    black calc(100% - 24px),
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to bottom,
    black calc(100% - 24px),
    transparent 100%
  );
}
.sa-result:not([data-scrolled-bottom]) {
  mask-image: linear-gradient(
    to bottom,
    black calc(100% - 24px),
    transparent 100%
  );
}
/* Remove fade when scrolled to bottom */
.sa-result:where([style*="overflow"]):not(:hover) {
  mask-image: linear-gradient(
    to bottom,
    black calc(100% - 24px),
    transparent 100%
  );
}
.sa-result:hover {
  mask-image: none;
  -webkit-mask-image: none;
}
</style>
