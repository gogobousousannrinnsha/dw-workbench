from pathlib import Path
import importlib.util
from types import SimpleNamespace
import pytest


def helper():
    path=Path(__file__).resolve().parents[2]/'portable/scripts/import_reviewed.py'
    spec=importlib.util.spec_from_file_location('reviewed_entry',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('kind',['folder','file','renamed','prompt','multiple','wrong-extension','api-failure'])
def test_one_document_import(tmp_path,monkeypatch,kind,capsys):
    root=Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root/'packages/docuworks-ctypes'))
    monkeypatch.syspath_prepend(str(root/'packages/docuworks-integrations'))
    import docuworks_integrations as api
    session=tmp_path/'日本語 session';session.mkdir()
    (session/'session.json').write_text('{}')
    edited=session/'review.xdw';edited.write_bytes(b'fixture')
    calls=[]
    monkeypatch.setattr(api,'load_review_session',lambda p:SimpleNamespace(root=Path(p).resolve()))
    def take(s,e,out,*,validation_mode):
        assert validation_mode=='identity'
        calls.append((s,e,out))
        assert out.parent==session.parent/'reviewed' and not out.exists()
        if kind=='api-failure':raise ValueError('mismatched document')
        out.mkdir()
        return SimpleNamespace(root=out,pages=({'items':[]},),data={'excluded_sticky_count':0})
    monkeypatch.setattr(api,'import_reviewed_result',take)
    entry=helper()
    if kind=='multiple':
        with pytest.raises(ValueError,match='1文書'):entry.main([str(edited),str(edited)])
        assert not calls;return
    if kind=='wrong-extension':
        with pytest.raises(ValueError):entry.main([str(session/'wrong.json')])
        assert not calls;return
    if kind=='renamed':
        edited=tmp_path/'別名.xdw';edited.write_bytes(b'fixture')
        monkeypatch.setattr('builtins.input',lambda _:str(session))
    if kind=='prompt':monkeypatch.setattr('builtins.input',lambda _:str(edited))
    args=[] if kind=='prompt' else [str(session if kind=='folder' else edited)]
    if kind=='api-failure':
        with pytest.raises(ValueError):entry.main(args)
        assert not calls[0][2].exists()
    else:
        assert entry.main(args)==0
        assert calls[0][0]==session and calls[0][1]==edited
        first=calls[0][2]
        assert entry.main(args)==0 and calls[1][2]!=first
        assert '0文字項目' in capsys.readouterr().out
