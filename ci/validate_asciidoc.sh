#!/bin/bash
set -uo pipefail

# Install script dependencies
set -e
cd rspec-tools && pipenv install && cd ..
set +e

# This script runs all tests; it doesn't exit at the first failure.
exit_code=0

readonly ALLOWED_RULE_SUB_FOLDERS=['common'];
readonly ROOT=$PWD
# Declare read-only variable PATH_WITH_VARIABLE and make it available to child processes
declare -xr PATH_WITH_VARIABLE="$(realpath ./ci/replace_variables_in_path.sh)"

# Validate user-visible rule descriptions
# i.e., without rspecator-view.
./ci/generate_html.sh
cd rspec-tools
if pipenv run rspec-tools check-description --d ../out; then
  echo "Rule descriptions are fine"
else
  echo "ERROR: There are invalid rule descriptions"
  exit_code=1
fi
cd ..

# Compute the set of affected rules
git fetch origin "$CIRRUS_DEFAULT_BRANCH"
branch_base_sha=$(git merge-base FETCH_HEAD HEAD)
echo "Comparing against the merge-base: $branch_base_sha"
changeset=$(git diff --name-only "$branch_base_sha"..HEAD)
affected_rules=$(printf '%s\n' "$changeset" | grep '/S[0-9]\+/' | sed 's:\(.*/S[0-9]\+\)/.*:\1:' | sort | uniq)
if printf '%s\n' "$changeset" | grep -qv '/S[0-9]\+/'; then
  echo "Some rpec tools or shared_content changed, validating all rules"
  affected_rules=rules/*
fi

# Validate some properties of the asciidoc:
#  * Rules should have at least one language specification,
#    unless they are closed or deprecated.
#  * The include:: should have an empty line before and after them.
#  * Only valid languages can be used as subdirectories in rule directories,
#    with the exception of ALLOWED_RULE_SUB_FOLDERS.
#  * Asciidoc files are free or errors and warnings.
#  * Rule descriptions can include other asciidoc files from the same rule
#    directory or from shared_content.
#  * All asciidoc files are used/included.

echo "Testing the following rules: ${affected_rules}"
supportedLanguages=$(sed 's/ or//' supported_languages.adoc | tr -d '`,')
for dir in $affected_rules
do
  if [ ! -d "$dir" ]; then
    echo "Apparently $dir is deleted, skipping"
    continue
  fi
  dir=${dir%*/}

  # check if there are language specializations
  subdircount=$(find "$dir" -maxdepth 1 -mindepth 1 -type d | wc -l)
  if [[ "$subdircount" -eq 0 ]]
  then
    # no specializations, that's fine if the rule is deprecated
    if grep -Pq '"status": "(deprecated|closed)"' "$dir/metadata.json"; then
      echo "INFO: deprecated generic rule $dir with no language specializations"
    else
      echo "ERROR: non-deprecated generic rule $dir with no language specializations"
      exit_code=1
    fi
  else
    # Make sure include:: clauses are always more than one line away from the previous content
    # Detect includes stuck to the line before
    find "$dir" -name "*.adoc" -execdir sh -c 'grep -Pzl "\S[ \t]*\ninclude::" $1  | xargs -r -I@ realpath "$PWD/@"' shell {} \; > stuck
    # Detect includes stuck to the line after
    find "$dir" -name "*.adoc" -execdir sh -c 'grep -Pzl "include::[^\[]+\[\]\n[ \t]*[^\n]" $1  | xargs -r -I@ realpath "$PWD/@"' shell {} \; >> stuck
    if [ -s stuck ]; then
      echo "ERROR: These adoc files contain an include that is stuck to other content."
      echo "This may result in broken tags and other display issues."
      echo "Make sure there is an empty line before and after each include:"
      cat stuck
      exit_code=1
    fi
    rm -f stuck

    for language in "${dir}"/*/
    do
      language=${language%*/}
      if [[ ! "${supportedLanguages[*]}" == *"${language##*/}"* ]]; then
        if [[ ! "${ALLOWED_RULE_SUB_FOLDERS[*]}" == *"${language##*/}"* ]]; then
          echo "ERROR: ${language##*/} is not a supported language"
          exit_code=1
        fi
      else
        RULE="$language/rule.adoc"
        if test -f "$RULE"; then
          # Errors emitted by asciidoctor don't include the full path.
          # https://github.com/asciidoctor/asciidoctor/issues/3414
          # To ease debugging, we copy the rule.adoc into tmp_SXYZ_language.adoc
          # and run asciidoctor on them instead.
          # We add the implicit header "Description" to prevent an asciidoctor warning.
          TMP_ADOC="$language/tmp_$(basename "${dir}")_${language##*/}.adoc"
          echo "== Description" > "$TMP_ADOC"
          cat "$RULE" >> "$TMP_ADOC"
        else
          echo "ERROR: no asciidoc file $RULE"
          exit_code=1
        fi
      fi
    done

    # Check that all adoc are included

    # Files can be included through variables. We create a list of variables
    # These paths are relative to the file where they are _included_, not where they are _declared_
    # Which is why we need to create this list and cannot do anything with the paths it contains until we find the corresponding include
    find "$dir" -name "*.adoc" ! -name 'tmp_*.adoc' -execdir sed -r -n -e 's/^:(\w+):\s+([A-Za-z0-9\/._-]+)$/\1\t\2/p' {} \; > vars
    # Directly included
    find "$dir" -name "*.adoc" ! -name 'tmp_*.adoc' -execdir sh -c 'grep -h "include::" "$1" | grep -Ev "{\w+}" | grep -v "rule.adoc" | sed -r "s/include::(.*)\[\]/\1/" | xargs -r -I@ realpath "$PWD/@"' shell {} \; > included
    # Included through variable
    VARS_FULL_PATH=$(realpath vars) find "$dir" ! -name 'tmp_*.adoc' -name "*.adoc" -execdir sh -c 'grep -Eh "include::.*\{" "$1" | xargs -r -I@ $PATH_WITH_VARIABLE $VARS_FULL_PATH "@" | xargs -r -I@ realpath "$PWD/@"' shell {} \; >> included
    # We should only include documents from the same rule or from shared_content
    cross_references=$(grep -vEh "${ROOT}\/${dir}\/|${ROOT}\/shared_content\/" included)
    if [[ -n "$cross_references" ]]; then
      printf 'ERROR: Rule %s tries to include content from unallowed directory:\n%s\nTo share content between rules, you should use the "shared_content" folder at the root of the repository\n' "$dir" "$cross_references"
      exit_code=1
    fi
    find "$dir" -name "*.adoc" ! -name 'rule.adoc' ! -name 'tmp*.adoc' -exec sh -c 'realpath $1' shell {} \; > created
    orphans=$(comm -1 -3 <(sort -u included) <(sort -u created))
    if [[ -n "$orphans" ]]; then
      printf 'ERROR: These adoc files are not included anywhere:\n-----\n%s\n-----\n' "$orphans"
      exit_code=1
    fi
    rm -f included created vars
  fi
done

# Run asciidoctor and fail if a warning is emitted.
# Use the tmp_SXYZ_language.adoc files (see note above).
ADOC_COUNT=$(find rules -name "tmp*.adoc" | wc -l)
if (( ADOC_COUNT > 0 )); then
  if asciidoctor --failure-level=WARNING -o /dev/null rules/*/*/tmp*.adoc; then
    if asciidoctor -a rspecator-view --failure-level=WARNING -o /dev/null rules/*/*/tmp*.adoc; then
      echo "${ADOC_COUNT} documents checked with success"
    else
      echo "ERROR: malformed asciidoc files in rspecator-view"
      exit_code=1
    fi
  else
    echo "ERROR: malformed asciidoc files"
    exit_code=1
  fi
else
  echo "No new asciidoc file changed"
fi
find rules -name "tmp*.adoc" -delete

if (( exit_code == 0 )); then
  echo "Success"
else
  echo "There were errors"
fi
exit $exit_code
