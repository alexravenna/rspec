import re
from pathlib import Path

import pytest
from rspec_tools.errors import RuleValidationError
from rspec_tools.rules import RulesRepository
from rspec_tools.validation.description import validate_how_to_fix_it_subsections, validate_section_names, \
  validate_section_levels, validate_parameters, validate_source_language, validate_resources_subsections


@pytest.fixture
def rule_language(mockrules: Path):
  def _rule_language(rule_id, language):
    rule = RulesRepository(rules_path=mockrules).get_rule(rule_id)
    return rule.get_language(language)
  return _rule_language

@pytest.fixture
def invalid_rule(mockinvalidrules: Path):
  def _invalid_rule(rule_id, language):
    rule = RulesRepository(rules_path=mockinvalidrules).get_rule(rule_id)
    return rule.get_language(language)
  return _invalid_rule

def test_valid_sections_passes_validation(rule_language):
  '''Check that description with standard sections is considered valid.'''
  validate_section_names(rule_language('S100', 'cfamily'))

def test_unexpected_section_fails_validation(invalid_rule):
  rule = invalid_rule('S100', 'cfamily')
  with pytest.raises(RuleValidationError, match=fr'^Rule {rule.id} has unconventional header "Invalid header"'):
    validate_section_names(rule)

def test_valid_section_levels_passes_validation(rule_language):
  '''Check that description with correct formatting is considered valid.'''
  validate_section_levels(rule_language('S100', 'cfamily'))

def test_level_0_section_fails_validation(invalid_rule):
  rule = invalid_rule('S100', 'cfamily')
  with pytest.raises(RuleValidationError, match=fr'^Rule {rule.id} has level-0 header "Invalid header level"'):
    validate_section_levels(rule)

def test_parameters_passes_validation(rule_language):
  '''Check that correctly formed parameters are considered valid.'''
  validate_parameters(rule_language('S100', 'cfamily'))

def test_parameters_fails_validation_missing_block(invalid_rule):
  '''Check that description with unexpected tag breaks validation.'''
  rule = invalid_rule('S100', 'cfamily')
  with pytest.raises(RuleValidationError, match=fr'^Rule {rule.id} should use `\*\*\*\*` blocks for each parameter'):
    validate_parameters(rule)

def test_parameters_fails_validation_missing_title(invalid_rule):
  rule = invalid_rule('S100', 'csharp')
  '''Check that parameters without key as title breaks validation.'''
  with pytest.raises(RuleValidationError, match=fr'^Rule {rule.id} should have a parameter name declared with `.name` before the bock, for each parameter'):
    validate_parameters(rule)

def test_parameters_fails_validation_missing_description(invalid_rule):
  rule = invalid_rule('S100', 'java')
  '''Check that parameters without any description break validation.'''
  with pytest.raises(RuleValidationError, match=fr'^Rule {rule.id} should have a description for each parameter'):
    validate_parameters(rule)

def test_valid_source_declaration_validation(rule_language):
  '''Check that declaring a language for sources is considered valid.'''
  # cpp and text
  validate_source_language(rule_language('S100', 'cfamily'))
  # javascript and no source
  validate_source_language(rule_language('S100', 'csharp'))

def test_missing_source_language_fails_validation(invalid_rule):
  '''Check that forgetting the language for sources breaks validation'''
  rule = invalid_rule('S100', 'cfamily')
  with pytest.raises(RuleValidationError, match=re.escape(f'Rule {rule.id} has non highlighted code example in section "Noncompliant Code Example".\nUse [source,cpp] or [source,text] before the opening \'----\'.')):
    validate_source_language(rule)

def test_missing_source_language_on_second_block_fails_validation(invalid_rule):
  '''Check that forgetting the language for sources breaks validation in case of multiple blocks too'''
  rule = invalid_rule('S100', 'java')
  with pytest.raises(RuleValidationError, match=re.escape(f'Rule {rule.id} has non highlighted code example in section "Noncompliant Code Example".\nUse [source,java] or [source,text] before the opening \'----\'.')):
    validate_source_language(rule)

