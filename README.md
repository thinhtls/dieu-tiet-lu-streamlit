# Ứng dụng điều tiết lũ hồ chứa — phiên bản 2.0

Giao diện Streamlit tiếng Việt, tính Potapop và giải cân bằng nước trực tiếp cho hồ mặt nước ngang. Đầu vào CSV/XLSX hoặc bảng nhập trực tiếp; kết quả gồm Q–t, q–t, Z–t, dung tích, kiểm tra cân bằng và hồ sơ CSV/Excel/HTML/ZIP.

## Chạy trên máy

Python 3.12 được dùng khi kiểm thử. Tại thư mục ứng dụng:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Nếu không có lệnh `py`, dùng `python` trỏ tới Python 3.12. Trên Windows đã cài thư viện, có thể mở `run_app.bat`. Trên Linux/macOS dùng `.venv/bin/python` thay đường dẫn Windows.

## Đưa lên Streamlit Community Cloud

1. Đưa `streamlit_app.py`, `routing.py`, `data_io.py`, `sample_data.py`, `requirements.txt`, README này và thư mục `tests`, `examples` lên kho GitHub. Không đưa `.venv`, `.uv-cache`, dữ liệu riêng tư hoặc tài liệu công trình chưa được phép công bố.
2. Đăng nhập https://share.streamlit.io bằng tài khoản GitHub.
3. Chọn **Create app**, chọn kho mã nguồn và nhánh, đặt Main file path là `streamlit_app.py`.
4. Trong Advanced settings chọn Python 3.12; triển khai và chia sẻ URL dạng `https://…streamlit.app`.
5. Mở URL từ cửa sổ không đăng nhập để xác nhận quyền truy cập công khai. Không cần mật khẩu/API key để chạy bộ tính.

Hướng dẫn chính thức: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app

Một lựa chọn khác: `docker build -t dieu-tiet-lu .` rồi `docker run --rm -p 8501:8501 dieu-tiet-lu`. Dockerfile đã có nhưng chưa được chạy kiểm thử trong máy này.

## Sử dụng

1. Nhập tên hồ/kịch bản, cao trình ngưỡng tràn, mực nước ban đầu, bề rộng thông thủy, hệ số và bước thời gian tối đa.
2. Trong thẻ **Dữ liệu**, dùng mẫu hoặc tải riêng từng tệp. Chọn rõ trang Excel, hai cột và đơn vị dung tích. Không tự thay dữ liệu còn thiếu bằng mẫu.
3. Bấm **Tính điều tiết lũ**, mở thẻ **Kết quả**, xem cực trị, biểu đồ, sai số và tải hồ sơ.
4. Trong **Kiểm chứng & phương án**, so sánh Potapop với giải trực tiếp, kiểm tra Δt/2; khảo sát các bề rộng cách nhau bằng dấu `;`.
5. Khi sửa đầu vào, kết quả cũ bị ẩn để tránh nhầm. Bấm tính lại.

Tệp `examples/inflow.csv` có các cột `Time (h)`, `Q (m3/s)`. Tệp `examples/vz.csv` có `Z (m)`, `V (10^6 m3)` (triệu m³). q–Z có `Z (m)`, `q (m3/s)` là tổng xả của mọi công trình. CSV UTF-8, dấu chấm thập phân; có thể dùng dấu phẩy hoặc chấm phẩy phân cách cột. Không hỗ trợ .xls cũ; hãy lưu lại thành .xlsx. Mỗi tệp tối đa 10 MB, tối đa 20.000 dòng; lưới tính tối đa 20.000 điểm và bảng phụ trợ khoảng 50.000 mức.

Bảng V–Z cần Z tăng nghiêm ngặt, V tăng nghiêm ngặt và không âm. Thời điểm Q–t không được trùng; Q không âm. Bảng q–Z không giảm theo Z. Ứng dụng sắp xếp theo cột thứ nhất; không xóa ô lỗi hay dòng thiếu dữ liệu âm thầm. Z0 và nghiệm phải nằm trong phạm vi chung của các bảng.

## Cơ sở mô hình và thay đổi so với bản gốc

Phương trình cân bằng nước:

`V2 − V1 = [(Q1 + Q2)/2 − (q1 + q2)/2] × Δt`, với Δt tính bằng giây.

Tràn tự do: `q = ε × σ × m × B × √(2g) × max(Z − Zc, 0)^1.5`.

Potapop: `f1 = (V − Vref)/Δt − q/2`, `f2 = (V − Vref)/Δt + q/2`, `f2 cuối = Q bình quân + f1 đầu`.

- Giải trực tiếp dùng Brent có chặn theo Z, không dùng fsolve thiếu kiểm tra hội tụ. Không giữ nghiệm ở biên khi vượt bảng và không ngoại suy.
- Potapop dùng bảng f2–Z, giữ dung tích làm biến trạng thái; không suy Z từ q khi q = 0. Lưới bảng chứa mọi điểm gãy V–Z/q–Z, Z0 và ngưỡng tràn; nội suy tuyến tính từng đoạn. Quan hệ q của Potapop là quan hệ tuyến tính trên lưới ΔZ, còn phương pháp trực tiếp dùng công thức xả gốc. Cột Rating residual báo sai số giữa hai quan hệ này.
- Mốc Vref là dung tích ban đầu; thay mốc không đổi phương trình. Các mực dưới ngưỡng vẫn được lưu giữ với q = 0.
- Lưới thời gian giữ mọi thời điểm gốc và điểm cuối, bổ sung các điểm theo Δt; do đó Δt là bước tối đa. Tổng lượng của đường lũ tuyến tính gốc được giữ, không bỏ đỉnh hoặc cắt thời điểm cuối. Bảng phụ trợ lập lại cho bước ngắn hơn thay vì dùng sai Δt.
- Đồ thị nối tuyến tính, không làm trơn spline gây cực trị giả.
- Bảng kết quả báo sai số từng bước, sai số tổng cân bằng và sai số thủy lực. Hai phương pháp cùng phương trình nên việc khớp nhau không phải là kiểm định độc lập ngoài thực tế.

