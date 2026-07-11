# KPI Definitions — single source of truth

Every dashboard (Streamlit, Power BI) and every ad-hoc query must match these
definitions. If a number on a chart disagrees with this file, the chart is wrong.

| KPI | Definition | Formula | Source mart | Caveats |
|---|---|---|---|---|
| **On-Time %** | Share of *completed* flights arriving < 15 min late (US DOT A14 convention) | `on_time_flights / completed_flights` where on-time = `NOT cancelled AND NOT diverted AND arr_delay_min < 15` | `operational_kpis`, `route_performance` | Cancelled/diverted flights are excluded from the denominator — an airline that cancels aggressively can look "more on-time"; always read next to Completion Factor. |
| **Completion Factor %** | Share of scheduled flights actually flown | `(total_flights - cancelled_flights) / total_flights` | `operational_kpis` | Diverted flights count as completed (they flew). |
| **Cancellation Rate %** | Share of scheduled flights cancelled | `cancelled_flights / total_flights` | `operational_kpis`, `cancellations`, `route_performance` | Reason codes: A=Carrier, B=Weather, C=NAS, D=Security. Weather cancellations cluster seasonally — compare year-over-year, not month-over-month. |
| **Average Arrival Delay** | Mean arrival delay of completed flights, in minutes | `avg(arr_delay_min) WHERE NOT cancelled` | `operational_kpis`, `delay_trends` | Includes early arrivals as negative values, which pulls the mean down; the delay distribution is right-skewed, so medians/percentiles tell a fairer story than the mean. NULL delays (cancelled) are excluded by definition. |
| **Average Departure Delay** | Mean departure delay of completed flights | `avg(dep_delay_min) WHERE NOT cancelled` | `operational_kpis` | Same skew caveat as arrival delay. |
| **Delay Rate %** | Share of flights arriving ≥ 15 min late | `delayed_flights / total_flights` where delayed = `arr_delay_min >= 15` | `delay_trends` | Denominator is *all* flights (incl. cancelled) to keep the daily trend stable when cancellations spike. |
| **Delay by Cause (minutes)** | Total delay minutes attributed per BTS cause | `sum(<cause>_delay_min)` per Carrier / Weather / NAS / Security / Late Aircraft | `fact_flight_delays`, `delay_trends` | BTS only attributes causes when `arr_delay_min >= 15`; cause minutes for shorter delays are structurally zero. Late Aircraft is knock-on delay — it double-counts an upstream root cause by design. |
| **Route Reliability (On-Time % by route)** | On-Time % computed per origin→dest pair | as On-Time %, grouped by route | `route_performance` | Routes with < 20 flights in the window are suppressed (small-sample noise). Directional: ATL→DFW ≠ DFW→ATL. |
| **Avg Route Delay** | Mean arrival delay per route | `avg(arr_delay_min) WHERE NOT cancelled` per route | `route_performance` | Same ≥ 20-flight suppression. |

## Conventions

- **The 15-minute threshold** is the US DOT standard (`ArrDel15`); changing it
  re-defines On-Time % and Delay Rate together — never change one without the other.
- **Percentages** are displayed to one decimal place; stored unrounded.
- **Time zones:** BTS times are airport-local wall-clock. Daily rollups group by
  local `flight_date` (industry convention), not UTC.
- **Grain guards:** all KPIs derive from `fact_flights` at one-row-per-flight;
  the dbt uniqueness test on `flight_id` protects every ratio above from
  double-counting.
