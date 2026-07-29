---
title: "实验 B（进阶）：权限与扩展边界"
weight: 290
math: true
breadcrumbs: false
---

## 目标

在实验 A 基础上补齐协作与演进能力：

- 完成只读角色闭环
- 完成一次扩展安装与可用性验证

## 前置条件

- 已通过实验 A。
- 当前账号具备角色管理与扩展安装权限（或可切换到具备权限的账号）。

## 标准步骤

### Step 1：创建并授权只读角色

```sql
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporter') THEN
    CREATE ROLE reporter LOGIN PASSWORD 'reporter_demo_pwd';
  END IF;
END$$;

GRANT CONNECT ON DATABASE meta TO reporter;
GRANT USAGE ON SCHEMA app TO reporter;
GRANT SELECT ON TABLE app.task TO reporter;
```

### Step 2：验证权限边界

```sql
SET ROLE reporter;
SELECT count(*) FROM app.task;                           -- 预期成功
INSERT INTO app.task(title) VALUES ('should fail');      -- 预期失败
RESET ROLE;
```

### Step 3：检查扩展状态并安装扩展

```sql
SELECT extname, extversion FROM pg_extension ORDER BY 1;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SELECT extname, extversion FROM pg_extension WHERE extname = 'pg_trgm';
SELECT similarity('postgres', 'postgre');
```

## 验收标准（全部满足为通过）

- `reporter` 查询成功且写入失败。
- 权限函数校验结果满足：`CONNECT/USAGE/SELECT=true`，`INSERT=false`。
- 能查到 `pg_trgm`，并成功执行 `similarity()`。
- 全局操作图中新增“权限边界/扩展边界”两层。

## 可提交产出模板

- `角色与授权 SQL`
- `权限验证日志`
- `扩展安装前后对照`
- `扩展函数调用结果`
