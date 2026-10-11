from dataclasses import replace
import io
import json
import zipfile
import numpy as np
import pandas as pd
import pytest
from routing import Config, Reservoir, ModelError, route, summarize
from sample_data import SAMPLE_INFLOW, SAMPLE_VZ
from data_io import excel_bytes, project_zip, read_table, report_html


def flood(t, q):
    return pd.DataFrame({'Time (h)':t,'Q (m3/s)':q})


@pytest.mark.parametrize('method',['direct','potapop'])
def test_below_crest_stores_water_without_discharge(method):
    vz = pd.DataFrame({'Z (m)':[0.,10.], 'V (10^6 m3)':[0.,1.]})
    c = Config(crest=8, initial=1, step=0.3)
    out = route(flood([0.,0.7,2.1],[10.,10.,10.]),vz,c,method)
    expected = 100000+out['Time (h)']*3600*10
    np.testing.assert_allclose(out['Volume V (m3)'],expected,atol=1e-5)
    assert (out['Outflow q (m3/s)'] == 0).all()
    assert out['Time (h)'].iloc[-1] == 2.1


@pytest.mark.parametrize('method',['direct','potapop'])
def test_steady_state(method):
    c = replace(Config(),initial=46.)
    q = float(Reservoir(SAMPLE_VZ,c).discharge(c.initial))
    out = route(flood([0,2.7,5.1],[q,q,q]),SAMPLE_VZ,c,method)
    np.testing.assert_allclose(out['Elevation Z (m)'],46.,atol=1e-9)


@pytest.mark.parametrize('method',['direct','potapop'])
def test_linear_outlet_matches_analytic_trapezoidal_recurrence(method):
    # S=A*z, q=k*z: trapezoidal scheme z2=z1*(1-k*dt/(2A))/(1+k*dt/(2A)).
    vz = pd.DataFrame({'Z (m)':[0.,10.], 'V (10^6 m3)':[0.,1.]})
    rating = pd.DataFrame({'Z (m)':[0.,10.], 'q (m3/s)':[0.,100.]})
    c = Config(crest=0, initial=5, step=0.25)
    out = route(flood([0.,2.],[0.,0.]),vz,c,method,rating)
    factor = (1-10*900/(2*100000))/(1+10*900/(2*100000))
    np.testing.assert_allclose(out['Elevation Z (m)'],5*factor**np.arange(len(out)),atol=1e-9)


def test_irregular_grid_preserves_input_peak_and_volume():
    source = flood([0,0.37,1.11,2.13],[0,17,4,0])
    out = route(source,SAMPLE_VZ,replace(Config(),step=0.8))
    expected = np.trapezoid(source['Q (m3/s)'],source['Time (h)']*3600)
    assert out['Inflow Q (m3/s)'].max() == 17
    assert out['Inflow volume (m3)'].iloc[-1] == pytest.approx(expected)
    assert out['Time (h)'].iloc[-1] == 2.13
    assert out['dt (h)'].max() <= 0.8+1e-10


def test_sample_methods_agree_and_balance():
    direct = route(SAMPLE_INFLOW,SAMPLE_VZ)
    pot = route(SAMPLE_INFLOW,SAMPLE_VZ,method='potapop')
    for df in [direct,pot]:
        assert abs(summarize(df)['Sai số tổng cân bằng (m3)']) < 0.01
        assert df['Balance residual (m3)'].abs().max() < 0.01
    assert np.max(abs(direct['Elevation Z (m)']-pot['Elevation Z (m)'])) < 0.001
    assert np.max(abs(direct['Outflow q (m3/s)']-pot['Outflow q (m3/s)'])) < 0.1


@pytest.mark.parametrize('method',['direct','potapop'])
def test_out_of_domain_rejected(method):
    with pytest.raises(ModelError,match='vượt biên'):
        route(flood([0,1],[1e6,1e6]),SAMPLE_VZ,method=method)


@pytest.mark.parametrize('bad',[
    flood([0,0],[1,2]), flood([0,1],[-1,2]), flood([0,1],[np.nan,2]),
    flood([0,1],[np.inf,2]), flood([0], [1])])
def test_invalid_inflows(bad):
    with pytest.raises(ModelError):
        route(bad,SAMPLE_VZ)


def test_nonmonotonic_volume_and_initial_outside_rejected():
    bad = SAMPLE_VZ.copy()
    bad.loc[2,'V (10^6 m3)'] = bad.loc[1,'V (10^6 m3)']
    with pytest.raises(ModelError):
        route(SAMPLE_INFLOW,bad)
    with pytest.raises(ModelError):
        route(SAMPLE_INFLOW,SAMPLE_VZ,replace(Config(),initial=80))


def test_zero_inflow_no_division_by_zero():
    out = route(flood([0,1],[0,0]),SAMPLE_VZ)
    assert summarize(out)['Giảm đỉnh (%)'] is None


def test_resource_limits():
    with pytest.raises(ModelError):
        route(SAMPLE_INFLOW,SAMPLE_VZ,replace(Config(),step=0.00001))
    with pytest.raises(ModelError):
        Reservoir(SAMPLE_VZ,replace(Config(),dz=0.00001))


def test_exports_reopen_and_preserve_reproducibility():
    cfg = Config()
    out = route(SAMPLE_INFLOW,SAMPLE_VZ,cfg)
    s = summarize(out)
    raw = excel_bytes(out,SAMPLE_INFLOW,SAMPLE_VZ,cfg,Reservoir(SAMPLE_VZ,cfg).auxiliary(),s)
    reopened = pd.read_excel(io.BytesIO(raw),sheet_name='Ket_qua')
    np.testing.assert_allclose(reopened['Elevation Z (m)'],out['Elevation Z (m)'])
    archive = project_zip(SAMPLE_INFLOW,SAMPLE_VZ,cfg,out,s,{'method':'direct'})
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        meta = json.loads(z.read('calculation.json'))
        assert meta['config']['step'] == 1
        assert meta['method'] == 'direct'
        pd.testing.assert_frame_equal(pd.read_csv(io.BytesIO(z.read('inflow.csv'))),SAMPLE_INFLOW)


def test_csv_semicolon_and_html_escaping():
    class Uploaded(io.BytesIO):
        name = 'data.csv'
    df = read_table(Uploaded(b't;q\n0;1\n1;2\n'))
    assert list(df.columns) == ['t','q']
    html = report_html('<script>alert(1)</script>','direct',Config(),{'test':1},[],['<img>']).decode()
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
