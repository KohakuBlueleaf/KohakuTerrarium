<template>
  <div class="hub-node">
    <Handle
      type="target"
      :position="Position.Top"
      class="hub-handle"
      :style="handleStyle"
    />
    <div
      class="hub-body"
      :class="isBroadcast ? 'hub-body--broadcast' : ''"
      :style="bodyStyle"
    >
      <span class="hub-name" :style="{ color: nameColor }">{{
        data.name
      }}</span>
      <span
        v-if="data.messageCount > 0"
        class="hub-badge"
        :style="{ backgroundColor: color }"
      >
        {{ data.messageCount }}
      </span>
    </div>
    <Handle
      type="source"
      :position="Position.Bottom"
      class="hub-handle"
      :style="handleStyle"
    />
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
const isBroadcast = computed(() => props.data.channelType === "broadcast");
const color = computed(() => channelColor(props.data.channelType).main);

const bodyStyle = computed(() => ({
  background: theme.dark ? "#282523" : "#EDE9E4",
  borderColor: isBroadcast.value
    ? theme.dark
      ? "#C49ECF"
      : "#A57EAE"
    : theme.dark
      ? "#6BC4B0"
      : "#4C9989",
}));

const handleStyle = computed(() => ({
  background: isBroadcast.value
    ? theme.dark
      ? "#C49ECF"
      : "#A57EAE"
    : theme.dark
      ? "#6BC4B0"
      : "#4C9989",
  borderColor: theme.dark ? "#282523" : "#EDE9E4",
}));

const nameColor = computed(() => (theme.dark ? "#D0C8C0" : "#4A4540"));
</script>

<style scoped>
.hub-body {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 14px;
  border: 2px solid;
  border-radius: 14px;
  cursor: pointer;
  transition:
    box-shadow 0.15s ease,
    background 0.2s ease,
    border-color 0.2s ease;
  min-width: 70px;
  justify-content: center;
}
.hub-body:hover {
  box-shadow: 0 0 0 3px rgba(76, 153, 137, 0.15);
}
.hub-body--broadcast {
  border-radius: 6px;
  clip-path: polygon(15% 0%, 85% 0%, 100% 50%, 85% 100%, 15% 100%, 0% 50%);
  padding: 5px 22px;
}
.hub-body--broadcast:hover {
  box-shadow: none;
}
.hub-name {
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 0.02em;
  transition: color 0.2s ease;
}
.hub-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: 8px;
  font-size: 8px;
  font-weight: 700;
  color: #fff;
}
.hub-handle {
  width: 6px;
  height: 6px;
  border: 2px solid;
  border-radius: 50%;
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}
</style>
