# herdr Fork Upstream Catchup

Cơ chế tự động hoá việc đồng bộ fork `vantt/herdr` lên các bản release mới của upstream `herdrdev/herdr`, tự động áp lại toàn bộ patch feature theo thứ tự, biên dịch và chạy kiểm thử.

---

## 1. Sử dụng nhanh (Quick Start)

### Chạy catchup lên release mới nhất của upstream
Chỉ cần chạy 1 lệnh:
```bash
python3 vantt/scripts/catchup.py
```

Hoặc gửi prompt cho AI Agent (có tích hợp skill `herdr-catchup`):
> *"Hãy chạy catchup lên release mới nhất của upstream herdr và kiểm tra lại toàn bộ patch series."*

Lệnh trên sẽ:
1. Tự động fetch `upstream` và tìm tag stable mới nhất (dạng `v*`, vd: `v0.9.1`).
2. Tạo nhánh release riêng `vantt/<tag>` (vd: `vantt/v0.9.1`).
3. Kiểm tra và áp từng patch trong `vantt/patches/series.toml`.
4. Biên dịch binary với định danh fork (`herdr --version` -> `0.9.1-vantt.1`).
5. Chạy unit tests và kiểm tra cờ `--executable` trong `herdr agent start --help`.

### Chạy thử trên một git ref bất kỳ (preview hoặc master)
```bash
python3 vantt/scripts/catchup.py --ref upstream/master
# hoặc
python3 vantt/scripts/catchup.py --ref preview-2026-09-28-80c0c07250d2
```

### Cài đặt binary vào máy
Catchup **không** tự cài đặt để đảm bảo an toàn. Khi muốn cài:
```bash
# Kiểm tra trước (dry run)
python3 vantt/scripts/install.py --dry-run

# Cài đặt thật (sẽ tự động backup binary cũ tại ~/.local/bin/herdr.bak-*)
python3 vantt/scripts/install.py
```

> **Lưu ý**: Sau khi cài, các session và gateway đang chạy vẫn dùng binary cũ trong bộ nhớ. Hãy khởi động lại gateway khi sẵn sàng:
> ```bash
> fgos gateway stop && fgos gateway start
> ```

### Rollback lại binary cũ
```bash
python3 vantt/scripts/install.py --rollback
```

### Cài đặt siêu nhanh bằng 1 lệnh (Khuyên dùng)
Nếu muốn tải và cài đặt ngay bản binary đã được GitHub CI build sẵn:
```bash
curl -fsSL https://raw.githubusercontent.com/vantt/herdr/master/vantt/install.sh | bash
```
Lệnh trên sẽ tự động:
1. Tải bản release mới nhất từ GitHub Releases của `vantt/herdr`.
2. Tạo bản sao lưu an toàn cho binary cũ tại `~/.local/bin/herdr.bak-<timestamp>`.
3. Cài binary mới vào `~/.local/bin/herdr`.
4. Kiểm tra phiên bản và cờ `--executable`.

---

## 2. Hướng dẫn Build & Cài đặt bản Tag hiện tại (Current Tag)

### Cách A: Cài đặt từ GitHub Release (Không tốn CPU máy)
Chạy script cài đặt trực tiếp qua `curl`:
```bash
# Cài đặt bản mới nhất:
curl -fsSL https://raw.githubusercontent.com/vantt/herdr/master/vantt/install.sh | bash

# Hoặc cài đặt một bản cụ thể (ví dụ: v0.9.1-vantt.1):
curl -fsSL https://raw.githubusercontent.com/vantt/herdr/master/vantt/install.sh | sh -s -- --version v0.9.1-vantt.1

# Rollback về bản cũ:
curl -fsSL https://raw.githubusercontent.com/vantt/herdr/master/vantt/install.sh | sh -s -- --rollback
```

---

### Cách B: Build và Cài đặt trực tiếp trên máy Local

#### 1. Build binary release cho tag hiện tại (vd: `v0.9.1`)
```bash
# Chạy catchup chỉ định rõ tag cần build:
python3 vantt/scripts/catchup.py --ref v0.9.1
```
*(Nếu nhánh `vantt/v0.9.1` đã được build và verify trước đó, lệnh sẽ nhận diện ngay trong 1s mà không build lại)*.

