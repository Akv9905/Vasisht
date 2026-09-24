package com.example.payment.controller;

import com.example.payment.client.MetricsFacade;
import com.example.payment.service.PaymentService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Second caller of {@link PaymentService} for multi-caller fixtures.
 */
@RestController
@RequestMapping("/api/refund")
public class RefundController {

    private final PaymentService paymentService;
    private final MetricsFacade metricsFacade;

    public RefundController(PaymentService paymentService, MetricsFacade metricsFacade) {
        this.paymentService = paymentService;
        this.metricsFacade = metricsFacade;
    }

    @PostMapping("/{paymentId}")
    public ResponseEntity<Void> refund(@PathVariable Long paymentId) {
        metricsFacade.increment("refund.requested");
        paymentService.acknowledgeNotification(paymentId);
        return ResponseEntity.accepted().build();
    }
}
