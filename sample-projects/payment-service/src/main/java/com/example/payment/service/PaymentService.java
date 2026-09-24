package com.example.payment.service;

import com.example.payment.client.MetricsFacade;
import com.example.payment.entity.PaymentEntity;
import com.example.payment.repository.PaymentRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

@Service
public class PaymentService {

    private final PaymentRepository paymentRepository;
    private final NotificationService notificationService;
    private final MetricsFacade metricsFacade;

    public PaymentService(
            PaymentRepository paymentRepository,
            NotificationService notificationService,
            MetricsFacade metricsFacade
    ) {
        this.paymentRepository = paymentRepository;
        this.notificationService = notificationService;
        this.metricsFacade = metricsFacade;
    }

    @Transactional
    public PaymentEntity processPayment(BigDecimal amount, String currency) {
        metricsFacade.increment("payment.started");
        PaymentEntity entity = new PaymentEntity();
        entity.setAmount(amount);
        entity.setCurrency(currency);
        entity.setStatus("PENDING");
        PaymentEntity saved = paymentRepository.save(entity);
        notificationService.notifyPaymentCreated(saved);
        metricsFacade.increment("payment.completed");
        return saved;
    }

    /** Called by NotificationService — deliberate circular dependency for fixtures. */
    public void acknowledgeNotification(Long paymentId) {
        metricsFacade.increment("payment.ack");
        paymentRepository.findById(paymentId).ifPresent(payment -> {
            payment.setStatus("NOTIFIED");
            paymentRepository.save(payment);
        });
    }
}