#### 2. Cài đặt vào `~/.local/bin/herdr`
```bash
python3 vantt/scripts/install.py
```
Lệnh trên sẽ:
- Kiểm tra xem binary trong `target/release/herdr` có hỗ trợ `--executable` không.
- Tạo bản sao lưu an toàn tại `~/.local/bin/herdr.bak-<timestamp>`.
- Copy binary mới vào vị trí.

#### 3. Kiểm tra tính năng sau khi cài
```bash
# Kiểm tra phiên bản (kèm nhận dạng fork vantt)
herdr --version
# Kết quả mong đợi: herdr 0.9.1-vantt.1

# Kiểm tra cờ --executable
herdr agent start --help | grep -C 1 -- '--executable'
```

---

### Cách C: Cơ chế GitHub Action tự động Catchup & Release

Repo đã được tích hợp workflow `[.github/workflows/fork-catchup-release.yml](.github/workflows/fork-catchup-release.yml)`:
- **Tự động thăm dò (Polling)**: Chạy định kỳ mỗi 6 giờ (`cron: '0 0,6,12,18 * * *'`).
- **Tự động áp patch & build**: Khi upstream có release tag mới, GitHub Actions tự động rẽ nhánh, áp patch series, build release binary và kiểm thử.
- **Tự động xuất bản (Publish)**: Nếu test pass, Action tự động tạo GitHub Release (kèm file `herdr-linux-x86_64.tar.gz`).
- **Cảnh báo conflict**: Nếu có conflict ở patch nào, Action tự động mở một GitHub Issue thông báo chi tiết để can thiệp.
- **Kích hoạt bằng tay**: Anh có thể vào tab **Actions** -> **Fork Catchup and Release** -> Bấm **Run workflow** bất cứ khi nào muốn.

---

## 3. Quản lý Patch Series

Mọi patch tính năng của fork được khai báo tường minh tại `vantt/patches/series.toml`:

```toml
[[patches]]
id = "agent-start-executable"
name = "feat: add --executable flag to agent start for custom launchers"
patch_file = "0001-agent-start-executable.patch"
metadata_file = "0001-agent-start-executable-spec.md"
consumer = "forgentX dispatch"
upstream_status = "unsubmitted"  # unsubmitted | pr_opened | merged
upstream_pr = ""
test_command = "cargo test --bin herdr agent_start_missing_executable_value_fails"
```

### Thêm một patch mới vào series
1. Viết code và commit tính năng.
2. Xuất patch file ra thư mục `vantt/patches/`:
   ```bash
   git format-patch -1 <commit-hash> -o vantt/patches/
   ```
3. Tạo file tài liệu đặc tả & bất biến `vantt/patches/<số>-<tên-patch>.spec.md` (ghi rõ mục đích, consumer, các bất biến không được vi phạm khi conflict).
4. Thêm một block `[[patches]]` vào cuối `vantt/patches/series.toml`.
5. Xong! Lần catchup tiếp theo sẽ tự động áp patch này theo thứ tự.

---

## 3. Xử lý khi có Conflict

Khi upstream có thay đổi lớn chạm vào dòng code của patch:
1. `catchup.py` sẽ **dừng lại ngay tại patch bị lỗi**, giữ nguyên working tree để kiểm tra.
2. Script in ra thông tin chi tiết:
   - Patch ID nào bị lỗi.
   - Các file bị conflict.
   - Đường dẫn tới file metadata bất biến (`.md`) để tham khảo cách viết lại code.
3. Người dùng hoặc agent mở file giải quyết conflict theo các bất biến đã đặc tả.
4. Sau khi giải quyết xong:
   ```bash
   git add <các-file-đã-sửa>
   python3 vantt/scripts/catchup.py --continue
   ```
   Script sẽ tiếp tục áp các patch còn lại, build và test.

Nếu muốn huỷ bỏ phiên catchup đang dở:
```bash
python3 vantt/scripts/catchup.py --abort
```

---

## 4. Kiểm tra tính năng phía consumer (`forgentX` / `fgos doctor`)

Khi forgentX cần kiểm tra xem binary `herdr` đang cài có hỗ trợ `--executable` không, có 2 cách:
1. **Kiểm tra cờ CLI (Khuyên dùng)**:
   ```bash
   herdr agent start --help | grep -q -- '--executable'
   ```
2. **Kiểm tra chuỗi phiên bản**:
   ```bash
   herdr --version | grep -E '\-vantt\.'
   ```
