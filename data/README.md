# Task data

Training data is distributed separately. Set `--train-dir /absolute/path/to/tasks`.
Each category is a JSON object mapping record IDs to objects with a nonempty
`changed_question`, `Changed Question`, or `Question` string. Each category needs
at least three records: two validation records and the remainder for training.
The split uses seed 0. Use only data you have permission to evaluate.
