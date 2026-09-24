package com.example.payment;

import com.example.payment.entity.PaymentEntity;
import com.example.payment.repository.PaymentRepository;
import com.example.payment.service.PaymentService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class PaymentServiceTest {

    @Autowired
    private PaymentService paymentService;

    @Autowired
    private PaymentRepository paymentRepository;

    @Test
    void processPaymentPersistsRow() {
        PaymentEntity saved = paymentService.processPayment(new BigDecimal("10.00"), "USD");
        assertNotNull(saved.getId());
        PaymentEntity loaded = paymentRepository.findById(saved.getId()).orElseThrow();
        assertEquals("USD", loaded.getCurrency());
    }
}
