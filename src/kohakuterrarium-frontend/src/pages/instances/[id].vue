<template>
  <div v-if="instance" class="flex flex-col h-full bg-warm-50 dark:bg-warm-900">
    <!-- Header -->
    <div class="flex items-center gap-3 px-4 py-2 border-b border-warm-200 dark:border-warm-700 bg-white dark:bg-warm-800">
      <StatusDot :status="instance.status" />
      <span class="font-medium text-warm-700 dark:text-warm-300">{{
        instance.config_name
      }}</span>
      <span
        v-if="chat.sessionInfo.model || instance?.model"
        class="px-2 py-0.5 rounded-md text-[11px] font-mono bg-iolite/10 dark:bg-iolite/15 text-iolite dark:text-iolite-light"
      >{{ chat.sessionInfo.model || instance?.model }}</span>
      <span class="text-xs text-warm-400 font-mono truncate">{{
        instance.pwd
      }}</span>
      <div class="flex-1" />
      <el-tooltip content="Stop instance" placement="bottom">
        <button
          class="nav-item !w-7 !h-7 text-coral hover:!text-coral-shadow"
          @click="showStopConfirm = true"
        >
          <div class="i-carbon-stop-filled text-sm" />
        </button>
      </el-tooltip>
    </div>

    <!-- Main content: Chat + StatusDashboard side by side -->
    <div class="flex-1 overflow-hidden">
      <SplitPane
        :initial-size="65"
        :min-size="30"
        persist-key="main"
      >
        <template #first>
          <ChatPanel :instance="instance" />
        </template>
        <template #second>
          <StatusDashboard
            :instance="instance"
            :on-open-tab="handleOpenTab"
          />
        </template>
      </SplitPane>
    </div>

    <!-- Stop confirmation dialog -->
    <el-dialog
      v-model="showStopConfirm"
      title="Stop Instance"
      width="400px"
      :close-on-click-modal="true"
    >
      <p class="text-warm-600 dark:text-warm-300">
        Stop <strong>{{ instance.config_name }}</strong>?
        This will terminate the {{ instance.type }} and all its processes.
      </p>
      <template #footer>
        <el-button size="small" @click="showStopConfirm = false">Cancel</el-button>
        <el-button
          size="small"
          type="danger"
          :loading="stopping"
          @click="confirmStop"
        >Stop</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import StatusDot from "@/components/common/StatusDot.vue";
import SplitPane from "@/components/common/SplitPane.vue";
import ChatPanel from "@/components/chat/ChatPanel.vue";
import StatusDashboard from "@/components/status/StatusDashboard.vue";
import { useInstancesStore } from "@/stores/instances";
import { useChatStore } from "@/stores/chat";

const route = useRoute();
const router = useRouter();
const instances = useInstancesStore();
const chat = useChatStore();

const instance = computed(() => instances.current);
const showStopConfirm = ref(false);
const stopping = ref(false);

onMounted(() => {
  loadInstance();
});

watch(() => route.params.id, loadInstance);

async function loadInstance() {
  const id = route.params.id;
  if (!id) return;
  await instances.fetchOne(id);
  if (instance.value) {
    chat.initForInstance(instance.value);
  }
}

function handleOpenTab(tabKey) {
  chat.openTab(tabKey);
}

async function confirmStop() {
  stopping.value = true;
  try {
    await instances.stop(route.params.id);
    showStopConfirm.value = false;
    router.push("/");
  } catch (err) {
    console.error("Stop failed:", err);
  } finally {
    stopping.value = false;
  }
}
</script>
