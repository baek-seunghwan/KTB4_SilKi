package kr.ktb.silko_be.session;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Validated
@RequestMapping("/api/v1/order-sessions/{sessionId}/fulfillment")
public class FulfillmentController {
    private final OrderSessionService service;

    public FulfillmentController(OrderSessionService service) {
        this.service = service;
    }

    @PatchMapping
    public FulfillmentResponse select(@PathVariable UUID sessionId,
                                      @RequestHeader("If-Match") @Min(0) long expectedCartVersion,
                                      @Valid @RequestBody FulfillmentRequest body) {
        return FulfillmentResponse.from(
            service.selectFulfillment(sessionId, expectedCartVersion, body.fulfillmentType())
        );
    }

    public record FulfillmentRequest(@NotNull FulfillmentType fulfillmentType) {}

    public record FulfillmentResponse(UUID sessionId, FulfillmentType fulfillmentType, long cartVersion) {
        static FulfillmentResponse from(OrderSession session) {
            return new FulfillmentResponse(
                session.getId(), session.getFulfillmentType(), session.getCartVersion()
            );
        }
    }
}
