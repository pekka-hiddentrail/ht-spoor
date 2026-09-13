# Output pipeline — ROADMAP.md §2d.
#
# Pluggable sinks downstream of extraction. This Phase-1 pass covers the text
# formats that need no dependencies — JSON, JSON Lines, CSV — with the field
# schema from §2a validated (via pydantic) before anything is written. SQLite
# and Parquet are named in §2d as further/optional sinks and land later (see the
# §2d output-pipeline decision note). Extraction without a usable output path
# isn't a finished tool, so the sink is a first-class stage, not a CLI afterthought.
#
# An output file is a shared surface §2h names explicitly: known secret shapes in
# a record's values are redacted on the way out, on by default, before anything is
# written (the raw record stays only in the local-only cache/map).

Feature: Writing extracted records to a chosen output format
  As someone running an extraction
  I want the records written to a JSON, JSON Lines, or CSV file
  So that I get usable structured output, validated against my config's fields

  Background:
    Given a config with a "title" string field and a "price" number field
    And two extracted records, the second missing its price

  Scenario: Records are written as a JSON array
    When I write the records to "out.json"
    Then "out.json" holds a JSON array of 2 objects
    And the first object has "title" of "Ceramic Mug" and "price" of 12.5
    And the second object has a null "price"

  Scenario: Records are written as JSON Lines, one object per line
    When I write the records to "out.jsonl"
    Then "out.jsonl" has 2 lines, each a standalone JSON object

  Scenario: Records are written as CSV with the config's fields as columns
    When I write the records to "out.csv"
    Then the CSV header row is "title,price"
    And the CSV has 2 data rows
    And the missing price is written as an empty cell

  Scenario: The format is taken from the file extension by default
    When I write the records to "out.csv"
    Then the output was written as "csv"

  Scenario: An explicit format overrides the file extension
    When I write the records to "data.dat" as "jsonl"
    Then "data.dat" has 2 lines, each a standalone JSON object

  Scenario: An unrecognized extension with no explicit format is rejected
    When I try to write the records to "data.dat"
    Then it fails before writing with an error naming the format

  Scenario: A record with a field not in the config schema is rejected before writing
    Given an extra record carrying an undeclared "sku" field
    When I try to write the records to "out.json"
    Then it fails before writing with an error naming "sku"

  Scenario: A secret in an extracted field is redacted before it is written
    # §2h: an output file is a shared surface, so a known secret shape that landed
    # in an extracted value is redacted on the way out, on by default.
    Given a single record whose "title" carries a bearer token
    When I write the records to "out.json"
    And I read the first written object's "title"
    Then it no longer contains the raw token
    And it equals "Bearer [REDACTED]"
