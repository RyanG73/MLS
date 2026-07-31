from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "webapp" / "index.html").read_text()
CLUB_WATCH = (ROOT / "webapp" / "intelligence.js").read_text()
STATIC_BUILDER = (ROOT / "scripts" / "build_static_pages.py").read_text()


def test_every_primary_surface_uses_club_watch_customer_name():
    assert ">Club Watch</a>" in INDEX
    assert "Track my club" in INDEX
    assert "Club Watch · Entenser" in CLUB_WATCH
    assert "Track {E(team)} with Club Watch" in STATIC_BUILDER


def test_paid_copy_keeps_the_free_boundary_and_checkout_honest():
    assert "The current answer stays free" in INDEX
    assert "one complete Club Watch sample" in INDEX
    assert "Checkout unavailable" in INDEX
    assert "Checkout unavailable" in CLUB_WATCH
    assert "See price at checkout" not in INDEX
    assert "The exact price and currency are shown" not in CLUB_WATCH
    assert "Creator exports" not in CLUB_WATCH


def test_unapproved_delivery_claims_are_explicitly_gated():
    assert (
        "Live alerts and briefings remain unavailable until the reliability "
        "gate and owner approval are complete."
    ) in CLUB_WATCH
    assert (
        "Live alerts and briefings are not offered until the shadow-run "
        "reliability gate and owner approval are complete."
    ) in INDEX
    assert "in your inbox" not in INDEX
    assert "email alerts" not in INDEX


def test_club_pages_carry_canonical_growth_events_and_state_labels():
    assert "club_page_view" in STATIC_BUILDER
    assert "track_club" in STATIC_BUILDER
    assert '"full forecast"' in STATIC_BUILDER
    assert '"results only"' in STATIC_BUILDER
    assert '"archive"' in STATIC_BUILDER


def test_outcome_triggered_conversion_moments_follow_demonstrated_value():
    assert 'moment=movement' in INDEX
    assert 'data-upsell="movement-explanation"' in INDEX
    assert 'moment=match' in INDEX
    assert 'data-upsell="match-stakes"' in INDEX
    assert "This scenario stays free. Save multi-match paths" in INDEX
    assert 'moment=club_limit' in INDEX
    assert "additional browser club" in INDEX
    assert 'moment === "movement"' in CLUB_WATCH
    assert 'moment === "match"' in CLUB_WATCH
    assert 'moment === "scenario"' in CLUB_WATCH
    assert 'moment === "club_limit"' in CLUB_WATCH
    assert "This match-stakes preview stays free." in CLUB_WATCH
    assert "The scenario you just ran stays free" in CLUB_WATCH


def test_account_feedback_copy_preserves_consent_and_privacy_boundary():
    assert 'id="acct-feedback"' in INDEX
    assert "exportable, deletable account record" in INDEX
    assert "Aggregate measurement receives only the category and consent state" in INDEX
    assert "anonymous testimonial" in INDEX
    assert "Separate permission is required before attaching my name" in INDEX
    assert "publication_consent" in INDEX
