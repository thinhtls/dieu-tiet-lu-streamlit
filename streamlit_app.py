import hashlib
import io
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from routing import Config, Reservoir, ModelError, route, summarize, validate_frame
from sample_data import SAMPLE_INFLOW, SAMPLE_VZ
from data_io import read_table, excel_bytes, report_html, project_zip

st.set_page_config(page_title='Điều tiết lũ | Hồ chứa', page_icon='💧', layout='wide')
st.markdown('''<style>
.stApp{background:linear-gradient(160deg,#f5f9fc 0%,#fff 65%)}
h1,h2,h3{color:#153c53} [data-testid="stMetric"]{background:white;border:1px solid #d9e6ed;border-radius:14px;padding:16px}
[data-testid="stSidebar"]{background:#eaf2f7}
</style>''', unsafe_allow_html=True)
st.caption('THỦY VĂN · HỒ CHỨA · TRÀN XẢ LŨ')
st.title('Điều tiết lũ qua hồ chứa')
st.write('Từ đường quá trình lũ đến đến mực nước hồ và lưu lượng xả. Kiểm tra cân bằng nước, đối chiếu phương pháp và khảo sát phương án trên cùng bộ dữ liệu.')

with st.sidebar:
    st.header('Thiết lập bài toán')
    title = st.text_input('Tên hồ / kịch bản', 'Hồ minh họa — tràn tự do')
    method_label = st.selectbox('Phương pháp', ['Cân bằng nước — giải trực tiếp', 'Potapop — bảng phụ trợ'])
    method = 'direct' if method_label.startswith('Cân') else 'potapop'
    hydraulic = st.radio('Quan hệ xả', ['Công thức tràn tự do', 'Bảng q–Z tổng xả'])
    crest = st.number_input('Cao trình ngưỡng Zc (m)', value=44.1, format='%.3f')
    initial = st.number_input('Mực nước ban đầu Z0 (m)', value=44.1, format='%.3f')
    width = st.number_input('Tổng bề rộng thông thủy B (m)', min_value=0.0, value=45.0, step=1.0, disabled=hydraulic.startswith('Bảng'))
    with st.expander('Hệ số thủy lực'):
        m = st.number_input('Hệ số lưu lượng m', min_value=0.001, value=0.35, step=0.01, format='%.3f')
        epsilon = st.number_input('Co hẹp bên ε', min_value=0.001, max_value=1.0, value=1.0, step=0.01)
        sigma = st.number_input('Hệ số ngập σ', min_value=0.001, max_value=1.0, value=1.0, step=0.01)
        g = st.number_input('g (m/s²)', min_value=0.01, value=9.81, step=0.01)
        st.caption('σ = 1 khi chảy tự do. Có hay không có cửa van không quyết định trạng thái ngập. σ cố định chỉ là giả thiết giản lược.')
    step = st.number_input('Bước thời gian tối đa Δt (giờ)', min_value=0.001, value=1.0, step=0.1, format='%.3f')
    dz = st.number_input('Độ chia bảng Potapop ΔZ (m)', min_value=0.001, value=0.02, step=0.01, format='%.3f')
    cfg = Config(crest, initial, width, m, epsilon, sigma, g, step, dz)
    with st.expander('Ngưỡng tham chiếu (tùy chọn)'):
        check_z = st.checkbox('So với mực nước giới hạn')
        limit_z = st.number_input('Mực nước giới hạn (m)', value=48.0, format='%.3f') if check_z else None
        check_dam = st.checkbox('So với cao trình đỉnh đập')
        dam_z = st.number_input('Cao trình đỉnh đập (m)', value=50.0, format='%.3f') if check_dam else None
        check_q = st.checkbox('So với lưu lượng giới hạn hạ lưu')
        limit_q = st.number_input('Lưu lượng tham chiếu (m³/s)', min_value=0.0, value=400.0) if check_q else None
    st.caption('Dữ liệu mẫu từ mã nguồn cung cấp; chưa được xác nhận là đặc trưng của một hồ thực tế.')


