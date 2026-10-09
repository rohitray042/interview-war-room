from app.interview_evaluation import evaluation_schema


def test_schema_binds_exact_snapshot_labels_and_counts():
    snapshot = {
        "rubric": {"weights": {"correctness": 60, "clarity": 40}},
        "content": {"expected_topics": ["Warehouse sizing", "Auto-suspend"]},
    }
    schema = evaluation_schema(snapshot)
    assert schema["$defs"]["RubricRating"]["properties"]["dimension"]["enum"] == [
        "correctness",
        "clarity",
    ]
    assert schema["$defs"]["TopicRating"]["properties"]["topic"]["enum"] == [
        "Warehouse sizing",
        "Auto-suspend",
    ]
    for name in ("dimensions", "topics"):
        assert schema["properties"][name]["minItems"] == 2
        assert schema["properties"][name]["maxItems"] == 2
    assert schema["properties"]["follow_up_topic"]["anyOf"][0]["enum"] == [
        "Warehouse sizing",
        "Auto-suspend",
    ]


def test_schema_is_not_shared_across_questions():
    def snapshot(dimension):
        return {
            "rubric": {"weights": {dimension: 100}},
            "content": {"expected_topics": [dimension]},
        }

    first = evaluation_schema(snapshot("accuracy"))
    second = evaluation_schema(snapshot("reasoning"))
    assert first["$defs"]["RubricRating"]["properties"]["dimension"]["enum"] == ["accuracy"]
    assert second["$defs"]["RubricRating"]["properties"]["dimension"]["enum"] == ["reasoning"]
