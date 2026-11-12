from app.providers.prompt_templates import DETAIL_GUIDANCE, MODE_GUIDANCE


def test_all_blueprint_modes_and_detail_levels_exist():
    assert set(MODE_GUIDANCE) == {"natural", "tags", "enhanced"}
    assert set(DETAIL_GUIDANCE) == {"quick", "standard", "detailed", "maximum"}


def test_modes_have_distinct_output_instructions():
    assert MODE_GUIDANCE["natural"] != MODE_GUIDANCE["tags"]
    assert MODE_GUIDANCE["tags"] != MODE_GUIDANCE["enhanced"]


def test_anime_tag_mode_requires_comma_separated_danbooru_style_tags():
    guidance = MODE_GUIDANCE["tags"].lower()
    assert "danbooru" in guidance
    assert "comma-separated" in guidance
    assert "never return prose" in guidance
    assert "output a single line" in guidance
    assert "fixed" not in guidance  # tag order is described explicitly, not vaguely