def data_input(label, sample, kind, key):
    st.subheader(label)
    mode = st.radio('Nguồn dữ liệu', ['Mẫu / nhập bảng', 'Tải tệp'], horizontal=True, key=key+'_mode')
    cols = list(sample.columns)
    if mode == 'Tải tệp':
        up = st.file_uploader('CSV UTF-8 hoặc Excel .xlsx (≤ 10 MB)', type=['csv', 'xlsx'], key=key+'_file')
        if up is None:
            st.info('Chọn tệp để tiếp tục; ứng dụng không tự thay bằng số liệu mẫu.')
            return None
        try:
            if len(up.getvalue()) > 10*1024*1024:
                raise ValueError('Tệp vượt giới hạn 10 MB.')
            sheet = None
            if up.name.lower().endswith('.xlsx'):
                names = pd.ExcelFile(io.BytesIO(up.getvalue()), engine='openpyxl').sheet_names
                sheet = st.selectbox('Trang tính', names, key=key+'_sheet')
            raw = read_table(up, sheet)
            if len(raw.columns) < 2 or len(raw) > 20000:
                raise ValueError('Cần ít nhất 2 cột và không quá 20.000 dòng.')
            a = st.selectbox('Cột '+cols[0], list(raw.columns), key=key+'_a')
            b = st.selectbox('Cột '+cols[1], list(raw.columns), index=1, key=key+'_b')
            if a == b:
                raise ValueError('Hai đại lượng phải dùng hai cột khác nhau.')
            df = raw[[a,b]].copy()
            df.columns = cols
            st.dataframe(df.head(10), hide_index=True)
        except Exception as exc:
            st.error('Không đọc được dữ liệu: '+str(exc))
            return None
    else:
        df = st.data_editor(sample.copy(), num_rows='dynamic', hide_index=True, key=key+'_editor', width='stretch')
    unit = st.selectbox('Đơn vị dung tích', ['Triệu m³', 'm³'], key=key+'_unit') if kind == 'vz' else None
    if unit == 'm³':
        try:
            df[cols[1]] = pd.to_numeric(df[cols[1]], errors='raise')/1e6
        except (ValueError, TypeError):
            st.error('Dung tích phải là số.')
            return None
    st.download_button('Tải mẫu CSV', sample.to_csv(index=False).encode('utf-8-sig'), key+'.csv', 'text/csv', key=key+'_template')
    if kind == 'vz':
        st.caption('Bảng mẫu dùng triệu m³. Đổi đơn vị trên khi số bạn nhập dùng m³. Dung tích là dung tích tích lũy toàn hồ.')
    return df


def chart(df, columns, ylabel, thresholds=()):
    fig = go.Figure()
    colors = ['#177ca5','#e5813d','#287f64']
    labels = {'Inflow Q (m3/s)':'Lũ đến Q', 'Outflow q (m3/s)':'Xả q', 'Elevation Z (m)':'Mực nước Z', 'Volume V (m3)':'Dung tích V'}
    for i,c in enumerate(columns):
        fig.add_trace(go.Scatter(x=df['Time (h)'],y=df[c],name=labels.get(c,c),mode='lines',line=dict(color=colors[i%3],width=3)))
    for value,label in thresholds:
        if value is not None:
            fig.add_hline(y=value,line_dash='dash',annotation_text=label, line_color='#a44141')
    fig.update_layout(template='plotly_white',height=380,margin=dict(l=15,r=25,t=35,b=10),xaxis_title='Thời gian (giờ)',yaxis_title=ylabel,legend=dict(orientation='h',y=1.15),hovermode='x unified')
    return fig


