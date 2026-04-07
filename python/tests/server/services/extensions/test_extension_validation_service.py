"""
Unit tests for ExtensionValidationService.

Tests validation of SKILL.md content including frontmatter parsing,
name format checks, secret detection, size limits, and content quality.
"""

import pytest

from src.server.services.extensions import ExtensionValidationService


@pytest.fixture
def validator():
    """Create a fresh ExtensionValidationService instance."""
    return ExtensionValidationService()


VALID_SKILL_CONTENT = """\
---
name: my-cool-skill
description: A useful skill that helps developers write better code with AI assistance.
---

## Overview

This skill does something useful for the user.

## Usage

Run `/my-cool-skill` to get started.
"""

MINIMAL_VALID_CONTENT = """\
---
name: minimal-skill
description: A minimal but valid skill.
---

## Usage

Just invoke it.
"""


# ── Valid skill passes validation ──────────────────────────────────────────────


class TestValidSkill:
    def test_valid_skill_passes(self, validator):
        """A well-formed SKILL.md should pass validation with no errors."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["parsed"]["name"] == "my-cool-skill"
        assert "useful skill" in result["parsed"]["description"]

    def test_minimal_valid_skill_passes(self, validator):
        """A minimal but valid skill should pass validation."""
        result = validator.validate(MINIMAL_VALID_CONTENT)

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["parsed"]["name"] == "minimal-skill"

    def test_valid_skill_with_existing_name_match(self, validator):
        """Validation passes when existing_name matches the content name."""
        result = validator.validate(VALID_SKILL_CONTENT, existing_name="my-cool-skill")

        assert result["valid"] is True
        assert result["errors"] == []


# ── Missing frontmatter ───────────────────────────────────────────────────────


class TestMissingFrontmatter:
    def test_no_frontmatter_at_all(self, validator):
        """Content without any --- delimiters should error."""
        content = "# My Skill\n\nJust some markdown."
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])

    def test_single_delimiter(self, validator):
        """Only one --- delimiter is not valid frontmatter."""
        content = "---\nname: test\n# Body"
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])

    def test_empty_frontmatter(self, validator):
        """Empty frontmatter block (no fields) should error on missing name."""
        content = "---\n---\n\n## Body"
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("name" in e.lower() for e in result["errors"])


# ── Missing name field ────────────────────────────────────────────────────────


class TestMissingName:
    def test_frontmatter_without_name(self, validator):
        """Frontmatter that has description but no name should error."""
        content = """\
---
description: Some description here that is long enough.
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("name" in e.lower() for e in result["errors"])

    def test_name_is_empty_string(self, validator):
        """An empty name should fail validation."""
        content = """\
---
name: ""
description: Some valid description for the skill.
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("name" in e.lower() for e in result["errors"])


# ── Bad name format (not kebab-case) ─────────────────────────────────────────


class TestBadNameFormat:
    def test_camel_case_name(self, validator):
        """camelCase names should fail kebab-case validation."""
        content = """\
---
name: myCoolSkill
description: A skill with a badly formatted name field.
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("kebab" in e.lower() for e in result["errors"])

    def test_name_with_spaces(self, validator):
        """Names with spaces should fail."""
        content = """\
---
name: my cool skill
description: A skill with spaces in its name field.
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("kebab" in e.lower() for e in result["errors"])

    def test_name_with_underscores(self, validator):
        """Names with underscores should fail."""
        content = """\
---
name: my_cool_skill
description: A skill with underscores in the name field.
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("kebab" in e.lower() for e in result["errors"])

    def test_name_starting_with_number(self, validator):
        """Names starting with a number should fail."""
        content = """\
---
name: 1-bad-skill
description: A skill whose name starts with a number.
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("kebab" in e.lower() for e in result["errors"])

    def test_name_with_uppercase(self, validator):
        """Names with uppercase letters should fail."""
        content = """\
---
name: My-Skill
description: A skill with uppercase letters in its name.
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("kebab" in e.lower() for e in result["errors"])

    def test_valid_kebab_names(self, validator):
        """Various valid kebab-case names should pass."""
        for name in ["a", "my-skill", "archon-memory", "x-y-z", "skill-v2"]:
            content = f"""\
---
name: {name}
description: A valid skill with a proper kebab-case name.
---

## Body
"""
            result = validator.validate(content)
            assert result["valid"] is True, f"Name '{name}' should be valid but got errors: {result['errors']}"


