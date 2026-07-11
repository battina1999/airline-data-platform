{#
  SCD Type-2 history for the airline dimension.

  What SCD-2 means: instead of overwriting a dimension row when an attribute
  changes (losing history), every change INSERTS a new row versioned with
  dbt_valid_from / dbt_valid_to. Facts joined "as of" a date see the attribute
  values that were true at that time — e.g. if a carrier rebrands or changes
  its fleet size, historical reports keep the old values.

  strategy='check' watches the listed columns; any change closes the current
  version (sets dbt_valid_to) and opens a new one. Runs as part of `dbt build`
  or explicitly via `dbt snapshot`.
#}
{% snapshot dim_airline_snapshot %}

{{
    config(
      target_schema='snapshots',
      unique_key='carrier_code',
      strategy='check',
      check_cols=['carrier_name', 'is_low_cost', 'fleet_size'],
    )
}}

select
    carrier_code,
    carrier_name,
    is_low_cost,
    fleet_size,
    founded_year
from {{ ref('stg_carriers') }}

{% endsnapshot %}
