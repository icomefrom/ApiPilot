# Agent Order Chain Demo: Create Order -> Query Order -> Assert Status

This demo shows how Bug Shoot can draft an executable API workflow from an English natural-language goal.

## Goal

```text
Create order, query order, status should be paid
```

Expected workflow:

1. Call the `Create order` API.
2. Extract `order_id` from the create-order response.
3. Pass `order_id` into the `Query order` API.
4. Assert that the queried order status is `paid`.

## Built-In Demo APIs

After Docker startup, Bug Shoot initializes two order demo APIs under the `Sample APIs` group.

### Create Order

- Method: `POST`
- URL: `{{env.base_url}}/api/debug/demo/orders/`
- Body:

```json
{
  "sku": "SKU-1001",
  "quantity": 2,
  "customer_name": "Alice",
  "unit_price": 99.9
}
```

Example response:

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

Key extraction:

```text
order_id <- $.body.data.order_id
```

### Query Order

- Method: `GET`
- URL: `{{env.base_url}}/api/debug/demo/orders/detail/`
- Query params:

```text
order_id={{vars.order_id}}
```

Example response:

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

Key assertion:

```text
$.body.data.order_status == paid
```

## Generate the Chain with Agent Planner

1. Open `Agent Planner`.
2. Select the `Local demo environment`.
3. Enter this goal:

```text
Create order, query order, status should be paid
```

4. Click `Generate chain draft`.
5. Check the Agent result:
   - `Create order` should match `POST Create order`.
   - `Query order` should match `GET Query order`.
   - Parameter planning should include `order_id <- $.body.data.order_id`.
   - Assertion planning should include `$.body.data.order_status == paid`.
6. Click `Save and open editor`.
7. Run the generated chain in the chain editor.

## Built-In Runnable Chain

The seed data also creates this ready-to-run chain:

```text
Sample chain: create order and verify status
```

You can run it directly from `Chain Test`. It contains:

- Step 1: `Create order`
  - Extract `order_id <- $.body.data.order_id`
  - Assert `$.body.data.order_status == created`
- Step 2: `Query order and assert status`
  - Use `order_id={{vars.order_id}}`
  - Assert `$.body.data.order_status == paid`

## What This Demo Validates

- English intent planning
- API candidate matching with English API names
- Runtime parameter extraction and downstream parameter injection
- Business assertion planning for order status
- End-to-end chain execution
