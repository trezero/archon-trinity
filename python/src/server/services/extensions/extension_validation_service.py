"""Extension content validation for SKILL.md files.

Validates frontmatter structure, naming conventions, content quality,
and scans for accidentally embedded secrets before allowing upload.
"""

import re
from typing import Any

import yaml

# Maximum allowed size for an extension file (50 KB)
MAX_EXTENSION_SIZE_BYTES = 50 * 1024

# Minimum description length to avoid a quality warning
MIN_DESCRIPTION_LENGTH = 20

# Kebab-case: lowercase letters, digits, hyphens; must start with a letter
KEBAB_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

# Secret detection patterns (compiled for performance)
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI API key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("JWT token", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("PEM private key", re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----")),
    ("Generic secret assignment", re.compile(r"(?:secret|password|token|api_key)\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE)),
]

# Hardcoded path patterns that suggest user-specific absolute paths
HARDCODED_PATH_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Unix home directory", re.compile(r"/home/\w+")),
    ("macOS home directory", re.compile(r"/Users/\w+")),
    ("Windows user directory", re.compile(r"C:\\Users\\\w+")),
]


class ExtensionValidationService:
    """Validates SKILL.md content before upload or update.

    Returns a result dict with:
        valid (bool): True if no errors (warnings are allowed)
        errors (list[str]): Blocking issues that prevent upload
        warnings (list[str]): Non-blocking quality suggestions
        parsed (dict): Extracted frontmatter fields and body text
    """

    def validate(
        self,
        content: str,
        existing_name: str | None = None,
        extension_type: str = "skill",
    ) -> dict[str, Any]:
        """Validate extension content and return structured results.

        Args:
            content: Raw extension file content.
            existing_name: If provided, the name in frontmatter must match this value.
                           Used when updating an existing extension to prevent name changes.
            extension_type: The type of extension being validated ("skill" or "command").
                            Commands allow optional frontmatter; skills require it.

        Returns:
            Dict with keys: valid, errors, warnings, parsed.
        """
        errors: list[str] = []
        warnings: list[str] = []
        parsed: dict[str, Any] = {}

        # Size check (runs on raw content before any parsing)
        self._check_size_limit(content, errors)

        # Frontmatter extraction
        frontmatter = self._parse_frontmatter(content)
        body = self._get_body(content)
        parsed["body"] = body

        if extension_type == "command":
            # Frontmatter is optional for commands — parse it if present but never error on absence
            if frontmatter is not None:
                name = frontmatter.get("name")
                parsed["name"] = name
                description = frontmatter.get("description")
                parsed["description"] = description
                for key, value in frontmatter.items():
                    if key not in ("name", "description"):
                        parsed[key] = value
        else:
            # Skills require valid frontmatter with a name field
            if frontmatter is None:
                errors.append("Missing or malformed YAML frontmatter. Content must start with '---' delimiters.")
            else:
                # Extract and validate name
                name = frontmatter.get("name")
                parsed["name"] = name
                self._check_name(name, errors)

                # Check name matches existing_name when updating
                if existing_name is not None and name and name != existing_name:
                    errors.append(
                        f"Name mismatch: frontmatter name '{name}' does not match "
                        f"existing extension name '{existing_name}'. Extension names cannot be changed after creation."
                    )

                # Extract and check description
                description = frontmatter.get("description")
                parsed["description"] = description
                self._check_description(description, warnings)

                # Pass through any extra frontmatter fields
                for key, value in frontmatter.items():
                    if key not in ("name", "description"):
                        parsed[key] = value

        # Content quality checks (run on body)
        self._check_content_structure(body, warnings)
        self._check_hardcoded_paths(body, warnings)

        # Security scan (run on entire content including frontmatter)
        self._check_secrets(content, errors)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "parsed": parsed,
        }

    def _parse_frontmatter(self, content: str) -> dict[str, Any] | None:
        """Extract YAML frontmatter from content between --- delimiters.

        Returns parsed dict, or None if frontmatter is missing/malformed.
        """
        stripped = content.strip()
        if not stripped.startswith("---"):
            return None

        # Find the closing --- delimiter (skip the opening one)
        second_delimiter = stripped.find("---", 3)
        if second_delimiter == -1:
            return None

        yaml_block = stripped[3:second_delimiter].strip()
        if not yaml_block:
            # Empty frontmatter block: return empty dict so callers
            # can distinguish "no frontmatter" from "empty frontmatter"
            return {}

        try:
            parsed = yaml.safe_load(yaml_block)
        except yaml.YAMLError:
            return None

        if not isinstance(parsed, dict):
            return None

        return parsed

    def _get_body(self, content: str) -> str:
        """Extract everything after the frontmatter block.

        If there's no valid frontmatter, return the entire content.
        """
        stripped = content.strip()
        if not stripped.startswith("---"):
            return content

        second_delimiter = stripped.find("---", 3)
        if second_delimiter == -1:
            return content

        return stripped[second_delimiter + 3:].strip()

    def _check_name(self, name: Any, errors: list[str]) -> None:
        """Validate the extension name field."""
        if not name or not isinstance(name, str) or not name.strip():
            errors.append("Missing required 'name' field in frontmatter.")
            return

        if not KEBAB_CASE_PATTERN.match(name):
            errors.append(
                f"Invalid name format '{name}'. Must be kebab-case "
                "(lowercase letters, digits, and hyphens; must start with a letter). "
                "Examples: 'my-extension', 'archon-memory', 'code-review'."
            )

    def _check_description(self, description: Any, warnings: list[str]) -> None:
        """Check description quality (warnings only, never errors)."""
        if not description or not isinstance(description, str) or not description.strip():
            warnings.append("Missing 'description' field in frontmatter. A description helps users discover the extension.")
            return

        if len(description.strip()) < MIN_DESCRIPTION_LENGTH:
            warnings.append(
                f"Description is short ({len(description.strip())} chars). "
                f"Aim for at least {MIN_DESCRIPTION_LENGTH} characters for better discoverability."
            )

    def _check_size_limit(self, content: str, errors: list[str]) -> None:
        """Check that content does not exceed the maximum allowed size."""
        size = len(content.encode("utf-8"))
        if size > MAX_EXTENSION_SIZE_BYTES:
            errors.append(
                f"Content size ({size:,} bytes) exceeds the {MAX_EXTENSION_SIZE_BYTES:,}-byte limit. "
                "Consider splitting into smaller, focused extensions."
            )

    def _check_secrets(self, content: str, errors: list[str]) -> None:
        """Scan content for accidentally embedded secrets or credentials."""
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(content):
                errors.append(
                    f"Potential secret detected: {label}. "
                    "Remove credentials before uploading. Use environment variables or config references instead."
                )

    def _check_content_structure(self, body: str, warnings: list[str]) -> None:
        """Check that the body contains markdown headings for structure."""
        if not re.search(r"^#{1,6}\s+", body, re.MULTILINE):
            warnings.append(
                "No markdown headings found in the body. "
                "Adding ## sections improves readability and helps AI parse the extension."
            )

    def _check_hardcoded_paths(self, body: str, warnings: list[str]) -> None:
        """Warn about user-specific absolute paths that won't work on other machines."""
        for label, pattern in HARDCODED_PATH_PATTERNS:
            if pattern.search(body):
                warnings.append(
                    f"Hardcoded path detected ({label}). "
                    "Consider using relative paths or environment variables for portability."
                )
                return  # One warning is sufficient
