# Agent 订单链路示例：创建订单 -> 查询订单 -> 断言订单状态

这个示例用于演示 Bug Shoot 的 Agent 链路编排能力：通过一句自然语言目标，自动匹配接口、规划参数依赖，并生成可运行的链路草稿。

## 场景目标

```text
创建订单，查询订单，断言订单状态为 paid
```

期望链路：

1. 调用“创建订单”接口。
2. 从创建订单响应中提取 `order_id`。
3. 将 `order_id` 传给“查询订单”接口。
4. 断言查询订单响应中的订单状态为 `paid`。

## 内置测试接口

Docker 启动后，系统会初始化两个订单 Demo 接口到“示例接口”分组。

### 创建订单

- 方法：`POST`
- 地址：`{{env.base_url}}/api/debug/demo/orders/`
- 请求体：

```json
{
  "sku": "SKU-1001",
  "quantity": 2,
  "customer_name": "Alice",
  "unit_price": 99.9
}
```

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "order_id": "ORD-12345",
    "order_no": "ORD-12345",
    "order_status": "created",
    "payment_status": "unpaid",
    "customer_name": "Alice",
    "sku": "SKU-1001",
    "quantity": 2,
    "amount": 199.8
  }
}
```

关键提取：

```text
order_id <- $.body.data.order_id
```

### 查询订单

- 方法：`GET`
- 地址：`{{env.base_url}}/api/debug/demo/orders/detail/`
- 查询参数：

```text
order_id={{vars.order_id}}
```

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "order_id": "ORD-12345",
    "order_no": "ORD-12345",
    "order_status": "paid",
    "payment_status": "paid",
    "shipping_status": "pending",
    "amount": 199.8,
    "currency": "CNY"
  }
}
```

关键断言：

```text
$.body.data.order_status == paid
```

## 使用 Agent 生成链路

1. 打开 `Agent 编排` 页面。
2. 选择环境：`本地演示环境`。
3. 输入目标：

```text
创建订单，查询订单，断言订单状态为 paid
```

4. 点击 `生成链路草稿`。
5. 检查 Agent 结果：
   - “创建订单”应匹配到 `POST 创建订单`。
   - “查询订单”应匹配到 `GET 查询订单`。
   - 参数依赖应包含 `order_id <- $.body.data.order_id`。
   - 断言规划应包含 `$.body.data.order_status == paid` 或订单状态字段存在性断言。
6. 点击 `保存并打开编辑器`。
7. 在链路编辑器中点击 `Run`。

## 已内置的可运行链路

初始化数据还会创建一条链路：

```text
示例链路：创建订单并校验状态
```

可以直接在 `链路测试` 页面运行它。该链路包含：

- 第 1 步：创建订单
  - 提取 `order_id <- $.body.data.order_id`
  - 断言 `$.body.data.order_status == created`
- 第 2 步：查询订单
  - 使用 `order_id={{vars.order_id}}`
  - 断言 `$.body.data.order_status == paid`

## 这个示例能验证什么

- 接口候选匹配：自然语言步骤能匹配到正确接口。
- 参数依赖规划：上游响应字段能传给下游请求参数。
- 业务断言规划：基于真实响应字段生成订单状态断言。
- 链路执行：保存后的链路可以直接运行并得到成功结果。
