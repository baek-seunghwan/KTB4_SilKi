package kr.ktb.silko_be.order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.checkout.OrderPreviewService;
import kr.ktb.silko_be.checkout.OrderPreviewService.OrderPreview;
import kr.ktb.silko_be.checkout.OrderPreviewService.PreviewItem;
import kr.ktb.silko_be.checkout.OrderPreviewService.PreviewOption;
import kr.ktb.silko_be.checkout.OrderPreviewService.ValidatedOrder;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.session.FulfillmentType;
import kr.ktb.silko_be.session.OrderSession;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.session.OrderSessionStatus;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreRepository;
import kr.ktb.silko_be.store.StoreService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.test.util.ReflectionTestUtils;

class OrderServiceCheckoutTest {
    private final OrderRepository orderRepository = mock(OrderRepository.class);
    private final OrderSessionRepository sessionRepository = mock(OrderSessionRepository.class);
    private final OrderPreviewService previewService = mock(OrderPreviewService.class);
    private final OrderSseRegistry sse = mock(OrderSseRegistry.class);
    private final OrderService service = new OrderService(
        orderRepository,
        mock(MenuRepository.class),
        mock(StoreRepository.class),
        mock(StoreService.class),
        sse,
        sessionRepository,
        previewService
    );
    private final Store store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
    private final OrderSession session = new OrderSession(store, OffsetDateTime.now().plusMinutes(30));

    @BeforeEach
    void setUp() {
        session.selectFulfillment(FulfillmentType.TAKEOUT);
        when(sessionRepository.findByIdForUpdate(session.getId())).thenReturn(Optional.of(session));
        when(orderRepository.findByOrderSessionId(session.getId())).thenReturn(Optional.empty());
        when(orderRepository.findByStoreIdAndIdempotencyKey(store.getId(), "checkout-1"))
            .thenReturn(Optional.empty());
        when(orderRepository.nextOrderNumber()).thenReturn(101L);
        when(orderRepository.saveAndFlush(any())).thenAnswer(invocation -> {
            var order = invocation.getArgument(0, CustomerOrder.class);
            ReflectionTestUtils.setField(order, "createdAt", OffsetDateTime.parse("2026-08-20T00:10:00+09:00"));
            ReflectionTestUtils.setField(order, "updatedAt", OffsetDateTime.parse("2026-08-20T00:10:00+09:00"));
            return order;
        });
    }

    @Test
    void createsCounterPaymentOrderFromValidatedCartAndCompletesSession() {
        var size = new PreviewOption(
            java.util.UUID.randomUUID(), java.util.UUID.randomUUID(), "SIZE", "사이즈",
            "LARGE", "라지", 500
        );
        var item = new PreviewItem(
            java.util.UUID.randomUUID(), java.util.UUID.randomUUID(), "카페 라떼", 2,
            4500, List.of(size), 5000, 10_000
        );
        var preview = new OrderPreview(
            session.getId(), store.getId(), 1, FulfillmentType.TAKEOUT,
            List.of(item), 2, 10_000, OffsetDateTime.now()
        );
        when(previewService.validate(session, 1)).thenReturn(new ValidatedOrder(session, store, preview));

        var response = service.checkout(session.getId(), 1, "checkout-1");

        assertThat(response.orderNumber()).isEqualTo(101L);
        assertThat(response.status()).isEqualTo(OrderStatus.RECEIVED);
        assertThat(response.fulfillmentType()).isEqualTo(FulfillmentType.TAKEOUT);
        assertThat(response.paymentMethod()).isEqualTo(PaymentMethod.PAY_AT_COUNTER);
        assertThat(response.totalPrice()).isEqualTo(10_000);
        assertThat(response.items().getFirst().options().getFirst().code()).isEqualTo("LARGE");
        assertThat(session.getStatus()).isEqualTo(OrderSessionStatus.ORDERED);

        var orderCaptor = ArgumentCaptor.forClass(CustomerOrder.class);
        verify(orderRepository).saveAndFlush(orderCaptor.capture());
        assertThat(orderCaptor.getValue().getOrderSessionId()).isEqualTo(session.getId());
        verify(sessionRepository).flush();
        verify(sse).orderCreated(store.getId(), response);
    }

    @Test
    void returnsExistingOrderForSameSessionAndIdempotencyKey() {
        var existing = new CustomerOrder(
            store, 101, "checkout-1", session.getId(), FulfillmentType.TAKEOUT,
            PaymentMethod.PAY_AT_COUNTER
        );
        when(orderRepository.findByOrderSessionId(session.getId())).thenReturn(Optional.of(existing));

        var response = service.checkout(session.getId(), 1, "checkout-1");

        assertThat(response.id()).isEqualTo(existing.getId());
        verify(previewService, never()).validate(any(), any(Long.class));
        verify(orderRepository, never()).saveAndFlush(any());
    }

    @Test
    void rejectsDifferentIdempotencyKeyForOrderedSession() {
        var existing = new CustomerOrder(
            store, 101, "checkout-1", session.getId(), FulfillmentType.TAKEOUT,
            PaymentMethod.PAY_AT_COUNTER
        );
        when(orderRepository.findByOrderSessionId(session.getId())).thenReturn(Optional.of(existing));

        assertThatThrownBy(() -> service.checkout(session.getId(), 1, "checkout-2"))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.CONFLICT);
                assertThat(exception.code()).isEqualTo("ORDER_SESSION_ALREADY_ORDERED");
            });
    }
}
