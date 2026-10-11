package kr.ktb.silko_be.session;

import java.time.OffsetDateTime;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/stores/{storeId}/order-sessions")
public class OrderSessionController {
    private final OrderSessionService service;

    public OrderSessionController(OrderSessionService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderSessionResponse create(@PathVariable UUID storeId) {
        return OrderSessionResponse.from(service.create(storeId));
    }

    public record OrderSessionResponse(
        UUID sessionId,
        UUID storeId,
        OrderSessionStatus status,
        long cartVersion,
        FulfillmentType fulfillmentType,
        OffsetDateTime expiresAt
    ) {
        static OrderSessionResponse from(OrderSession session) {
            return new OrderSessionResponse(
                session.getId(),
                session.getStoreId(),
                session.getStatus(),
                session.getCartVersion(),
                session.getFulfillmentType(),
                session.getExpiresAt()
            );
        }
    }
}
