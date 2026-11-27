import importlib

import pytest

kg_schema = importlib.import_module("kg-schema")

EXPECTED_ENTITY_TYPES = (
    "ARCHITECTURE",
    "CONVENTION",
    "TASK",
    "BUSINESS_TERM",
    "NOTE",
    "TAG",
    "REQUIREMENT",
    "ISSUE",
    "COMMIT",
    "SOURCE_FILE",
)

EXPECTED_RELATIONSHIP_TYPES = (
    "DEPENDS_ON",
    "EXTENDS",
    "USES",
    "CONNECTS_TO",
    "IMPLEMENTS",
    "RELATES_TO",
    "FIXES",
    "RESOLVES",
    "CAUSED_BY",
    "FOLLOWS",
    "VIOLATES",
    "LINKS_TO",
    "TAGGED_WITH",
    "REFERENCES",
    "CHANGES",
)

EXPECTED_MANDATORY_PROPERTY_NAMES = (
    "origin",
    "source_doc",
    "content_hash",
    "rule_id",
    "schema_version",
    "created_at",
    "updated_at",
)


def test_entity_types_match_spec_section_5():
    assert kg_schema.ENTITY_TYPES == EXPECTED_ENTITY_TYPES


def test_relationship_types_match_spec_section_5():
    assert kg_schema.RELATIONSHIP_TYPES == EXPECTED_RELATIONSHIP_TYPES


def test_default_relationship_type_is_links_to():
    assert kg_schema.DEFAULT_RELATIONSHIP_TYPE == "LINKS_TO"
    assert kg_schema.DEFAULT_RELATIONSHIP_TYPE in kg_schema.RELATIONSHIP_TYPES


def test_mandatory_property_names_match_spec_section_5():
    assert kg_schema.MANDATORY_PROPERTY_NAMES == EXPECTED_MANDATORY_PROPERTY_NAMES


def test_schema_version_is_read_from_version_file():
    assert kg_schema.SCHEMA_VERSION == (kg_schema._VERSION_PATH.read_text().strip())


@pytest.mark.parametrize(
    "origin,absent_properties",
    [
        ("curated", {"source_doc", "content_hash", "rule_id"}),
        ("explicit", {"rule_id"}),
        ("extracted", set()),
    ],
)
def test_absent_for_origins_matches_spec_notes(origin, absent_properties):
    actually_absent = {
        prop["name"]
        for prop in kg_schema.MANDATORY_PROPERTIES
        if origin in prop.get("absent_for_origins", ())
    }
    assert actually_absent == absent_properties


def test_schema_version_is_1_2_0_for_traceability_types():
    # ADR-0036: additive bump adding ISSUE/COMMIT/SOURCE_FILE, REFERENCES/
    # CHANGES and shared entity types.
    assert kg_schema.SCHEMA_VERSION == "1.2.0"


def test_source_file_is_the_only_shared_entity_type():
    assert kg_schema.SHARED_ENTITY_TYPES == ("SOURCE_FILE",)


def test_shared_entity_types_are_all_entity_types():
    assert set(kg_schema.SHARED_ENTITY_TYPES) <= set(kg_schema.ENTITY_TYPES)


def test_ownership_properties_are_absent_for_shared_entity_types():
    # A shared node has no owning document (ADR-0036), so the properties
    # that name its owner are absent; everything else still applies.
    absent = {
        prop["name"]
        for prop in kg_schema.MANDATORY_PROPERTIES
        if prop.get("absent_for_shared_entity_types")
    }
    assert absent == {"source_doc", "content_hash"}
