# Payment Service (sample)

Sample Java / Spring Boot project used as the primary Enterprise AI test fixture.

## Flow

`POST /api/payment` → `PaymentController` → `PaymentService` → `PaymentRepository` → `payments` table

## Notes

- Includes multiple callers of `PaymentService`
- Includes a deliberate circular dependency between `PaymentService` and `NotificationService`
- Includes a high fan-out helper (`MetricsFacade`) used by several components
