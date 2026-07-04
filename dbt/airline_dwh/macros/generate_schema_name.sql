{#
  Use the custom schema name literally (staging, marts, raw) instead of the
  default dbt behaviour of prefixing it with the target schema. Keeps the
  warehouse layout clean and identical on DuckDB and Snowflake.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
