# pg36_shop logical model v0: business facts

This file is an input to chapter 3, not a substitute for stakeholder review.

## Ownership

| Fact | Authoritative owner | Consumers |
|---|---|---|
| Current customer profile | pg36_shop | checkout, support |
| Current product catalog record | pg36_shop for this teaching scope | checkout, search |
| Accepted order and line snapshots | pg36_shop | payment, fulfillment, support |
| Payment attempt and provider reference | pg36_shop payment boundary | order, support, reconciliation |

## Commands

- Register or update a customer profile.
- Create or update a current product record.
- Place an order once for a customer-scoped request key.
- Record immutable purchase-time line snapshots.
- Record a payment attempt once for a provider-scoped idempotency key.

## Invariants closed in v0

- Every canonical relation has a primary key.
- Customer reference, email, SKU, order number, and scoped external payment
  references are unique.
- Orders reference an existing customer.
- Order lines reference an existing order and product.
- Payments reference an existing order.
- Line number and quantity are positive; monetary inputs are nonnegative or
  positive according to their current meaning.

## Invariants deliberately left open for chapter 4 or later

- Exact money representation, scale, currency, and rounding.
- Allowed order/payment states and transition rules.
- Business-time zone, precision, and clock-source policy.
- Identifier type, generation location, and public exposure.
- “Paid” means captured amount equals accepted order total.
- An order can enter an accepted state only after at least one line exists.
- Reuse of an idempotency key with a different fingerprint is a conflict.
