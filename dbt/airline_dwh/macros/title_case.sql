{#
  Portable TITLE CASE. dbt's adapter.dispatch picks the right implementation
  for the active warehouse, so the SAME staging model runs on DuckDB locally
  and Snowflake in the cloud without edits.
    - Snowflake / Postgres : native initcap()
    - DuckDB               : lambda over the split words
#}
{% macro title_case(col) -%}
    {{ return(adapter.dispatch('title_case', 'airline_dwh')(col)) }}
{%- endmacro %}

{% macro default__title_case(col) -%}
    initcap({{ col }})
{%- endmacro %}

{% macro duckdb__title_case(col) -%}
    array_to_string(
        list_transform(
            string_split(lower(trim({{ col }})), ' '),
            x -> upper(x[1:1]) || x[2:]
        ),
        ' '
    )
{%- endmacro %}
