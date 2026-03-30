# Complexity Tracking

Auto-generated from AST analysis. Updated: 2026-03-30

## File Sizes (over 100 lines)

| File | Lines | Funcs | Status |
|------|-------|-------|--------|
| `parsing/state_machine.py` | 636 | 20 | SPLIT |
| `modules/subagent/manager.py` | 605 | 26 | SPLIT |
| `prompt/aggregator.py` | 588 | 11 | SPLIT |
| `core/agent_handlers.py` | 581 | 10 | SPLIT |
| `core/controller.py` | 541 | 21 | SPLIT |
| `modules/subagent/base.py` | 517 | 14 | SPLIT |
| `llm/openai.py` | 501 | 13 | SPLIT |
| `core/agent_init.py` | 496 | 14 | WATCH |
| `core/agent.py` | 474 | 28 | WATCH |
| `core/config.py` | 463 | 15 | WATCH |
| `terrarium/runtime.py` | 436 | 11 | WATCH |
| `serving/manager.py` | 432 | 30 | WATCH |
| `modules/subagent/interactive.py` | 430 | 14 | WATCH |
| `modules/output/router.py` | 416 | 30 | WATCH |
| `builtins/tools/edit.py` | 396 | 7 |  |
| `core/executor.py` | 386 | 19 |  |
| `builtins/outputs/tts.py` | 385 | 25 |  |
| `core/conversation.py` | 374 | 20 |  |
| `builtins/inputs/whisper.py` | 362 | 9 |  |
| `core/channel.py` | 349 | 34 |  |
| `llm/message.py` | 325 | 18 |  |
| `commands/read.py` | 321 | 12 |  |
| `prompt/plugins.py` | 299 | 21 |  |
| `core/loader.py` | 293 | 9 |  |
| `llm/base.py` | 292 | 12 |  |
| `builtins/tools/bash.py` | 289 | 12 |  |
| `builtins/tui/session.py` | 289 | 22 |  |
| `utils/async_utils.py` | 288 | 17 |  |
| `utils/logging.py` | 286 | 13 |  |
| `builtins/inputs/asr.py` | 282 | 15 |  |
| `core/job.py` | 278 | 21 |  |
| `modules/tool/base.py` | 271 | 19 |  |
| `parsing/patterns.py` | 249 | 8 |  |
| `builtins/tools/tree.py` | 248 | 7 |  |
| `llm/tools.py` | 245 | 1 |  |
| `testing/agent.py` | 237 | 14 |  |
| `__main__.py` | 218 | 4 |  |
| `terrarium/api.py` | 214 | 10 |  |
| `terrarium/cli.py` | 212 | 7 |  |
| `terrarium/hotplug.py` | 208 | 4 |  |
| `builtins/tools/send_message.py` | 204 | 5 |  |
| `modules/subagent/config.py` | 202 | 4 |  |
| `core/events.py` | 195 | 8 |  |
| `builtins/tools/grep.py` | 194 | 5 |  |
| `builtins/inputs/cli.py` | 181 | 9 |  |
| `builtins/tools/json_write.py` | 181 | 7 |  |
| `terrarium/observer.py` | 178 | 9 |  |
| `parsing/events.py` | 175 | 7 |  |
| `core/registry.py` | 171 | 20 |  |
| `builtins/tools/json_read.py` | 169 | 7 |  |
| `testing/llm.py` | 164 | 7 |  |
| `terrarium/config.py` | 163 | 4 |  |
| `terrarium/output_log.py` | 155 | 15 |  |
| `builtins/tools/wait_channel.py` | 151 | 5 |  |
| `core/termination.py` | 151 | 9 |  |
| `builtins/tools/scratchpad_tool.py` | 144 | 5 |  |
| `builtins/tools/http_tool.py` | 143 | 5 |  |
| `prompt/skill_loader.py` | 142 | 4 |  |
| `builtins/outputs/stdout.py` | 141 | 9 |  |
| `builtins/tools/read.py` | 141 | 5 |  |
| `builtins/tools/glob.py` | 140 | 6 |  |
| `commands/base.py` | 132 | 9 |  |
| `modules/output/base.py` | 127 | 20 |  |
| `modules/trigger/base.py` | 127 | 14 |  |
| `modules/trigger/context.py` | 127 | 7 |  |
| `modules/trigger/channel.py` | 125 | 4 |  |
| `testing/output.py` | 123 | 17 |  |
| `parsing/__init__.py` | 121 | 3 |  |
| `builtins/tools/write.py` | 115 | 5 |  |
| `builtins/inputs/__init__.py` | 114 | 7 |  |
| `builtins/outputs/__init__.py` | 113 | 7 |  |
| `testing/events.py` | 112 | 11 |  |
| `builtins/tui/input.py` | 111 | 5 |  |
| `serving/agent_session.py` | 111 | 8 |  |
| `core/__init__.py` | 109 | 1 |  |
| `builtins/tui/output.py` | 106 | 11 |  |
| `prompt/template.py` | 103 | 5 |  |
| `modules/trigger/timer.py` | 102 | 5 |  |
| `builtin_skills/__init__.py` | 101 | 6 |  |

