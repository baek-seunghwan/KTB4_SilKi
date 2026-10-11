package kr.ktb.silko_be.checkout;

import jakarta.validation.constraints.Min;
import java.util.UUID;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Validated
@RequestMapping("/api/v1/order-sessions/{sessionId}/preview")
public class OrderPreviewController {
    private final OrderPreviewService service;

    public OrderPreviewController(OrderPreviewService service) {
        this.service = service;
    }

    @PostMapping
    public OrderPreviewService.OrderPreview preview(
        @PathVariable UUID sessionId,
        @RequestHeader("If-Match") @Min(0) long expectedCartVersion
    ) {
        return service.preview(sessionId, expectedCartVersion);
    }
}
