"""Regression seams for candidate identity, signed units and orphaned receipts."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import pytest

from academic_agent import pdf_extractor as extractor
from academic_agent.claim_grounding import check_report
from api import access, main, papers, receipts, runs
from tests.test_pdf_input_identity_boundaries import _pdf, fields
from tests.test_server_receipts import contribution, headers, paid_api  # noqa: F401


@pytest.mark.parametrize('filename', ['pdf_extractor.py', 'claim_grounding.py'])
def test_local_recovery_identity_binds_pdf_and_grounding_rules(monkeypatch, filename):
    """Local resumes must notice identity/audit changes without a deployed SHA."""
    from academic_agent import checkpoint_runtime
    for name in checkpoint_runtime._REVISION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    before = checkpoint_runtime.pipeline_revision()
    read = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda path: read(path) + (b'changed' if path.name == filename else b''))
    assert checkpoint_runtime.pipeline_revision() != before


@pytest.mark.parametrize("text", [
    "References: 10.1234/cited-paper", "Related work arXiv:2501.01234",
    "doi:10.1234/header-candidate\nReferences: 10.1234/cited-paper",
])
def test_pdf_candidate_cannot_become_registry_identity_via_http_and_storage(paid_api, monkeypatch, text):
    """A label alone did not stop the bibliography DOI reaching A1.doi/url."""
    client, _, _ = paid_api
    monkeypatch.setattr(extractor, "_call_llm_json", MagicMock(return_value=fields(
        candidate_doi="10.1234/model-invention", candidate_url="https://example.com/model",
    )))
    auth = headers()
    response = client.post('/api/papers', headers=auth,
                           files={'file': ('paper.pdf', _pdf([text]).read_bytes())})
    assert response.status_code == 200, response.text
    body = response.json()
    saved = papers.load_extraction(body['paper_id'])
    assert {k: body[k] for k in extractor.PaperContribution.model_fields} == saved
    assert body['candidate_doi'] == extractor._find_doi(text)
    assert body['candidate_url']
    assert body['url'] is None and body['doi'].startswith('10.0000/uploaded-')
    checker = MagicMock(return_value=(True, ''))
    source = extractor.paper_to_evidence_source(extractor.PaperContribution.model_validate(saved), checker)
    assert source.url is None and source.doi == body['doi']
    assert source.title == body['title'] and source.evidence_summary
    checker.assert_not_called()
    assert client.get('/api/receipts', headers=auth).json()['response'] == body


@pytest.mark.parametrize('claim,source,status', [
    ('Gain +10%', 'Gain -10%', 'ungrounded'),
    ('Gain -10%', 'Gain 10%', 'ungrounded'),
    ('Gain −10%', 'Gain +10%', 'ungrounded'),
    ('Gain −10%', 'Gain -10.00 percent', 'grounded'),
    ('Gain +10%', 'Gain 10 percent', 'grounded'),
    ('Power 100 mW', 'Power 100 MW', 'ungrounded'),
    ('Power 100 MW', 'Power 100 mW', 'ungrounded'),
    ('Energy 100 mWh', 'Energy 100 MWh', 'ungrounded'),
    ('Pressure 100 mPa', 'Pressure 100 MPa', 'ungrounded'),
    ('Frequency 100 mHz', 'Frequency 100 MHz', 'ungrounded'),
    ('Power 100 mW', 'Power 100 mW', 'grounded'),
    ('Figure 26.1 furlongs', 'Figure 26.1%', 'unverifiable'),
    ('Figure 26.1%', 'Figure 26.1 furlongs', 'unverifiable'),
    ('Figure 26.1 qubits', 'Figure 26.1 qubits', 'unverifiable'),
    ('Figure 26.1 kg/mystery', 'Figure 26.1 kg', 'unverifiable'),
    ('Figure 26.1', 'Figure 26.1 unknownunit', 'unverifiable'),
    ('Resistance 26.1 Ω', 'Figure 26.1%', 'unverifiable'),
    ('Resistance 26.1 欧姆', 'Figure 26.1%', 'unverifiable'),
    ('Resistance 26.1 kΩ', 'Temperature 26.1 K', 'unverifiable'),
    ('Concentration 26.1 mM', 'Length 26.1 mm', 'unverifiable'),
    ('Power 100 Mw', 'Power 100 MW', 'unverifiable'),
    ('Efficiency 19.7% on 1 cm²', 'Efficiency 19.7% on 1 cm', 'unverifiable'),
])
def test_signed_or_unknown_unit_reaches_audit_verdict(claim, source, status):
    """A known opposite sign/scale fails; unsupported unit grammar abstains."""
    report = SimpleNamespace(findings=[SimpleNamespace(finding_id='F1', claim=claim, source_ids=['A1'])],
        sources=[SimpleNamespace(source_id='A1', title='', publisher='', summary_source='abstract',
                                 evidence_summary=source + '. ' + 'Supporting prose. ' * 40)])
    result = check_report(report)
    assert result.error is None
    assert len(result.checks) == 1
    assert result.checks[0].status == status
    assert result.checked_count == (status != 'unverifiable')
    assert result.ungrounded_count == (status == 'ungrounded')
    assert result.unverifiable_count == (status == 'unverifiable')


@pytest.mark.parametrize('failure,status,code', [
    ('provider', 422, None), ('storage', 500, None),
    ('concurrency', 429, 'concurrency_limit'), ('quota', 429, 'daily_quota_exceeded'),
    ('ledger', 503, None),
])
@pytest.mark.parametrize('cancel', [False, True])
def test_actual_pdf_thread_publishes_failure_even_without_waiter(paid_api, monkeypatch, failure, status, code, cancel):
    """Read a terminal failure over HTTP after the real thread, not the waiter, exits."""
    client, _, root = paid_api
    auth = headers()
    ticket, _ = receipts.claim(root, auth['Idempotency-Key'], access.owner_id('offline-owner-a'), 'paper', {})
    paper_id, path = papers.save_upload(b'%PDF-offline')
    entered, release = threading.Event(), threading.Event()
    failures = {'provider': ValueError, 'concurrency': runs.ConcurrencyLimitReached,
                'quota': runs.DailyCapReached, 'ledger': runs.PaidLedgerUnavailable}

    def extract(*_args, **_kwargs):
        entered.set()
        assert release.wait(5)
        if failure != 'storage':
            raise failures[failure]('SECRET_PROVIDER_EXCERPT')
        return contribution()

    monkeypatch.setattr(main, '_extract_paper_with_paid_reservation', extract)
    if failure == 'storage':
        monkeypatch.setattr(papers, 'save_extraction', MagicMock(side_effect=OSError('SECRET_STORAGE_PATH')))

    async def exercise():
        with receipts.activate(ticket):
            waiter = asyncio.create_task(main._process_uploaded_paper(paper_id, str(path)))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            if cancel:
                waiter.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await waiter
        finally:
            release.set()
        if not cancel:
            with pytest.raises(main._PaperStorageError if failure == 'storage' else failures[failure]):
                await waiter
        for _ in range(300):
            if not main._paper_jobs:
                break
            await asyncio.sleep(.01)
        assert not main._paper_jobs

    asyncio.run(exercise())
    response = client.get('/api/receipts', headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['state'] == 'failed' and body['status_code'] == status
    assert body['response']['error_code'] == code
    assert 'SECRET' not in response.text
    assert 'zero cost' in body['response']['detail']
    assert not path.exists()
    assert not (papers.paper_dir(paper_id) / 'extraction.json').exists()


def test_pdf_receipt_commit_failure_is_not_a_false_extraction_failure(paid_api, monkeypatch):
    """A success whose journal write fails remains unresolved and cannot re-dispatch."""
    client, _, _ = paid_api
    model = MagicMock(return_value=contribution())
    monkeypatch.setattr(main, 'extract_paper_contribution', model)
    auth = headers()
    files = {'file': ('paper.pdf', b'%PDF-offline')}
    with monkeypatch.context() as fault:
        committer = MagicMock(side_effect=receipts.ReceiptError(503, 'receipt_unavailable', 'unavailable'))
        fault.setattr(receipts.Ticket, 'finish', committer)
        assert client.post('/api/papers', headers=auth, files=files).status_code == 503
        assert committer.call_count == 1
    record = client.get('/api/receipts', headers=auth).json()
    assert record['state'] == 'pending'
    assert papers.load_extraction(record['resource_id'])['title'] == contribution().title
    assert client.post('/api/papers', headers=auth, files=files).status_code == 409
    assert model.call_count == 1
