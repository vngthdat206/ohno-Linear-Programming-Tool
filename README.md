# NhomConTraiMeoMeo_K24_KDL

Bộ mã đã được tách thành nhiều file nhỏ để dễ kiểm tra, sửa chữa, bảo trì và mở rộng. Phần mềm được xây dựng bằng **Python + Tkinter**, giải **bài toán Quy hoạch tuyến tính** bằng **thuật toán Đơn hình**, đồng thời hỗ trợ **trực quan hóa bài toán 2 biến** và **xuất lời giải ra file .txt**.

---

## I. Giới thiệu

### 1. Thành viên nhóm

| Họ và tên | MSSV | Lớp |
|---|---:|---|
| Nguyễn Đăng Nhân | 24280038 | 24KDL1 |
| Trần Nguyên Hưng | 24280048 | 24KDL1 |
| Trương Đình Hưng | 24280068 | 24KDL1 |
| Lê Tự Phong | 24280039 | 24KDL1 |
| Vương Thành Đạt | 24280058 | 24KDL1 |

### 2. Mục đích phần mềm

Phần mềm được tạo ra để hỗ trợ người học:
- nhập một bài toán quy hoạch tuyến tính theo cách trực quan;
- giải bài toán bằng thuật toán đơn hình;
- theo dõi từng bước biến đổi của bảng đơn hình;
- xuất nội dung lời giải ra file văn bản;
- trực quan hóa hình học cho các bài toán có đúng 2 biến.

### 3. Các chức năng chính của chương trình

Phần mềm hiện có các chức năng nổi bật sau:
- nhập số biến, số ràng buộc và các hệ số tương ứng;
- lựa chọn bài toán **Max** hoặc **Min**;
- hỗ trợ ràng buộc dạng **≤, ≥, =**;
- hỗ trợ dấu của biến:
  - **x ≥ 0**
  - **x ≤ 0**
  - **biến tự do**
- giải bài toán bằng **thuật toán đơn hình**;
- xử lý các tình huống đặc biệt như:
  - bài toán **không có nghiệm tối ưu**;
  - bài toán **không giới nội**;
  - bài toán **có xoay vòng**;
  - bài toán **có vô số nghiệm tối ưu**;
- cho phép dùng dữ liệu **phân số** hoặc **số thập phân**;
- xuất lời giải ra **file .txt**;
- trực quan hóa bài toán 2 biến trên mặt phẳng Oxy.

### 4. Giải thuật được sử dụng

Chương trình sử dụng:
- **Thuật toán Đơn hình** làm thuật toán chính;
- **Phương pháp 2 pha** khi bài toán cần xử lý tình huống khởi tạo cơ sở không thuận lợi;
- cơ chế lựa chọn phần tử xoay theo:
  - **Dantzig**;
  - **Bland** để giảm nguy cơ lặp xoay vòng.

---

## II. Đánh giá

### 1. Các trường hợp chương trình giải được

Phần mềm được thiết kế để xử lý nhiều tình huống khác nhau của bài toán quy hoạch tuyến tính:

- **Bài toán Max / Min**  
  Người dùng có thể chọn bài toán cực đại hoặc cực tiểu.

- **Số biến từ 1 đến 5**  
  Phần mềm hỗ trợ nhập tối đa 5 biến.

- **Số ràng buộc từ 1 đến 10**  
  Có thể nhập nhiều ràng buộc để mô tả bài toán thực tế.

- **Ràng buộc đa dạng**
  - dạng **≤**
  - dạng **≥**
  - dạng **=**

- **Biến có nhiều kiểu dấu**
  - không âm
  - không dương
  - tự do

- **Dữ liệu phân số hoặc thập phân**  
  Có thể nhập cả số nguyên, phân số và số thập phân.

- **Bài toán cần 2 pha**  
  Khi cần, chương trình tự xử lý bằng pha 1 và pha 2.

- **Bài toán không có nghiệm tối ưu**  
  Nếu hệ ràng buộc vô nghiệm, phần mềm có thể nhận diện.

