# PCD 格式支持矩阵与编码规范 (PCD Support Matrix)

> 审计依据: Prompt 05 | 对应模块: `src/core/pcd_loader.py`, `src/domain/map/stage_map_asset.py`

## 1. PCD 编码格式支持情况

| 编码模式 | 支持状态 | 边界处理与错误策略 | 测试用例证据 |
| :--- | :--- | :--- | :--- |
| **DATA ascii** | ✅ 完全支持 | 逐行流式解析，跳过空行与注释，容忍空格/制表符分隔，校验非有限浮点数 | `test_pcd_loader_ascii_and_binary_parsers` |
| **DATA binary** | ✅ 完全支持 | 使用 `struct.unpack_from` 按 `FIELDS/SIZE/TYPE` 紧凑二进制解包，严格检查包长度 | `test_pcd_loader_ascii_and_binary_parsers` |
| **DATA binary_compressed** | ⚠️ 明确拒绝 | 识别头部并抛出 `UnsupportedPcdFormatError`，友好提示用户先转换为标准 ASCII/Binary | `test_pcd_rejection_of_invalid_and_compressed` |
| **未知/破损编码** | ❌ 明确拒绝 | 抛出 `InvalidPcdFileError` 或 `UnsupportedPcdFormatError`，绝不静默创建假点云 | `test_pcd_rejection_of_invalid_and_compressed` |

---

## 2. 字段与头部合规约束

- **必需字段**: `FIELDS` 必须包含 `x`, `y`, `z` 空间三维坐标。缺失三维坐标时直接拦截并抛出 `InvalidPcdFileError`。
- **数据大小**: 单点占用字节数 (`SIZE`)、类型 (`TYPE: F/I/U`) 与计数 (`COUNT`) 严格对应。
- **点数一致性**: 声明点数 `POINTS` 必须大于 0；0 字节文件或空文件直接拦截。
- **物理范围边界**: 自动计算 `[min_x, max_x]`, `[min_y, max_y]`, `[min_z, max_z]` 并保留三位小数精度。
