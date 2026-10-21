# Data

Raw logs are written by the car to its microSD card, one CSV file per run.
They are **not** stored in git: large binary-like files make the repository
slow and cannot be diffed. During the project they are backed up to cloud
storage on the day of each session (risk R12 of the plan).

At the end of the project (task 8.1) the cleaned dataset, a data dictionary
and the session metadata are published in a public archive with a DOI, and
linked from here.

`raw/` and `processed/` are ignored by git. This README and the licence are not.
