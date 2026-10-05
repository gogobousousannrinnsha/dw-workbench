from pathlib import Path
from types import SimpleNamespace
import pytest
from docuworks_integrations import jobs, reviewed
from docuworks_integrations.results import load_ocr_result
from test_multipage import fake, Engine


@pytest.mark.parametrize('mode',['legacy','success','document-error','storage-error','ocr-error','invalid-option'])
def test_review_stage_contract(fake,tmp_path,monkeypatch,mode):
    calls=[]
    monkeypatch.setattr(jobs,'resolve_font',lambda *a:None)
    monkeypatch.setattr(jobs,'annotate_rectangles',lambda *a,**k:calls.append('rectangles'))
    monkeypatch.setattr(jobs,'render_text_maps',lambda *a,**k:calls.append('maps'))
    def create(run,out,**kwargs):
        loaded=load_ocr_result(run)
        assert [p.page for p in loaded.pages]==[1,2,3]
        calls.append('review')
        if mode=='document-error':
            from docuworks_ctypes import XdwError
            from docuworks_ctypes._raw.constants import XDW_E_SHARING_VIOLATION
            raise XdwError(XDW_E_SHARING_VIOLATION,'test')
        if mode=='storage-error':raise OSError('disk failure')
        Path(out).mkdir()
        return SimpleNamespace(review_id='test-review',manifest_sha256='a'*64)
    monkeypatch.setattr(reviewed,'create_review_session',create)
    source=tmp_path/'input';source.mkdir()
    for n in ('a.xdw','b.xdw'):(source/n).write_bytes(b'generated')
    if mode=='invalid-option':
        with pytest.raises(TypeError):jobs.process_documents([source],tmp_path/'out',tmp_path/'runs',tmp_path,review=1)
        assert not (tmp_path/'out').exists();return
    result=jobs.process_documents([source],tmp_path/'out',tmp_path/'runs',tmp_path,
        engine=Engine(failure=mode=='ocr-error'),review=mode!='legacy')
    if mode=='legacy':
        assert result['schema_version']=='1.0' and 'review' not in result['counts']
        assert 'review' not in calls
    elif mode=='success':
        assert result['schema_version']=='1.1' and result['counts']['review']['SUCCEEDED']==2
        assert calls==['review','rectangles','maps']*2
        assert result['documents'][0]['review_dir']=='doc-000001/review-session'
    elif mode=='document-error':
        assert result['status']=='PARTIAL_FAILED' and result['counts']['review']['FAILED']==2
        assert result['counts']['rectangles']['SUCCEEDED']==2
    elif mode=='storage-error':
        assert result['status']=='FAILED' and result['counts']['ocr']['PENDING']==1
        load_ocr_result(tmp_path/'runs/doc-000001')
    else:
        assert result['status']=='FAILED' and result['counts']['review']['PENDING']==2 and not calls


def test_empty_input_with_review(tmp_path):
    source=tmp_path/'input';source.mkdir()
    result=jobs.process_documents([source],tmp_path/'out',tmp_path/'runs',tmp_path,review=True)
    assert result['status']=='NO_INPUT' and result['counts']['review']['SUCCEEDED']==0
