package com.example.payment.client;

import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * High fan-out helper referenced by multiple services/controllers.
 */
@Component
public class MetricsFacade {

    private final Map<String, AtomicLong> counters = new ConcurrentHashMap<>();

    public void increment(String name) {
        counters.computeIfAbsent(name, key -> new AtomicLong()).incrementAndGet();
    }

    public long get(String name) {
        AtomicLong value = counters.get(name);
        return value == null ? 0L : value.get();
    }
}
