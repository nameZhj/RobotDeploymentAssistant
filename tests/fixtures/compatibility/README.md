# Compatibility Test Fixtures

> 本目录为 2026-10-01 前历史功能兼容性与行为契约保护测试专用的测试数据 (Fixtures)。
> 声明：本目录下所有数据仅供自动化测试与 Characterization Tests 断言使用，严禁注入生产 UI 或作为默认生产数据！

## 目录索引
- `license/`: 合法测试证书、过期测试证书与格式错误样本（使用专用测试签名，非生产凭据）
- `map/`: 标准 ASCII 格式 PCD 舞台样本与无效/损毁点云测试文件
- `trajectory/`: 符合 TrajectoryModel 契约的标准 JSON 轨迹基线样本
- `robot_status/`: 模拟心跳遥测与状态报文