data_tab, result_tab, compare_tab, theory_tab = st.tabs(['01 · Dữ liệu', '02 · Kết quả', '03 · Kiểm chứng & phương án', '04 · Phương pháp & tài liệu'])
with data_tab:
    st.info('Thời gian tính bằng giờ, lưu lượng bằng m³/s, cao trình bằng m. Có thể sửa trực tiếp bảng mẫu hoặc tải hai tệp độc lập.')
    a,b = st.columns(2)
    with a:
        inflow = data_input('Đường quá trình lũ đến Q–t', SAMPLE_INFLOW, 'inflow', 'inflow')
    with b:
        vz = data_input('Đặc trưng lòng hồ V–Z', SAMPLE_VZ, 'vz', 'vz')
    rating = None
    if hydraulic.startswith('Bảng'):
        sample_rating = pd.DataFrame({'Z (m)':SAMPLE_VZ['Z (m)'], 'q (m3/s)':0.35*45*np.sqrt(2*9.81)*np.maximum(SAMPLE_VZ['Z (m)']-44.1,0)**1.5})
        rating = data_input('Quan hệ tổng xả q–Z', sample_rating, 'rating', 'rating')
        st.caption('Tổng xả của mọi công trình; bảng phải đơn trị, không giảm theo Z. Bảng mẫu chỉ minh họa công thức mặc định. Không biểu diễn lịch mở cửa van thay đổi theo thời gian.')
    ready = inflow is not None and vz is not None and (not hydraulic.startswith('Bảng') or rating is not None)
    valid = False
    if ready:
        try:
            reservoir = Reservoir(vz,cfg,rating)
            validate_frame(inflow,['Time (h)','Q (m3/s)'],'Lũ đến')
            valid = True
            st.success(f'Dữ liệu hợp lệ: {len(inflow)} điểm Q–t, {len(vz)} điểm V–Z. Phạm vi tính: {reservoir.lo:g}–{reservoir.hi:g} m.')
        except ModelError as exc:
            st.error(str(exc))
    run = st.button('Tính điều tiết lũ', type='primary', disabled=not valid, width='stretch')

fingerprint = None
if ready:
    payload = json.dumps({'cfg':asdict(cfg),'method':method,'hydraulic':hydraulic,'title':title,'limits':[limit_z,dam_z,limit_q]},sort_keys=True)
    payload += inflow.to_csv(index=False)+vz.to_csv(index=False)+(rating.to_csv(index=False) if rating is not None else '')
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
if run:
    st.session_state.pop('calculation',None)
    try:
        with st.spinner('Đang giải cân bằng nước…'):
            results = route(inflow,vz,cfg,method,rating)
        st.session_state.calculation = dict(fingerprint=fingerprint, results=results,timestamp=datetime.now(timezone(timedelta(hours=7))).isoformat())
        st.success('Đã tính xong. Mở thẻ “02 · Kết quả” để xem và tải báo cáo.')
    except ModelError as exc:
        st.error(str(exc))
saved = st.session_state.get('calculation')
active = saved is not None and saved['fingerprint'] == fingerprint and valid

