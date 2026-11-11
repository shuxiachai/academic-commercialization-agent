"""Request-level regressions for the paid composer, with no network or keys."""

from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("outcome", ["accepted", "unknown", "mismatch", "late_identity"])
def test_durable_receipt_lookup_never_reposts_or_crosses_identity(outcome):
    node = shutil.which("node")
    assert node, "Node is required for the paid receipt delivery seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "durable_receipt_lookup", outcome], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS durable_receipt_lookup" in result.stdout


@pytest.mark.parametrize("mode", ["ordered", "code", "byok", "gate"])
def test_history_responses_belong_to_latest_view_and_identity(mode):
    """Old success responses previously re-exposed A's capabilities after B login."""
    node = shutil.which("node")
    assert node, "Node is required for the history delivery seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "sidebar_generation", mode], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS sidebar_generation" in result.stdout


@pytest.mark.parametrize("scenario", [
    "pending_submit", "rejected_submit", "existing_topic_pdf", "empty_topic_pdf",
    "missing_suggestion_pdf", "serialized_pdf", "stale_pdf_response", "failed_pdf",
    "upload_during_submit", "classified_errors",
    "accepted_history_failure", "resume_rerender", "lost_acknowledgement", "malformed_history",
    "gate_pending", "gate_finished", "cross_tab_exit", "receipt_handoff", "receipt_storage_failure",
    "receipt_navigation_failure",
])
def test_composer_delivers_one_intended_operation(scenario):
    """Input events and delayed extraction cannot duplicate or change paid intent."""
    node = shutil.which("node")
    assert node is not None, "Node is required for the shipped client contract."
    script = Path(__file__).with_name("js") / "composer_contract.mjs"
    result = subprocess.run(
        [node, str(script), scenario], capture_output=True, text=True,
        encoding="utf-8", timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


@pytest.mark.parametrize("operation", ["run", "pdf", "resume"])
def test_identity_switch_waits_for_paid_ack_and_clears_attachment(operation):
    """The previous A PDF reply attached to B's next paid request after logout."""
    node = shutil.which("node")
    assert node, "Node is required for the identity seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "pending_exit", operation], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS pending_exit" in result.stdout


@pytest.mark.parametrize("operation", ["run", "pdf", "resume"])
@pytest.mark.parametrize("outcome", ["refresh", "transport", "malformed", "handoff", "408", "500", "401", "422", "429"])
def test_refresh_preserves_unconfirmed_paid_intent(operation, outcome):
    """A fresh document previously sent another POST after losing the first reply."""
    node = shutil.which("node")
    assert node, "Node is required for the reload seam"
    scenario = "receipt_refresh" if outcome == "refresh" else "receipt_outcome"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        scenario, operation, outcome], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


@pytest.mark.parametrize("outcome", ["accepted", "rejected", "model", "unreachable", "unverified", "left", "off"])
def test_an_account_saving_keys_is_told_what_the_providers_said(outcome):
    """A wrong key was only discovered when the run it started failed."""
    node = shutil.which("node")
    assert node, "Node is required for the key-check seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "account_keys", outcome], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS account_keys" in result.stdout


@pytest.mark.parametrize("kind", ["account", "silent", "code", "off", "signin"])
def test_an_account_previews_the_search_on_its_own_key(kind):
    """An account had to pay for a whole run to learn how its topic was read."""
    node = shutil.which("node")
    assert node, "Node is required for the account-preview seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "account_preview", kind], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS account_preview" in result.stdout


@pytest.mark.parametrize("kind", ["changed", "refused", "unavailable"])
def test_the_waiting_preview_does_not_outlive_its_question(kind):
    """The panel says the topic is being read; it must not stay saying so.

    A topic changed meanwhile and a refused request both end with no panel;
    a planner that could not be reached ends with its reason and a way on.
    """
    node = shutil.which("node")
    assert node, "Node is required for the preview-waiting seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "preview_waiting", kind], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS preview_waiting" in result.stdout


@pytest.mark.parametrize("kind", ["pending", "done", "failed"])
def test_a_pressed_cancel_stays_pressed_until_the_run_stops(kind):
    """Each poll repainted Cancel as if it had never been pressed."""
    node = shutil.which("node")
    assert node, "Node is required for the cancel-feedback seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "cancel_feedback", kind], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS cancel_feedback" in result.stdout


@pytest.mark.parametrize("scenario", ["asks_now", "not_twice_at_once", "not_after_stop"])
def test_the_run_follower_can_be_asked_to_poll_now(scenario):
    """After a cancel the header waited up to four seconds for the next poll."""
    node = shutil.which("node")
    assert node, "Node is required for the run-follower seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "run_follow_contract.mjs"),
        scenario], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


def test_cancelling_is_said_in_both_languages():
    strings = (Path(__file__).parents[1] / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
    assert 'cancelling: "Cancelling…"' in strings
    assert 'cancelling: "正在取消…"' in strings


@pytest.mark.parametrize("contact", ["address", "sentence", "none"])
def test_the_sign_up_form_says_who_gives_out_invite_codes(contact):
    """The invite code field was a dead end for anyone who arrived by a link."""
    node = shutil.which("node")
    assert node, "Node is required for the invite-hint seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "invite_hint", contact], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS invite_hint" in result.stdout


def test_compare_asks_which_run_and_only_navigates():
    """The second run is chosen from the rail's own list; the choice sends nothing."""
    node = shutil.which("node")
    assert node, "Node is required for the compare-picker seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "compare_pick"], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS compare_pick" in result.stdout


@pytest.mark.parametrize("kind", ["finished", "blocked", "running", "fallback", "refused"])
def test_a_run_offers_its_topic_again_and_its_link(kind):
    """An earlier topic had to be retyped, and a run's address copied by hand.

    `fallback` and `refused` are a browser that will not let the page write
    to the clipboard itself: the one inside a chat app, where a link to a
    run is most often opened. The older way of copying is tried, and the
    reader is told what the browser said.
    """
    node = shutil.which("node")
    assert node, "Node is required for the run-reuse seam"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "composer_contract.mjs"),
        "run_reuse", kind], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS run_reuse" in result.stdout
