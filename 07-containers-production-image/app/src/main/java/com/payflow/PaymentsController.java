package com.payflow;

import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentsController {
    record PaymentRequest(String fromAccount, String toAccount, BigDecimal amount) {}

    @PostMapping("/payments")
    public Map<String, String> create(@RequestBody PaymentRequest request) {
        return Map.of("paymentId", UUID.randomUUID().toString(), "status", "ACCEPTED");
    }
}
