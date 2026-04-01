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
      <GemBadge :gem="instance.type === 'terrarium' ? 'iolite' : 'aquamarine'">
        {{ instance.type }}
      </GemBadge>
      <span class="text-xs text-warm-400 font-mono truncate">{{
        instance.pwd
      }}</span>
      <div class="flex-1" />
      <el-tooltip
        :content="
          layoutMode === 'horizontal' ? 'Vertical layout' : 'Horizontal layout'
        "
        placement="bottom"
      >
        <button class="nav-item !w-7 !h-7" @click="toggleLayout">
          <div
            :class="
              layoutMode === 'horizontal' ? 'i-carbon-column' : 'i-carbon-row'
            "
            class="text-sm"
          />
        </button>
      </el-tooltip>
      <el-tooltip content="Stop instance" placement="bottom">
        <button
          class="nav-item !w-7 !h-7 text-coral hover:!text-coral-shadow"
          @click="handleStop"
        >
          <div class="i-carbon-stop-filled text-sm" />
        </button>
      </el-tooltip>
    </div>

    <!-- Main content -->
    <div class="flex-1 overflow-hidden">
      <!-- Terrarium: chat + graph + inspector -->
      <SplitPane
        v-if="instance.type === 'terrarium'"
        :horizontal="layoutMode === 'vertical'"
        :initial-size="50"
      >
        <template #first>
          <ChatPanel :instance="instance" />
        </template>
        <template #second>
          <SplitPane
            :horizontal="layoutMode === 'horizontal'"
            :initial-size="50"
          >
            <template #first>
              <TopologyGraph
                :instance="instance"
                @node-click="handleNodeClick"
              />
            </template>
            <template #second>
              <InspectorPanel :instance="instance" />
            </template>
          </SplitPane>
        </template>
      </SplitPane>
      <!-- Standalone creature: chat only, full width -->
      <div v-else class="h-full">
        <ChatPanel :instance="instance" />
      </div>
    </div>
  </div>
</template>

<script setup>
import StatusDot from "@/components/common/StatusDot.vue";
import GemBadge from "@/components/common/GemBadge.vue";
import SplitPane from "@/components/common/SplitPane.vue";
import ChatPanel from "@/components/chat/ChatPanel.vue";
import TopologyGraph from "@/components/graph/TopologyGraph.vue";
import InspectorPanel from "@/components/inspector/InspectorPanel.vue";
import { useInstancesStore } from "@/stores/instances";
import { useChatStore } from "@/stores/chat";
import { useInspectorStore } from "@/stores/inspector";
import { ElMessageBox } from "element-plus";

const route = useRoute();
const router = useRouter();
const instances = useInstancesStore();
const chat = useChatStore();
const inspector = useInspectorStore();

const instance = computed(() => instances.current);

const layoutMode = ref(localStorage.getItem("layout-mode") || "horizontal");

function toggleLayout() {
  layoutMode.value =
    layoutMode.value === "horizontal" ? "vertical" : "horizontal";
  localStorage.setItem("layout-mode", layoutMode.value);
}

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
    inspector.showOverview(instance.value);
  }
}

function handleNodeClick({ type, data }) {
  if (type === "creature") {
    inspector.selectCreature(data);
  } else if (type === "channel") {
    inspector.selectChannel(data);
  }
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
