"""
Prompt templating using Jinja2.

Provides simple variable substitution and control flow for prompts.
"""

from typing import Any

from jinja2 import Environment, BaseLoader, TemplateSyntaxError

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


# Create Jinja2 environment with safe defaults
_env = Environment(
    loader=BaseLoader(),
    autoescape=False,  # Prompts are not HTML
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_template(template: str, **variables: Any) -> str:
    """
    Render a prompt template with variables.

    Supports Jinja2 syntax:
    - Variables: {{ variable }}
    - Conditionals: {% if condition %}...{% endif %}
    - Loops: {% for item in items %}...{% endfor %}

    Args:
        template: Template string with Jinja2 syntax
        **variables: Variables to substitute

    Returns:
        Rendered template string

    Raises:
        TemplateSyntaxError: If template syntax is invalid
    """
    try:
        jinja_template = _env.from_string(template)
        result = jinja_template.render(**variables)
        return result
    except TemplateSyntaxError as e:
        logger.error("Template syntax error", line=e.lineno, message=str(e))
        raise


def render_template_safe(template: str, **variables: Any) -> str:
    """
    Render template, returning original on error.

    Args:
        template: Template string
        **variables: Variables to substitute

    Returns:
        Rendered template or original on error
    """
    try:
        return render_template(template, **variables)
    except Exception as e:
        logger.warning("Template rendering failed, using original", error=str(e))
        return template


class PromptTemplate:
    """
    Reusable prompt template.

    Compiles template once for efficient repeated rendering.
    """

    def __init__(self, template: str):
        """
        Create a prompt template.

        Args:
            template: Jinja2 template string
        """
        self._source = template
        self._template = _env.from_string(template)

    def render(self, **variables: Any) -> str:
        """
        Render the template with variables.

        Args:
            **variables: Variables to substitute

        Returns:
            Rendered string
        """
        return self._template.render(**variables)

    @property
    def source(self) -> str:
        """Get original template source."""
        return self._source
