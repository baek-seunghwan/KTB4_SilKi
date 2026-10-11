package kr.ktb.silko_be.order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.order.OrderDtos.OrderResponse;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class OrderControllerTest {
    private final OrderService service = mock(OrderService.class);
    private final OrderController controller = new OrderController(service, mock(OrderSseRegistry.class));

    @Test
    void returnsCompleteCustomerOrder() {
        var orderId = UUID.randomUUID();
        var response = new OrderResponse(orderId, 12, OrderStatus.RECEIVED, null, null, List.of(), 8_000,
            OffsetDateTime.now(), OffsetDateTime.now());
        when(service.get(orderId)).thenReturn(response);

        assertThat(controller.get(orderId)).isSameAs(response);
    }

    @Test
    void propagatesOrderNotFound() {
        var orderId = UUID.randomUUID();
        when(service.get(orderId)).thenThrow(
            new ApiException(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", "주문을 찾을 수 없습니다."));

        assertThatThrownBy(() -> controller.get(orderId))
            .isInstanceOfSatisfying(ApiException.class,
                exception -> assertThat(exception.status()).isEqualTo(HttpStatus.NOT_FOUND));
    }
}
