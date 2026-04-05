import { terrariumAPI, agentAPI } from "@/utils/api";

export const useInstancesStore = defineStore("instances", {
  state: () => ({
    /** @type {import('@/utils/api').InstanceInfo[]} */
    list: [],
    /** @type {import('@/utils/api').InstanceInfo | null} */
    current: null,
    loading: false,
  }),

  getters: {
    running: (state) => state.list.filter((i) => i.status === "running"),
    terrariums: (state) => state.list.filter((i) => i.type === "terrarium"),
    creatures: (state) => state.list.filter((i) => i.type === "creature"),
  },

  actions: {
    /** Fetch all running instances (both terrariums and standalone agents) */
    async fetchAll() {
      this.loading = true;
      try {
        const [terrariums, agents] = await Promise.all([
          terrariumAPI.list(),
          agentAPI.list(),
        ]);

        const tInstances = terrariums.map((t) => _mapTerrarium(t));
        const aInstances = agents.map((a) => _mapAgent(a));
        this.list = [...tInstances, ...aInstances];
      } catch (err) {
        console.error("Failed to fetch instances:", err);
      } finally {
        this.loading = false;
      }
    },

    /** Fetch a single instance by ID */
    async fetchOne(id) {
      this.loading = true;
      try {
        if (id.startsWith("terrarium_")) {
          const data = await terrariumAPI.get(id);
          this.current = _mapTerrarium(data);
        } else if (id.startsWith("agent_")) {
          const data = await agentAPI.get(id);
          this.current = _mapAgent(data);
        }
      } catch (err) {
        console.error("Failed to fetch instance:", err);
      } finally {
        this.loading = false;
      }
    },

    /** Create a new instance */
    async create(type, configPath) {
      if (type === "terrarium") {
        const { terrarium_id } = await terrariumAPI.create(configPath);
        await this.fetchAll();
        return terrarium_id;
      } else {
        const { agent_id } = await agentAPI.create(configPath);
        await this.fetchAll();
        return agent_id;
      }
    },

    /** Stop an instance */
    async stop(id) {
      if (id.startsWith("terrarium_")) {
        await terrariumAPI.stop(id);
      } else if (id.startsWith("agent_")) {
        await agentAPI.stop(id);
      }
      this.list = this.list.filter((i) => i.id !== id);
      if (this.current?.id === id) {
        this.current = null;
      }
    },
  },
});

/** Map terrarium API response to frontend InstanceInfo */
function _mapTerrarium(data) {
  return {
    id: data.terrarium_id,
    type: "terrarium",
    config_name: data.name,
    status: data.running ? "running" : "stopped",
    has_root: !!data.has_root,
    creatures: Object.entries(data.creatures || {}).map(([name, info]) => ({
      name,
      status: info.running ? "running" : "idle",
      model: "",
      listen_channels: info.listen_channels || [],
      send_channels: info.send_channels || [],
    })),
    channels: (data.channels || []).map((ch) => ({
      name: ch.name,
      type: ch.type,
      description: ch.description || "",
      message_count: ch.qsize || 0,
    })),
  };
}

/** Map agent API response to frontend InstanceInfo */
function _mapAgent(data) {
  return {
    id: data.agent_id,
    type: "creature",
    config_name: data.name || "agent",
    status: data.running ? "running" : "stopped",
    has_root: false,
    creatures: [
      {
        name: data.name || "agent",
        status: data.running ? "running" : "idle",
        model: "",
        listen_channels: [],
        send_channels: [],
      },
    ],
    channels: [],
  };
}
