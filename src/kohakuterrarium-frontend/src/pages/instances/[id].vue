<template>
  <div
    v-if="!instance"
    class="h-full flex items-center justify-center text-secondary"
  >
    Loading instance...
  </div>
  <div v-else class="h-full flex flex-col overflow-hidden">
    <!-- Instance header bar -->
    <div
      class="flex items-center gap-3 px-4 py-2 border-b border-b-warm-200 dark:border-b-warm-700 bg-white dark:bg-warm-900 shrink-0"
    >
      <StatusDot :status="instance.status" />
      <span class="font-semibold text-warm-800 dark:text-warm-200 text-sm">{{
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
          @click="handleStop"
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
  </div>
</template>

<script setup>
import StatusDot from "@/components/common/StatusDot.vue";
import SplitPane from "@/components/common/SplitPane.vue";
import ChatPanel from "@/components/chat/ChatPanel.vue";
import StatusDashboard from "@/components/status/StatusDashboard.vue";
import { useInstancesStore } from "@/stores/instances";
import { useChatStore } from "@/stores/chat";
import { ElMessageBox } from "element-plus";

const route = useRoute();
const router = useRouter();
const instances = useInstancesStore();
const chat = useChatStore();

const instance = computed(() => instances.current);

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

async function handleStop() {
  try {
    await ElMessageBox.confirm(
      `Stop instance "${instance.value?.config_name}"?`,
      "Confirm",
      {
        confirmButtonText: "Stop",
        cancelButtonText: "Cancel",
        type: "warning",
      },
    );
    await instances.stop(route.params.id);
    router.push("/");
  } catch {
    // cancelled
  }
}
</script>