- **Bài toán không giới nội**  
  Nếu hàm mục tiêu có thể tăng/giảm mãi, phần mềm có thể phát hiện.

- **Bài toán có xoay vòng**  
  Chương trình có cơ chế chống lặp bằng Bland để tăng độ an toàn.

- **Bài toán có vô số nghiệm tối ưu**  
  Phần mềm có thể nhận diện trường hợp có nhiều phương án tối ưu.

### 2. Những chức năng phần mềm mang lại cho người dùng

- giao diện nhập liệu rõ ràng, chia khối hợp lý;
- nút điền ví dụ giúp kiểm thử nhanh;
- nút chạy giải thuật cho ra lời giải từng bước;
- lời giải hiển thị trong khung riêng;
- nút xuất file giúp lưu kết quả ra `.txt` để nộp bài, đối chiếu hoặc in ấn;
- chức năng trực quan hóa giúp người học hiểu hình học của bài toán 2 biến:
  - miền chấp nhận được;
  - các ràng buộc;
  - các đường đồng mức của hàm mục tiêu;
  - điểm tối ưu trên miền nghiệm.

### 3. Đánh giá tổng quan

Ưu điểm của phần mềm:
- bám sát nội dung học thuật của môn Quy hoạch tuyến tính;
- có khả năng trình bày từng bước giải;
- giao diện thân thiện, có phân khu rõ ràng;
- hỗ trợ nhiều dạng bài thường gặp trong thực hành;
- có phần trực quan hóa giúp tăng khả năng hiểu bản chất.

Hạn chế:
- phần trực quan hóa chỉ áp dụng cho bài toán đúng **2 biến**;
- với bài toán quá nhiều ràng buộc, hình vẽ có thể dày hơn;
- đây là phần mềm phục vụ học tập nên không thay thế các bộ giải tối ưu chuyên nghiệp quy mô lớn.

---

## III. Chi tiết sử dụng

### 1. Cài đặt và chạy chương trình

Sau khi giải nén bộ mã, mở thư mục dự án và chạy:

```bash
python main.py
```

Yêu cầu:
- Python 3.x;
- có thư viện chuẩn `tkinter`;
- môi trường có thể hiển thị cửa sổ đồ họa.

---

### 2. Nhập bài toán

#### 2.1 Chọn kiểu dữ liệu
Trong khung **Thiết lập**, chọn:
- **Phân số** nếu muốn nhập dạng `1/2`, `3/4`, `-5/2`...
- **Số thập phân** nếu muốn nhập dạng `0.5`, `-1.25`...

#### 2.2 Chọn số biến và số ràng buộc
- **Số biến**: từ 1 đến 5
- **Số ràng buộc**: từ 1 đến 10

Sau khi thay đổi số lượng, bấm:
- **Tạo lại bảng nhập**

#### 2.3 Nhập hàm mục tiêu
Trong khung **Hàm mục tiêu**:
- chọn **max** hoặc **min**;
- nhập hệ số tương ứng cho từng biến `x1, x2, ...`

Ví dụ:
- `max Z = 3x1 + 2x2`
- `min Z = 5x1 - 7x2`

#### 2.4 Nhập dấu của biến
Ở phần dấu biến:
- chọn `≥0` nếu biến không âm;
- chọn `≤0` nếu biến không dương;
- chọn `tự do` nếu biến không bị ràng buộc dấu.

#### 2.5 Nhập ràng buộc
Trong khung **Ràng buộc**:
- nhập hệ số từng biến trên mỗi dòng;
- chọn dấu ràng buộc:
  - `≤`
  - `≥`
  - `=`
- nhập vế phải của ràng buộc.

Ví dụ:
- `2x1 + x2 ≤ 10`
- `x1 - x2 ≥ 3`
- `x1 + x2 = 5`

---

### 3. Dùng nút điền ví dụ

Trong khung **Thiết lập**, tại mục **Mẫu**, người dùng có thể chọn một trong các ví dụ có sẵn:

- **Ví dụ giải bằng 2 pha**
- **Ví dụ giải bài toán xoay vòng**
- **Ví dụ giải bài toán vô số nghiệm**