with result_tab:
    if not active:
        st.info('Nhập dữ liệu và bấm “Tính điều tiết lũ” ở thẻ 01.' if not saved else 'Đầu vào đã thay đổi. Hãy tính lại để cập nhật kết quả; kết quả cũ đã được ẩn.')
    else:
        results = saved['results']
        summary = summarize(results)
        st.subheader(title)
        st.caption(method_label+' · '+saved['timestamp'][:19].replace('T',' ')+' (UTC+7)')
        metrics = st.columns(2)
        for i, (name, val, unit) in enumerate(zip(['Đỉnh lũ đến','Đỉnh xả','Mực nước lớn nhất','Dung tích tăng lớn nhất'],[summary['Q đến max (m3/s)'],summary['q xả max (m3/s)'],summary['Z max (m)'],summary['Dung tích tăng max (triệu m3)']],['m³/s','m³/s','m','triệu m³'])):
            metrics[i % 2].metric(f'{name} ({unit})',f'{val:,.3f}')
        warnings = []
        if limit_z is not None and summary['Z max (m)'] > limit_z:
            warnings.append(f'Zmax vượt mực nước tham chiếu {limit_z:g} m.')
        if dam_z is not None:
            gap = dam_z-summary['Z max (m)']
            warnings.append(f'Khoảng cách hình học từ Zmax đến đỉnh đập: {gap:.3f} m; chưa xét sóng, nước dềnh và yêu cầu độ vượt cao.')
            if gap <= 0:
                warnings.append('Mực nước đạt/vượt đỉnh đập. Mô hình hiện tại chưa tính xả tràn qua thân đập; không tiếp tục diễn giải như hồ chỉ xả qua tràn thiết kế.')
        if limit_q is not None and summary['q xả max (m3/s)'] > limit_q:
            warnings.append(f'Đỉnh xả vượt lưu lượng tham chiếu hạ lưu {limit_q:g} m³/s. Chưa diễn toán dòng chảy hạ lưu.')
        if results['Outflow q (m3/s)'].iloc[-1] > results['Inflow Q (m3/s)'].iloc[-1] or results['Inflow Q (m3/s)'].iloc[-1] > 0:
            warnings.append('Chuỗi kết thúc khi hồ/lũ còn nước. Tổng lượng và các cực trị chỉ thuộc khoảng thời gian đã cung cấp; bổ sung nhánh rút nếu cần.')
        for w in warnings:
            st.warning(w)
        st.caption(f"Thời điểm Zmax: {summary['t Z max (h)']:.3f} h · Trễ đỉnh xả: {summary['Trễ đỉnh (h)']:.3f} h · " + (f"Giảm đỉnh so với Qmax: {summary['Giảm đỉnh (%)']:.2f}%" if summary['Giảm đỉnh (%)'] is not None else 'Qmax = 0: không tính tỷ lệ giảm đỉnh.'))
        f_q = chart(results,['Inflow Q (m3/s)','Outflow q (m3/s)'],'Lưu lượng (m³/s)',[(limit_q,'Giới hạn hạ lưu')])
        f_z = chart(results,['Elevation Z (m)'],'Cao trình (m)',[(crest,'Ngưỡng tràn'),(limit_z,'Mực nước giới hạn'),(dam_z,'Đỉnh đập')])
        st.plotly_chart(f_q,width='stretch')
        st.plotly_chart(f_z,width='stretch')
        with st.expander('Cân bằng nước & bảng tính',expanded=True):
            st.write(f"Tổng đến **{summary['Tổng đến (triệu m3)']:.6f}** − tổng xả **{summary['Tổng xả (triệu m3)']:.6f}** = thay đổi dung tích **{summary['Thay đổi dung tích (triệu m3)']:.6f} triệu m³**.")
            st.caption(f"Sai số tổng: {summary['Sai số tổng cân bằng (m3)']:.3g} m³ · sai số bước lớn nhất: {summary['Sai số bước max (m3)']:.3g} m³ · sai số quan hệ xả lớn nhất: {summary['Sai số thủy lực max (m3/s)']:.3g} m³/s.")
            st.dataframe(results,hide_index=True,width='stretch')
        auxiliary = reservoir.auxiliary()
        with st.expander('Bảng và biểu đồ phụ trợ Potapop'):
            st.caption('Bảng ứng với Δt danh định; mỗi bước ngắn hơn lập lại f1, f2 theo thời đoạn thực tế. ΔV lấy mốc tại Z0.')
            st.dataframe(auxiliary,hide_index=True)
            fig = go.Figure()
            for c in ['f1 (m3/s)','f2 (m3/s)']:
                fig.add_trace(go.Scatter(x=auxiliary[c],y=auxiliary['q (m3/s)'],name=c))
            fig.update_layout(xaxis_title='f1, f2 (m³/s)',yaxis_title='q (m³/s)',template='plotly_white')
            st.plotly_chart(fig,width='stretch')
        st.subheader('Tải hồ sơ tính toán')
        e1,e2,e3,e4 = st.columns(4)
        e1.download_button('Kết quả CSV',results.to_csv(index=False).encode('utf-8-sig'),'ket_qua.csv','text/csv')
        e2.download_button('Bảng Excel',excel_bytes(results,inflow,vz,cfg,auxiliary,summary,rating),'dieu_tiet_lu.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        e3.download_button('Báo cáo HTML',report_html(title,method_label,cfg,summary,[f_q,f_z],warnings),'bao_cao_dieu_tiet.html','text/html')
        e4.download_button('Toàn bộ hồ sơ ZIP',project_zip(inflow,vz,cfg,results,summary,{'method':method,'hydraulic':hydraulic,'timestamp':saved['timestamp'],'thresholds':{'z':limit_z,'dam':dam_z,'q':limit_q}},rating),'ho_so_dieu_tiet.zip','application/zip')

with compare_tab:
    st.subheader('Kiểm chứng kết quả')
    st.write('Hai phương pháp dùng cùng phương trình cân bằng. So sánh phản ánh sai số tra bảng; kiểm tra Δt/2 phản ánh độ nhạy thời gian. Sự thống nhất không thay thế kiểm định số liệu công trình.')
    if st.button('So sánh hai phương pháp & Δt/2',disabled=not valid):
        try:
            with st.spinner('Đang kiểm tra…'):
                comparison = []
                for name, meth, conf in [('Trực tiếp', 'direct', cfg),('Potapop','potapop',cfg),('Trực tiếp Δt/2','direct',replace(cfg,step=cfg.step/2))]:
                    d = route(inflow,vz,conf,meth,rating)
                    comparison.append({'Trường hợp':name,**summarize(d)})
                st.session_state.comparison = (fingerprint,pd.DataFrame(comparison))
        except ModelError as exc:
            st.error(str(exc))
    comparison = st.session_state.get('comparison')
    if comparison and comparison[0] == fingerprint and valid:
        cdf = comparison[1]
        st.dataframe(cdf,hide_index=True)
        dq = cdf.iloc[2]['q xả max (m3/s)']-cdf.iloc[0]['q xả max (m3/s)']
        dz_diff = cdf.iloc[2]['Z max (m)']-cdf.iloc[0]['Z max (m)']
        st.info(f'Giảm Δt một nửa: chênh Zmax {dz_diff:+.6f} m; chênh qmax {dq:+.6f} m³/s. Tiếp tục giảm bước đến khi đạt dung sai của bài toán.')
    st.divider()
    st.subheader('Khảo sát bề rộng tràn')
    st.caption('Giữ nguyên đường lũ, Z0, ngưỡng và hệ số. Tràn rộng hơn có thể giảm mực nước hồ nhưng tăng đỉnh xả xuống hạ lưu.')
    widths_text = st.text_input('Các bề rộng B (m), cách nhau bằng dấu chấm phẩy', '30; 45; 60')
    if st.button('Tính các phương án',disabled=not valid or rating is not None):
        try:
            widths = sorted(set(float(x.strip()) for x in widths_text.split(';')))
            if not 1 <= len(widths) <= 12 or not all(np.isfinite(x) and x > 0 for x in widths):
                raise ModelError('Nhập 1–12 bề rộng dương, dùng dấu chấm thập phân và dấu ; phân cách.')
            rows = []
            for w in widths:
                try:
                    s = summarize(route(inflow,vz,replace(cfg,width=w),'direct'))
                    rows.append({'B (m)':w, 'Trạng thái':'Đã tính', **s})
                except ModelError as exc:
                    rows.append({'B (m)':w,'Trạng thái':str(exc)})
            st.session_state.scenarios = (fingerprint,pd.DataFrame(rows))
        except ValueError as exc:
            st.error(str(exc))
    scenarios = st.session_state.get('scenarios')
    if scenarios and scenarios[0] == fingerprint and valid:
        sdf = scenarios[1]
        st.dataframe(sdf,hide_index=True)
        st.download_button('Tải bảng phương án',sdf.to_csv(index=False).encode('utf-8-sig'),'phuong_an.csv','text/csv')
        good = sdf[sdf['Trạng thái']=='Đã tính']
        if not good.empty:
            c1,c2 = st.columns(2)
            for col,y in [(c1,'Z max (m)'),(c2,'q xả max (m3/s)')]:
                fig = go.Figure(go.Scatter(x=good['B (m)'],y=good[y],mode='lines+markers'))
                fig.update_layout(xaxis_title='B (m)',yaxis_title=y,template='plotly_white',height=300)
                col.plotly_chart(fig,width='stretch')

with theory_tab:
    st.subheader('Cơ sở tính toán')
    st.latex(r'V_2-V_1=\left[\frac{Q_1+Q_2}{2}-\frac{q_1+q_2}{2}\right]\Delta t')
    st.latex(r'q(Z)=\varepsilon\,\sigma\,m\,B\sqrt{2g}\,[\max(Z-Z_c,0)]^{3/2}')
    st.latex(r'f_1=\frac{V-V_{ref}}{\Delta t}-\frac{q}{2},\quad f_2=\frac{V-V_{ref}}{\Delta t}+\frac{q}{2},\quad f_{2,2}=\overline Q+f_{1,1}')
    st.markdown('''**Giải trực tiếp:** giải nghiệm mực nước cuối bước trong phạm vi bảng V–Z, dùng nghiệm có chặn. **Potapop:** nội suy bảng f2–Z, giữ dung tích là biến trạng thái để tính đúng khi Z0 dưới ngưỡng. Phương pháp bảng dùng quan hệ xả tuyến tính từng đoạn trên lưới ΔZ; có báo sai số so với công thức xả.

**Thời gian:** nội suy tuyến tính Q–t, giữ mọi thời điểm gốc và thời điểm kết thúc. Δt là bước tối đa, có thể có bước ngắn hơn tại điểm gãy. Không kéo dài hoặc tự giả định nhánh lũ rút. Tích phân hình thang trên lưới này giữ tổng lượng của đường lũ tuyến tính gốc.

**Giả thiết:** mặt nước hồ ngang; bỏ qua lưu tốc tới gần; không xét trực tiếp mưa lên mặt hồ, bốc hơi, thấm, vỡ đập hoặc diễn toán hạ lưu. Nếu có dòng gia nhập khác, cần tổng hợp vào Q đến. Bảng q–Z phải mô tả tổng xả đơn trị theo mực nước; không áp dụng cho lịch vận hành cửa van thay đổi theo thời gian hoặc ảnh hưởng hạ lưu chưa được mô hình hóa.

**Diễn giải:** dung tích tăng lớn nhất là max(V)−V ban đầu trong cửa sổ tính, không tự động là dung tích phòng lũ theo quy hoạch. Zmax chỉ được gọi MNLTK/MNLKT khi dùng đúng đường lũ thiết kế/kiểm tra, điều kiện đầu và tổ hợp vận hành tương ứng. So sánh với đỉnh đập chỉ cho khoảng cách hình học, chưa gồm sóng và độ vượt cao theo tiêu chuẩn áp dụng.

**Hệ số:** m trong công thức trên là không thứ nguyên. Nếu tài liệu dùng q = C·B·H^1.5 thì C = ε·σ·m·√(2g); không nhập trực tiếp C vào ô m. B là bề rộng thông thủy; tránh trừ trụ pin hai lần qua B và ε. Các hệ số cần được lựa chọn theo hình dạng công trình, thí nghiệm hoặc hồ sơ đã kiểm chứng.
''')
    st.subheader('Đối chiếu tài liệu cung cấp')
    st.write('Đã đọc ba tài liệu Word, bản PDF Potapop và hai mã tính toán. Một số công thức trong “Cac buoc DTL potapop.docx” có nhầm dấu V1−V2 và dấu của f2; ứng dụng dùng công thức cân bằng ở trên. Các ví dụ cao trình 414–418 m và 102–108 m thuộc bài toán khác với bộ mẫu 23–60 m trong code; không trộn các bảng này.')
    st.subheader('Nguồn tham khảo')
    st.markdown('''- [USACE HEC-HMS — Reservoir Modeling Concepts and Equations](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations): cân bằng nước và giả thiết hồ mặt nước ngang.
- [USACE HEC-HMS — Spillways](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/spillways): quan hệ thủy lực tràn và ảnh hưởng hạ lưu.
- [USACE — Outflow Curve Option](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/modeling-reservoirs-in-hec-hms/modeling-reservoir-operations-with-hec-hms/outflow-curve-option-for-an-hec-hms-reservoir-element): tổng hợp mọi nguồn xả trong quan hệ tổng xả.
- [Streamlit — Triển khai Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app): công bố ứng dụng từ mã nguồn GitHub.
''')
st.divider()
st.caption('Công cụ nghiên cứu và kiểm tra phương án điều tiết lũ · Phiên bản 2.0 · Không ngoại suy đặc trưng hồ. Kết quả cần được kiểm chứng theo hồ sơ công trình trước khi sử dụng cho thiết kế hoặc vận hành thực tế.')
