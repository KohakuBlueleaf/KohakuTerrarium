<template>
  <div class="h-full flex flex-col bg-white dark:bg-warm-900">
    <!-- Tabs -->
    <el-tabs
      v-model="activeTab"
      class="status-tabs"
    >
      <el-tab-pane label="Overview" name="overview" />
      <el-tab-pane label="Status" name="status" />
      <el-tab-pane label="Settings" name="settings" />
    </el-tabs>

    <!-- Tab content -->
    <div class="flex-1 overflow-y-auto p-3 text-xs">
      <!-- ── Overview Tab ── -->
      <template v-if="activeTab === 'overview'">
        <template v-if="instance?.type === 'terrarium'">
          <!-- Creature list -->
          <div class="mb-4">
            <div class="section-label">Creatures</div>
            <div class="flex flex-col gap-1">
              <div
                v-for="c in instance.creatures"
                :key="c.name"
                class="flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-colors hover:bg-warm-100 dark:hover:bg-warm-800"
                @click="onOpenTab(c.name)"
              >
                <StatusDot :status="c.status" />
                <span class="font-medium text-warm-700 dark:text-warm-300">{{ c.name }}</span>
                <span class="flex-1" />
                <span
                  class="text-[10px] px-1.5 py-0.5 rounded"
                  :class="c.status === 'running'
                    ? 'bg-aquamarine/10 text-aquamarine'
                    : 'bg-warm-100 dark:bg-warm-800 text-warm-400'"
                >{{ c.status }}</span>
              </div>
            </div>
          </div>

          <!-- Channel list -->
          <div>
            <div class="section-label">Channels</div>
            <div class="flex flex-col gap-1">
              <div
                v-for="ch in instance.channels"
                :key="ch.name"
                class="flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-colors hover:bg-warm-100 dark:hover:bg-warm-800"
                @click="onOpenTab('ch:' + ch.name)"
              >
                <span
                  class="w-2 h-2 rounded-sm shrink-0"
                  :class="ch.type === 'broadcast' ? 'bg-taaffeite' : 'bg-aquamarine'"
                />
                <span class="font-medium text-warm-700 dark:text-warm-300">{{ ch.name }}</span>
                <span class="flex-1" />
                <GemBadge
                  v-if="ch.message_count"
                  :gem="ch.type === 'broadcast' ? 'taaffeite' : 'aquamarine'"
                >{{ ch.message_count }}</GemBadge>
                <span
                  class="text-[10px] px-1.5 py-0.5 rounded bg-warm-100 dark:bg-warm-800 text-warm-400"
                >{{ ch.type }}</span>
              </div>
            </div>
          </div>
        </template>

        <!-- Standalone creature: agent info card -->
        <template v-else>
          <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-4">
            <div class="flex items-center gap-2 mb-3">
              <StatusDot :status="instance?.status" />
              <span class="font-semibold text-warm-700 dark:text-warm-300 text-sm">
                {{ instance?.config_name }}
              </span>
            </div>
            <div class="flex flex-col gap-1.5 text-warm-500">
              <div class="flex items-center gap-2">
                <span class="text-warm-400 w-12">Name</span>
                <span class="text-warm-600 dark:text-warm-400">
                  {{ instance?.creatures?.[0]?.name || instance?.config_name }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-warm-400 w-12">Model</span>
                <span class="text-warm-600 dark:text-warm-400 font-mono text-[11px]">
                  {{ chat.sessionInfo.model || 'default' }}
                </span>
              </div>
            </div>
          </div>
        </template>
      </template>

      <!-- ── Status Tab ── -->
      <template v-if="activeTab === 'status'">
        <!-- Session info card -->
        <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3 mb-3">
          <div class="section-label">Session</div>
          <div class="flex flex-col gap-1.5">
            <div class="flex items-center gap-2">
              <span class="text-warm-400 w-16">Agent</span>
              <span class="text-warm-600 dark:text-warm-400">
                {{ chat.sessionInfo.agentName || instance?.config_name || '--' }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-warm-400 w-16">Session</span>
              <span class="text-warm-600 dark:text-warm-400 font-mono text-[10px] truncate max-w-32">
                {{ chat.sessionInfo.sessionId || '--' }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-warm-400 w-16">Runtime</span>
              <span class="text-warm-600 dark:text-warm-400 font-mono">
                {{ runtimeDisplay }}
              </span>
            </div>
          </div>
        </div>

        <!-- Token usage -->
        <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3 mb-3">
          <div class="section-label">Token Usage</div>
          <div class="flex flex-col gap-1.5">
            <div class="flex items-center gap-2">
              <span class="text-warm-400 w-20">Prompt in</span>
              <span class="text-warm-600 dark:text-warm-400 font-mono">
                {{ formatTokens(totalUsage.prompt) }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-warm-400 w-20">Completion</span>
              <span class="text-warm-600 dark:text-warm-400 font-mono">
                {{ formatTokens(totalUsage.completion) }}
              </span>
            </div>
            <div v-if="totalUsage.cached > 0" class="flex items-center gap-2">
              <span class="text-warm-400 w-20">Cached</span>
              <span class="text-aquamarine font-mono">
                {{ formatTokens(totalUsage.cached) }}
              </span>
            </div>
            <!-- Context usage bar -->
            <div v-if="chat.sessionInfo.compactThreshold > 0" class="mt-1">
              <div class="flex items-center justify-between mb-1">
                <span class="text-warm-400">Context</span>
                <span
                  class="font-mono"
                  :class="contextPct >= 80 ? 'text-coral' : contextPct >= 60 ? 'text-amber' : 'text-warm-500'"
                >{{ contextPct }}%</span>
              </div>
              <div class="w-full h-1.5 rounded-full bg-warm-100 dark:bg-warm-800 overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-300"
                  :class="contextPct >= 80 ? 'bg-coral' : contextPct >= 60 ? 'bg-amber' : 'bg-aquamarine'"
                  :style="{ width: Math.min(contextPct, 100) + '%' }"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Running jobs -->
        <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3">
          <div class="section-label">Running Jobs</div>
          <div v-if="Object.keys(chat.runningJobs).length === 0" class="text-warm-400 py-2 text-center">
            No running jobs
          </div>
          <div v-else class="flex flex-col gap-1.5">
            <div
              v-for="(job, jobId) in chat.runningJobs"
              :key="jobId"
              class="flex items-center gap-2 px-2 py-1.5 rounded-md bg-amber/10"
            >
              <span class="w-1.5 h-1.5 rounded-full bg-amber kohaku-pulse shrink-0" />
              <span class="font-mono text-[11px] text-amber-shadow dark:text-amber-light truncate">
                {{ job.name }}
              </span>
              <span class="flex-1" />
              <span class="text-warm-400 font-mono text-[10px]">
                {{ formatElapsed(job.startedAt) }}
              </span>
            </div>
          </div>
        </div>
      </template>

      <!-- ── Settings Tab ── -->
      <template v-if="activeTab === 'settings'">
        <!-- Model selector -->
        <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3 mb-3">
          <div class="section-label">Model</div>
          <el-select
            v-model="selectedModel"
            placeholder="Select model"
            class="w-full"
            size="small"
            :loading="modelsLoading"
            @change="handleModelSwitch"
          >
            <el-option
              v-for="m in availableModels"
              :key="m.id"
              :label="m.name || m.id"
              :value="m.id"
            />
          </el-select>
          <div v-if="modelSwitchError" class="text-coral text-[10px] mt-1">
            {{ modelSwitchError }}
          </div>
        </div>

        <!-- Temperature slider (display only) -->
        <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3 mb-3">
          <div class="flex items-center justify-between mb-2">
            <span class="section-label !mb-0">Temperature</span>
            <span class="font-mono text-warm-500 text-[11px]">{{ temperature.toFixed(1) }}</span>
          </div>
          <el-slider
            v-model="temperature"
            :min="0"
            :max="2"
            :step="0.1"
            :show-tooltip="false"
            size="small"
            disabled
          />
          <div class="text-warm-400 text-[10px] mt-1">Display only (no backend endpoint yet)</div>
        </div>

        <!-- Reasoning effort (display only) -->
        <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3">
          <div class="section-label">Reasoning Effort</div>
          <el-select
            v-model="reasoningEffort"
            placeholder="Select effort"
            class="w-full"
            size="small"
            disabled
          >
            <el-option label="None" value="none" />
            <el-option label="Minimal" value="minimal" />
            <el-option label="Low" value="low" />
            <el-option label="Medium" value="medium" />
            <el-option label="High" value="high" />
            <el-option label="Extra High" value="xhigh" />
          </el-select>
          <div class="text-warm-400 text-[10px] mt-1">Display only (no backend endpoint yet)</div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import StatusDot from "@/components/common/StatusDot.vue";
import GemBadge from "@/components/common/GemBadge.vue";
import { useChatStore } from "@/stores/chat";
import { configAPI, agentAPI } from "@/utils/api";

const props = defineProps({
  instance: { type: Object, default: null },
  onOpenTab: { type: Function, default: () => {} },
});

const chat = useChatStore();

const activeTab = ref("overview");
const selectedModel = ref("");
const modelsLoading = ref(false);
const modelSwitchError = ref("");
const temperature = ref(0.7);
const reasoningEffort = ref("medium");

/** @type {import('vue').Ref<{id: string, name: string}[]>} */
const availableModels = ref([]);

// Runtime timer
const runtimeSeconds = ref(0);
let runtimeInterval = null;

onMounted(() => {
  loadModels();
  runtimeInterval = setInterval(() => {
    runtimeSeconds.value++;
  }, 1000);
});

onUnmounted(() => {
  if (runtimeInterval) clearInterval(runtimeInterval);
});

// Sync selected model with session info
watch(
  () => chat.sessionInfo.model,
  (newModel) => {
    if (newModel && !selectedModel.value) {
      selectedModel.value = newModel;
    }
  },
  { immediate: true },
);

const runtimeDisplay = computed(() => {
  const s = runtimeSeconds.value;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(sec).padStart(2, "0")}s`;
  return `${sec}s`;
});

const totalUsage = computed(() => {
  let prompt = 0;
  let completion = 0;
  let cached = 0;
  for (const usage of Object.values(chat.tokenUsage)) {
    prompt += usage.prompt || 0;
    completion += usage.completion || 0;
    cached += usage.cached || 0;
  }
  return { prompt, completion, cached };
});

const contextPct = computed(() => {
  const threshold = chat.sessionInfo.compactThreshold;
  if (!threshold || !totalUsage.value.prompt) return 0;
  return Math.min(100, Math.round((totalUsage.value.prompt / threshold) * 100));
});

function formatTokens(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}

function formatElapsed(startedAt) {
  const elapsed = Math.floor((Date.now() - startedAt) / 1000);
  if (elapsed >= 60) return Math.floor(elapsed / 60) + "m " + (elapsed % 60) + "s";
  return elapsed + "s";
}

async function loadModels() {
  modelsLoading.value = true;
  try {
    const models = await configAPI.getModels();
    // Filter only available models
    availableModels.value = (models || []).filter((m) => m.available !== false);
  } catch {
    // API might not exist yet
    availableModels.value = [];
  } finally {
    modelsLoading.value = false;
  }
}

async function handleModelSwitch(modelId) {
  if (!props.instance?.id) return;
  modelSwitchError.value = "";
  try {
    await agentAPI.switchModel(props.instance.id, modelId);
  } catch (err) {
    modelSwitchError.value = err.response?.data?.detail || "Failed to switch model";
    // Revert selection
    selectedModel.value = chat.sessionInfo.model || "";
  }
}
</script>

<style scoped>
.section-label {
  @apply text-warm-400 mb-1.5 uppercase tracking-wider text-[10px] font-medium;
}

/* Override Element Plus tabs styling to match gemstone theme */
:deep(.status-tabs) {
  --el-tabs-header-height: 32px;
}

:deep(.status-tabs .el-tabs__header) {
  margin: 0;
  padding: 0 12px;
  border-bottom: 1px solid var(--color-border);
}

:deep(.status-tabs .el-tabs__nav-wrap::after) {
  display: none;
}

:deep(.status-tabs .el-tabs__item) {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-muted);
  height: 32px;
  line-height: 32px;
  padding: 0 12px;
}

:deep(.status-tabs .el-tabs__item.is-active) {
  color: #5A4FCF;
}

:deep(.status-tabs .el-tabs__active-bar) {
  background-color: #5A4FCF;
}

html.dark :deep(.status-tabs .el-tabs__item.is-active) {
  color: #8B82E0;
}

html.dark :deep(.status-tabs .el-tabs__active-bar) {
  background-color: #8B82E0;
}

/* Element Plus select/slider warm toning */
:deep(.el-select) {
  --el-fill-color-blank: var(--color-surface);
  --el-border-color: var(--color-border);
  --el-text-color-regular: var(--color-text);
}

:deep(.el-slider) {
  --el-slider-main-bg-color: #5A4FCF;
  --el-slider-runway-bg-color: var(--color-border);
}
</style>
