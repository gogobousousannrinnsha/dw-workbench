"""A/B opt-in routing, failed publication, observations and comparison conditions."""
import json
import pytest

from docuworks_integrations import reviewed as reviewed
from docuworks_integrations._performance import Recorder, measure
from docuworks_integrations.jobs import process_documents
from test_reviewed import setup, hashes


def test_page_join_route_and_immutable_canonical(tmp_path, monkeypatch):
    run, _, sdk = setup(tmp_path, monkeypatch)
    before = hashes(run.root)
    calls = []
    def create(identity, digest, path):
        calls.append(identity)
        return sdk.create(identity, digest, path)
    sdk.create_page_join = create
    session = reviewed.create_review_session(run.root, tmp_path/'joined', review_creation_mode='page_join')
    assert len(calls) == 1 and len(calls[0]['pages']) == 2
    assert session.data['generator']['review_creation_mode'] == 'page_join'
    assert hashes(run.root) == before
    with pytest.raises(FileExistsError):
        reviewed.create_review_session(run.root, session.root, review_creation_mode='page_join')


@pytest.mark.parametrize('fault', ['blank', 'text', 'save', 'merge', 'inspect'])
def test_failure_never_publishes_session(tmp_path, monkeypatch, fault):
    run, _, sdk = setup(tmp_path, monkeypatch)
    before = hashes(run.root)
    def fail(*args):
        raise RuntimeError('injected '+fault)
    if fault == 'inspect':
        sdk.create_page_join = sdk.create
        sdk.inspect = fail
    else:
        def partial(identity, digest, path):
            path.write_bytes(b'unfinished')
            fail()
        sdk.create_page_join = partial
    output = tmp_path/'failed'
    with pytest.raises(RuntimeError, match='injected'):
        reviewed.create_review_session(run.root, output, review_creation_mode='page_join')
    assert not output.exists()
    assert not list(tmp_path.glob('.review-session-*'))
    assert hashes(run.root) == before


def test_invalid_mode_is_rejected_before_any_output(tmp_path):
    with pytest.raises(ValueError, match='review_creation_mode'):
        reviewed.create_review_session(tmp_path/'missing', tmp_path/'output', review_creation_mode='typo')
    with pytest.raises(ValueError, match='review_creation_mode'):
        process_documents([], tmp_path/'output', tmp_path/'runs', tmp_path/'models', review_creation_mode='typo')
    assert not (tmp_path/'output').exists()


def test_observations_keep_failure_context(tmp_path):
    with Recorder(variant='B') as recorder:
        with pytest.raises(RuntimeError):
            with measure('review', document_id='doc-000001'):
                with measure('review.text', page=201, item_count=20):
                    raise RuntimeError('injected')
    target = recorder.write(tmp_path, status='FAILED')
    data = json.loads(target.read_text(encoding='utf-8'))
    assert all(e['status']=='FAILED' for e in data['events'])
    assert data['events'][1]['page'] == 201
    assert data['events'][1]['document_id'] == 'doc-000001'
    assert data['events'][1]['seconds'] >= 0