def test_wrong_source_language_fails_validation(invalid_rule):
  '''Check that forgetting the language for sources breaks validation'''
  rule = invalid_rule('S100', 'csharp')
  with pytest.raises(RuleValidationError, match=re.escape(f'Rule {rule.id} has unknown language "unknown" in code example in section "Noncompliant Code Example".\nAre you looking for "csharp"?')):
    validate_source_language(rule)

def test_unsupported_framework_name_in_how_to_fix_it_subsection_validation(invalid_rule):
  '''Check that having "How to fix it" subsections using framework names that are not inside the "allowed_framework_names.adoc" file breaks validation'''
  rule = invalid_rule('S101', 'csharp')
  with pytest.raises(RuleValidationError, match=f'Rule csharp:S101 has a "How to fix it" section for an unsupported framework: "Foo Bar Framework"'):
    validate_how_to_fix_it_subsections(rule)

def test_too_many_subsections_in_how_to_fix_it_validation(invalid_rule):
  '''Check that having more than the current hard limit (6) "How to fix it" subsections breaks validation'''
  rule = invalid_rule('S101', 'javascript')
  with pytest.raises(RuleValidationError, match=f'Rule javascript:S101 has more than 6 "How to fix it" subsections. Please ensure this limit can be increased with PM/UX teams'):
    validate_how_to_fix_it_subsections(rule)

def test_unallowed_subsections_in_how_to_fix_it_validation(invalid_rule):
  '''Check that having "How to fix it" subsections with unallowed names breaks validation'''
  rule = invalid_rule('S200', 'java')
  with pytest.raises(RuleValidationError, match=f'Rule java:S200 has a "How to fix it" subsection with an unallowed name for the Razor framework'):
    validate_how_to_fix_it_subsections(rule)

def test_duplicate_subsections_in_how_to_fix_it_validation(invalid_rule):
  '''Check that having duplicate "How to fix it" subsections breaks validation'''
  rule = invalid_rule('S200', 'csharp')
  with pytest.raises(RuleValidationError, match=f'Rule csharp:S200 has duplicate "How to fix it" subsections for the Razor framework. There are 2 occurences of "Pitfalls"'):
    validate_how_to_fix_it_subsections(rule)

def test_unallowed_subsections_in_resources_validation(invalid_rule):
  '''Check that having "Resources" subsections with unallowed names breaks validation'''
  rule = invalid_rule('S200', 'cpp')
  with pytest.raises(RuleValidationError, match=f'Rule cpp:S200 has a "Resources" subsection with an unallowed name: "Yolo"'):
    validate_resources_subsections(rule)

def test_duplicate_subsections_in_resources_validation(invalid_rule):
  '''Check that having duplicate "Resources" subsections breaks validation'''
  rule = invalid_rule('S200', 'scala')
  with pytest.raises(RuleValidationError, match=f'Rule scala:S200 has duplicate "Resources" subsections. There are 2 occurences of "Documentation"'):
    validate_resources_subsections(rule)

def test_education_format_missing_mandatory_sections_validation(invalid_rule):
  '''Check that not having all the required sections in the education format breaks validation'''
  rule = invalid_rule('S200', 'common')
  with pytest.raises(RuleValidationError, match=f'Rule common:S200 is missing the "How to fix it\\?" section'):
    validate_section_names(rule)

def test_valid_how_to_fix_it_subsections_validation(rule_language):
  '''Check that expected format is considered valid'''
  rule = rule_language('S101', 'csharp')
  validate_how_to_fix_it_subsections(rule)

def test_valid_optional_resources(rule_language):
  '''Check that the "Resources" section is optional'''
  rule = rule_language('S200', 'csharp')
  validate_resources_subsections(rule)
  validate_section_names(rule)

def test_subsections_without_a_framework_in_how_to_fix_it_validation(rule_language):
  '''Check that having subsections without a framework in "How to fix it" is considered valid'''
  rule = rule_language('S200', 'cobol')
  validate_how_to_fix_it_subsections(rule)
