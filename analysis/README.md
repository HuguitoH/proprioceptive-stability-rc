# Analysis

Pipeline that turns the logged runs into the metrics of the study: RMSE and
peak of the yaw-rate error, the FMVSS 126 yaw-rate ratio, the maximum speed
in the double lane change, and the Mann–Whitney U test with Cliff's delta.

It reads only from `data/` and never edits the raw logs, so every figure in
the dissertation can be regenerated from the published dataset.

Built in work package 7 of the plan.
