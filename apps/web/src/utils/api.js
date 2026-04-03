/**
 * API client for KohakuTerrarium backend.
 */

import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

/**
 * @typedef {{ name: string, path: string, description: string }} ConfigItem
 * @typedef {{ id: string, type: string, config_name: string, config_path: string, pwd: string, status: string, has_root: boolean, creatures: object[], channels: object[], created_at: string }} InstanceInfo
 * @typedef {{ id: string, role: string, content: string, timestamp: string, sender?: string, tool_calls?: object[] }} ChatMessage
 */

/** Config discovery */
export const configAPI = {
  /** @returns {Promise<ConfigItem[]>} */
  async listCreatures() {
    const { data } = await api.get("/configs/creatures");
    return data;
  },

  /** @returns {Promise<ConfigItem[]>} */
  async listTerrariums() {
    const { data } = await api.get("/configs/terrariums");
    return data;
  },
};

/** Terrarium lifecycle */
export const terrariumAPI = {
  /** @returns {Promise<{terrarium_id: string}>} */
  async create(configPath) {
    const { data } = await api.post("/terrariums", { config_path: configPath });
    return data;
  },

  /** @returns {Promise<object[]>} */
  async list() {
    const { data } = await api.get("/terrariums");
    return data;
  },

  /** @returns {Promise<object>} */
  async get(id) {
    const { data } = await api.get(`/terrariums/${id}`);
    return data;
  },

  async stop(id) {
    await api.delete(`/terrariums/${id}`);
  },

  /** @returns {Promise<object[]>} */
  async listChannels(id) {
    const { data } = await api.get(`/terrariums/${id}/channels`);
    return data;
  },

  async sendToChannel(id, channelName, content, sender = "human") {
    const { data } = await api.post(
      `/terrariums/${id}/channels/${channelName}/send`,
      { content, sender },
    );
    return data;
  },

  /**
   * Get full history for a creature/root in a terrarium.
   * Returns { messages: [...], events: [...] }
   */
  async getHistory(id, target) {
    const { data } = await api.get(`/terrariums/${id}/history/${target}`);
    return data;
  },

  async interruptCreature(id, name) {
    const { data } = await api.post(
      `/terrariums/${id}/creatures/${name}/interrupt`,
    );
    return data;
  },

  async listCreatureJobs(id, name) {
    const { data } = await api.get(
      `/terrariums/${id}/creatures/${name}/jobs`,
    );
    return data;
  },

  async stopCreatureTask(id, name, jobId) {
    const { data } = await api.post(
      `/terrariums/${id}/creatures/${name}/tasks/${jobId}/stop`,
    );
    return data;
  },
};

/** Standalone agent lifecycle */
export const agentAPI = {
  /** @returns {Promise<{agent_id: string}>} */
  async create(configPath) {
    const { data } = await api.post("/agents", { config_path: configPath });
    return data;
  },

  /** @returns {Promise<object[]>} */
  async list() {
    const { data } = await api.get("/agents");
    return data;
  },

  /** @returns {Promise<object>} */
  async get(id) {
    const { data } = await api.get(`/agents/${id}`);
    return data;
  },

  async stop(id) {
    await api.delete(`/agents/${id}`);
  },

  async interrupt(id) {
    const { data } = await api.post(`/agents/${id}/interrupt`);
    return data;
  },

  /** Get conversation history + event log */
  async getHistory(id) {
    const { data } = await api.get(`/agents/${id}/history`);
    return data;
  },

  /** Non-streaming chat */
  async chat(id, message) {
    const { data } = await api.post(`/agents/${id}/chat`, { message });
    return data;
  },

  async listJobs(id) {
    const { data } = await api.get(`/agents/${id}/jobs`);
    return data;
  },

  async stopTask(id, jobId) {
    const { data } = await api.post(`/agents/${id}/tasks/${jobId}/stop`);
    return data;
  },
};

/** Saved sessions */
export const sessionAPI = {
  /** @returns {Promise<object[]>} */
  async list() {
    const { data } = await api.get("/sessions");
    return data;
  },

  /** @returns {Promise<{instance_id: string, type: string, session_name: string}>} */
  async resume(sessionName) {
    const { data } = await api.post(`/sessions/${sessionName}/resume`);
    return data;
  },

  async delete(sessionName) {
    const { data } = await api.delete(`/sessions/${sessionName}`);
    return data;
  },
};

export default api;
