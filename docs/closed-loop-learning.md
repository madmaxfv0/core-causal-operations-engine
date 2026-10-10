# Closed-loop intervention learning

Intervention outcomes are stored separately from recommendations. An approved
job can be recorded through `POST /api/intervention-outcomes` with the predicted
uplift, actual uplift, evaluation window, and intervention date. The API derives
prediction accuracy as:

```text
1 - abs(actual uplift - predicted uplift) / abs(predicted uplift)
```

This is an accuracy diagnostic, not a claim that one outcome proves causality.
Future model training should use approved outcomes with the same provenance and
the existing causal evidence checks. Until an operator outcome is recorded, the
map and well detail do not display invented success rates.

