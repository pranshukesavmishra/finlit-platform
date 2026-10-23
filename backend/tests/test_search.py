

def test_a_score_row_written_on_saturday_is_labelled_with_fridays_close():
    from datetime import datetime, timezone, timedelta
    from finlit.search import session_of
    ist = timezone(timedelta(hours=5, minutes=30))
    assert session_of(datetime(2026, 10, 24, 2, 13, tzinfo=ist)).isoformat() == "2026-10-23"     # Saturday 02:13
    assert session_of(datetime(2026, 10, 23, 10, 0, tzinfo=ist)).isoformat() == "2026-10-22"     # Friday before the close
    assert session_of(datetime(2026, 10, 23, 16, 0, tzinfo=ist)).isoformat() == "2026-10-23"     # Friday after the close
    assert session_of(datetime(2026, 10, 26, 9, 0, tzinfo=ist)).isoformat() == "2026-10-23"      # Monday morning
