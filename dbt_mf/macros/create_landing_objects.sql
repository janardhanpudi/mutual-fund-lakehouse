{% macro create_landing_objects() %}
  {#- Bronze schema and Volumes that must exist before ingestion runs -#}
  {% set catalog = target.database %}
  {% set statements = [
      "create schema if not exists " ~ catalog ~ ".bronze",
      "create volume if not exists " ~ catalog ~ ".bronze.raw_landing",
      "create volume if not exists " ~ catalog ~ ".bronze.autoloader_state"
  ] %}
  {% for stmt in statements %}
    {% do run_query(stmt) %}
    {{ log("OK: " ~ stmt, info=True) }}
  {% endfor %}
{% endmacro %}