# ── Secret detection ──────────────────────────────────────────────────────────


class TestSecretDetection:
    def test_openai_api_key(self, validator):
        """OpenAI-style API keys should be detected."""
        content = """\
---
name: leaky-skill
description: A skill that accidentally contains an OpenAI key.
---

## Setup

Set your key: sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("secret" in e.lower() or "key" in e.lower() for e in result["errors"])

    def test_aws_access_key(self, validator):
        """AWS access key IDs should be detected."""
        content = """\
---
name: aws-skill
description: A skill that leaks AWS credentials in the content.
---

## Config

AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("secret" in e.lower() or "key" in e.lower() for e in result["errors"])

    def test_jwt_token(self, validator):
        """JWT tokens should be detected."""
        # A realistic JWT structure (header.payload.signature)
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        content = f"""\
---
name: jwt-skill
description: A skill that accidentally contains a JWT bearer token.
---

## Auth

Bearer {jwt}
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("secret" in e.lower() or "token" in e.lower() or "key" in e.lower() for e in result["errors"])

    def test_private_key_block(self, validator):
        """PEM private key blocks should be detected."""
        content = """\
---
name: pem-skill
description: A skill that accidentally contains a PEM private key.
---

## Setup

-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy5AhBp
-----END RSA PRIVATE KEY-----
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("secret" in e.lower() or "key" in e.lower() or "private" in e.lower() for e in result["errors"])

    def test_clean_content_no_secrets(self, validator):
        """Content without secrets should not trigger detection."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert result["valid"] is True
        assert not any("secret" in e.lower() for e in result["errors"])


# ── Size limit exceeded ───────────────────────────────────────────────────────


class TestSizeLimit:
    def test_content_over_50kb(self, validator):
        """Content exceeding 50KB should fail validation."""
        # 50KB = 51200 bytes; create content slightly over
        large_body = "x" * 52000
        content = f"""\
---
name: big-skill
description: A skill that is way too large for comfortable loading.
---

## Content

{large_body}
"""
        result = validator.validate(content)

        assert result["valid"] is False
        assert any("size" in e.lower() or "large" in e.lower() or "limit" in e.lower() for e in result["errors"])

    def test_content_under_50kb(self, validator):
        """Content under 50KB should not trigger size error."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert result["valid"] is True
        assert not any("size" in e.lower() for e in result["errors"])

    def test_content_exactly_at_50kb(self, validator):
        """Content exactly at 50KB boundary should pass."""
        # Build content that's exactly at the limit
        header = """\
---
name: edge-skill
description: A skill right at the size boundary limit.
---

## Content

"""
        padding_needed = 50 * 1024 - len(header.encode("utf-8"))
        content = header + "a" * padding_needed

        result = validator.validate(content)

        # At exactly 50KB should pass (limit is >, not >=)
        assert result["valid"] is True


# ── Short description warning ─────────────────────────────────────────────────


class TestShortDescriptionWarning:
    def test_short_description_warns(self, validator):
        """A description under 20 characters should produce a warning (not error)."""
        content = """\
---
name: short-desc
description: Too short
---

## Body
"""
        result = validator.validate(content)

        # Should still be valid (warnings don't block)
        assert result["valid"] is True
        assert any("description" in w.lower() for w in result["warnings"])

    def test_missing_description_warns(self, validator):
        """Missing description should produce a warning."""
        content = """\
---
name: no-desc
---

## Body
"""
        result = validator.validate(content)

        assert result["valid"] is True
        assert any("description" in w.lower() for w in result["warnings"])

    def test_adequate_description_no_warning(self, validator):
        """A description >= 20 chars should not produce a warning."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert not any("description" in w.lower() for w in result["warnings"])


# ── No headings warning ──────────────────────────────────────────────────────


class TestNoHeadingsWarning:
    def test_no_headings_warns(self, validator):
        """Content without markdown ## headings should produce a warning."""
        content = """\
---
name: flat-skill
description: A skill with no markdown headings at all in the body.
---

Just some plain text without any headings or structure.
More text here that goes on for a while.
"""
        result = validator.validate(content)

        assert result["valid"] is True
        assert any("heading" in w.lower() for w in result["warnings"])

    def test_with_headings_no_warning(self, validator):
        """Content with ## headings should not produce heading warning."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert not any("heading" in w.lower() for w in result["warnings"])


# ── Parsed output structure ──────────────────────────────────────────────────


class TestParsedOutput:
    def test_parsed_contains_name_and_description(self, validator):
        """The parsed dict should contain name and description from frontmatter."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert "name" in result["parsed"]
        assert "description" in result["parsed"]
        assert result["parsed"]["name"] == "my-cool-skill"

    def test_parsed_contains_body(self, validator):
        """The parsed dict should contain the body (content after frontmatter)."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert "body" in result["parsed"]
        assert "## Overview" in result["parsed"]["body"]

    def test_result_structure(self, validator):
        """Validate result always has valid, errors, warnings, parsed keys."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert "valid" in result
        assert "errors" in result
        assert "warnings" in result
        assert "parsed" in result
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["parsed"], dict)


