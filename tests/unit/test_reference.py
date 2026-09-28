import pytest

from collective_intelligence_overlay.reference import capability, check, csv_sum


def test_checker_does_not_certify_unrecognized_artifact():
    cap = capability("producer", "csv-sum")
    altered = cap.model_copy(
        update={"subject": cap.subject.model_copy(update={"digest": "a" * 64})}
    )
    source = "category,amount\na,1\n"
    result = check("verifier", altered, source, csv_sum(source), "receiver")
    assert result.verdict == "UNKNOWN"
    assert result.obligations


def test_reference_composition_cannot_omit_dependencies():
    with pytest.raises(ValueError, match="exact installed"):
        capability("producer", "csv-report")
