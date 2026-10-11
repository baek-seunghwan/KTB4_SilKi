package kr.ktb.silko_be.store;

import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/stores/{storeId}")
public class PublicStoreController {
    private final StoreService service;

    public PublicStoreController(StoreService service) {
        this.service = service;
    }

    @GetMapping("/order-context")
    public OrderContextResponse orderContext(@PathVariable UUID storeId) {
        return OrderContextResponse.from(service.requireStore(storeId));
    }

    public record OrderContextResponse(
        UUID storeId,
        String storeName,
        OperatingStatus operatingStatus,
        boolean orderAvailable,
        String message
    ) {
        static OrderContextResponse from(Store store) {
            boolean orderAvailable = store.getOperatingStatus() == OperatingStatus.OPEN;
            String message = orderAvailable ? "현재 주문 가능합니다." : "현재 영업이 종료되었습니다.";
            return new OrderContextResponse(
                store.getId(),
                store.getName(),
                store.getOperatingStatus(),
                orderAvailable,
                message
            );
        }
    }

    @GetMapping("/status")
    public StoreController.StoreStatusResponse status(@PathVariable UUID storeId) {
        return new StoreController.StoreStatusResponse(service.requireStore(storeId).getOperatingStatus());
    }
}
