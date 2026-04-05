<template>
  <div class="h-full overflow-y-auto bg-white dark:bg-warm-900">
    <div class="flex flex-col gap-3 p-3 text-xs">
      <!-- ── Overview Section ── -->
      <template v-if="instance?.type === 'terrarium'">
        <!-- Creature list -->
        <div>
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

      <!-- ── Divider ── -->
      <div class="border-t border-warm-200 dark:border-warm-700" />

      <!-- ── Status Section ── -->
      <!-- Session info card -->
      <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3">
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
      <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3">
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

      <!-- ── Divider ── -->
      <div class="border-t border-warm-200 dark:border-warm-700" />

      <!-- ── Model Section ── -->
      <div class="rounded-lg border border-warm-200 dark:border-warm-700 p-3">
        <div class="section-label">Model</div>
        <div class="flex items-center gap-2">
          <el-select
            v-model="selectedModel"
            placeholder="Select model"
            class="flex-1"
            size="small"
            :loading="modelsLoading"
            @change="handleModelSwitch"
          >
            <el-option
              v-for="m in availableModels"
              :key="m.name"
              :label="`${m.name}  (${m.login_provider})`"
              :value="m.name"
            />
          </el-select>
          <el-button
            size="small"
            :icon="SettingIcon"
            circle
            class="model-config-btn"
            title="Model Config"
            @click="openModelConfig"
          />
        </div>
        <div v-if="modelSwitchError" class="text-coral text-[10px] mt-1">
          {{ modelSwitchError }}
        </div>
      </div>
    </div>

    <!-- ── Model Config Dialog ── -->
    <el-dialog
      v-model="configDialogVisible"
      title="Model Config"
      width="480px"
      :close-on-click-modal="false"
      class="model-config-dialog"
    >
      <div class="text-xs text-warm-400 mb-2">
        Edit LLM profile settings as JSON. Changes apply to the current session.
      </div>
      <el-input
        v-model="configJson"
        type="textarea"
        :rows="14"
        class="config-textarea"
        spellcheck="false"
      />
      <div v-if="configJsonError" class="text-coral text-[10px] mt-1">
        {{ configJsonError }}
      </div>
      <template #footer>
        <el-button size="small" @click="configDialogVisible = false">Cancel</el-button>
        <el-button size="small" type="primary" class="save-btn" @click="saveModelConfig">
          Save
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { Setting as SettingIcon } from "@element-plus/icons-vue";

import StatusDot from "@/components/common/StatusDot.vue";
import GemBadge from "@/components/common/GemBadge.vue";
import { useChatStore } from "@/stores/chat";
import { useStatusStore } from "@/stores/status";
import { configAPI, agentAPI } from "@/utils/api";

const props = defineProps({
  instance: { type: Object, default: null },
  onOpenTab: { type: Function, default: () => {} },
});

const chat = useChatStore();
const status = useStatusStore();

const selectedModel = ref("");
const modelsLoading = ref(false);
const modelSwitchError = ref("");

/** @type {import('vue').Ref<{id: string, name: string}[]>} */
const availableModels = ref([]);

// Model config dialog state
const configDialogVisible = ref(false);
const configJson = ref("");
const configJsonError = ref("");

// Runtime display: show elapsed time from sessionInfo.startTime, or "--" if unavailable
const now = ref(Date.now());
let runtimeInterval = null;

onMounted(() => {
  loadModels();
  runtimeInterval = setInterval(() => {
    now.value = Date.now();
  }, 1000);
});

onUnmounted(() => {
  if (runtimeInterval) clearInterval(runtimeInterval);
});

// Init model from instance data (available immediately) or session info (from WS)
watch(
  [() => props.instance?.model, () => chat.sessionInfo.model],
  ([instanceModel, sessionModel]) => {
    const best = sessionModel || instanceModel || "";
    if (best && best !== selectedModel.value) {
      selectedModel.value = best;
    }
  },
  { immediate: true },
);

const runtimeDisplay = computed(() => {
  const startTime = status.sessionInfo.startTime;
  if (!startTime) return "\u2014";

  // Force reactivity on the ticking `now` ref
  const elapsed = Math.max(0, Math.floor((now.value - startTime) / 1000));
  if (elapsed < 1) return "\u2014";

  const h = Math.floor(elapsed / 3600);
  const m = Math.floor((elapsed % 3600) / 60);
  const sec = elapsed % 60;
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
    availableModels.value = (models || []).filter((m) => m.available !== false);
  } catch {
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
    selectedModel.value = chat.sessionInfo.model || "";
  }
}

/** Open the model config dialog with current profile as JSON */
function openModelConfig() {
  configJsonError.value = "";
  // Build a default profile object from what we know
  const profile = {
    model: selectedModel.value || chat.sessionInfo.model || "",
    extra_body: {},
  };
  configJson.value = JSON.stringify(profile, null, 2);
  configDialogVisible.value = true;
}

/** Validate and save model config (currently logs to console) */
function saveModelConfig() {
  configJsonError.value = "";
  try {
    const parsed = JSON.parse(configJson.value);
    console.log("[StatusDashboard] Model config saved:", parsed);
    configDialogVisible.value = false;
  } catch (e) {
    configJsonError.value = "Invalid JSON: " + e.message;
  }
}
</script>

<style scoped>
.section-label {
  @apply text-warm-400 mb-1.5 uppercase tracking-wider text-[10px] font-medium;
}

/* Element Plus select warm toning */
:deep(.el-select) {
  --el-fill-color-blank: var(--color-surface);
  --el-border-color: var(--color-border);
  --el-text-color-regular: var(--color-text);
}

/* Model config gear button - iolite accent */
.model-config-btn {
  --el-button-hover-bg-color: rgba(90, 79, 207, 0.1);
  --el-button-hover-border-color: #5A4FCF;
  --el-button-hover-text-color: #5A4FCF;
  color: var(--color-text-muted);
}

/* Model config dialog */
:deep(.model-config-dialog .el-dialog__header) {
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--el-border-color);
}

:deep(.model-config-dialog .el-dialog__title) {
  font-weight: 600;
}

:deep(.model-config-dialog .el-dialog__body) {
  padding: 16px 20px;
}

:deep(.model-config-dialog .el-dialog__footer) {
  padding: 12px 20px 16px;
  border-top: 1px solid var(--el-border-color);
}

:deep(.config-textarea .el-textarea__inner) {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  resize: vertical;
}

/* Save button iolite accent */
.save-btn {
  --el-button-bg-color: #5A4FCF;
  --el-button-border-color: #5A4FCF;
  --el-button-hover-bg-color: #4A3FBF;
  --el-button-hover-border-color: #4A3FBF;
}
</style>
