package kr.ktb.silko_be.order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.checkout.OrderPreviewService;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.DrinkSize;
import kr.ktb.silko_be.menu.DrinkOptions.ExtraShot;
import kr.ktb.silko_be.menu.DrinkOptions.FinalSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.SweetnessAdjustment;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.menu.Menu;
import kr.ktb.silko_be.menu.MenuCategory;
import kr.ktb.silko_be.menu.MenuRepository;
import kr.ktb.silko_be.order.OrderDtos.OrderCreateRequest;
import kr.ktb.silko_be.order.OrderDtos.OrderItemRequest;
import kr.ktb.silko_be.order.OrderDtos.OrderOptionsRequest;
import kr.ktb.silko_be.store.Store;
import kr.ktb.silko_be.store.StoreRepository;
import kr.ktb.silko_be.store.StoreService;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.session.FulfillmentType;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.test.util.ReflectionTestUtils;

class OrderServiceTest {
    private final OrderRepository orderRepository = mock(OrderRepository.class);
    private final MenuRepository menuRepository = mock(MenuRepository.class);
    private final StoreRepository storeRepository = mock(StoreRepository.class);
    private final StoreService storeService = mock(StoreService.class);
    private final OrderSseRegistry sse = mock(OrderSseRegistry.class);
    private final OrderService service = new OrderService(orderRepository, menuRepository, storeRepository,
        storeService, sse, mock(OrderSessionRepository.class), mock(OrderPreviewService.class));
    private final Store store = new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));

    @Test
    void mergesOnlyIdenticalOptionsAndCalculatesServerPrice() {
        var menu = menu(Set.of(Temperature.HOT, Temperature.ICE));
        prepare(menu);

        var largeShot = new OrderOptionsRequest(Temperature.ICE, DrinkSize.LARGE,
            ExtraShot.SHOT_2, SweetnessAdjustment.LESS);
        var defaults = new OrderOptionsRequest(Temperature.HOT, null, null, null);
        var result = service.create(store.getId(), "request-1", new OrderCreateRequest(List.of(
            new OrderItemRequest(menu.getId(), 1, largeShot),
            new OrderItemRequest(menu.getId(), 2, largeShot),
            new OrderItemRequest(menu.getId(), 1, defaults)
        )));

        assertThat(result.items()).hasSize(2);
        assertThat(result.items().getFirst().quantity()).isEqualTo(3);
        assertThat(result.items().getFirst().basePrice()).isEqualTo(4500);
        assertThat(result.items().getFirst().unitPrice()).isEqualTo(6000);
        assertThat(result.items().getFirst().subtotal()).isEqualTo(18_000);
        assertThat(result.items().getFirst().finalSweetness()).isEqualTo(FinalSweetness.LOW);
        assertThat(result.items().getFirst().options()).extracting(OrderDtos.OrderOptionResponse::code)
            .containsExactly("ICE", "LARGE", "SHOT_2", "LESS");
        assertThat(result.items().get(1).unitPrice()).isEqualTo(4500);
        assertThat(result.items().get(1).finalSweetness()).isEqualTo(FinalSweetness.MEDIUM);
        assertThat(result.totalPrice()).isEqualTo(22_500);
        verify(sse).orderCreated(store.getId(), result);
    }

    @Test
    void rejectsUnavailableTemperature() {
        var menu = menu(Set.of(Temperature.HOT));
        prepare(menu);
        var options = new OrderOptionsRequest(Temperature.ICE, null, null, null);

        assertThatThrownBy(() -> service.create(store.getId(), "request-1",
            new OrderCreateRequest(List.of(new OrderItemRequest(menu.getId(), 1, options)))))
            .isInstanceOfSatisfying(ApiException.class,
                exception -> assertThat(exception.code()).isEqualTo("MENU_OPTION_NOT_AVAILABLE"));
    }

    @Test
    void rejectsExtraShotWhenMenuDoesNotAllowIt() {
        var menu = menu(Set.of(Temperature.ICE), false);
        prepare(menu);
        var options = new OrderOptionsRequest(Temperature.ICE, null, ExtraShot.SHOT_1, null);

        assertThatThrownBy(() -> service.create(store.getId(), "request-1",
            new OrderCreateRequest(List.of(new OrderItemRequest(menu.getId(), 1, options)))))
            .isInstanceOfSatisfying(ApiException.class,
                exception -> assertThat(exception.code()).isEqualTo("MENU_OPTION_NOT_AVAILABLE"));
    }

    @Test
    void allowsNoExtraShotWhenMenuDoesNotAllowIt() {
        var menu = menu(Set.of(Temperature.ICE), false);
        prepare(menu);

        var result = service.create(store.getId(), "request-1", new OrderCreateRequest(List.of(
            new OrderItemRequest(menu.getId(), 1, new OrderOptionsRequest(Temperature.ICE, null, null, null))
        )));

        assertThat(result.items().getFirst().options())
            .filteredOn(option -> option.type() == kr.ktb.silko_be.menu.DrinkOptions.OptionType.EXTRA_SHOT)
            .extracting(OrderDtos.OrderOptionResponse::code)
            .containsExactly("NONE");
    }

    @Test
    void limitsQuantityAcrossDifferentOptions() {
        var menu = menu(Set.of(Temperature.HOT, Temperature.ICE));
        when(storeRepository.findByIdForUpdate(store.getId())).thenReturn(Optional.of(store));
        when(orderRepository.findByStoreIdAndIdempotencyKey(store.getId(), "request-1")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.create(store.getId(), "request-1", new OrderCreateRequest(List.of(
            new OrderItemRequest(menu.getId(), 11, new OrderOptionsRequest(Temperature.HOT, null, null, null)),
            new OrderItemRequest(menu.getId(), 10, new OrderOptionsRequest(Temperature.ICE, null, null, null))
        )))).isInstanceOfSatisfying(ApiException.class,
            exception -> assertThat(exception.code()).isEqualTo("INVALID_QUANTITY"));
    }

    @Test
    void returnsStoredOptionsInAdminOrderList() {
        var menu = menu(Set.of(Temperature.ICE));
        var order = new CustomerOrder(store, 1L, "request-1");
        order.addItem(menu.getId(), menu.getName(), menu.getPrice(), 1, FinalSweetness.LOW,
            Temperature.ICE, DrinkSize.LARGE, ExtraShot.SHOT_1, SweetnessAdjustment.LESS);
        when(orderRepository.findAllByStoreIdInWorkflowOrder(any(), any())).thenReturn(new PageImpl<>(List.of(order)));

        var item = service.list(store.getId(), 0, 20).getContent().getFirst().items().getFirst();

        assertThat(item.options()).extracting(OrderDtos.OrderOptionResponse::code)
            .containsExactly("ICE", "LARGE", "SHOT_1", "LESS");
        assertThat(item.finalSweetness()).isEqualTo(FinalSweetness.LOW);
        verify(storeService).requireManagedStore(store.getId());
    }

    @Test
    void returnsCompleteCustomerOrder() {
        var menu = menu(Set.of(Temperature.HOT));
        var order = new CustomerOrder(store, 7L, "request-1");
        order.addItem(menu.getId(), menu.getName(), menu.getPrice(), 2, FinalSweetness.MEDIUM,
            Temperature.HOT, DrinkSize.REGULAR, ExtraShot.NONE, SweetnessAdjustment.NORMAL);
        ReflectionTestUtils.setField(order, "createdAt", OffsetDateTime.parse("2026-08-19T16:00:00+09:00"));
        ReflectionTestUtils.setField(order, "updatedAt", OffsetDateTime.parse("2026-08-19T16:00:01+09:00"));
        when(orderRepository.findById(order.getId())).thenReturn(Optional.of(order));

        var result = service.get(order.getId());

        assertThat(result.orderNumber()).isEqualTo(7L);
        assertThat(result.items()).hasSize(1);
        assertThat(result.items().getFirst().quantity()).isEqualTo(2);
        assertThat(result.totalPrice()).isEqualTo(9_000);
    }

    @Test
    void filtersAdminOrderListByStatus() {
        when(orderRepository.findAllByStoreIdAndStatusInWorkflowOrder(any(), any(), any()))
            .thenReturn(new PageImpl<>(List.of()));

        service.list(store.getId(), List.of(OrderStatus.RECEIVED, OrderStatus.PREPARING), 0, 20);

        verify(orderRepository).findAllByStoreIdAndStatusInWorkflowOrder(
            store.getId(), List.of("RECEIVED", "PREPARING"), PageRequest.of(0, 20));
    }

    private Menu menu(Set<Temperature> temperatures) {
        return menu(temperatures, true);
    }

    private Menu menu(Set<Temperature> temperatures, boolean extraShotAvailable) {
        return new Menu(store, MenuCategory.COFFEE, "아메리카노", null, 4500, null,
            temperatures, DefaultSweetness.MEDIUM, true, extraShotAvailable);
    }

    private void prepare(Menu menu) {
        when(storeRepository.findByIdForUpdate(store.getId())).thenReturn(Optional.of(store));
        when(orderRepository.findByStoreIdAndIdempotencyKey(store.getId(), "request-1")).thenReturn(Optional.empty());
        when(menuRepository.findAllByStoreIdAndIdIn(any(), any())).thenReturn(List.of(menu));
        when(orderRepository.nextOrderNumber()).thenReturn(1L);
        when(orderRepository.saveAndFlush(any())).thenAnswer(invocation -> {
            var order = invocation.getArgument(0, CustomerOrder.class);
            ReflectionTestUtils.setField(order, "createdAt", OffsetDateTime.parse("2026-08-19T16:00:00+09:00"));
            ReflectionTestUtils.setField(order, "updatedAt", OffsetDateTime.parse("2026-08-19T16:00:01+09:00"));
            return order;
        });
    }
}
