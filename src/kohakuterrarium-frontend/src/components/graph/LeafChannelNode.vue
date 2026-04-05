<template>
  <div class="leaf-node">
    <Handle
      v-if="data.handleSide === 'right'"
      type="source"
      :position="Position.Right"
      class="leaf-handle"
      :style="handleStyle"
    />
    <Handle
      v-if="data.handleSide === 'left'"
      type="target"
      :position="Position.Left"
      class="leaf-handle"
      :style="handleStyle"
    />
    <div class="leaf-body" :style="bodyStyle">
      <span class="leaf-icon" :style="{ color: color }">
        {{ data.handleSide === "right" ? "&#8594;" : "&#8592;" }}
      </span>
      <span class="leaf-name" :style="{ color: nameColor }">{{
        data.name
      }}</span>
      <span
        v-if="data.messageCount > 0"
        class="leaf-badge"
        :style="{ backgroundColor: color }"
      >
        {{ data.messageCount }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { Handle, Position } from "@vue-flow/core";
import { channelColor } from "@/utils/colors";
import { useThemeStore } from "@/stores/theme";

const props = defineProps({
  data: { type: Object, required: true },
});

const theme = useThemeStore();
const color = computed(
  () => channelColor(props.data.channelType || "queue").main,
);

const bodyStyle = computed(() => ({
  background: theme.dark ? "#282523" : "#EDE9E4",
  borderColor: theme.dark ? "#6BC4B0" : "#4C9989",
}));

const handleStyle = computed(() => ({
  background: theme.dark ? "#6BC4B0" : "#4C9989",
  borderColor: theme.dark ? "#282523" : "#EDE9E4",
}));

const nameColor = computed(() => (theme.dark ? "#D0C8C0" : "#4A4540"));
</script>

<style scoped>
.leaf-body {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1.5px dashed;
  border-radius: 10px;
  cursor: pointer;
  transition:
    box-shadow 0.15s ease,
    background 0.2s ease,
    border-color 0.2s ease;
  min-width: 60px;
  justify-content: center;
}
.leaf-body:hover {
  box-shadow: 0 0 0 3px rgba(76, 153, 137, 0.12);
}
.leaf-icon {
  font-size: 10px;
  font-weight: 700;
}
.leaf-name {
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
  transition: color 0.2s ease;
}
.leaf-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 7px;
  font-size: 8px;
  font-weight: 700;
  color: #fff;
}
.leaf-handle {
  width: 6px;
  height: 6px;
  border: 2px solid;
  border-radius: 50%;
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}
</style>
