<template>
  <div class="flex items-center gap-2 min-w-0">
    <el-select v-if="isTerrarium" :model-value="selectedTarget" size="small" class="status-select target-select" :disabled="!instanceId" @change="onPickTarget">
      <el-option v-for="target in targetOptions" :key="target.value" :label="target.label" :value="target.value" />
    </el-select>
    <div class="flex items-center gap-2 min-w-0">
      <el-select :model-value="currentModel" size="small" class="status-select model-select" :disabled="!instanceId || !canPickModel" :loading="loading" placeholder="Select model" popper-class="model-switcher-popper" @visible-change="onVisibleChange" @change="onPick">
        <template #header>
          <div class="model-search-header" @click.stop @mousedown.stop>
            <input ref="modelSearchInput" v-model.trim="modelSearch" type="text" class="model-search-field" placeholder="Search / filter" @click.stop @keydown.stop />
          </div>
        </template>
        <el-option v-for="m in filteredModels" :key="m.name" :label="modelLabel(m)" :value="m.name" :disabled="m.available === false" />
      </el-select>
      <el-select v-model="reasoningEffort" size="small" class="status-select reasoning-select" :disabled="!supportsReasoningControls" @change="onChangeReasoningEffort">
        <el-option v-for="option in reasoningOptions" :key="option.value || 'default'" :label="option.label" :value="option.value" />
      </el-select>
    </div>
  </div>

  <!-- Model config dialog (opened by gear button in StatusBar) -->
  <el-dialog v-model="configDialogVisible" title="Model Configuration" width="500px" :close-on-click-modal="true">
    <div class="flex flex-col gap-2">
      <p class="text-xs text-warm-400">
        JSON profile for
        <strong class="text-warm-600 dark:text-warm-300">{{ currentModel || "current model" }}</strong>
      </p>
      <textarea v-model="configJson" class="w-full h-48 bg-warm-50 dark:bg-warm-800 border border-warm-200 dark:border-warm-700 rounded p-2 font-mono text-xs resize-y" spellcheck="false" />
      <p v-if="configJsonError" class="text-coral text-xs">
        {{ configJsonError }}
      </p>
    </div>
    <template #footer>
      <el-button size="small" @click="configDialogVisible = false">Cancel</el-button>
      <el-button size="small" type="primary" @click="saveModelConfig">Save</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import { ElMessage } from "element-plus"

import { useChatStore } from "@/stores/chat"
import { useInstancesStore } from "@/stores/instances"
import { agentAPI, terrariumAPI, configAPI } from "@/utils/api"
import { onLayoutEvent, LAYOUT_EVENTS } from "@/utils/layoutEvents"

const route = useRoute()
const chat = useChatStore()
const instances = useInstancesStore()

const models = ref([])
const loading = ref(false)
const modelSearch = ref("")
const modelSearchInput = ref(null)
const reasoningEffort = ref("")
const filteredModels = computed(() => {
  const q = modelSearch.value.trim().toLowerCase()
  if (!q) return models.value
  return models.value.filter((model) => {
    const haystack = [model.name, model.provider, model.login_provider, model.description].filter(Boolean).join(" ").toLowerCase()
    return haystack.includes(q)
  })
})

// Config dialog state
const configDialogVisible = ref(false)
const configJson = ref("")
const configJsonError = ref("")

const currentInstance = computed(() => {
  const id = String(route.params.id || "")
  if (!id) return instances.current
  if (instances.current?.id === id) return instances.current
  return instances.list.find((item) => item.id === id) || null
})
const instanceId = computed(() => currentInstance.value?.id || null)
const isTerrarium = computed(() => currentInstance.value?.type === "terrarium")
const terrariumTarget = computed(() => (isTerrarium.value ? chat.terrariumTarget : null))
const targetOptions = computed(() => {
  const inst = currentInstance.value
  if (inst?.type !== "terrarium") return []
  return [...(inst.has_root ? [{ value: "root", label: "root" }] : []), ...(inst.creatures || []).map((c) => ({ value: c.name, label: c.name }))]
})
const selectedTarget = computed(() => terrariumTarget.value || targetOptions.value[0]?.value || null)
const canPickModel = computed(() => !!instanceId.value && (!isTerrarium.value || !!selectedTarget.value))
const currentModel = computed(() => {
  const inst = currentInstance.value
  if (inst?.type === "terrarium") {
    const target = selectedTarget.value
    if (target === "root") return terrariumTarget.value === target ? chat.sessionInfo.model || inst.model || "" : inst.model || ""
    if (target) {
      const creature = inst.creatures?.find((c) => c.name === target)
      return terrariumTarget.value === target ? chat.sessionInfo.model || creature?.model || "" : creature?.model || ""
    }
    return ""
  }
  return chat.sessionInfo.model || inst?.model || ""
})
const currentModelProfile = computed(() => models.value.find((m) => m.name === currentModel.value) || null)
const reasoningProvider = computed(() => {
  const name = currentModel.value.toLowerCase()
  const provider = String(currentModelProfile.value?.provider || currentModelProfile.value?.login_provider || "").toLowerCase()
  if (name.includes("codex") || provider.includes("codex")) return "codex"
  if (name.includes("gemini") || provider.includes("gemini") || provider.includes("google")) return "gemini"
  if (name.includes("claude") || provider.includes("anthropic") || name.startsWith("anthropic/")) return "anthropic"
  if (name.includes("gpt") || provider.includes("openai")) return "openai"
  return ""
})
const reasoningOptions = computed(() => {
  const base = [{ label: "Reasoning: default", value: "" }]
  if (reasoningProvider.value === "codex") return [...base, { label: "Reasoning: minimal", value: "minimal" }, { label: "Reasoning: low", value: "low" }, { label: "Reasoning: medium", value: "medium" }, { label: "Reasoning: high", value: "high" }, { label: "Reasoning: xhigh", value: "xhigh" }]
  if (reasoningProvider.value === "anthropic") return [...base, { label: "Reasoning: low", value: "low" }, { label: "Reasoning: medium", value: "medium" }, { label: "Reasoning: high", value: "high" }, { label: "Reasoning: max", value: "max" }]
  if (reasoningProvider.value === "gemini") return [...base, { label: "Reasoning: low", value: "low" }, { label: "Reasoning: high", value: "high" }]
  if (reasoningProvider.value === "openai") return [...base, { label: "Reasoning: minimal", value: "minimal" }, { label: "Reasoning: low", value: "low" }, { label: "Reasoning: medium", value: "medium" }, { label: "Reasoning: high", value: "high" }, { label: "Reasoning: xhigh", value: "xhigh" }]
  return base
})
const supportsReasoningControls = computed(() => reasoningProvider.value !== "")