## Large Functions (over 30 lines)

| File | Function | Lines | Nest | Status |
|------|----------|-------|------|--------|
| `core/agent_handlers.py` | `AgentHandlersMixin._process_event_with_controller` | 258 | 6 | SPLIT+NEST |
| `core/controller.py` | `Controller.run_once` | 137 | 6 | SPLIT+NEST |
| `llm/openai.py` | `OpenAIProvider._stream_chat` | 135 | 8 | SPLIT+NEST |
| `llm/openai.py` | `OpenAIProvider._complete_chat` | 123 | 3 | SPLIT |
| `core/config.py` | `load_agent_config` | 122 | 4 | SPLIT |
| `builtins/tools/send_message.py` | `SendMessageTool._execute` | 110 | 3 | SPLIT |
| `builtins/tools/grep.py` | `GrepTool._execute` | 107 | 7 | SPLIT+NEST |
| `builtins/tools/edit.py` | `EditTool._execute` | 105 | 2 | SPLIT |
| `core/agent_handlers.py` | `AgentHandlersMixin._get_and_cleanup_background_status` | 104 | 4 | SPLIT |
| `modules/subagent/interactive.py` | `InteractiveSubAgent._generate_response` | 100 | 7 | WATCH+NEST |
| `prompt/aggregator.py` | `aggregate_system_prompt` | 96 | 3 | WATCH |
| `modules/subagent/base.py` | `SubAgent._run_internal` | 92 | 5 | WATCH+NEST |
| `modules/subagent/manager.py` | `SubAgentManager.spawn` | 90 | 2 | WATCH |
| `llm/tools.py` | `build_tool_schemas` | 87 | 4 | WATCH |
| `builtins/inputs/whisper.py` | `WhisperASR._recording_loop` | 86 | 6 | WATCH+NEST |
| `builtins/tools/edit.py` | `parse_unified_diff` | 86 | 6 | WATCH+NEST |
| `core/executor.py` | `Executor._run_tool` | 84 | 2 | WATCH |
| `terrarium/cli.py` | `_run_terrarium_cli` | 81 | 2 | WATCH |
| `terrarium/runtime.py` | `TerrariumRuntime._build_creature` | 79 | 2 | WATCH |
| `prompt/aggregator.py` | `_build_tool_examples` | 78 | 4 | WATCH |
| `builtins/tools/bash.py` | `BashTool._execute` | 74 | 2 | WATCH |
| `builtins/tools/wait_channel.py` | `WaitChannelTool._execute` | 74 | 3 | WATCH |
| `terrarium/hotplug.py` | `HotPlugMixin.wire_channel` | 73 | 2 | WATCH |
| `builtins/tools/edit.py` | `apply_hunks` | 71 | 5 | WATCH+NEST |
| `prompt/aggregator.py` | `_build_channel_hints` | 70 | 2 | WATCH |
| `terrarium/runtime.py` | `_build_channel_topology_prompt` | 70 | 2 | WATCH |
| `builtins/tools/tree.py` | `build_tree` | 68 | 7 | WATCH+NEST |
| `builtins/tools/http_tool.py` | `HttpTool._execute` | 67 | 2 | WATCH |
| `parsing/state_machine.py` | `StreamParser._complete_block` | 67 | 4 | WATCH |
| `core/agent.py` | `Agent.run` | 65 | 4 | WATCH |
| `prompt/aggregator.py` | `aggregate_with_plugins` | 65 | 3 | WATCH |
| `builtins/tools/edit.py` | `EditTool.get_full_documentation` | 64 | 0 | WATCH |
| `builtins/tools/read.py` | `ReadTool._execute` | 62 | 2 | WATCH |
| `modules/subagent/base.py` | `SubAgent._execute_tools` | 62 | 3 | WATCH |
| `testing/agent.py` | `TestAgentBuilder.build` | 62 | 3 | WATCH |
| `__main__.py` | `show_agent_info_cli` | 60 | 4 |  |
| `builtins/tools/scratchpad_tool.py` | `ScratchpadTool.get_full_documentation` | 60 | 0 |  |
| `core/controller.py` | `Controller.__init__` | 60 | 1 |  |
| `builtins/tools/json_write.py` | `JsonWriteTool._execute` | 59 | 3 |  |
| `commands/read.py` | `InfoCommand._execute` | 59 | 5 | NEST |
| `modules/subagent/manager.py` | `SubAgentManager.start_interactive` | 59 | 1 |  |
| `utils/async_utils.py` | `retry_async` | 59 | 3 |  |
| `commands/read.py` | `WaitCommand._execute` | 58 | 5 | NEST |
| `serving/manager.py` | `KohakuManager._stream_from_registry` | 58 | 3 |  |
| `core/agent_handlers.py` | `AgentHandlersMixin._collect_tool_results` | 56 | 4 |  |
| `llm/openai.py` | `OpenAIProvider.__init__` | 56 | 1 |  |
| `builtins/tools/send_message.py` | `SendMessageTool.get_full_documentation` | 55 | 0 |  |
| `core/agent.py` | `Agent.__init__` | 55 | 0 |  |
| `commands/read.py` | `ReadCommand._execute` | 54 | 5 | NEST |
| `parsing/state_machine.py` | `StreamParser.flush` | 54 | 9 | NEST |
| `utils/logging.py` | `ColoredFormatter.format` | 54 | 2 |  |
| `core/agent_init.py` | `AgentInitMixin._init_controller` | 53 | 2 |  |
| `core/loader.py` | `ModuleLoader._load_module_from_file` | 53 | 2 |  |
| `modules/subagent/manager.py` | `SubAgentManager._run_subagent` | 53 | 2 |  |
| `__main__.py` | `main` | 52 | 4 |  |
| `terrarium/runtime.py` | `TerrariumRuntime.start` | 52 | 1 |  |
| `builtins/tools/scratchpad_tool.py` | `ScratchpadTool._execute` | 51 | 2 |  |
| `builtins/tools/json_read.py` | `JsonReadTool._execute` | 50 | 2 |  |
| `builtins/tools/tree.py` | `TreeTool.get_full_documentation` | 50 | 0 |  |
| `core/agent.py` | `Agent.set_output_handler` | 50 | 1 |  |
| `core/controller.py` | `Controller._format_events_for_context` | 50 | 6 | NEST |
| `core/termination.py` | `TerminationChecker.should_terminate` | 50 | 3 |  |
| `modules/subagent/base.py` | `SubAgent.__init__` | 50 | 2 |  |
| `terrarium/runtime.py` | `TerrariumRuntime._run_creature` | 50 | 4 |  |
| `core/conversation.py` | `Conversation._maybe_truncate` | 49 | 3 |  |
| `terrarium/config.py` | `load_terrarium_config` | 49 | 1 |  |
| `core/agent_init.py` | `AgentInitMixin._create_trigger` | 47 | 2 |  |
| `builtins/inputs/whisper.py` | `WhisperASR._process_audio` | 46 | 2 |  |
| `builtins/tools/bash.py` | `PythonTool._execute` | 46 | 2 |  |
| `core/agent_init.py` | `AgentInitMixin._create_subagent_config` | 46 | 3 |  |
| `terrarium/api.py` | `TerrariumAPI.send_to_channel` | 46 | 1 |  |
| `builtins/tools/grep.py` | `GrepTool.get_full_documentation` | 45 | 0 |  |
| `builtins/tools/json_write.py` | `JsonWriteTool.get_full_documentation` | 45 | 0 |  |
| `core/agent_handlers.py` | `AgentHandlersMixin._start_tool_async` | 45 | 2 |  |
| `core/conversation.py` | `Conversation.append` | 45 | 1 |  |
| `modules/subagent/base.py` | `SubAgent.run` | 45 | 1 |  |
| `modules/subagent/config.py` | `SubAgentConfig.load_prompt` | 45 | 3 |  |
| `modules/trigger/channel.py` | `ChannelTrigger.wait_for_trigger` | 45 | 4 |  |
| `builtins/tools/tree.py` | `parse_frontmatter` | 44 | 4 |  |
| `commands/base.py` | `parse_command_args` | 44 | 4 |  |
| `core/executor.py` | `Executor.submit` | 44 | 1 |  |
| `modules/subagent/config.py` | `SubAgentConfig.from_dict` | 44 | 1 |  |
| `utils/async_utils.py` | `first_result` | 44 | 3 |  |
| `utils/logging.py` | `get_logger` | 44 | 1 |  |
| `modules/output/router.py` | `OutputRouter._handle_output` | 43 | 2 |  |
| `builtins/inputs/whisper.py` | `WhisperASR._load_models` | 42 | 2 |  |
| `builtins/tools/ask_user.py` | `AskUserTool.get_full_documentation` | 42 | 0 |  |
| `builtins/tools/bash.py` | `BashTool.get_full_documentation` | 42 | 0 |  |
| `builtins/tools/http_tool.py` | `HttpTool.get_full_documentation` | 42 | 0 |  |
| `builtins/tools/write.py` | `WriteTool._execute` | 42 | 2 |  |
| `core/agent_init.py` | `AgentInitMixin._init_input` | 42 | 5 | NEST |
| `parsing/state_machine.py` | `StreamParser._handle_in_close_name` | 42 | 5 | NEST |
| `prompt/aggregator.py` | `_build_full_tool_docs` | 42 | 3 |  |
| `prompt/plugins.py` | `ProjectInstructionsPlugin.get_content` | 42 | 4 |  |
| `builtins/tools/glob.py` | `GlobTool.get_full_documentation` | 41 | 0 |  |
| `builtins/tools/json_read.py` | `JsonReadTool.get_full_documentation` | 41 | 0 |  |
| `core/loader.py` | `ModuleLoader.load_config_object` | 41 | 2 |  |
| `prompt/plugins.py` | `FrameworkHintsPlugin.get_content` | 40 | 0 |  |
| `__main__.py` | `list_agents_cli` | 39 | 4 |  |
| `modules/subagent/base.py` | `SubAgent._build_system_prompt` | 39 | 2 |  |
| `terrarium/cli.py` | `add_terrarium_subparser` | 39 | 0 |  |
| `builtins/tools/read.py` | `ReadTool.get_full_documentation` | 38 | 0 |  |
| `llm/base.py` | `LLMProvider.chat` | 38 | 0 |  |
| `modules/subagent/manager.py` | `SubAgentManager.__init__` | 38 | 0 |  |
| `terrarium/hotplug.py` | `HotPlugMixin.remove_creature` | 38 | 3 |  |
| `builtins/inputs/cli.py` | `CLIInput.get_input` | 37 | 2 |  |
| `core/agent_init.py` | `AgentInitMixin._create_output_module` | 37 | 2 |  |
| `core/executor.py` | `Executor.wait_all` | 37 | 1 |  |
| `llm/openai.py` | `OpenAIProvider._build_request_body` | 37 | 2 |  |
| `parsing/state_machine.py` | `StreamParser._handle_maybe_close` | 37 | 3 |  |
| `core/loader.py` | `ModuleLoader.load_class` | 36 | 2 |  |
| `parsing/state_machine.py` | `StreamParser._parse_block_content` | 36 | 3 |  |
| `terrarium/hotplug.py` | `HotPlugMixin.add_creature` | 36 | 1 |  |
| `testing/agent.py` | `TestAgentEnv.inject` | 36 | 4 |  |
| `builtins/tools/tree.py` | `TreeTool._execute` | 35 | 1 |  |
| `builtins/tools/wait_channel.py` | `WaitChannelTool.get_full_documentation` | 35 | 0 |  |
| `core/agent_init.py` | `AgentInitMixin._init_executor` | 35 | 2 |  |
| `llm/message.py` | `create_message` | 35 | 2 |  |
| `modules/subagent/manager.py` | `SubAgentManager.wait_all` | 35 | 1 |  |
| `modules/trigger/timer.py` | `TimerTrigger.wait_for_trigger` | 35 | 2 |  |
| `parsing/patterns.py` | `build_tool_args` | 35 | 2 |  |
| `parsing/state_machine.py` | `StreamParser._handle_in_open_name` | 35 | 4 |  |
| `prompt/aggregator.py` | `_build_tools_list` | 35 | 2 |  |
| `prompt/skill_loader.py` | `parse_frontmatter` | 35 | 2 |  |
| `terrarium/cli.py` | `_info_terrarium_cli` | 35 | 2 |  |
| `builtins/tools/glob.py` | `GlobTool._find_files` | 34 | 2 |  |
| `core/controller.py` | `Controller._collect_events` | 34 | 4 |  |
| `prompt/skill_loader.py` | `load_skill_doc` | 34 | 1 |  |
| `serving/agent_session.py` | `AgentSession.chat` | 34 | 3 |  |
| `modules/output/router.py` | `OutputRouter.__init__` | 33 | 0 |  |
| `modules/subagent/interactive.py` | `InteractiveSubAgent.__init__` | 33 | 0 |  |
| `__main__.py` | `run_agent_cli` | 32 | 2 |  |
| `builtins/inputs/cli.py` | `NonBlockingCLIInput.get_input` | 32 | 2 |  |
| `builtins/tools/bash.py` | `PythonTool.get_full_documentation` | 32 | 0 |  |
| `builtins/tools/write.py` | `WriteTool.get_full_documentation` | 32 | 0 |  |
| `modules/output/router.py` | `OutputRouter.route` | 32 | 1 |  |
| `modules/subagent/base.py` | `SubAgent._create_limited_registry` | 32 | 3 |  |
| `terrarium/cli.py` | `_run` | 32 | 2 |  |
| `core/agent_init.py` | `AgentInitMixin._resolve_tool_format` | 31 | 2 |  |
| `core/agent.py` | `Agent.from_path` | 30 | 0 |  |
| `core/agent_init.py` | `AgentInitMixin._create_tool` | 30 | 2 |  |
| `core/agent_init.py` | `AgentInitMixin._init_output` | 30 | 1 |  |
| `core/channel.py` | `ChannelRegistry.get_or_create` | 30 | 2 |  |
| `modules/subagent/interactive.py` | `InteractiveSubAgent.start` | 30 | 1 |  |
| `terrarium/hotplug.py` | `HotPlugMixin.add_channel` | 30 | 1 |  |

