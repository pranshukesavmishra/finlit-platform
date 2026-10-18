from backend import email_service


def test_all_email_templates_escape_submitted_markup_and_preserve_readable_text():
    markup = '<a href="https://evil.test">click</a><img src=x onerror="alert(1)"><script>alert(1)</script>'
    message = f"First line & 'quoted'\nSecond line — ₹50,000\n{markup}"
    contact = {
        "name": "O'Reilly & Co <Team>",
        "email": "person+tag@example.com",
        "phone": "+91 <script>alert(1)</script>",
        "subject": "Subject & <b>bold</b>",
        "message": message,
        "created_at": "2026-10-07T10:20:30+00:00",
    }
    enquiry = {
        "name": contact["name"], "email": contact["email"], "phone": contact["phone"],
        "services": ["Global <Investing>", "Stocks & ETFs"],
        "message": message, "created_at": contact["created_at"],
    }

    templates = [email_service._alert_html(contact), email_service._reply_html(contact), email_service._enquiry_html(enquiry)]

    for rendered in templates:
        assert markup not in rendered
        assert "&lt;a href=&quot;https://evil.test&quot;&gt;click&lt;/a&gt;" in rendered
        assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in rendered
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
        assert "&amp;" in rendered and "&#x27;" in rendered
        assert "₹50,000" in rendered
        assert "First line" in rendered and "Second line" in rendered and "<br/>" in rendered

    for rendered in (templates[0], templates[2]):
        assert "O&#x27;Reilly &amp; Co &lt;Team&gt;" in rendered
        assert "+91 &lt;script&gt;alert(1)&lt;/script&gt;" in rendered
        assert "person+tag@example.com" in rendered
    assert "Subject &amp; &lt;b&gt;bold&lt;/b&gt;" in templates[0]
    assert "O&#x27;Reilly &amp; Co &lt;Team&gt;" in templates[1]
    assert "Global &lt;Investing&gt;" in templates[2]
    assert "Stocks &amp; ETFs" in templates[2]


def test_email_rendering_does_not_mutate_submitted_values():
    message = "Keep <b>this</b> exactly in storage\nwith a second line"
    lead = {"name": "Asha", "email": "asha@example.com", "message": message}

    email_service._reply_html(lead)

    assert lead["message"] == message
