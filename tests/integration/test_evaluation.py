from collective_intelligence_overlay.evaluation import compare
from collective_intelligence_overlay.models import UseRequest


async def test_matched_microbenchmark(overlay, records):
    cap = records[0]
    result = await compare(
        overlay,
        UseRequest(
            receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
        ),
    )
    assert len(result["comparison"]) == 4
    assert all(row["correct"] == row["tasks"] == 3 for row in result["comparison"])
    assert all(row["currency_cost"] is None for row in result["comparison"])
