package kr.ktb.silko_be.order;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.order.OrderDtos.OrderResponse;
import kr.ktb.silko_be.order.OrderDtos.OrderStatusRequest;
import kr.ktb.silko_be.store.StoreService;
import org.springframework.data.domain.Page;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Validated
@RestController
@RequestMapping("/api/v1/admin/stores/{storeId}/orders")
public class AdminOrderController {
    private final OrderService service;
    private final OrderSseRegistry sse;
    private final StoreService storeService;

    public AdminOrderController(OrderService service, OrderSseRegistry sse, StoreService storeService) {
        this.service = service;
        this.sse = sse;
        this.storeService = storeService;
    }

    @GetMapping
    public PageResponse<OrderResponse> list(@PathVariable UUID storeId,
                                            @RequestParam(required = false) List<OrderStatus> status,
                                            @RequestParam(defaultValue = "0") @Min(0) int page,
                                            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return PageResponse.from(service.list(storeId, status, page, size));
    }

    @PatchMapping("/{orderId}/status")
    public OrderResponse changeStatus(@PathVariable UUID storeId, @PathVariable UUID orderId,
                                      @Valid @RequestBody OrderStatusRequest body) {
        return service.changeStatus(storeId, orderId, body.status());
    }

    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(@PathVariable UUID storeId) {
        storeService.requireManagedStore(storeId);
        return sse.subscribeStore(storeId);
    }

    public record PageResponse<T>(List<T> content, int page, int size, long totalElements,
                                  int totalPages, boolean first, boolean last) {
        static <T> PageResponse<T> from(Page<T> page) {
            return new PageResponse<>(page.getContent(), page.getNumber(), page.getSize(),
                page.getTotalElements(), page.getTotalPages(), page.isFirst(), page.isLast());
        }
    }
}