## Deep Nesting (depth >= 5)

| File | Function | Lines | Nest |
|------|----------|-------|------|
| `parsing/state_machine.py` | `StreamParser.flush` | 54 | **9** |
| `llm/openai.py` | `OpenAIProvider._stream_chat` | 135 | **8** |
| `builtins/tools/grep.py` | `GrepTool._execute` | 107 | **7** |
| `builtins/tools/tree.py` | `build_tree` | 68 | **7** |
| `modules/subagent/interactive.py` | `InteractiveSubAgent._generate_response` | 100 | **7** |
| `builtins/inputs/whisper.py` | `WhisperASR._recording_loop` | 86 | **6** |
| `builtins/tools/edit.py` | `parse_unified_diff` | 86 | **6** |
| `core/agent_handlers.py` | `AgentHandlersMixin._process_event_with_controller` | 258 | **6** |
| `core/controller.py` | `Controller._format_events_for_context` | 50 | **6** |
| `core/controller.py` | `Controller.run_once` | 137 | **6** |
| `builtins/tools/edit.py` | `apply_hunks` | 71 | **5** |
| `commands/read.py` | `ReadCommand._execute` | 54 | **5** |
| `commands/read.py` | `InfoCommand._execute` | 59 | **5** |
| `commands/read.py` | `WaitCommand._execute` | 58 | **5** |
| `core/agent_init.py` | `AgentInitMixin._init_input` | 42 | **5** |
| `core/controller.py` | `Controller.run_loop` | 22 | **5** |
| `modules/subagent/base.py` | `SubAgent._run_internal` | 92 | **5** |
| `parsing/state_machine.py` | `StreamParser._handle_in_close_name` | 42 | **5** |

## Summary

- Files over 500 lines (SPLIT): 7
- Files 400-500 lines (WATCH): 7
- Functions over 100 lines (SPLIT): 9
- Functions with nesting >= 5: 18
