"""Explicit data loading and reproducible exports."""
import io
import json
import zipfile
import html
from dataclasses import asdict
import pandas as pd


def read_table(upload, sheet=None):
    if len(upload.getvalue()) > 10 * 1024 * 1024:
        raise ValueError('Tệp vượt 10 MB. Hãy rút gọn bảng dữ liệu.')
    raw = io.BytesIO(upload.getvalue())
    if upload.name.lower().endswith('.csv'):
        return pd.read_csv(raw, sep=None, engine='python', encoding='utf-8-sig')
    return pd.read_excel(raw, sheet_name=sheet or 0, engine='openpyxl')


def excel_bytes(results, inflow, vz, cfg, auxiliary, summary, rating=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        for name, df in [('Ket_qua', results), ('Lu_den', inflow), ('V_Z', vz),
                         ('Phu_tro', auxiliary), ('Tong_hop', pd.DataFrame([summary])),
                         ('Thong_so', pd.DataFrame([asdict(cfg)]))]:
            df.to_excel(writer, sheet_name=name, index=False)
        if rating is not None:
            rating.to_excel(writer, sheet_name='q_Z', index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = 'A2'
            sheet.auto_filter.ref = sheet.dimensions
            for col in sheet.columns:
                sheet.column_dimensions[col[0].column_letter].width = min(42, max(15, len(str(col[0].value))+2))
    return buf.getvalue()


def report_html(title, method, cfg, summary, figures, warnings):
    import plotly.io as pio
    rows = ''.join(f'<tr><td>{html.escape(k)}</td><td>{v:.6g}</td></tr>' for k,v in summary.items() if v is not None)
    charts = ''.join(pio.to_html(f, full_html=False, include_plotlyjs=True if i == 0 else False) for i,f in enumerate(figures))
    return ('<!doctype html><html lang="vi"><meta charset="utf-8"><title>Báo cáo điều tiết lũ</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;color:#18364b}'
        'td{padding:9px;border-bottom:1px solid #ddd}table{border-collapse:collapse;width:100%}</style>'
        f'<h1>{html.escape(title)}</h1><p>Phương pháp: {html.escape(method)}</p>'
        '<p>Mô hình hồ mặt nước ngang, quan hệ xả đơn trị theo Z; kết quả trong thời gian số liệu được cung cấp.</p>'
        f'<pre>{html.escape(json.dumps(asdict(cfg),ensure_ascii=False,indent=2))}</pre><table>{rows}</table>'
        + ''.join(f'<p>{html.escape(w)}</p>' for w in warnings) + charts +
        '<p>Cần kiểm tra đặc trưng hồ và công trình trước khi sử dụng cho thiết kế/vận hành. '
        'Zmax không tự động là MNLTK hoặc MNLKT; khoảng cách đến đỉnh đập chưa gồm sóng và độ vượt cao.</p></html>').encode('utf-8')


def project_zip(inflow, vz, cfg, results, summary, metadata, rating=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, df in [('inflow.csv',inflow),('vz.csv',vz),('results.csv',results)]:
            z.writestr(name, df.to_csv(index=False).encode('utf-8-sig'))
        if rating is not None:
            z.writestr('rating.csv',rating.to_csv(index=False).encode('utf-8-sig'))
        z.writestr('calculation.json',json.dumps({'config':asdict(cfg),'summary':summary,**metadata},ensure_ascii=False,indent=2))
    return buf.getvalue()