Sau đó bấm:
- **Điền ví dụ**

Chương trình sẽ tự điền dữ liệu tương ứng vào bảng nhập.

---

### 4. Chạy giải thuật

Bấm:
- **Chạy giải thuật (Ctrl+Alt+R)**

Kết quả sẽ xuất hiện trong khung **Lời giải**, bao gồm:
- bài toán gốc;
- quá trình chuẩn hóa;
- các bước đơn hình;
- các phép chọn biến vào/ra;
- kết luận cuối cùng.

Nếu bài toán thuộc loại đặc biệt, chương trình cũng sẽ thông báo tương ứng:
- không có nghiệm tối ưu;
- không giới nội;
- xoay vòng;
- nhiều nghiệm tối ưu.

---

### 5. Xuất file .txt

Nút **Xuất file .txt** chỉ hoạt động khi đã có lời giải.

#### Trường hợp chưa giải bài toán
- nút ở trạng thái khóa;
- màu xám;
- không xuất được file.

#### Trường hợp đã giải xong
- nút chuyển sang trạng thái cho phép bấm;
- màu xanh lá;
- bấm vào sẽ mở hộp thoại lưu file.

Khi lưu:
- đặt tên file bất kỳ;
- mặc định phần mở rộng là `.txt`;
- nội dung file chính là phần lời giải đang hiển thị trên màn hình.

---

### 6. Trực quan hóa bài toán 2 biến

Nút:
- **Trực quan hóa BT 2 biến**

chỉ dùng cho bài toán có đúng **2 biến**.

#### Điều kiện để dùng
- bài toán phải có chính xác 2 biến;
- đã nhập đầy đủ hệ số hàm mục tiêu và ràng buộc.

#### Kết quả trực quan hóa
Cửa sổ trực quan sẽ hiển thị:
- các trục tọa độ Oxy;
- các đường ràng buộc;
- miền chấp nhận được;
- các đường đồng mức của hàm mục tiêu;
- các đỉnh của miền nghiệm;
- điểm tối ưu.

#### Tương tác trên cửa sổ trực quan
Người dùng có thể:
- kéo thả để di chuyển vùng nhìn;
- dùng chuột để phóng to/thu nhỏ;
- sử dụng các nút điều khiển trực quan đi kèm.

#### Lưu ý
- nếu số biến khác 2, chức năng này sẽ không thực hiện;
- hình trực quan được thiết kế để phục vụ học tập và quan sát miền nghiệm.

---

### 7. Những lưu ý khi sử dụng

- nên nhập số hợp lệ, tránh để trống ô quan trọng;
- với dữ liệu phân số, nên nhập đúng định dạng `a/b`;
- khi thay đổi số biến hoặc số ràng buộc, nên bấm **Tạo lại bảng nhập** để cập nhật giao diện;
- sau khi giải xong mới dùng được chức năng xuất file;
- để xem hình học, chỉ dùng cho bài toán 2 biến.

---

## IV. Tài liệu tham khảo

- **Giáo trình Quy Hoạch Tuyến Tính** của **Phan Quốc Khánh – Trần Tuệ Nương**
- **AI hỗ trợ viết code**

---

## Cấu trúc dự án

- `main.py`: điểm chạy chương trình
- `simplex_app.py`: giao diện Tkinter và phần trực quan hóa
- `simplex_engine.py`: thuật toán đơn hình
- `models.py`: các dataclass dùng chung
- `utils.py`: các hàm tiện ích xử lý số và định dạng
- `__init__.py`: đánh dấu thư mục gói Python

---

## Cách chạy 

### Bước 1: Clone dự án

```bash
git clone https://github.com/vngthdat206/LinearProgrammingTool_byVC
cd LinearProgrammingTool_byVC
```

### Bước 2: Tạo môi trường ảo

```bash
py -m venv .venv
```

### Bước 3: Kích hoạt môi trường ảo

```bash
.venv\Scripts\activate
```

### Bước 4: Cài đặt thư viện

```bash
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

### Bước 5: Chạy chương trình

```bash
py main.py
```
