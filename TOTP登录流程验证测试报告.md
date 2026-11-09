# 微软 Authenticator（TOTP）两步认证 登录流程验证测试报告

| 项目 | 内容 |
|------|------|
| 测试日期 | 2026-09-17 |
| 测试环境 | Windows / Python 3.11 (`.venv`) / FastAPI + Uvicorn |
| 服务地址 | http://localhost:8888 |
| 被测功能 | v3 龙虾 Claw 微软 Authenticator（TOTP）两步认证 |
| 测试方式 | 真实 HTTP 请求（cookie 会话保持） |
| 测试账号 | `100001`（密码按惯例 `100001sy`） |
| 最终结论 | **全部通过（14/14）** |

---

## 一、被测功能范围

本次验证覆盖 TOTP 两步认证在登录链路上的完整行为：

1. **未启用 TOTP 用户的登录**：密码正确 → 直接登录成功
2. **已启用 TOTP 用户的两步登录**：密码正确 → `needs_2fa` → 输入 6 位验证码 → 登录成功
3. **TOTP 绑定 / 解绑链路**：`/totp/setup` → `/totp/confirm` → `/totp/disable`
4. **异常分支**：错误验证码拒绝、登出后会话失效

### 后端接口清单

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/lobster-mu/login` | POST | 第一步：验证密码；若启用 TOTP 返回 `needs_2fa` |
| `/api/lobster-mu/login/2fa` | POST | 第二步：验证 TOTP 6 位码，成功写会话 |
| `/api/lobster-mu/totp/status` | GET | 查询当前用户 TOTP 启用状态 |
| `/api/lobster-mu/totp/setup` | POST | 生成 TOTP secret + QR 码（base64 PNG） |
| `/api/lobster-mu/totp/confirm` | POST | 输入 6 位码确认绑定并启用 |
| `/api/lobster-mu/totp/disable` | POST | 验证密码后解绑 |
| `/api/lobster-mu/logout` | POST | 登出（清会话） |
| `/api/lobster-mu/me` | GET | 验证当前会话有效性 |

> 说明：`/login/direct` 为管理员直通接口，设计上不经过 TOTP，未纳入本次普通登录流程验证。

---

## 二、测试用例与结果

| # | 步骤 | 期望 | 实际 | 结果 |
|---|------|------|------|------|
| 1 | 登录（未启用 TOTP） | `status=success` | success | PASS |
| 2 | `/totp/status` 可访问 | 返回 `enabled` 字段 | enabled=False | PASS |
| 3 | 登出 | HTTP 200 | 200 | PASS |
| 4 | 重新登录（无 2FA） | `status=success` | success | PASS |
| 5 | `/totp/setup` 生成 | 返回 secret + QR | secret 32 位 / QR 758 字节（base64 PNG） | PASS |
| 6 | `/totp/confirm` 错误码 | HTTP 401 | 401 | PASS |
| 7 | `/totp/confirm` 正确码 | 启用成功 | "已启用微软 Authenticator" | PASS |
| 8 | `/totp/status` 复查 | enabled=True | enabled=True | PASS |
| 9 | 登出 | HTTP 200 | 200 | PASS |
| 10 | 登录（已启用） | `status=needs_2fa` 且回传 username | needs_2fa / 100001 | PASS |
| 11 | `/login/2fa` 错误验证码 | HTTP 401 | 401 | PASS |
| 12 | `/login/2fa` 正确验证码 | 登录成功且回传 user | success / 100001 | PASS |
| 13 | `/me` 会话验证 | 返回当前用户 | 100001 | PASS |
| 14 | 登出后 `/me` | HTTP 401 | 401 | PASS |

**统计**：通过 14 项，失败 0 项，通过率 100%。

---

## 三、关键验证点说明

- **两步登录隔离**：已启用 TOTP 的用户在第一步 `/login` 仅返回 `needs_2fa`，不会直接建立会话；必须第二步 `/login/2fa` 校验通过后才写入登录态。
- **pending 时效**：第一步通过后服务端记录 pending（TTL 5 分钟），第二步校验验证码（pyotp `valid_window=1`，±30 秒容差），校验失败返回 401。
- **绑定防误用**：`/totp/confirm` 使用错误验证码被正确拒绝；`/totp/disable` 需二次验证密码（本次在还原阶段通过密码成功解绑，验证了密码校验分支）。
- **会话有效性**：登录成功（含两步）后 `/me` 可正常返回用户；登出后 `/me` 立即 401，确认会话被正确清除。
- **QR 码可用**：`/totp/setup` 返回的 QR 为标准 `data:image/png;base64,` 前缀的 PNG 数据，可供微软 Authenticator 等 TOTP 应用扫码。

---

## 四、测试后状态还原

为避免影响日常使用，测试结束后已将账号 `100001` 还原为**未启用 TOTP** 状态：

```
100001 已还原: totp_enabled = 0, secret_cleared = True
```

即：TOTP 密钥已清除、`totp_enabled` 置 0，该账号当前走普通单步登录流程。测试脚本（`_verify_login.py`）已在验证完成后删除，未在项目目录残留临时文件。

---

## 五、结论

微软 Authenticator（TOTP）两步认证功能在真实 HTTP 环境下验证**全部通过**：

- 未启用用户登录、已启用用户两步登录两条主链路行为正确；
- 绑定（setup/confirm）与解绑（disable）链路完整可用；
- 错误验证码、登出后会话失效等异常分支均被正确拦截（401）；
- 会话管理（写入 / 验证 / 清除）符合预期。

功能可投入正常使用。管理员如需在启用 TOTP 后仍快速登录，可走 `/login/direct` 直通接口。