# ── Hardcoded paths detection ────────────────────────────────────────────────


class TestHardcodedPaths:
    def test_home_directory_path_warns(self, validator):
        """Hardcoded /home/username paths should produce a warning."""
        content = """\
---
name: path-skill
description: A skill that references a hardcoded home directory path.
---

## Setup

Edit the file at /home/john/projects/config.yaml
"""
        result = validator.validate(content)

        assert result["valid"] is True
        assert any("path" in w.lower() or "hardcoded" in w.lower() for w in result["warnings"])

    def test_windows_user_path_warns(self, validator):
        """Hardcoded C:\\Users paths should produce a warning."""
        content = """\
---
name: win-path-skill
description: A skill that references a hardcoded Windows user directory.
---

## Setup

Edit C:\\Users\\john\\Documents\\config.yaml
"""
        result = validator.validate(content)

        assert result["valid"] is True
        assert any("path" in w.lower() or "hardcoded" in w.lower() for w in result["warnings"])

    def test_no_hardcoded_paths_clean(self, validator):
        """Clean content should not produce path warnings."""
        result = validator.validate(VALID_SKILL_CONTENT)

        assert not any("path" in w.lower() or "hardcoded" in w.lower() for w in result["warnings"])


# ── Name mismatch with existing_name ─────────────────────────────────────────


class TestNameMismatch:
    def test_name_mismatch_errors(self, validator):
        """When existing_name is provided and differs from content name, should error."""
        result = validator.validate(VALID_SKILL_CONTENT, existing_name="different-name")

        assert result["valid"] is False
        assert any("mismatch" in e.lower() or "match" in e.lower() for e in result["errors"])


# ── Command validation ────────────────────────────────────────────────────────


class TestCommandValidation:
    def test_command_without_frontmatter_is_valid(self):
        """Commands should be valid even without YAML frontmatter."""
        service = ExtensionValidationService()
        content = "# My Command\n\nDo something useful.\n\n## Instructions\n\nStep 1..."
        result = service.validate(content, extension_type="command")
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_command_with_frontmatter_is_valid(self):
        """Commands with frontmatter should also pass validation."""
        service = ExtensionValidationService()
        content = "---\nname: prime\ndescription: Prime the context\n---\n\n# Prime\n\nContent here."
        result = service.validate(content, extension_type="command")
        assert result["valid"] is True

    def test_command_still_checks_size_limit(self):
        """Commands should still be rejected if they exceed the size limit."""
        service = ExtensionValidationService()
        content = "# Huge Command\n\n" + "x" * (50 * 1024 + 1)
        result = service.validate(content, extension_type="command")
        assert result["valid"] is False
        assert any("size" in e.lower() for e in result["errors"])

    def test_command_still_checks_secrets(self):
        """Commands should still be rejected if they contain secrets."""
        service = ExtensionValidationService()
        content = "# Setup\n\ntoken = 'sk-proj-AAAAAAAAAAAAAAAAAAAAAA'"
        result = service.validate(content, extension_type="command")
        assert result["valid"] is False
        assert any("secret" in e.lower() for e in result["errors"])

    def test_skill_without_frontmatter_still_fails(self):
        """Skills (default type) should still require frontmatter."""
        service = ExtensionValidationService()
        content = "# No Frontmatter Skill\n\nContent."
        result = service.validate(content)
        assert result["valid"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])