async function loadModels() {
  loading.value = true
  try {
    const data = await configAPI.getModels()
    models.value = Array.isArray(data) ? data : []
  } catch (err) {
    models.value = []
  } finally {
    loading.value = false
  }
}

function syncReasoningEffort() {
  reasoningEffort.value = currentModelProfile.value?.reasoning_effort || "medium"
}

function onVisibleChange(open) {
  if (open) {
    if (models.value.length === 0) loadModels()
    syncReasoningEffort()
    nextTick(() => modelSearchInput.value?.focus())
    return
  }
  modelSearch.value = ""
}

function modelLabel(model) {
  const provider = model.login_provider || model.provider || ""
  return provider ? `${model.name} · ${provider}` : model.name
}

function onPickTarget(target) {
  if (!target || !isTerrarium.value) return
  if (chat.tabs.includes(target)) chat.setActiveTab(target)
  else chat.openTab(target)
}

async function onPick(modelName) {
  const id = instanceId.value
  if (!id || !modelName || modelName === currentModel.value) return
  try {
    const inst = currentInstance.value
    if (inst?.type === "terrarium") {
      const target = selectedTarget.value
      if (!target) {
        ElMessage.error("Select a root or creature first")
        return
      }
      await terrariumAPI.switchCreatureModel(id, target, modelName)
      await instances.fetchOne(id)
      if (terrariumTarget.value === target) {
        chat.sessionInfo.model = modelName
      }
    } else {
      await agentAPI.switchModel(id, modelName)
      chat.sessionInfo.model = modelName
    }
    syncReasoningEffort()
    ElMessage.success(`Switched to ${modelName}`)
  } catch (err) {
    ElMessage.error(`Model switch failed: ${err?.message || err}`)
  }
}

function onChangeReasoningEffort(value) {
  if (!reasoningOptions.value.some((item) => item.value === value)) {
    reasoningEffort.value = ""
    chat.sessionInfo.reasoningEffort = ""
    return
  }
  chat.sessionInfo.reasoningEffort = value || ""
}

/** Open model config dialog with the current profile's JSON */
function openModelConfig() {
  configJsonError.value = ""
  if (models.value.length === 0) loadModels()
  const modelName = currentModel.value
  const fullProfile = models.value.find((m) => m.name === modelName)
  const profile = fullProfile
    ? {
        model: fullProfile.model,
        provider: fullProfile.provider,
        max_context: fullProfile.max_context || 0,
        max_output: fullProfile.max_output || 0,
        temperature: fullProfile.temperature,
        reasoning_effort: fullProfile.reasoning_effort || "",
        extra_body: fullProfile.extra_body || {},
        base_url: fullProfile.base_url || "",
      }
    : { model: modelName, extra_body: {} }
  configJson.value = JSON.stringify(profile, null, 2)
  configDialogVisible.value = true
}

function saveModelConfig() {
  configJsonError.value = ""
  try {
    JSON.parse(configJson.value)
    configDialogVisible.value = false
    ElMessage.success("Config saved")
    // TODO: send updated config to backend when API supports it
  } catch (e) {
    configJsonError.value = "Invalid JSON: " + e.message
  }
}

// Listen for gear button event from StatusBar
let _cleanup = null
watch(currentModelProfile, () => syncReasoningEffort(), { immediate: true })

onMounted(() => {
  _cleanup = onLayoutEvent(LAYOUT_EVENTS.MODEL_CONFIG_OPEN, () => openModelConfig())
})
onUnmounted(() => {
  if (_cleanup) _cleanup()
})
</script>

<style>
.status-select {
  --el-input-bg-color: transparent;
  --el-fill-color-blank: transparent;
  --el-border-color: rgba(120, 109, 98, 0.25);
  --el-border-color-hover: rgba(120, 109, 98, 0.4);
  --el-text-color-regular: currentColor;
}

.target-select {
  width: 8.5rem;
}

.model-select {
  width: 12rem;
}

.reasoning-select {
  width: 8.5rem;
}

.model-search-header {
  padding: 0.375rem;
  border-bottom: 1px solid rgba(120, 109, 98, 0.18);
}

.model-search-field {
  width: 100%;
  height: 28px;
  padding: 0 0.625rem;
  border-radius: 8px;
  border: 1px solid rgba(120, 109, 98, 0.25);
  background: rgba(120, 109, 98, 0.08);
  color: inherit;
  outline: none;
}

.model-search-field:focus {
  border-color: rgba(125, 108, 255, 0.55);
}
</style>
