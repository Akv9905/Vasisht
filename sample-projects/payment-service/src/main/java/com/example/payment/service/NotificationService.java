package com.example.payment.service;

import com.example.payment.client.MetricsFacade;
import com.example.payment.entity.PaymentEntity;
import org.springframework.stereotype.Service;

/**
 * Deliberately depends on {@link PaymentService} to create a circular dependency
 * used by later impact/risk analysis fixtures.
 */
@Service
public class NotificationService {

    private final PaymentService paymentService;
    private final MetricsFacade metricsFacade;

    public NotificationService(PaymentService paymentService, MetricsFacade metricsFacade) {
        this.paymentService = paymentService;
        this.metricsFacade = metricsFacade;
    }

    public void notifyPaymentCreated(PaymentEntity payment) {
        metricsFacade.increment("notification.sent");
        // Circular call back into PaymentService
        paymentService.acknowledgeNotification(payment.getId());
    }
}