## Đọc và đối chiếu tài liệu người dùng

Đã đọc `Cac buoc DTL potapop.docx`, `Nội dung tính toán điều tiết lũ theo phương pháp potapop.docx` cùng bản PDF, `PP tính DTL thu dan.docx`, `code V2.txt`, `Code tran tu do 29.07.txt` và bản Streamlit ban đầu.

Trong `Cac buoc DTL potapop.docx`, một số biểu thức chép sai dấu V1−V2 và dấu f2. Ứng dụng dùng V2−V1 và f2 có dấu cộng như suy ra từ cân bằng nước. Ví dụ bảng phụ trợ tại H = 0,2 m có f2−f1 = 6,898 m³/s, khớp q và xác nhận dấu cộng. Có các ô bảng bất nhất (ví dụ 0,797 thay cho 0,197 triệu m³ và 419,167 tại H = 2,4 m không khớp f1+q); không dùng các ô này như kết quả chuẩn để ép mô hình khớp.

Các ví dụ cao trình 414–418 m, 102–108 m và bộ mẫu 23–60 m thuộc các bài toán khác nhau. Không ghép chúng. Bộ mẫu giữ nguyên số liệu từ code (Qmax = 728,2 m³/s, Zc = Z0 = 44,1 m, B = 45 m, m = 0,35, ε = σ = 1). Chưa xác nhận dữ liệu thực đo hoặc tần suất của bộ mẫu.

## Phạm vi sử dụng

Mặt nước hồ ngang; bỏ qua lưu tốc tới gần, mưa trực tiếp lên mặt hồ, thấm và bốc hơi. Tổng hợp gia nhập khác vào Q đến nếu có. Chỉ mô phỏng thời đoạn được nhập, không tự thêm nhánh lũ rút.

σ = 1 ứng với chảy tự do, không phải vì tràn không có cửa van. σ cố định là giản lược; ảnh hưởng hạ lưu theo thời gian cần mô hình phù hợp. Bảng q–Z là quan hệ đơn trị không giảm, không mô tả quy trình vận hành cửa van theo thời gian. Bề rộng B là thông thủy; tránh tính co hẹp trụ pin hai lần.

m không thứ nguyên; nếu tài liệu cho `q = C × B × H^1.5`, hệ số C có đơn vị và `C = ε × σ × m × √(2g)`. Không nhập C vào ô m.

Dung tích tăng max là max(V)−V0 trong cửa sổ mô phỏng, không tự động là dung tích phòng lũ quy hoạch. Zmax chỉ được gọi MNLTK/MNLKT khi đã nhập đúng đường lũ, tần suất, điều kiện đầu và tổ hợp vận hành. Không suy tần suất kiểm tra bằng nhân hệ số đường lũ thiết kế.

Ngưỡng mực nước/lưu lượng là tham chiếu do người dùng nhập, chưa xác nhận theo quy chuẩn/tiêu chuẩn của công trình. Khoảng cách đến đỉnh đập chưa xét sóng, nước dềnh, lún hoặc độ vượt cao. Nếu Z đạt đỉnh đập, công cụ chỉ cảnh báo và chưa tính xả qua thân đập/vỡ đập. Không diễn toán ngập hạ lưu hay tự chứng nhận an toàn đập.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

Bộ kiểm thử gồm tích nước dưới ngưỡng (nghiệm thể tích chính xác), dòng cân bằng, tháo hồ qua quan hệ xả tuyến tính (nghiệm truy hồi giải tích), bảo toàn tổng lượng lũ không đều, sai số cân bằng, phạm vi dữ liệu, đọc lại tệp xuất và giao diện. Kết quả kiểm tra đã ghi trong `examples/verification.csv`.

## Nguồn tham khảo bổ sung

Tra cứu ngày 11/10/2026, ưu tiên tài liệu chính thức:

- USACE HEC-HMS — [Reservoir Modeling Concepts and Equations](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations): cân bằng nước, quan hệ dung tích–xả, giả thiết level pool.
- USACE HEC-HMS — [Spillways](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/spillways): công thức thủy lực tràn, hệ số và ảnh hưởng mực nước hạ lưu.
- USACE — [Outflow Curve Option](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/modeling-reservoirs-in-hec-hms/modeling-reservoir-operations-with-hec-hms/outflow-curve-option-for-an-hec-hms-reservoir-element): tổng hợp các nguồn xả trong một quan hệ đơn trị.
- [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app): cấu trúc kho, dependencies và triển khai.

## Cấu trúc mã nguồn

`streamlit_app.py`: giao diện. `routing.py`: bộ tính độc lập. `data_io.py`: đọc tệp và xuất hồ sơ. `sample_data.py`: số liệu mẫu. `tests/`: kiểm thử. `legacy/streamlit_app_original.py`: bản gốc giữ để đối chiếu tại máy, không cần công bố. Tài liệu gốc không bị sửa.

Ứng dụng không ghi tệp người dùng lên đĩa; kết quả giữ trong phiên trình duyệt trên máy chủ. Việc truyền và xử lý tệp vẫn diễn ra trên máy chủ triển khai: cân nhắc quyền công bố dữ liệu công trình trước khi tải lên dịch vụ công khai. Không dùng bộ nhớ cache chung cho dữ liệu tải lên.
