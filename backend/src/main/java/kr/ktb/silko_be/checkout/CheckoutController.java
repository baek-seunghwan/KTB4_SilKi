package kr.ktb.silko_be.checkout;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import kr.ktb.silko_be.order.OrderDtos.OrderResponse;
import kr.ktb.silko_be.order.OrderService;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Validated
@RequestMapping("/api/v1/order-sessions/{sessionId}/orders")
public class CheckoutController {
    private final OrderService service;

    public CheckoutController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderResponse checkout(
        @PathVariable UUID sessionId,
        @RequestHeader("If-Match") @Min(0) long expectedCartVersion,
        @RequestHeader("Idempotency-Key") @NotBlank @Size(max = 100) String idempotencyKey
    ) {
        return service.checkout(sessionId, expectedCartVersion, idempotencyKey);
    }
}
