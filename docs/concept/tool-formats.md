# Tool Call Formats

KohakuTerrarium supports multiple formats for tool calls in LLM output. The format is configurable per agent via the `tool_format` field in `config.yaml`.

## Available Formats

### Bracket Format (Default)

The default text-based format. Opening tags use `[/name]`, closing tags use `[name/]`. Arguments use `@@key=value` on separate lines.

```
[/bash]ls -la[bash/]

[/read]
@@path=src/main.py
@@offset=100
@@limit=50
[read/]

[/send_message]
@@channel=ideas
Here is my story concept.
[send_message/]
```

**Properties:**
- `start_char`: `[`
- `end_char`: `]`
- `slash_means_open`: `true` (slash after `[` means opening tag)
- `arg_style`: `line` (one `@@key=value` per line)

### XML Format

XML-style tags. Arguments are inline attributes. Useful for models trained on XML-heavy data.

```
<bash>ls -la</bash>

<read path="src/main.py" offset="100" limit="50"></read>

<send_message channel="ideas">
Here is my story concept.
</send_message>
```

**Properties:**
- `start_char`: `<`
- `end_char`: `>`
- `slash_means_open`: `false` (slash after `<` means closing tag, standard XML)
- `arg_style`: `inline` (attributes in opening tag)

### Native Tool Calling

Uses the LLM provider's built-in function calling API (e.g., OpenAI tool use). The stream parser is bypassed - tool calls come as structured data from the API response.

This is the most reliable format for models that support it well, since the model is constrained to produce valid tool calls.

## Configuration

Set the format in your agent's `config.yaml`:

```yaml
controller:
  model: "gpt-4o-mini"
  tool_format: bracket    # "bracket", "xml", or "native"
```

### Bracket (default)

```yaml
controller:
  tool_format: bracket
```

### XML

```yaml
controller:
  tool_format: xml
```

### Native

```yaml
controller:
  tool_format: native
```

### Custom Format

You can also pass a dict with custom delimiters:

```yaml
controller:
  tool_format:
    start_char: "["
    end_char: "]"
    slash_means_open: true
    arg_style: "line"
    arg_prefix: "@@"
    arg_kv_sep: "="
```

## How It Works

The `ToolCallFormat` dataclass defines the parsing rules:

```python
@dataclass(frozen=True)
class ToolCallFormat:
    start_char: str = "["
    end_char: str = "]"
    slash_means_open: bool = True
    arg_style: str = "line"     # "line" or "inline"
    arg_prefix: str = "@@"
    arg_kv_sep: str = "="
```

The stream parser's state machine uses `start_char` and `end_char` to detect potential tags. The `slash_means_open` flag determines whether a slash after the start character indicates an opening or closing tag:

- **Bracket** (`slash_means_open=True`): `[/name]` is opening, `[name/]` is closing
- **XML** (`slash_means_open=False`): `<name>` is opening, `</name>` is closing

The `arg_style` field controls how arguments are parsed:
- **line**: Arguments on separate lines with `@@key=value` syntax
- **inline**: Attributes in the opening tag with `key="value"` syntax

For native tool calling, the parser is not involved - the LLM provider returns structured tool call objects directly.

## Choosing a Format

| Format | Best for | Notes |
|--------|----------|-------|
| `bracket` | Most models, default | Clear delimiters, unlikely to conflict with natural text |
| `xml` | Models trained on XML data | Standard XML syntax, may conflict with HTML/XML in output |
| `native` | OpenAI, Anthropic, Gemini | Most reliable, but requires provider support |

The prompt aggregator automatically adjusts framework hints to match the configured format, so the LLM receives instructions appropriate for the format in use.
