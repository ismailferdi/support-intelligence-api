from app.prompt import build_system_prompt, build_user_prompt


def test_user_prompt_embeds_subject_and_body(sample_ticket):
    prompt = build_user_prompt(sample_ticket)
    assert "TICKET SUBJECT" in prompt
    assert "TICKET BODY" in prompt
    assert sample_ticket.subject in prompt
    assert sample_ticket.body in prompt


def test_system_prompt_mentions_every_output_field():
    prompt = build_system_prompt().lower()
    for field in (
        "category",
        "priority",
        "sentiment",
        "summary",
        "suggested_response",
        "confidence",
        "review_required",
    ):
        assert field in prompt
