{#- Fails for every row where `expression` is false (nulls count as failures
    unless the expression handles them). -#}
{% test expression_is_true(model, expression) %}
select *
from {{ model }}
where not ({{ expression }})
{% endtest %}
