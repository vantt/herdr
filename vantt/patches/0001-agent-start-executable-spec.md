# Patch: `agent start --executable`

- Commit gốc: `490325d1 feat: add --executable flag to agent start for custom launchers` (2026-09-18). Upstream base lúc đó: `preview-2026-09-16-2c29fb29e302`.
- Consumer: forgentX (fgOS), đường `herdr-spawn` của dispatch engine (`src/runner/dispatch/herdr-round.mjs`, `herdr-agent.mjs`, `transport.mjs`).
- Trạng thái upstream: chưa gửi PR.
- Trạng thái phía consumer (2026-09-29): **chưa nối dây**. forgentX chưa truyền `--executable`, hiện vẫn dùng workaround ở mục 3.

## 1. Yêu cầu (thứ phải còn đúng sau mọi lần merge hay viết lại)

fgOS cần herdr khởi chạy **đúng lệnh mà Confinement Authority đã chuẩn bị** trong một pane, ví dụ `bwrap [flags] -- claude ...` hoặc một launcher tuỳ biến. Đồng thời process đó vẫn phải được herdr theo dõi như một agent **thuộc kind đã khai báo**: có tên trong `agent list`, dùng được `agent get/wait/prompt/read`, và readiness/state detection vẫn chạy.

Bất biến:

1. **Chọn binary.** `agent start <name> --kind <kind> --pane <id> --executable <path> -- <args>` phải chạy `<path> <args...>` thay cho executable canonical của kind (`crate::detect::interactive_agent_executable(kind)`).
2. **Mặc định không đổi.** Không có `--executable` thì hành vi phải giữ nguyên như upstream.
3. **Kind vẫn là kind.** `--executable` chỉ thay argv[0]. Nó không đổi kind, không đổi integration/hook, và không đổi cách herdr nhận diện trạng thái agent. Đây là toàn bộ giá trị của patch: có confinement mà vẫn giữ được tracking.
4. **Đi qua cả hai cửa.** Cờ phải có ở CLI (`src/cli/agent.rs`) **và** trong wire API (`AgentStartParams.executable`, `src/api/schema/agents.rs`, dạng optional, `skip_serializing_if = None`). Nếu thiếu ở wire API thì gateway/API client không dùng được.
5. **Argument đứng trước `--`.** `--executable` được parse trước separator `--`. Mọi thứ sau `--` vẫn là argv truyền cho executable.
6. **Validate giống `--pane`.** Thiếu giá trị thì in `missing value for --executable` và exit 2.
7. **Vẫn qua shell wrapper của platform.** argv mới vẫn phải đi qua `crate::platform::interactive_shell_command(&argv, &shell_name)` như argv gốc. Không được spawn thẳng mà bỏ qua lớp này.

## 2. Vì sao cần: `agent start --kind` không nhận lệnh thay thế

Đã kiểm chứng live trong forgentX (runtime-recovery track, tháng 9/2026): `agent start --kind` chỉ khởi chạy executable canonical của kind đó. Các args sau `--` được **nối thêm vào sau binary của kind**, không dùng để thay binary. Vì vậy không thể bọc agent trong `bwrap` hay một launcher khác mà vẫn giữ agent tracking.

Nguồn trong forgentX:

- `plans/260911-2305-runtime-recovery/phase-designs/launch-reconciliation.md`, mục "This exact syntax does not work".
- `docs/platform/agent-coordination/verification/runtime-recovery/p02h.md` (lần thử đầu, bị bác bỏ) và `p02h-reopen.md` (cơ chế đang ship).

## 3. Workaround đang ship ở forgentX (sẽ được thay khi nối dây patch)

1. Ghi lệnh đã chuẩn bị `{command, args, env}` ra một launcher script trong thư mục protected của Run.
2. `herdr pane run <paneId> bash <scriptPath>`. `pane run` chỉ là sugar của `pane.send_text`, nên phải gõ một lệnh ngắn để shell không tokenize sai.
3. `herdr pane report-agent` / `report-agent-session` để đăng ký process vào `agent list/get`.
4. Kiểm tra độc lập sau khi launch: `/proc/<pid>/exe`, argv, `/proc/<pid>/environ`, `/proc/<pid>/cwd`, và đọc lại launcher script so khớp từng byte. Lệch bất kỳ thứ gì thì kill process, đóng pane, fail-closed.

Workaround này tốn 8 vòng sửa. Nó còn một residual đã biết: env ngoài danh sách vector bị tiêm vào trong một cửa sổ race khoảng 10–90 ms. Patch `--executable` cho phép herdr tự launch đúng argv, bỏ bước gõ vào shell và bước `report-agent`. Các kiểm tra `/proc` phía fgOS vẫn nên giữ.

## 4. Cần kiểm chứng khi nối dây (chưa chạy, NOT RUN)

- Readiness gate của herdr đối chiếu identity của foreground process với kind. Khi argv[0] là `bwrap` hay một launcher, liệu gate còn nhận ra kind (vd. `claude`) không? Theo `p02h-reopen.md`, `agent prompt` chỉ thành công khi argv[0] thật sự khớp với kind đã khai báo. Nếu gate từ chối thì patch phải mở rộng thêm, hoặc detection phải dựa vào process con.
- State detection bằng hook/integration vẫn chạy khi agent nằm bên trong bwrap (hook script có thấy được socket/env của herdr không?).

## 5. Khi merge upstream có conflict, hoặc phải viết lại

- Upstream có thể đã đổi tên hoặc cấu trúc `AgentStartParams`, `App::start_agent` (`src/app/agents.rs`, chỗ dựng `argv`) hay parser CLI `agent_start`. Đừng cố áp diff cũ. Hãy tìm lại **ba điểm chạm** rồi viết lại theo mục 1: (a) field optional trong wire schema, (b) chỗ dựng argv[0] ở app layer, (c) parse cờ ở CLI.
- Nếu upstream đã có cơ chế tương đương (vd. `--command`, `--exec`, hoặc một field trong `agent start`), **bỏ patch này** và báo cho consumer đổi sang cờ của upstream. Chỉ giữ patch nếu cơ chế của upstream không thoả bất biến 3.
- Test tối thiểu sau khi rebase:
  - `herdr agent start --help` (hoặc parse) nhận `--executable`.
  - Chạy một kind thật với `--executable` trỏ tới một wrapper (vd. script `exec "$@"` hoặc `bwrap ... -- <kind-binary>`), rồi xác nhận `agent get` báo đúng kind và `agent wait/prompt` hoạt động.
  - Không có cờ thì hành vi y như upstream.
- Nên bổ sung unit test Rust cho parse CLI và cho chỗ dựng argv. Patch gốc chưa có test.
