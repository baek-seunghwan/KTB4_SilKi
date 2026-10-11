package kr.ktb.silko_be.order;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import kr.ktb.silko_be.order.OrderDtos.OrderCreateRequest;
import kr.ktb.silko_be.order.OrderDtos.OrderResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Validated
@RestController
@RequestMapping("/api/v1")
public class OrderController {
    private final OrderService service;
    private final OrderSseRegistry sse;

    public OrderController(OrderService service, OrderSseRegistry sse) {
        this.service = service;
        this.sse = sse;
    }

    @PostMapping("/stores/{storeId}/orders")
    @ResponseStatus(HttpStatus.CREATED)
    public OrderResponse create(@PathVariable UUID storeId,
                                @RequestHeader("Idempotency-Key") @NotBlank @Size(max = 100) String idempotencyKey,
                                @Valid @RequestBody OrderCreateRequest body) {
        return service.create(storeId, idempotencyKey, body);
    }

    @GetMapping("/orders/{orderId}")
    public OrderResponse get(@PathVariable UUID orderId) {
        return service.get(orderId);
    }

    @GetMapping(value = "/orders/{orderId}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(@PathVariable UUID orderId) {
        service.requireOrderExists(orderId);
        return sse.subscribeOrder(orderId);
    }
}
