{#- Naive UTC timestamp -> naive Europe/Dublin local timestamp (handles DST). -#}
{% macro to_local(column) -%}
    (({{ column }} at time zone 'UTC') at time zone '{{ var("local_timezone") }}')
{%- endmacro %}
