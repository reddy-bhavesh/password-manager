from app.services.audit import calculate_security_health_score


def test_calculate_security_health_score_weighted_deductions() -> None:
    score = calculate_security_health_score(
        failed_logins_30d=2,
        mfa_adoption_pct=50,
        suspended_accounts=1,
        over_shared_items=1,
    )
    assert score == 61


def test_calculate_security_health_score_clamps_inputs_and_floor() -> None:
    score = calculate_security_health_score(
        failed_logins_30d=999,
        mfa_adoption_pct=-20,
        suspended_accounts=999,
        over_shared_items=999,
    )
    assert score == 0

    perfect = calculate_security_health_score(
        failed_logins_30d=0,
        mfa_adoption_pct=100,
        suspended_accounts=0,
        over_shared_items=0,
    )
    assert perfect == 100
