from streamlit.testing.v1 import AppTest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def button(app, label):
    return next(x for x in app.button if x.label == label)


def test_default_calculation_comparison_scenarios_and_invalidation():
    app = AppTest.from_file(APP,default_timeout=30).run()
    assert not app.exception
    button(app,'Tính điều tiết lũ').click().run()
    assert not app.exception
    assert len(app.metric) == 4
    button(app,'So sánh hai phương pháp & Δt/2').click().run()
    assert not app.exception
    button(app,'Tính các phương án').click().run()
    assert not app.exception
    next(x for x in app.number_input if x.label == 'Mực nước ban đầu Z0 (m)').set_value(43.5).run()
    assert not app.exception
    assert len(app.metric) == 0
    button(app,'Tính điều tiết lũ').click().run()
    assert not app.exception
    assert len(app.metric) == 4


def test_potapop_custom_rating_and_invalid_configuration():
    app = AppTest.from_file(APP,default_timeout=30).run()
    next(x for x in app.selectbox if x.label == 'Phương pháp').select('Potapop — bảng phụ trợ').run()
    button(app,'Tính điều tiết lũ').click().run()
    assert not app.exception
    assert len(app.metric) == 4
    next(x for x in app.radio if x.label == 'Quan hệ xả').set_value('Bảng q–Z tổng xả').run()
    button(app,'Tính điều tiết lũ').click().run()
    assert not app.exception
    assert len(app.metric) == 4
    assert button(app,'Tính các phương án').disabled
    next(x for x in app.number_input if x.label == 'Mực nước ban đầu Z0 (m)').set_value(100.0).run()
    assert not app.exception
    assert button(app,'Tính điều tiết lũ').disabled
    assert len(app.metric) == 0
