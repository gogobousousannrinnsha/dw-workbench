"""Real Tk widgets with a fake native boundary; no Viewer interaction claimed."""
import json
import subprocess
import sys
import time

import pytest

from test_template_authoring import environment, add_rect


@pytest.fixture(scope='module')
def tk_root():
    tk = pytest.importorskip('tkinter')
    try: window = tk.Tk()
    except tk.TclError as exc: pytest.skip('Tk display unavailable: '+str(exc))
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def editor(tmp_path, monkeypatch, tk_root):
    import tkinter as tk
    from docuworks_integrations.template_editor import Editor
    window = tk.Toplevel(tk_root); window.withdraw()
    app, draft, *_ = environment(tmp_path, monkeypatch)
    draft = add_rect(add_rect(draft))
    ui = Editor(window, app)
    monkeypatch.setattr(ui, 'render_page', lambda: None)
    errors = []
    monkeypatch.setattr(ui.messages, 'showerror', lambda *a, **k: errors.append(a))
    ui.adopt(draft)
    yield ui, errors
    ui.closed = True
    if ui.save_timer: window.after_cancel(ui.save_timer)
    window.destroy()


def test_real_widgets_edit_switch_purpose_reorder_and_resume(editor):
    ui, errors = editor
    uid = ui.selected
    ui.field_name.set('部品番号')
    ui.purpose.set('適用判定')
    ui.window.update()
    assert ui.expected_row.winfo_manager() == 'pack'
    assert ui.expected.get() == ui.examples[uid]['value'].strip()
    ui.purpose.set('取得')
    assert ui.required_box.winfo_manager() == 'pack'
    ui.reorder(1)
    assert ui.ordered()[-1] == uid
    assert ui.save()
    saved = ui.api.load_template_draft(ui.draft.root)
    assert saved.data['settings'][uid]['name'] == '部品番号'
    ui.adopt(saved)
    assert ui.settings == saved.data['settings']
    assert not errors


def test_confirmation_and_busy_controls(editor):
    ui, errors = editor
    result = dict(conditions=[], fields=[], diagnostics=['no_conditions'], warnings=True, applicable=True)
    ui.checked(result)
    assert ui.publish_button.instate(['disabled'])
    ui.confirmed.set(True); ui.update_publish_button()
    assert ui.publish_button.instate(['!disabled'])
    ui.set_busy(True)
    assert ui.field_entry.instate(['disabled']) and ui.publish_button.instate(['disabled'])
    ui.set_busy(False)
    assert ui.field_entry.instate(['!disabled']) and ui.purpose_box.instate(['readonly'])
    result['applicable'] = False; ui.checked(result)
    assert ui.publish_button.instate(['disabled'])
    assert not errors


def test_canvas_selection_and_page_coordinates(editor):
    from PIL import Image
    from types import SimpleNamespace
    ui, _ = editor
    ui.image = Image.new('RGB', (600, 800), 'white'); ui.page_mm = (10, 20)
    ui.draw()
    uid = ui.selected
    x, y, x2, y2 = ui.boxes[uid]
    ui.canvas_select(SimpleNamespace(x=(x+x2)/2, y=(y+y2)/2))
    ui.window.update()
    assert ui.selected != uid  # identical rectangles can both be selected
    ui.zoom.set('200%'); ui.draw()
    assert ui.boxes[uid] != (x,y,x2,y2)


def test_small_window_keeps_preview_and_save_status_visible(editor):
    ui, _ = editor
    ui.window.geometry('860x650'); ui.window.deiconify()
    ui.details_open.set(True); ui.toggle_details(); ui.window.update()
    bottom = ui.window.winfo_rooty() + ui.window.winfo_height()
    for widget in (ui.check_button, ui.status_label):
        assert widget.winfo_viewable()
        assert widget.winfo_rooty() + widget.winfo_height() <= bottom
    ui.window.withdraw()


def test_child_process_failure_returns_to_editable_state(editor):
    ui, errors = editor
    ui.run_job('preview', {'draft_dir': str(ui.app_root/'absent')}, lambda value: pytest.fail('unexpected success'))
    deadline = time.monotonic() + 15
    while ui.process and time.monotonic() < deadline:
        ui.window.update(); time.sleep(.01)
    assert ui.process is None and errors
    assert ui.field_entry.instate(['!disabled'])


def test_cli_help_and_lazy_api_do_not_load_gui_or_native():
    code = ('import sys; import docuworks_integrations as p; '
            'f=p.load_template_draft; from docuworks_integrations.cli import _parser; '
            'assert _parser().parse_args(["template-editor","--app-root","."]).command=="template-editor"; '
            'assert not any(k in sys.modules for k in ("tkinter","PIL","docuworks_ctypes"))')
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True)
