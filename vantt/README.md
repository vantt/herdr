# herdr Fork Upstream Catchup

Cơ chế tự động hoá việc đồng bộ fork `vantt/herdr` lên các bản release mới của upstream `herdrdev/herdr`, tự động áp lại toàn bộ patch feature theo thứ tự, biên dịch và chạy kiểm thử.

---

## 1. Sử dụng nhanh (Quick Start)

### Chạy catchup lên release mới nhất của upstream
Chỉ cần chạy 1 lệnh:
```bash
python3 vantt/scripts/catchup.py
```
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

---

## 2. Quản lý Patch Series

Mọi patch tính năng của fork được khai báo tường minh tại `vantt/patches/series.toml`:

```toml
[[patches]]
id = "agent-start-executable"
name = "feat: add --executable flag to agent start for custom launchers"
patch_file = "0001-agent-start-executable.patch"
metadata_file = "agent-start-executable.md"
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
3. Tạo file tài liệu bất biến `vantt/patches/<tên-patch>.md` (ghi rõ mục đích, consumer, các bất biến không được vi phạm khi conflict).
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
